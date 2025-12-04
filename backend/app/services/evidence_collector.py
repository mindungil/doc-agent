"""
증거 수집 모듈 (Evidence Accumulation)
문서 배부 이력 + 사무분장 규정을 종합하여 LLM 추론을 위한 증거를 수집
"""
from typing import List, Dict, Any, Optional, Tuple
import logging
from .similarity_search import get_similarity_search
from .rag import rag_service
from .text_preprocessor import get_preprocessor
from app.config import settings


logger = logging.getLogger(__name__)


class EvidenceCollector:
    """증거 수집기 (Snowball Pipeline)"""

    def __init__(self, top_k_history: int = 10, top_k_job: int = 5):
        """
        Args:
            top_k_history: 문서 배부 이력 상위 K개
            top_k_job: 사무분장 상위 K개
        """
        self.top_k_history = top_k_history
        self.top_k_job = top_k_job

        # 서비스 초기화
        self.similarity_search = get_similarity_search()
        self.qdrant_client = rag_service.qdrant_client
        self.preprocessor = get_preprocessor()

    def collect_history_evidence(
        self,
        title: str,
        dept_filter: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """문서 배부 이력 증거 수집

        Args:
            title: 문서 제목
            dept_filter: 부서 필터 (수신자 필터링 결과)

        Returns:
            (유사 문서 리스트, 조기 종료 여부)

        수집 데이터:
            - 유사 문서 제목
            - 처리 부서
            - 기안자 (보고자)
            - 기안 일자
            - 유사도 점수
        """
        logger.info(f"문서 배부 이력 증거 수집: '{title}'")

        # 유사 문서 검색
        results, early_stopped = self.similarity_search.search_similar_documents(
            title=title,
            dept_filter=dept_filter,
            early_stop=True
        )

        # 증거 포맷팅
        evidence = []
        for result in results[:self.top_k_history]:
            evidence.append({
                'title': result['title'],
                'cleaned_title': result['cleaned_title'],
                'dept': result['dept'],
                'reporter': result['reporter'],
                'date': str(result['date']),
                'similarity': result['similarity'],
                'doc_no': result['doc_no']
            })

        logger.info(f"문서 배부 이력 증거 {len(evidence)}건 수집")

        return evidence, early_stopped

    def collect_job_description_evidence(self, title: str) -> List[Dict[str, Any]]:
        """사무분장 규정 증거 수집

        Args:
            title: 문서 제목

        Returns:
            사무분장 매칭 리스트

        수집 데이터:
            - 담당 부서
            - 업무 정의 텍스트
            - 관련 직급/담당자
            - 유사도 점수
        """
        logger.info(f"사무분장 규정 증거 수집: '{title}'")

        # 제목 정규화
        cleaned_title = self.preprocessor.clean_title(title)

        # Qdrant Vector Search
        try:
            # 임베딩 생성
            query_embedding = rag_service.create_query_embedding(cleaned_title)

            # Qdrant 검색
            results = self.qdrant_client.search(
                collection_name=settings.qdrant_collection,
                query_vector=query_embedding,
                limit=self.top_k_job
            )

            evidence = []
            for result in results:
                payload = result.payload
                evidence.append({
                    'dept': payload.get('부서', ''),
                    'job_description': payload.get('업무내용', ''),
                    'rank': payload.get('직급', ''),
                    'manager': payload.get('담당자', ''),
                    'score': result.score
                })

            logger.info(f"사무분장 규정 증거 {len(evidence)}건 수집")

            return evidence

        except Exception as e:
            logger.error(f"사무분장 검색 실패: {e}")
            return []

    def collect_all_evidence(
        self,
        title: str,
        dept_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """모든 증거 수집 (통합)

        Args:
            title: 문서 제목
            dept_filter: 부서 필터 (옵션)

        Returns:
            통합 증거 딕셔너리
        """
        # 1. 문서 배부 이력 증거
        history_evidence, early_stopped = self.collect_history_evidence(
            title=title,
            dept_filter=dept_filter
        )

        # 2. 조기 종료 체크
        if early_stopped and history_evidence:
            # 유사도가 매우 높은 과거 문서 발견 -> 즉시 자동 배정
            best_match = history_evidence[0]
            logger.info(
                f"조기 종료: 유사도 {best_match['similarity']:.2f}% "
                f"-> 부서: {best_match['dept']}"
            )

            # 상세한 자동 배정 사유 생성
            past_doc_title = best_match['title']
            reporter = best_match.get('reporter', '알 수 없음')
            dept = best_match['dept']
            similarity = best_match['similarity']

            reason = (
                f"과거 유사 문서(유사도 {similarity:.2f}%)가 발견되어 자동 배정되었습니다.\n\n"
                f"**과거 문서**: {past_doc_title}\n"
                f"**보고자**: {reporter}\n"
                f"**배부 부서**: {dept}\n\n"
                f"동일하거나 유사한 주제의 문서는 행정 관례상 동일한 부서로 배부됩니다. "
                f"이 문서는 과거 배부 이력을 기반으로 신뢰도 높게 자동 배정되었습니다."
            )

            return {
                'early_stopped': True,
                'auto_assigned_dept': best_match['dept'],
                'reason': reason,
                'matched_document': best_match,
                'history_evidence': history_evidence,
                'job_evidence': []
            }

        # 3. 사무분장 규정 증거
        job_evidence = self.collect_job_description_evidence(title)

        return {
            'early_stopped': False,
            'auto_assigned_dept': None,
            'history_evidence': history_evidence,
            'job_evidence': job_evidence
        }


# 싱글톤 인스턴스
_evidence_collector = None


def get_evidence_collector() -> EvidenceCollector:
    """증거 수집기 싱글톤 인스턴스 반환"""
    global _evidence_collector
    if _evidence_collector is None:
        _evidence_collector = EvidenceCollector()
    return _evidence_collector


# Tuple import 추가
from typing import Tuple
