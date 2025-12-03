"""부서 필터링 서비스"""
import json
import logging
import httpx
from typing import List, Set, Dict
from collections import defaultdict

from app.config import settings
from app.models.ocr_schemas import DepartmentInfo, SelectedDepartment, DepartmentFilterResult
from app.models.schemas import EmployeeCandidate
from app.services.rag import rag_service
from app.exceptions import LLMServiceError

logger = logging.getLogger(__name__)


class DepartmentFilterService:
    """문서 내용 기반 부서 필터링 서비스"""

    def __init__(self):
        self.llm_api_url = settings.llm_api_url
        self.llm_api_key = settings.llm_api_key
        self.llm_model = settings.llm_model
        self._department_cache: Dict[str, List[DepartmentInfo]] = {}

    async def get_unique_departments(self) -> List[DepartmentInfo]:
        """
        Qdrant에서 전체 부서 정보 추출 및 중복 제거

        Returns:
            List[DepartmentInfo]: unique 부서 목록
        """
        try:
            # 캐시 확인
            cache_key = "all_departments"
            if cache_key in self._department_cache:
                logger.info("Using cached department list")
                return self._department_cache[cache_key]

            # Qdrant에서 모든 직원 정보 조회 (충분히 큰 top_k)
            # 실제로는 scroll API 사용이 더 적절하지만, search로 대체
            all_employees = await rag_service.search_similar_employees(
                document_text="전체 부서 조회",
                top_k=1000  # 충분히 큰 값
            )

            # 부서 정보 추출 및 중복 제거
            departments_set: Set[tuple] = set()

            for emp in all_employees:
                dept_tuple = (
                    emp.dept1 or "",
                    emp.dept2 or "",
                    emp.dept3 or ""
                )
                departments_set.add(dept_tuple)

            # DepartmentInfo 리스트로 변환
            departments = []
            for dept1, dept2, dept3 in departments_set:
                if dept1:  # 최소한 dept1은 있어야 함
                    departments.append(DepartmentInfo(
                        dept1=dept1 if dept1 else None,
                        dept2=dept2 if dept2 else None,
                        dept3=dept3 if dept3 else None
                    ))

            # 정렬 (dept1 > dept2 > dept3 순)
            departments.sort(key=lambda d: (d.dept1 or "", d.dept2 or "", d.dept3 or ""))

            # 캐시 저장
            self._department_cache[cache_key] = departments

            logger.info(f"Extracted {len(departments)} unique departments")
            return departments

        except Exception as e:
            logger.error(f"Failed to get unique departments: {str(e)}")
            return []

    def _format_departments_for_llm(self, departments: List[DepartmentInfo]) -> str:
        """
        부서 목록을 LLM이 읽기 쉬운 형식으로 변환

        Args:
            departments: 부서 목록

        Returns:
            str: 포맷된 문자열
        """
        # dept1 기준으로 그룹화
        grouped: Dict[str, List[DepartmentInfo]] = defaultdict(list)

        for dept in departments:
            grouped[dept.dept1 or "기타"].append(dept)

        # 포맷팅
        lines = []
        for dept1, dept_list in sorted(grouped.items()):
            lines.append(f"\n[{dept1}]")

            for dept in dept_list:
                parts = [dept1]
                if dept.dept2:
                    parts.append(dept.dept2)
                if dept.dept3:
                    parts.append(dept.dept3)

                lines.append(f"  - {' > '.join(parts)}")

        return '\n'.join(lines)

    async def filter_by_department(
        self,
        document_text: str,
        document_title: str = ""
    ) -> DepartmentFilterResult:
        """
        LLM으로 관련 부서 선택

        Args:
            document_text: 문서 내용
            document_title: 문서 제목

        Returns:
            DepartmentFilterResult: 선택된 부서 목록
        """
        try:
            # 1. 부서 목록 조회
            all_departments = await self.get_unique_departments()

            if not all_departments:
                logger.warning("No departments found")
                return DepartmentFilterResult(
                    selected_departments=[],
                    reasoning="사용 가능한 부서 정보가 없습니다."
                )

            # 2. LLM 호출
            result = await self._call_llm_for_department_selection(
                document_text,
                document_title,
                all_departments
            )

            logger.info(f"Selected {len(result.selected_departments)} departments")
            return result

        except Exception as e:
            logger.error(f"Department filtering failed: {str(e)}")
            return DepartmentFilterResult(
                selected_departments=[],
                reasoning=f"부서 필터링 실패: {str(e)}"
            )

    async def _call_llm_for_department_selection(
        self,
        document_text: str,
        document_title: str,
        departments: List[DepartmentInfo]
    ) -> DepartmentFilterResult:
        """
        LLM API 호출하여 부서 선택

        Args:
            document_text: 문서 내용
            document_title: 문서 제목
            departments: 가용 부서 목록

        Returns:
            DepartmentFilterResult: 선택 결과
        """
        # 부서 목록 포맷팅
        dept_list_str = self._format_departments_for_llm(departments)

        system_prompt = """당신은 문서 내용을 분석하여 업무 관련 부서를 특정하는 전문가입니다.

문서의 내용과 제목을 분석하여 관련 부서를 1~3개 선택하세요.

**선택 기준:**
1. 문서의 주제와 직접 관련된 부서
2. 문서에 명시된 업무를 담당하는 부서
3. 문서 내용에서 언급된 부서나 팀

**점수 부여 (0-100):**
- 90-100: 직접적으로 관련된 핵심 부서
- 70-89: 관련성 높은 부서
- 50-69: 부분적으로 관련된 부서
- 50 미만: 선택하지 마세요"""

        user_prompt = f"""[문서 제목]
{document_title}

[문서 내용]
{document_text[:2000]}

[가용 부서 목록]
{dept_list_str}

위 문서와 관련된 부서를 1~3개 선택하고, 다음 JSON 형식으로 응답하세요:

{{
  "selected_departments": [
    {{
      "dept1": "부서1",
      "dept2": "부서2",
      "dept3": "부서3",
      "relevance_score": 95,
      "reasoning": "선택 이유 (1-2문장)"
    }},
    ...
  ],
  "reasoning": "전체 선택 이유 (2-3문장)"
}}

**주의사항:**
- dept2, dept3는 해당하는 경우에만 포함
- relevance_score는 50 이상인 부서만 선택
- 최대 3개까지만 선택
- JSON 형식만 반환하고 다른 설명은 포함하지 마세요"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {"Content-Type": "application/json"}
                if self.llm_api_key:
                    headers["Authorization"] = f"Bearer {self.llm_api_key}"

                payload = {
                    "model": self.llm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.1,
                }

                logger.info("Calling LLM for department selection")
                response = await client.post(
                    self.llm_api_url,
                    json=payload,
                    headers=headers
                )

                response.raise_for_status()
                result = response.json()

                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                # JSON 파싱
                filter_result = self._parse_department_response(content)

                return filter_result

        except Exception as e:
            logger.error(f"Department selection LLM call failed: {str(e)}")
            raise LLMServiceError(f"부서 선택 실패: {str(e)}")

    def _parse_department_response(self, response_content: str) -> DepartmentFilterResult:
        """
        LLM 응답 파싱

        Args:
            response_content: LLM 응답

        Returns:
            DepartmentFilterResult: 파싱 결과
        """
        try:
            # JSON 블록 추출
            content = response_content.strip()

            if '```json' in content:
                start = content.find('```json') + 7
                end = content.find('```', start)
                content = content[start:end].strip()
            elif '```' in content:
                start = content.find('```') + 3
                end = content.find('```', start)
                content = content[start:end].strip()

            if not content.startswith('{'):
                start = content.find('{')
                end = content.rfind('}')
                if start != -1 and end != -1:
                    content = content[start:end + 1]

            data = json.loads(content)

            # SelectedDepartment 리스트 생성
            selected = []
            for dept_data in data.get('selected_departments', []):
                selected.append(SelectedDepartment(
                    dept1=dept_data.get('dept1', ''),
                    dept2=dept_data.get('dept2'),
                    dept3=dept_data.get('dept3'),
                    relevance_score=dept_data.get('relevance_score', 50),
                    reasoning=dept_data.get('reasoning', '')
                ))

            return DepartmentFilterResult(
                selected_departments=selected,
                reasoning=data.get('reasoning', '')
            )

        except Exception as e:
            logger.error(f"Failed to parse department response: {str(e)}")
            return DepartmentFilterResult(
                selected_departments=[],
                reasoning=f"응답 파싱 실패: {str(e)}"
            )

    def filter_candidates_by_departments(
        self,
        candidates: List[EmployeeCandidate],
        selected_departments: List[SelectedDepartment]
    ) -> List[EmployeeCandidate]:
        """
        선택된 부서에 속한 후보자만 필터링

        Args:
            candidates: 전체 후보자 목록
            selected_departments: 선택된 부서 목록

        Returns:
            List[EmployeeCandidate]: 필터링된 후보자 목록
        """
        if not selected_departments:
            logger.info("No departments selected, returning all candidates")
            return candidates

        filtered = []

        for candidate in candidates:
            # 후보자의 부서가 선택된 부서 중 하나와 매칭되는지 확인
            for dept in selected_departments:
                if self._match_department(candidate, dept):
                    filtered.append(candidate)
                    break

        logger.info(f"Filtered {len(filtered)} candidates from {len(candidates)} by departments")
        return filtered

    def _match_department(
        self,
        candidate: EmployeeCandidate,
        department: SelectedDepartment
    ) -> bool:
        """
        후보자가 해당 부서에 속하는지 확인

        Args:
            candidate: 후보자
            department: 부서 정보

        Returns:
            bool: 매칭 여부
        """
        # dept1 매칭 (필수)
        if candidate.dept1 != department.dept1:
            return False

        # dept2 매칭 (있는 경우)
        if department.dept2 and candidate.dept2 != department.dept2:
            return False

        # dept3 매칭 (있는 경우)
        if department.dept3 and candidate.dept3 != department.dept3:
            return False

        return True


# 싱글톤 인스턴스
department_filter_service = DepartmentFilterService()
