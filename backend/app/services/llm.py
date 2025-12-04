import json
import re
import httpx
from typing import List, Optional
from pydantic import BaseModel, Field, ValidationError
from app.config import settings
from app.models.schemas import EmployeeCandidate, AssignmentRecommendation
from app.exceptions import LLMServiceError, LLMAPIError, LLMResponseParseError

# 1. LLM의 응답 구조를 명확히 정의 (Pydantic 활용)
class CandidateEvaluation(BaseModel):
    name: str
    match_score: int = Field(..., description="0~100 사이의 업무 적합성 점수")
    reasoning: str = Field(..., description="이 직원을 추천하거나 추천하지 않는 구체적인 이유")

class ReviewResult(BaseModel):
    document_summary: str = Field(..., description="문서의 핵심 내용 요약 (한 줄)")
    key_requirements: List[str] = Field(..., description="담당자가 갖춰야 할 핵심 역량 3가지")
    evaluations: List[CandidateEvaluation] = Field(..., description="각 후보자에 대한 평가 리스트")
    best_candidate_name: str = Field(..., description="최종 선정된 1순위 담당자 이름")

class LLMService:
    def __init__(self):
        self.api_url = settings.llm_api_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    def _format_candidate_block(self, candidates: List[EmployeeCandidate]) -> str:
        """후보자 정보를 LLM이 읽기 쉬운 마크다운 형태로 변환"""
        formatted = []
        for cand in candidates:
            # 부서 정보 계층화
            dept = f"{cand.dept1}"
            if cand.dept2: dept += f" > {cand.dept2}"
            if cand.dept3: dept += f" > {cand.dept3}"
            
            # 검색 엔진 점수(score)가 있다면 참고용으로 제공
            search_score = f"(검색 유사도: {cand.score:.2f})" if cand.score else ""
            
            formatted.append(f"""
---
### 후보자: {cand.name} ({cand.rank})
- **소속:** {dept}
- **주요 업무:** {cand.tasks}
- **참고:** {search_score}
""")
        return "\n".join(formatted)

    async def recommend_assignee(
        self,
        document_title: str,
        document_content: str,
        candidates: List[EmployeeCandidate]
    ) -> AssignmentRecommendation:
        
        # 1. 프롬프트 엔지니어링: CoT (Chain of Thought) 적용
        system_prompt = """
당신은 전북도청의 문서 배부 시스템 AI입니다. 
주어진 문서 내용을 분석하고, 제공된 직원 목록 중에서 이 문서를 처리하기에 가장 적합한 담당자를 찾아야 합니다.

[분석 단계]
1. 문서의 핵심 주제와 필요한 행정 처리가 무엇인지 파악하십시오.
2. 각 후보자의 '주요 업무' 텍스트를 분석하여 문서 내용과의 연관성을 0~100점으로 채점하십시오.
3. 단순히 단어가 일치하는 것이 아니라, '업무의 맥락'이 일치하는지 판단하십시오.
   (예: '도로 보수' 문서는 '도로과'의 '유지보수' 담당자에게 가야 함)

**반드시 아래의 JSON 스키마를 정확히 준수하여 응답하십시오. 다른 텍스트나 설명 없이 JSON만 반환하세요.**

응답 형식 (예시):
{
  "document_summary": "문서의 핵심 내용을 한 줄로 요약",
  "key_requirements": ["필수 역량 1", "필수 역량 2", "필수 역량 3"],
  "evaluations": [
    {
      "name": "직원 이름",
      "match_score": 85,
      "reasoning": "이 직원을 추천하는 구체적인 이유"
    },
    {
      "name": "다른 직원 이름",
      "match_score": 70,
      "reasoning": "이 직원을 추천하는 이유"
    }
  ],
  "best_candidate_name": "최종 선정된 1순위 담당자 이름"
}
"""
        
        candidates_text = self._format_candidate_block(candidates)
        
        # 후보자 이름 목록을 명확히 표시
        candidate_names = [c.name for c in candidates]
        names_list = ", ".join(candidate_names)
        
        # f-string에서 중괄호를 리터럴로 사용하려면 {{ }}로 이스케이프해야 함
        # document_content에 중괄호가 있을 수 있으므로 안전하게 처리
        # f-string 대신 .format() 또는 % 포맷팅 사용을 고려할 수 있지만,
        # 여기서는 document_content를 먼저 처리하여 중괄호를 이스케이프
        safe_document_content = document_content.replace("{", "{{").replace("}", "}}")
        
        user_prompt = f"""
[문서 정보]
제목: {document_title}
내용:
{safe_document_content}

[후보 직원 목록]
{candidates_text}

**중요: 사용 가능한 후보자 이름 목록**
{names_list}

위 후보자들 중 가장 적합한 담당자를 선정하고, 반드시 아래 형식의 JSON만 반환해주세요. 다른 설명이나 텍스트는 포함하지 마세요.

**name 필드와 best_candidate_name 필드에는 반드시 위에 나열된 이름 중 하나를 정확히 입력해야 합니다.**

{{
  "document_summary": "문서의 핵심 내용을 한 줄로 요약",
  "key_requirements": ["필수 역량 1", "필수 역량 2", "필수 역량 3"],
  "evaluations": [
    {{
      "name": "직원 이름 (반드시 후보자 목록에 있는 이름)",
      "match_score": 85,
      "reasoning": "이 직원을 추천하는 구체적인 이유"
    }}
  ],
  "best_candidate_name": "최종 선정된 1순위 담당자 이름 (반드시 후보자 목록에 있는 이름)"
}}

중요: evaluations 배열에는 모든 후보자에 대한 평가를 포함해야 하며, name 필드는 반드시 제공된 후보자 목록에 있는 이름과 정확히 일치해야 합니다.
"""

        # 2. Schema 정의 (OpenAI Function Calling 스타일 혹은 JSON Mode 유도)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1, # 사실적 추론을 위해 온도를 낮춤
        }
        
        # response_format은 모델이 지원하는 경우에만 추가
        # 일부 모델은 이 옵션을 지원하지 않을 수 있음
        try:
            # OpenAI 호환 API인 경우 response_format 지원
            payload["response_format"] = {"type": "json_object"}
        except:
            pass

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {
                    "Content-Type": "application/json",
                }
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                
                response = await client.post(
                    self.api_url, 
                    json=payload, 
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()
                
                if "choices" not in result or len(result["choices"]) == 0:
                    raise LLMAPIError("LLM API 응답에 choices가 없습니다.")
                
                content = result["choices"][0]["message"]["content"].strip()
            
            # 3. JSON 파싱 (다양한 패턴 처리)
            json_data = None
            
            # 1. 직접 JSON 파싱 시도
            try:
                json_data = json.loads(content)
            except json.JSONDecodeError:
                pass
            
            # 2. 코드 블록에서 JSON 추출 시도
            if json_data is None:
                for pattern in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```"]:
                    match = re.search(pattern, content, re.DOTALL)
                    if match:
                        try:
                            json_data = json.loads(match.group(1).strip())
                            break
                        except json.JSONDecodeError:
                            continue
            
            # 3. 중괄호로 감싸진 JSON 추출 시도
            if json_data is None:
                match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
                if match:
                    try:
                        json_data = json.loads(match.group(0))
                    except json.JSONDecodeError:
                        pass
            
            # 4. 첫 번째 { 부터 마지막 } 까지 추출 시도
            if json_data is None:
                start_idx = content.find('{')
                end_idx = content.rfind('}')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    try:
                        json_str = content[start_idx:end_idx+1]
                        json_data = json.loads(json_str)
                    except json.JSONDecodeError:
                        pass
            
            # 모든 시도 실패
            if json_data is None:
                error_msg = f"LLM 응답에서 JSON을 찾을 수 없습니다. 응답 내용 (처음 500자): {content[:500]}"
                raise LLMResponseParseError(error_msg)
            
            # 4. Pydantic을 이용한 검증 및 파싱
            try:
                review_data = ReviewResult.model_validate(json_data)
            except ValidationError as validation_error:
                # Validation 오류 상세 로깅
                error_details = json.dumps(validation_error.errors(), indent=2, ensure_ascii=False)
                
                # JSON 데이터 구조 로깅 (디버깅용)
                json_structure = json.dumps(json_data, indent=2, ensure_ascii=False)[:1000]
                
                # Fallback: 기존 방식으로 처리 시도 (첫 번째 후보자를 선택)
                # 하지만 먼저 상세한 에러를 로깅
                import logging
                logger = logging.getLogger(__name__)
                logger.error(
                    f"ReviewResult validation 실패:\n"
                    f"오류 상세: {error_details}\n"
                    f"받은 JSON 구조 (처음 1000자):\n{json_structure}\n"
                    f"원본 LLM 응답 (처음 500자):\n{content[:500]}"
                )
                
                # Fallback: 간단한 방식으로 처리
                # JSON에서 최소한의 정보를 추출하여 사용
                fallback_employee = candidates[0] if candidates else None
                if not fallback_employee:
                    raise LLMServiceError("후보자가 없습니다.")
                
                # JSON에서 이름이나 점수 정보가 있으면 활용
                best_name = None
                if isinstance(json_data, dict):
                    best_name = json_data.get("best_candidate_name") or (json_data.get("evaluations", [{}])[0].get("name") if json_data.get("evaluations") else None)
                
                if best_name:
                    cand_map = {c.name: c for c in candidates}
                    fallback_employee = cand_map.get(best_name, fallback_employee)
                
                # Fallback reasoning 생성
                fallback_reasoning = "LLM 응답 형식 오류로 인해 자동 추천되었습니다."
                if isinstance(json_data, dict):
                    summary = json_data.get("document_summary", "")
                    if summary:
                        fallback_reasoning = f"문서 요약: {summary}"
                
                return AssignmentRecommendation(
                    primary=fallback_employee,
                    candidates=candidates[1:3] if len(candidates) > 1 else [],
                    reasoning=fallback_reasoning
                )
            except Exception as e:
                # 기타 validation 오류
                error_msg = f"ReviewResult validation 실패: {str(e)}"
                raise LLMResponseParseError(error_msg)
            
            # 4. 결과 매핑 (LLM의 분석 결과 + 원본 직원 정보 결합)
            # 이름으로 원본 객체 매핑
            cand_map = {c.name: c for c in candidates}
            candidate_names = list(cand_map.keys())
            
            # 이름 유사도 매칭 함수 (대소문자 무시, 공백 제거)
            def find_best_match_name(llm_name: str, candidate_names: List[str]) -> Optional[str]:
                """LLM이 반환한 이름과 가장 유사한 후보자 이름 찾기"""
                if not llm_name:
                    return None
                
                llm_name_clean = llm_name.strip()
                
                # 정확히 일치
                if llm_name_clean in candidate_names:
                    return llm_name_clean
                
                # 대소문자 무시하고 비교
                llm_name_lower = llm_name_clean.lower()
                for cand_name in candidate_names:
                    if cand_name.lower() == llm_name_lower:
                        return cand_name
                
                # 부분 일치 (포함 관계)
                for cand_name in candidate_names:
                    if llm_name_lower in cand_name.lower() or cand_name.lower() in llm_name_lower:
                        return cand_name
                
                return None
            
            # 점수순 정렬 (LLM이 매긴 점수 기준)
            sorted_evals = sorted(review_data.evaluations, key=lambda x: x.match_score, reverse=True)
            
            if not sorted_evals:
                raise LLMServiceError("적절한 후보자를 찾을 수 없습니다.")

            best_match = sorted_evals[0]
            matched_name = find_best_match_name(best_match.name, candidate_names)
            best_employee = cand_map.get(matched_name) if matched_name else None
            
            if not best_employee:
                # LLM이 환각으로 없는 이름을 만든 경우
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"LLM이 반환한 이름 '{best_match.name}'이 후보자 목록에 없습니다. "
                    f"사용 가능한 이름: {candidate_names}. "
                    f"첫 번째 후보자로 fallback합니다."
                )
                best_employee = candidates[0]

            # best_candidate_name도 확인 (더 정확할 수 있음)
            if review_data.best_candidate_name:
                matched_best_name = find_best_match_name(review_data.best_candidate_name, candidate_names)
                if matched_best_name and matched_best_name != matched_name:
                    # best_candidate_name이 더 정확한 경우 사용
                    best_employee = cand_map.get(matched_best_name, best_employee)

            # 2~3순위 추출
            other_candidates = []
            for eval_item in sorted_evals[1:4]: # 2,3,4위
                matched_name = find_best_match_name(eval_item.name, candidate_names)
                emp = cand_map.get(matched_name) if matched_name else None
                if emp:
                    # 점수가 너무 낮으면(예: 30점 미만) 제외하는 로직 추가 가능
                    if eval_item.match_score > 30: 
                        other_candidates.append(emp)
                else:
                    # 이름 매칭 실패 시 로깅
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"후보자 이름 매칭 실패: '{eval_item.name}' -> 사용 가능한 이름: {candidate_names}"
                    )

            # 최종 결과 반환 (LLM의 추론 이유를 포함)
            return AssignmentRecommendation(
                primary=best_employee,
                candidates=other_candidates,
                reasoning=f"[{review_data.document_summary}] \n핵심요건: {', '.join(review_data.key_requirements)}\n선정이유: {best_match.reasoning}"
            )

        except httpx.HTTPStatusError as e:
            raise LLMAPIError(f"LLM API HTTP 오류 ({e.response.status_code}): {str(e)}")
        except httpx.TimeoutException as e:
            raise LLMAPIError(f"LLM API 타임아웃: {str(e)}")
        except httpx.RequestError as e:
            raise LLMAPIError(f"LLM API 요청 실패: {str(e)}")
        except (LLMResponseParseError, LLMAPIError, LLMServiceError):
            raise
        except Exception as e:
            # 실무에서는 로그를 남기고, Rule-base(단순 키워드 매칭)로 Fallback 처리하는 것이 안전함
            raise LLMServiceError(f"AI 분석 중 오류 발생: {str(e)}")

    def generate_completion(
        self,
        messages: List[dict],
        temperature: float = 0.1,
        max_tokens: int = 1000
    ) -> dict:
        """LLM completion 생성 (동기 버전)

        Args:
            messages: 메시지 리스트 [{"role": "system", "content": "..."}, ...]
            temperature: 온도 (0.0~1.0)
            max_tokens: 최대 토큰 수

        Returns:
            응답 딕셔너리 {"content": "..."}
        """
        import httpx

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                headers = {
                    "Content-Type": "application/json",
                }
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                response = client.post(
                    self.api_url,
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()

                if "choices" not in result or len(result["choices"]) == 0:
                    raise LLMAPIError("LLM API 응답에 choices가 없습니다.")

                content = result["choices"][0]["message"]["content"].strip()

                return {"content": content}

        except httpx.HTTPStatusError as e:
            raise LLMAPIError(f"LLM API HTTP 오류 ({e.response.status_code}): {str(e)}")
        except httpx.TimeoutException as e:
            raise LLMAPIError(f"LLM API 타임아웃: {str(e)}")
        except httpx.RequestError as e:
            raise LLMAPIError(f"LLM API 요청 실패: {str(e)}")
        except Exception as e:
            raise LLMServiceError(f"LLM 생성 중 오류 발생: {str(e)}")


# 싱글톤 인스턴스
_llm_service = None


def get_llm_service() -> LLMService:
    """LLM 서비스 싱글톤 인스턴스 반환"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service