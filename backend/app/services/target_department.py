"""타겟 부서 결정 서비스"""
import json
import logging
from typing import Optional
from app.models.ocr_schemas import RecipientInfo, DepartmentFilterResult, SelectedDepartment

logger = logging.getLogger(__name__)


class TargetDepartmentService:
    """
    문서의 타겟 부서 결정

    우선순위:
    1. 수신자 필터링 (명시적) - 문서에 특정 부서가 명시된 경우
    2. 부서 필터링 (추론적) - LLM이 문서 내용 분석으로 추론한 부서
    """

    @staticmethod
    def determine_target_department(
        recipient_info: Optional[RecipientInfo],
        dept_filter_result: Optional[DepartmentFilterResult]
    ) -> Optional[SelectedDepartment]:
        """
        타겟 부서 결정

        Args:
            recipient_info: 수신자 필터링 결과
            dept_filter_result: 부서 필터링 결과

        Returns:
            SelectedDepartment: 타겟 부서 (없으면 None)
        """
        # 1순위: 수신자 필터링 (명시적)
        if recipient_info and recipient_info.has_recipient and recipient_info.is_specific:
            # 수신자 텍스트에서 부서명 추출
            dept = TargetDepartmentService._extract_dept_from_recipient(
                recipient_info.recipient_text
            )
            if dept:
                logger.info(f"타겟 부서 결정 (수신자 명시): {dept.dept1}")
                return dept

        # 2순위: 부서 필터링 (추론적)
        if dept_filter_result and dept_filter_result.selected_departments:
            # 최고 점수 부서 선택
            top_dept = dept_filter_result.selected_departments[0]
            logger.info(
                f"타겟 부서 결정 (LLM 추론): {top_dept.dept1} "
                f"(점수: {top_dept.relevance_score})"
            )
            return top_dept

        logger.warning("타겟 부서를 결정할 수 없습니다")
        return None

    @staticmethod
    def _extract_dept_from_recipient(recipient_text: str) -> Optional[SelectedDepartment]:
        """
        수신자 텍스트에서 부서명 추출

        예:
        - "수신: 정책기획관" → SelectedDepartment(dept1="정책기획관")
        - "수신: 기획조정실 정책기획관 성과평가팀" → dept1/2/3 파싱
        - "전북특별자치도지사(행정정보과장)" → dept1="행정정보과"

        Args:
            recipient_text: 수신자 텍스트

        Returns:
            SelectedDepartment: 추출된 부서 (실패 시 None)
        """
        import re

        # "수신:", "받는사람:" 등 제거
        cleaned = re.sub(r'(수신|받는사람|수신자|수신처)\s*:\s*', '', recipient_text)
        cleaned = cleaned.strip()

        # 괄호 안에 부서명이 있는 경우 추출 (예: "전북특별자치도지사(행정정보과장)")
        bracket_match = re.search(r'\(([가-힣]+)과장\)', cleaned)
        if bracket_match:
            dept_name = bracket_match.group(1) + "과"  # "행정정보" → "행정정보과"
            return SelectedDepartment(
                dept1=dept_name,
                dept2=None,
                dept3=None,
                relevance_score=100,
                reasoning="수신자 필드 괄호에서 추출"
            )

        # 부서 계층 파싱 (간단한 휴리스틱)
        # 예: "기획조정실 정책기획관 성과평가팀"
        parts = cleaned.split()

        if not parts:
            return None

        # 최소 dept1은 있어야 함
        dept1 = parts[0] if len(parts) > 0 else None
        dept2 = parts[1] if len(parts) > 1 else None
        dept3 = parts[2] if len(parts) > 2 else None

        if dept1:
            return SelectedDepartment(
                dept1=dept1,
                dept2=dept2,
                dept3=dept3,
                relevance_score=100,  # 명시적이므로 100점
                reasoning="수신자 필드에 명시됨"
            )

        return None


# 싱글톤 인스턴스
target_dept_service = TargetDepartmentService()
