"""
휴먼 피드백 서비스
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from app.database.db import FeedbackModel
from datetime import datetime
import logging


logger = logging.getLogger(__name__)


class FeedbackService:
    """휴먼 피드백 관리 서비스"""

    @staticmethod
    async def add_feedback(
        db: AsyncSession,
        keyword: str,
        reporter: Optional[str],
        llm_predicted_dept: str,
        human_corrected_dept: str,
        reason: Optional[str] = None,
        document_id: Optional[int] = None,
        document_title: Optional[str] = None
    ) -> FeedbackModel:
        """피드백 추가

        Args:
            db: 데이터베이스 세션
            keyword: 문서 핵심 키워드 (보통 제목)
            reporter: 보고자
            llm_predicted_dept: LLM 예측 부서
            human_corrected_dept: 담당자 수정 부서
            reason: 수정 사유
            document_id: 원본 문서 ID
            document_title: 원본 문서 제목

        Returns:
            생성된 피드백 모델
        """
        feedback = FeedbackModel(
            keyword=keyword,
            reporter=reporter,
            llm_predicted_dept=llm_predicted_dept,
            human_corrected_dept=human_corrected_dept,
            reason=reason,
            document_id=document_id,
            document_title=document_title
        )

        db.add(feedback)
        await db.commit()
        await db.refresh(feedback)

        logger.info(
            f"피드백 추가: {llm_predicted_dept} -> {human_corrected_dept} "
            f"(키워드: {keyword})"
        )

        return feedback

    @staticmethod
    async def get_feedback_for_inference(
        db: AsyncSession,
        keyword: Optional[str] = None,
        reporter: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """추론을 위한 피드백 조회

        Args:
            db: 데이터베이스 세션
            keyword: 키워드 (부분 매칭)
            reporter: 보고자 (완전 매칭)
            limit: 최대 개수

        Returns:
            피드백 리스트
        """
        conditions = []

        if keyword:
            conditions.append(FeedbackModel.keyword.like(f"%{keyword}%"))

        if reporter:
            conditions.append(FeedbackModel.reporter == reporter)

        if not conditions:
            return []

        # OR 조건으로 검색
        query = select(FeedbackModel).where(
            or_(*conditions)
        ).order_by(
            FeedbackModel.created_at.desc()
        ).limit(limit)

        result = await db.execute(query)
        feedbacks = result.scalars().all()

        return [
            {
                'keyword': f.keyword,
                'reporter': f.reporter,
                'llm_predicted_dept': f.llm_predicted_dept,
                'human_corrected_dept': f.human_corrected_dept,
                'reason': f.reason,
                'created_at': f.created_at.isoformat()
            }
            for f in feedbacks
        ]

    @staticmethod
    async def get_all_feedbacks(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100
    ) -> List[FeedbackModel]:
        """전체 피드백 조회

        Args:
            db: 데이터베이스 세션
            skip: 건너뛸 개수
            limit: 최대 개수

        Returns:
            피드백 리스트
        """
        query = select(FeedbackModel).order_by(
            FeedbackModel.created_at.desc()
        ).offset(skip).limit(limit)

        result = await db.execute(query)
        return result.scalars().all()


# 싱글톤 (필요 시)
_feedback_service = FeedbackService()


def get_feedback_service() -> FeedbackService:
    """피드백 서비스 인스턴스 반환"""
    return _feedback_service
