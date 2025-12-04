"""
문서 배부 자동화 Pipeline V2
pipeline_v2.md 사양에 따른 구현
"""
from typing import Dict, Any, Optional
import logging
import json
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.db import DocumentModel
from .text_preprocessor import get_preprocessor
from .recipient_filter import recipient_filter_service
from .department_recommender import get_department_recommender
from .feedback_service import get_feedback_service
from .bm25_index import get_bm25_system
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


# 싱글톤 인스턴스
_pipeline = None


def get_pipeline_v2() -> DocumentProcessingPipelineV2:
    """파이프라인 V2 싱글톤 인스턴스 반환"""
    global _pipeline
    if _pipeline is None:
        _pipeline = DocumentProcessingPipelineV2()
    return _pipeline
