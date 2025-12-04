"""
부서 추천 엔진 (LLM Reasoning + Evidence)
"""
from typing import Dict, Any, List, Optional
import logging
import json
from .evidence_collector import get_evidence_collector
from .llm import get_llm_service
from .text_preprocessor import get_preprocessor


logger = logging.getLogger(__name__)


class DepartmentRecommender:
    """부서 추천 엔진"""

    def __init__(self):
        self.evidence_collector = get_evidence_collector()
        self.llm_service = get_llm_service()
        self.preprocessor = get_preprocessor()

    def recommend_department(
        self,
        title: str,
        recipient_info: Optional[Dict[str, Any]] = None,
        feedback_data: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """부서 추천 (증거 수집 + LLM 추론)

        Args:
            title: 문서 제목
            recipient_info: 수신자 정보 (OCR + LLM 보정 결과)
            feedback_data: 휴먼 피드백 데이터 (옵션)

        Returns:
            추천 결과 딕셔너리
        """
        logger.info(f"부서 추천 시작: '{title}'")

        # 1. 제목 정규화
        cleaned_title = self.preprocessor.clean_title(title)

        # 2. 부서 필터 (수신자 정보)
        dept_filter = None
        if recipient_info and recipient_info.get('is_explicit'):
            dept_filter = recipient_info.get('dept_name')
            logger.info(f"수신자 필터 적용: {dept_filter}")

        # 3. 증거 수집
        evidence = self.evidence_collector.collect_all_evidence(
            title=cleaned_title,
            dept_filter=dept_filter
        )

        # 4. 조기 종료 체크 (자동 배정)
        if evidence['early_stopped']:
            return {
                'recommended_dept': evidence['auto_assigned_dept'],
                'recommended_employee': evidence.get('matched_document', {}).get('reporter'),
                'confidence': 'high',
                'reasoning': evidence['reason'],
                'auto_assigned': True,
                'evidence': evidence
            }

        # 5. LLM 추론
        llm_result = self._llm_inference(
            title=title,
            cleaned_title=cleaned_title,
            recipient_info=recipient_info,
            history_evidence=evidence['history_evidence'],
            job_evidence=evidence['job_evidence'],
            feedback_data=feedback_data
        )

        return {
            'recommended_dept': llm_result['recommended_dept'],
            'recommended_employee': llm_result.get('recommended_employee'),
            'confidence': llm_result['confidence'],
            'reasoning': llm_result['reasoning'],
            'auto_assigned': False,
            'evidence': evidence,
            'llm_output': llm_result
        }

    def _llm_inference(
        self,
        title: str,
        cleaned_title: str,
        recipient_info: Optional[Dict[str, Any]],
        history_evidence: List[Dict[str, Any]],
        job_evidence: List[Dict[str, Any]],
        feedback_data: Optional[List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """LLM 추론 수행

        Args:
            title: 원본 제목
            cleaned_title: 정규화된 제목
            recipient_info: 수신자 정보
            history_evidence: 문서 배부 이력 증거
            job_evidence: 사무분장 규정 증거
            feedback_data: 휴먼 피드백 데이터

        Returns:
            LLM 추론 결과
        """
        # 프롬프트 구성
        prompt = self._build_prompt(
            title=title,
            cleaned_title=cleaned_title,
            recipient_info=recipient_info,
            history_evidence=history_evidence,
            job_evidence=job_evidence,
            feedback_data=feedback_data
        )

        # LLM 호출
        try:
            response = self.llm_service.generate_completion(
                messages=[
                    {"role": "system", "content": "당신은 전북도청 문서 배부 전문가입니다. 문서의 제목, 수신자 정보, 과거 배부 이력, 사무분장 규정을 종합적으로 고려하여 최적의 담당 부서를 추천해주세요."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )

            # 응답 파싱
            content = response.get('content', '')
            return self._parse_llm_response(content)

        except Exception as e:
            logger.error(f"LLM 추론 실패: {e}")
            # Fallback: 가장 많이 나온 부서 선택
            return self._fallback_inference(history_evidence, job_evidence)

    def _build_prompt(
        self,
        title: str,
        cleaned_title: str,
        recipient_info: Optional[Dict[str, Any]],
        history_evidence: List[Dict[str, Any]],
        job_evidence: List[Dict[str, Any]],
        feedback_data: Optional[List[Dict[str, Any]]]
    ) -> str:
        """LLM 프롬프트 구성"""
        prompt = f"""# 문서 배부 부서 추천 요청

## 분석 대상 문서
- **원본 제목**: {title}
- **정규화 제목**: {cleaned_title}
"""

        # 수신자 정보
        if recipient_info:
            prompt += f"""
## 수신자 정보 (OCR 추출)
- **명시적 수신자**: {"있음" if recipient_info.get('is_explicit') else "없음/모호함"}
"""
            if recipient_info.get('is_explicit'):
                prompt += f"- **수신 부서**: {recipient_info.get('dept_name')}\n"
                prompt += f"- **근거**: {recipient_info.get('reason')}\n"

        # 문서 배부 이력 증거
        if history_evidence:
            prompt += "\n## 과거 문서 배부 이력 (유사도 기준 상위 문서)\n"
            for i, doc in enumerate(history_evidence[:5], 1):
                prompt += f"""
### {i}. 과거 문서
- **제목**: {doc['title']}
- **배부 부서**: {doc['dept']}
- **보고자**: {doc['reporter']}
- **보고 일자**: {doc['date']}
- **유사도**: {doc['similarity']:.2f}%
"""

        # 사무분장 규정 증거
        if job_evidence:
            prompt += "\n## 사무분장 규정 (관련 업무)\n"
            for i, job in enumerate(job_evidence[:3], 1):
                prompt += f"""
### {i}. 사무분장
- **부서**: {job['dept']}
- **업무 내용**: {job['job_description']}
- **직급**: {job['rank']}
- **담당자**: {job['manager']}
"""

        # 휴먼 피드백 데이터
        if feedback_data:
            prompt += "\n## 휴먼 피드백 이력 (중요!)\n"
            prompt += "**주의**: 과거에 이 키워드/보고자에 대해 LLM 추천이 수정된 이력이 있습니다.\n"
            for i, feedback in enumerate(feedback_data, 1):
                prompt += f"""
### {i}. 피드백
- **LLM 예측 (오답)**: {feedback['llm_predicted_dept']}
- **담당자 수정 (정답)**: {feedback['human_corrected_dept']}
- **수정 사유**: {feedback.get('reason', '(없음)')}
"""

        # 추론 지시사항
        prompt += """

## 추론 지시사항

**핵심 원칙: 행정 업무는 연속성과 관례를 따릅니다. 과거 배부 이력을 최우선으로 고려하세요.**

1. **휴먼 피드백 최우선**: 휴먼 피드백이 있다면 절대적으로 우선 고려하세요.

2. **과거 배부 이력 중심 분석** (가장 중요!):
   - 유사도가 높은 과거 문서의 **배부 부서**와 **보고자**를 최우선으로 고려하세요.
   - 동일하거나 유사한 주제의 문서는 **동일한 담당자/부서**로 배부되는 것이 행정 관례입니다.
   - 과거 보고자가 반복적으로 나타나는 경우, 해당 담당자가 계속 업무를 맡고 있을 가능성이 높습니다.
   - 유사도 70% 이상인 문서가 있다면, 해당 문서의 배부 부서를 **강하게** 고려하세요.

3. **사무분장 규정 참고** (보조 자료):
   - 사무분장은 **참고 자료**로만 활용하세요.
   - 과거 이력이 있다면 사무분장보다 **과거 이력을 우선**하세요.
   - 과거 이력이 전혀 없거나 유사도가 매우 낮을 때(70% 미만)만 사무분장을 주요 근거로 사용하세요.

4. **업무 연속성 보장**:
   - 같은 기관, 같은 주제, 같은 유형의 문서는 계속 같은 부서/담당자에게 배부됩니다.
   - 과거 이력이 명확하다면 confidence를 'high'로 설정하세요.

5. **부서명 정확성**: 반드시 실제 존재하는 부서명을 선택하세요.

## 출력 형식 (JSON)
다음 JSON 형식으로만 응답하세요:

```json
{
  "recommended_dept": "추천 부서명",
  "recommended_employee": "추천 담당자명 또는 null",
  "confidence": "high|medium|low",
  "reasoning": "추천 근거 (2-3문장, 담당자 선택 이유 포함)",
  "alternative_depts": ["대안 부서1", "대안 부서2"]
}
```

**담당자 추천 지침**:
- 과거 배부 이력에서 **동일한 보고자가 반복**되면 해당 담당자를 추천하세요.
- 유사도 70% 이상 문서의 보고자는 **강력한 후보**입니다.
- 담당자 정보가 불명확하거나 과거 이력이 없으면 `"recommended_employee": null`로 설정하세요.
- 보고자 이름만 작성하고 직급/부서는 포함하지 마세요. (예: "김지수" ⭕, "행정정보과 김지수" ❌)

**응답**:
"""

        return prompt

    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """LLM 응답 파싱"""
        try:
            # JSON 코드 블록 추출
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()

            # JSON 파싱
            result = json.loads(json_str)

            # recommended_employee 처리: null, "null", 빈 문자열 등을 None으로 정규화
            recommended_employee = result.get('recommended_employee')
            if recommended_employee in [None, "null", "None", ""]:
                recommended_employee = None
            elif isinstance(recommended_employee, str):
                recommended_employee = recommended_employee.strip()

            return {
                'recommended_dept': result.get('recommended_dept', '행정정보과'),
                'recommended_employee': recommended_employee,  # 추가
                'confidence': result.get('confidence', 'medium'),
                'reasoning': result.get('reasoning', ''),
                'alternative_depts': result.get('alternative_depts', [])
            }

        except Exception as e:
            logger.error(f"LLM 응답 파싱 실패: {e}\n응답: {content}")
            return {
                'recommended_dept': '행정정보과',
                'recommended_employee': None,  # 추가
                'confidence': 'low',
                'reasoning': 'LLM 응답 파싱 실패',
                'alternative_depts': []
            }

    def _fallback_inference(
        self,
        history_evidence: List[Dict[str, Any]],
        job_evidence: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Fallback 추론 (가장 많이 나온 부서)"""
        dept_counts = {}

        # 문서 배부 이력 카운트
        for doc in history_evidence:
            dept = doc['dept']
            dept_counts[dept] = dept_counts.get(dept, 0) + 1

        # 사무분장 카운트
        for job in job_evidence:
            dept = job['dept']
            dept_counts[dept] = dept_counts.get(dept, 0) + 0.5  # 가중치 절반

        # 가장 많이 나온 부서
        if dept_counts:
            recommended_dept = max(dept_counts, key=dept_counts.get)
        else:
            recommended_dept = '행정정보과'  # 기본값

        return {
            'recommended_dept': recommended_dept,
            'confidence': 'low',
            'reasoning': 'Fallback: 과거 이력 및 사무분장에서 가장 많이 나온 부서',
            'alternative_depts': list(dept_counts.keys())[:2]
        }


# 싱글톤 인스턴스
_department_recommender = None


def get_department_recommender() -> DepartmentRecommender:
    """부서 추천 엔진 싱글톤 인스턴스 반환"""
    global _department_recommender
    if _department_recommender is None:
        _department_recommender = DepartmentRecommender()
    return _department_recommender
