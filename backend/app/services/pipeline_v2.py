"""
문서 배부 자동화 Pipeline V2
pipeline_v2.md 사양에 따른 구현
"""
from typing import Dict, Any, Optional, List
import logging
import json
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.db import DocumentModel
from app.models.schemas import EmployeeCandidate, AssignmentRecommendation
from .text_preprocessor import get_preprocessor
from .recipient_filter import recipient_filter_service
from .department_recommender import get_department_recommender
from .feedback_service import get_feedback_service
from .bm25_index import get_bm25_system
from .rag import rag_service
from .llm import get_llm_service
from datetime import datetime


logger = logging.getLogger(__name__)


class DocumentProcessingPipelineV2:
    """문서 처리 파이프라인 V2"""

    def __init__(self):
        self.preprocessor = get_preprocessor()
        self.recipient_filter = recipient_filter_service
        self.department_recommender = get_department_recommender()
        self.feedback_service = get_feedback_service()
        self.bm25_system = get_bm25_system()
        self.llm_service = get_llm_service()

    async def process_document(
        self,
        db: AsyncSession,
        document: DocumentModel,
        ocr_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """문서 처리 메인 파이프라인

        Args:
            db: 데이터베이스 세션
            document: 문서 모델
            ocr_text: OCR 텍스트 (옵션)

        Returns:
            처리 결과 딕셔너리

        파이프라인:
            1. 전처리 및 정규화 (Cleaned Title)
            2. 수신자 필터링 (OCR + LLM)
            3. 휴먼 피드백 조회
            4. 증거 수집 + LLM 추론
            5. 결과 저장
        """
        logger.info(f"=== 문서 처리 시작: {document.title} ===")

        # 1. 전처리 및 정규화
        cleaned_title = self.preprocessor.clean_title(document.title)
        logger.info(f"정규화 제목: {cleaned_title}")

        # 2. 수신자 필터링 (OCR 필요 시)
        recipient_info = None
        if ocr_text:
            try:
                # 수신자 정보 추출
                recipient_result = await self.recipient_filter.extract_recipient_info(ocr_text)

                # RecipientInfo를 dict로 변환
                if recipient_result:
                    recipient_info = {
                        'has_recipient': recipient_result.has_recipient,
                        'is_specific': recipient_result.is_specific,
                        'recipient_text': recipient_result.recipient_text,
                        'is_explicit': recipient_result.is_specific,
                        'dept_name': None  # TODO: 부서명 추출 로직 필요 시 추가
                    }
                    logger.info(f"수신자 정보: {recipient_info}")

                    # 문서에 저장
                    document.recipient_info = json.dumps(recipient_info, ensure_ascii=False)
                    await db.commit()

            except Exception as e:
                logger.error(f"수신자 필터링 실패: {e}")
                recipient_info = None

        # 3. 휴먼 피드백 조회
        feedback_data = await self.feedback_service.get_feedback_for_inference(
            db=db,
            keyword=cleaned_title,
            reporter=None,  # 보고자 정보가 있다면 추가
            limit=5
        )

        if feedback_data:
            logger.info(f"휴먼 피드백 {len(feedback_data)}건 발견")

        # 4. 부서 추천 (증거 수집 + LLM 추론)
        recommendation = self.department_recommender.recommend_department(
            title=cleaned_title,
            recipient_info=recipient_info,
            feedback_data=feedback_data
        )

        logger.info(
            f"추천 결과: {recommendation['recommended_dept']} "
            f"(신뢰도: {recommendation['confidence']}, "
            f"자동배정: {recommendation['auto_assigned']})"
        )

        # 5. 결과 저장
        document.recommendation_json = json.dumps(recommendation, ensure_ascii=False)
        document.is_auto_assigned = recommendation['auto_assigned']

        if recommendation['auto_assigned']:
            document.assigned_to = recommendation['recommended_dept']
            document.assigned_at = datetime.utcnow()
            document.status = "자동배정"
        else:
            document.status = "검토필요"

        await db.commit()
        await db.refresh(document)

        logger.info(f"=== 문서 처리 완료: {document.id} ===")

        return {
            'document_id': document.id,
            'cleaned_title': cleaned_title,
            'recipient_info': recipient_info,
            'recommendation': recommendation,
            'feedback_count': len(feedback_data)
        }

    async def handle_human_correction(
        self,
        db: AsyncSession,
        document_id: int,
        corrected_dept: str,
        reason: Optional[str] = None
    ):
        """휴먼 피드백 처리 (부서 수정)

        Args:
            db: 데이터베이스 세션
            document_id: 문서 ID
            corrected_dept: 수정된 부서
            reason: 수정 사유
        """
        # 문서 조회
        from sqlalchemy import select
        result = await db.execute(
            select(DocumentModel).where(DocumentModel.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError(f"문서를 찾을 수 없습니다: {document_id}")

        # LLM 예측 부서 추출
        recommendation = json.loads(document.recommendation_json or '{}')
        llm_predicted_dept = recommendation.get('recommended_dept', '')

        # 피드백이 필요한지 확인 (LLM 예측과 다른 경우에만)
        if llm_predicted_dept and llm_predicted_dept != corrected_dept:
            # 피드백 저장
            cleaned_title = self.preprocessor.clean_title(document.title)

            await self.feedback_service.add_feedback(
                db=db,
                keyword=cleaned_title,
                reporter=None,  # 보고자 정보 추가 가능
                llm_predicted_dept=llm_predicted_dept,
                human_corrected_dept=corrected_dept,
                reason=reason,
                document_id=document_id,
                document_title=document.title
            )

            logger.info(
                f"휴먼 피드백 저장: {llm_predicted_dept} -> {corrected_dept}"
            )

        # 문서 상태 업데이트
        document.assigned_to = corrected_dept
        document.assigned_at = datetime.utcnow()
        document.status = "확정"
        await db.commit()

        logger.info(f"부서 수정 완료: {document_id} -> {corrected_dept}")

    async def batch_distribute(
        self,
        db: AsyncSession,
        auto_confirm: bool = False
    ) -> Dict[str, Any]:
        """일괄 배부 처리

        Args:
            db: 데이터베이스 세션
            auto_confirm: 자동 확정 여부 (시간 기반)

        Returns:
            배부 통계
        """
        from sqlalchemy import select

        # 대기 중인 문서 조회
        query = select(DocumentModel).where(
            DocumentModel.status.in_(["자동배정", "검토필요"])
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        stats = {
            'total': len(documents),
            'auto_assigned': 0,
            'needs_review': 0,
            'confirmed': 0
        }

        for doc in documents:
            if doc.is_auto_assigned:
                stats['auto_assigned'] += 1
                if auto_confirm:
                    doc.status = "확정"
                    stats['confirmed'] += 1
            else:
                stats['needs_review'] += 1

        await db.commit()

        logger.info(f"일괄 배부 완료: {stats}")

        return stats

    async def recommend_assignee_with_pipeline(
        self,
        document_title: str,
        document_content: str,
        db: Optional[AsyncSession] = None
    ) -> AssignmentRecommendation:
        """Pipeline V2 기반 담당자 추천 (부서 추천 + RAG + LLM)

        Args:
            document_title: 문서 제목
            document_content: 문서 내용
            db: 데이터베이스 세션 (피드백 조회용, 옵션)

        Returns:
            AssignmentRecommendation 객체
        """
        logger.info(f"=== Pipeline V2 담당자 추천 시작: {document_title} ===")

        # 1. 제목 정규화
        cleaned_title = self.preprocessor.clean_title(document_title)

        # 2. 휴먼 피드백 조회 (DB 있을 경우)
        feedback_data = []
        if db:
            feedback_data = await self.feedback_service.get_feedback_for_inference(
                db=db,
                keyword=cleaned_title,
                reporter=None,
                limit=5
            )
            if feedback_data:
                logger.info(f"휴먼 피드백 {len(feedback_data)}건 발견")

        # 3. 부서 추천 (증거 수집 + 과거 이력 기반)
        dept_recommendation = self.department_recommender.recommend_department(
            title=cleaned_title,
            recipient_info=None,
            feedback_data=feedback_data
        )

        logger.info(
            f"부서 추천 결과: {dept_recommendation['recommended_dept']} "
            f"(신뢰도: {dept_recommendation['confidence']}, "
            f"자동배정: {dept_recommendation['auto_assigned']})"
        )

        # 4. 조기 종료 케이스: 과거 담당자 이름으로 직접 검색
        if dept_recommendation['auto_assigned']:
            recommended_dept = dept_recommendation['recommended_dept']
            recommended_employee_name = dept_recommendation.get('recommended_employee')

            logger.info(
                f"🚀 조기 종료 모드 - 추천 부서: {recommended_dept}, "
                f"과거 담당자: {recommended_employee_name}"
            )

            # 과거 담당자 이름으로 메타데이터 직접 검색
            primary_candidate = None
            if recommended_employee_name:
                logger.info(f"📌 과거 담당자 '{recommended_employee_name}'를 메타데이터로 직접 검색 중...")
                primary_candidate = await rag_service.search_employee_by_name(recommended_employee_name)

                if primary_candidate:
                    logger.info(f"✅ 과거 담당자 메타데이터 검색 성공: {recommended_employee_name}")
                else:
                    logger.warning(f"❌ 과거 담당자 '{recommended_employee_name}'를 Qdrant에서 찾을 수 없음")

            # 추가 후보: 해당 부서 직원 검색
            document_text = f"{document_title}\n\n{document_content}"
            other_candidates = await rag_service.search_similar_employees(
                document_text,
                top_k=5,
                dept_filter=recommended_dept
            )

            logger.info(f"부서 '{recommended_dept}' 추가 후보 검색: {len(other_candidates)}명")

            # primary_candidate가 없으면 부서 내 1순위 선택
            if not primary_candidate:
                if other_candidates:
                    primary_candidate = other_candidates[0]
                    other_candidates = other_candidates[1:]
                    logger.info(f"⚠️  과거 담당자 미발견. 부서 내 1순위 선택: {primary_candidate.name}")
                else:
                    # 최종 Fallback
                    logger.error("과거 담당자도 부서 후보도 없음. Fallback 모드")
                    primary_candidate = EmployeeCandidate(
                        name=recommended_employee_name or '알 수 없음',
                        rank='',
                        dept1=recommended_dept,
                        dept2='',
                        dept3='',
                        tasks='',
                        phone=None,
                        score=None
                    )
                    other_candidates = []
            else:
                # primary_candidate가 other_candidates에 포함되어 있으면 제거
                other_candidates = [c for c in other_candidates if c.name != primary_candidate.name][:3]

            return AssignmentRecommendation(
                primary=primary_candidate,
                candidates=other_candidates,
                reasoning=dept_recommendation['reasoning']
            )

        # 5. 일반 케이스: 부서 필터 없이 검색
        document_text = f"{document_title}\n\n{document_content}"
        rag_candidates = await rag_service.search_similar_employees(document_text, top_k=20)

        if not rag_candidates:
            logger.warning("RAG에서 후보자를 찾을 수 없습니다.")
            # Fallback: 추천 부서 정보만 반환
            fallback_employee = EmployeeCandidate(
                name=dept_recommendation.get('recommended_employee', '알 수 없음'),
                rank='',
                dept1=dept_recommendation['recommended_dept'],
                dept2='',
                dept3='',
                tasks='',
                phone=None,
                score=None
            )
            return AssignmentRecommendation(
                primary=fallback_employee,
                candidates=[],
                reasoning=dept_recommendation['reasoning']
            )

        logger.info(f"RAG 후보자 {len(rag_candidates)}명 발견")

        # 6. 일반 케이스: LLM으로 최종 담당자 선정
        logger.info("LLM으로 최종 담당자 선정 중...")

        # 부서 추천 정보를 바탕으로 후보자 필터링 (옵션)
        recommended_dept = dept_recommendation['recommended_dept']
        recommended_employee_name = dept_recommendation.get('recommended_employee')

        # 추천 부서에 속한 후보를 우선순위로 배치
        dept_matched_candidates = [
            c for c in rag_candidates
            if recommended_dept in f"{c.dept1} {c.dept2} {c.dept3}"
        ]
        other_candidates_list = [
            c for c in rag_candidates
            if recommended_dept not in f"{c.dept1} {c.dept2} {c.dept3}"
        ]

        # 부서 매칭 후보를 앞에, 나머지를 뒤에 배치
        reordered_candidates = dept_matched_candidates + other_candidates_list

        if not reordered_candidates:
            reordered_candidates = rag_candidates

        logger.info(
            f"후보자 재정렬 완료: 부서 매칭 {len(dept_matched_candidates)}명, "
            f"기타 {len(other_candidates_list)}명"
        )

        # LLM 호출
        llm_recommendation = await self.llm_service.recommend_assignee(
            document_title=document_title,
            document_content=document_content,
            candidates=reordered_candidates[:10]  # 상위 10명만 LLM에 전달
        )

        # LLM 추론 결과에 부서 추천 근거 추가
        combined_reasoning = (
            f"**부서 분석 결과**: {dept_recommendation['recommended_dept']} "
            f"(신뢰도: {dept_recommendation['confidence']})\n\n"
            f"{dept_recommendation['reasoning']}\n\n"
            f"---\n\n"
            f"**담당자 선정 결과**:\n{llm_recommendation.reasoning}"
        )

        return AssignmentRecommendation(
            primary=llm_recommendation.primary,
            candidates=llm_recommendation.candidates,
            reasoning=combined_reasoning
        )


# 싱글톤 인스턴스
_pipeline = None


def get_pipeline_v2() -> DocumentProcessingPipelineV2:
    """파이프라인 V2 싱글톤 인스턴스 반환"""
    global _pipeline
    if _pipeline is None:
        _pipeline = DocumentProcessingPipelineV2()
    return _pipeline
