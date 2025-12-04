"""
문자열 유사도 검증 모듈 (BM25S + Levenshtein Distance)
"""
from typing import List, Dict, Any, Tuple, Optional
from rapidfuzz import fuzz
from .bm25_index import get_bm25_system
from .text_preprocessor import get_preprocessor
import logging


logger = logging.getLogger(__name__)


class SimilaritySearch:
    """문자열 유사도 기반 문서 검색"""

    def __init__(
        self,
        similarity_threshold_high: float = 90.0,  # 조기 종료 임계값 (95% → 90%로 변경)
        similarity_threshold_low: float = 70.0,   # 유사 문서 최소 임계값
        top_k_blocking: int = 50,  # BM25S 1차 필터링 개수
        top_k_final: int = 10  # 최종 반환 개수
    ):
        self.threshold_high = similarity_threshold_high
        self.threshold_low = similarity_threshold_low
        self.top_k_blocking = top_k_blocking
        self.top_k_final = top_k_final

        # BM25S 시스템
        self.bm25_system = get_bm25_system()
        # 전처리기
        self.preprocessor = get_preprocessor()

    def search_similar_documents(
        self,
        title: str,
        dept_filter: Optional[str] = None,
        early_stop: bool = True
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """유사 문서 검색 (BM25S + Levenshtein Distance)

        Args:
            title: 검색할 문서 제목
            dept_filter: 부서 필터 (옵션)
            early_stop: 조기 종료 활성화 여부

        Returns:
            (유사 문서 리스트, 조기 종료 여부)

        파이프라인:
            1. 제목 정규화 (Cleaned Title)
            2. BM25S로 1차 필터링 (Blocking) - Top K개 후보군
            3. Levenshtein Distance로 2차 정밀 검증
            4. 유사도 >= threshold_high이면 조기 종료
            5. 유사도 >= threshold_low인 문서들 반환
        """
        # 1. 제목 정규화
        cleaned_title = self.preprocessor.clean_title(title)
        logger.info(f"검색 쿼리: '{cleaned_title}'")

        # 2. BM25S 1차 필터링 (Blocking)
        candidates = self.bm25_system.search(
            query=cleaned_title,
            top_k=self.top_k_blocking,
            dept_filter=dept_filter
        )

        logger.info(f"BM25S 후보군: {len(candidates)}건")

        if not candidates:
            return [], False

        # 3. Levenshtein Distance 2차 정밀 검증
        results = []
        early_stopped = False

        for candidate in candidates:
            candidate_title = candidate['cleaned_title']

            # 문자열 유사도 계산 (Levenshtein Distance 기반)
            similarity = fuzz.ratio(cleaned_title, candidate_title)

            # 유사도 추가
            candidate['similarity'] = similarity
            candidate['query_title'] = cleaned_title

            # 조기 종료 체크
            if early_stop and similarity >= self.threshold_high:
                logger.info(
                    f"조기 종료: 유사도 {similarity:.2f}% "
                    f"(임계값: {self.threshold_high}%) - '{candidate_title}'"
                )
                # 조기 종료: 해당 문서만 반환
                return [candidate], True

            # 유사도 임계값 체크
            if similarity >= self.threshold_low:
                results.append(candidate)

        # 4. 유사도 순 정렬
        results.sort(key=lambda x: x['similarity'], reverse=True)

        # 5. 상위 K개 반환
        final_results = results[:self.top_k_final]

        logger.info(
            f"유사 문서 {len(final_results)}건 반환 "
            f"(임계값: {self.threshold_low}% 이상)"
        )

        return final_results, early_stopped

    def get_best_match(self, title: str, dept_filter: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """가장 유사한 문서 1건 반환

        Args:
            title: 검색할 문서 제목
            dept_filter: 부서 필터 (옵션)

        Returns:
            가장 유사한 문서 (없으면 None)
        """
        results, early_stopped = self.search_similar_documents(
            title=title,
            dept_filter=dept_filter,
            early_stop=True
        )

        if results:
            return results[0]
        return None


# 싱글톤 인스턴스
_similarity_search = None


def get_similarity_search() -> SimilaritySearch:
    """유사도 검색 싱글톤 인스턴스 반환"""
    global _similarity_search
    if _similarity_search is None:
        _similarity_search = SimilaritySearch()
    return _similarity_search
