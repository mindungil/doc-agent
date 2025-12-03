"""문서 요약 및 최종 랭킹 서비스"""
import json
import logging
import httpx
from typing import List

from app.config import settings
from app.models.ocr_schemas import DocumentSummary, RankedCandidate
from app.models.schemas import EmployeeCandidate
from app.services.rag import rag_service
from app.exceptions import LLMServiceError

logger = logging.getLogger(__name__)


class DocumentSummarizerService:
    """문서 요약 및 후보자 랭킹 서비스"""

    def __init__(self):
        self.llm_api_url = settings.llm_api_url
        self.llm_api_key = settings.llm_api_key
        self.llm_model = settings.llm_model

    async def summarize_document_keywords(
        self,
        text: str,
        title: str = ""
    ) -> DocumentSummary:
        """
        LLM으로 문서 키워드 및 요약 추출

        Args:
            text: 문서 텍스트
            title: 문서 제목

        Returns:
            DocumentSummary: 문서 요약 정보

        Raises:
            LLMServiceError: LLM 처리 실패
        """
        system_prompt = """당신은 문서의 핵심 키워드와 요약을 추출하는 전문가입니다.

다음을 추출하세요:
1. **키워드**: 문서의 핵심 주제를 나타내는 5-10개의 키워드
2. **요약**: 문서의 핵심 내용을 2-3문장으로 요약
3. **필요 역량**: 이 문서를 처리하는데 필요한 전문성/역량

**키워드 선정 기준:**
- 문서의 주제와 직접 관련된 명사 우선
- 업무 분야, 기술, 주요 개념 포함
- 너무 일반적인 단어는 제외"""

        user_prompt = f"""[문서 제목]
{title}

[문서 내용]
{text[:2500]}

다음 JSON 형식으로 응답하세요:
{{
  "keywords": ["키워드1", "키워드2", "키워드3", ...],
  "summary": "문서 핵심 요약 (2-3문장)",
  "required_expertise": ["필요 역량1", "필요 역량2", ...]
}}

**주의:** JSON 형식만 반환하고 다른 설명은 포함하지 마세요."""

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
                    "temperature": 0.2,
                }

                logger.info("Calling LLM for document summarization")
                response = await client.post(
                    self.llm_api_url,
                    json=payload,
                    headers=headers
                )

                response.raise_for_status()
                result = response.json()

                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                # JSON 파싱
                summary = self._parse_summary_response(content, text, title)

                logger.info(f"Document summarized: {len(summary.keywords)} keywords extracted")
                return summary

        except Exception as e:
            logger.error(f"Document summarization failed: {str(e)}")
            raise LLMServiceError(f"문서 요약 실패: {str(e)}")

    def _parse_summary_response(
        self,
        response_content: str,
        fallback_text: str,
        fallback_title: str
    ) -> DocumentSummary:
        """
        LLM 응답 파싱

        Args:
            response_content: LLM 응답
            fallback_text: 파싱 실패 시 사용할 원본 텍스트
            fallback_title: 파싱 실패 시 사용할 제목

        Returns:
            DocumentSummary: 파싱 결과
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

            return DocumentSummary(
                keywords=data.get('keywords', [fallback_title]),
                summary=data.get('summary', fallback_text[:200]),
                required_expertise=data.get('required_expertise', [])
            )

        except Exception as e:
            logger.warning(f"Failed to parse summary response: {str(e)}")
            return DocumentSummary(
                keywords=[fallback_title] if fallback_title else ["문서"],
                summary=fallback_text[:200],
                required_expertise=[]
            )

    async def rank_candidates(
        self,
        document_summary: DocumentSummary,
        filtered_candidates: List[EmployeeCandidate],
        document_text: str = "",
        use_hybrid: bool = True
    ) -> List[RankedCandidate]:
        """
        필터링된 후보자들의 최종 순위 결정

        하이브리드 방식:
        1. RAG로 키워드 기반 유사도 점수 계산
        2. LLM으로 세부 평가 및 최종 순위 결정

        Args:
            document_summary: 문서 요약
            filtered_candidates: 필터링된 후보자 목록
            document_text: 문서 원문 (선택)
            use_hybrid: 하이브리드 방식 사용 여부

        Returns:
            List[RankedCandidate]: 순위가 매겨진 후보자 목록
        """
        if not filtered_candidates:
            logger.warning("No candidates to rank")
            return []

        try:
            if use_hybrid:
                # 하이브리드 방식: RAG + LLM
                ranked = await self._hybrid_ranking(
                    document_summary,
                    filtered_candidates,
                    document_text
                )
            else:
                # LLM만 사용
                ranked = await self._llm_only_ranking(
                    document_summary,
                    filtered_candidates
                )

            logger.info(f"Ranked {len(ranked)} candidates")
            return ranked

        except Exception as e:
            logger.error(f"Candidate ranking failed: {str(e)}")
            # 실패 시 원본 순서로 반환
            return self._fallback_ranking(filtered_candidates)

    async def _hybrid_ranking(
        self,
        summary: DocumentSummary,
        candidates: List[EmployeeCandidate],
        document_text: str
    ) -> List[RankedCandidate]:
        """
        하이브리드 랭킹: RAG 유사도 + LLM 평가

        Args:
            summary: 문서 요약
            candidates: 후보자 목록
            document_text: 문서 텍스트

        Returns:
            List[RankedCandidate]: 랭킹 결과
        """
        # 1. RAG로 키워드 기반 유사도 점수 재계산
        query_text = f"{' '.join(summary.keywords)}\n{summary.summary}"

        # 후보자들의 RAG 점수 업데이트
        rag_candidates = await rag_service.search_similar_employees(
            document_text=query_text,
            top_k=len(candidates) * 2  # 충분히 많이 검색
        )

        # 기존 후보자와 RAG 점수 매칭
        candidate_rag_scores = {}
        for rag_cand in rag_candidates:
            candidate_rag_scores[rag_cand.name] = rag_cand.score or 0.0

        # 2. LLM으로 세부 평가
        llm_evaluation = await self._call_llm_for_ranking(
            summary,
            candidates,
            document_text
        )

        # 3. 하이브리드 점수 계산
        ranked = []
        for candidate in candidates:
            rag_score = candidate_rag_scores.get(candidate.name, 0.0)
            llm_eval = llm_evaluation.get(candidate.name, {})
            llm_score = llm_eval.get('score', 50.0)

            # 가중 평균 (RAG 40%, LLM 60%)
            final_score = (rag_score * 100 * 0.4) + (llm_score * 0.6)

            ranked.append(RankedCandidate(
                name=candidate.name,
                rank=candidate.rank,
                dept1=candidate.dept1,
                dept2=candidate.dept2,
                dept3=candidate.dept3,
                tasks=candidate.tasks,
                phone=candidate.phone,
                rag_score=rag_score,
                llm_score=llm_score,
                final_score=final_score,
                reasoning=llm_eval.get('reasoning', '')
            ))

        # 최종 점수로 정렬
        ranked.sort(key=lambda x: x.final_score, reverse=True)

        return ranked

    async def _llm_only_ranking(
        self,
        summary: DocumentSummary,
        candidates: List[EmployeeCandidate]
    ) -> List[RankedCandidate]:
        """
        LLM만 사용한 랭킹

        Args:
            summary: 문서 요약
            candidates: 후보자 목록

        Returns:
            List[RankedCandidate]: 랭킹 결과
        """
        llm_evaluation = await self._call_llm_for_ranking(summary, candidates, "")

        ranked = []
        for candidate in candidates:
            llm_eval = llm_evaluation.get(candidate.name, {})
            llm_score = llm_eval.get('score', 50.0)

            ranked.append(RankedCandidate(
                name=candidate.name,
                rank=candidate.rank,
                dept1=candidate.dept1,
                dept2=candidate.dept2,
                dept3=candidate.dept3,
                tasks=candidate.tasks,
                phone=candidate.phone,
                rag_score=None,
                llm_score=llm_score,
                final_score=llm_score,
                reasoning=llm_eval.get('reasoning', '')
            ))

        ranked.sort(key=lambda x: x.final_score, reverse=True)

        return ranked

    async def _call_llm_for_ranking(
        self,
        summary: DocumentSummary,
        candidates: List[EmployeeCandidate],
        document_text: str = ""
    ) -> dict:
        """
        LLM 호출하여 후보자 평가

        Args:
            summary: 문서 요약
            candidates: 후보자 목록
            document_text: 문서 원문 (선택)

        Returns:
            dict: {후보자명: {'score': 점수, 'reasoning': 이유}}
        """
        # 후보자 정보 포맷팅
        candidates_text = self._format_candidates_for_llm(candidates)

        system_prompt = """당신은 문서 내용과 직원의 업무 역량을 분석하여 최적의 담당자를 선정하는 전문가입니다.

각 후보자를 평가하여 0-100점 점수를 부여하세요.

**평가 기준:**
1. 업무 적합성 (40점): 직원의 담당 업무가 문서 내용과 얼마나 관련되는가
2. 전문성 (30점): 필요한 역량을 보유하고 있는가
3. 부서 관련성 (30점): 소속 부서가 문서 주제와 관련되는가

**점수 기준:**
- 90-100: 최적의 담당자, 직접적으로 관련된 업무 수행
- 70-89: 적합한 담당자, 관련 업무 경험 있음
- 50-69: 가능한 담당자, 부분적 관련성
- 50 미만: 부적합"""

        user_prompt = f"""[문서 정보]
키워드: {', '.join(summary.keywords)}
요약: {summary.summary}
필요 역량: {', '.join(summary.required_expertise)}

[후보자 목록]
{candidates_text}

각 후보자를 평가하고 다음 JSON 형식으로 응답하세요:

{{
  "evaluations": [
    {{
      "name": "후보자 이름",
      "score": 85,
      "reasoning": "평가 이유 (2-3문장)"
    }},
    ...
  ]
}}

**주의:** JSON 형식만 반환하고 다른 설명은 포함하지 마세요."""

        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
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

                logger.info("Calling LLM for candidate ranking")
                response = await client.post(
                    self.llm_api_url,
                    json=payload,
                    headers=headers
                )

                response.raise_for_status()
                result = response.json()

                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                # JSON 파싱
                evaluations = self._parse_ranking_response(content)

                return evaluations

        except Exception as e:
            logger.error(f"LLM ranking call failed: {str(e)}")
            return {}

    def _format_candidates_for_llm(self, candidates: List[EmployeeCandidate]) -> str:
        """후보자 정보를 LLM용 텍스트로 포맷팅"""
        lines = []
        for idx, cand in enumerate(candidates, 1):
            dept_parts = [cand.dept1]
            if cand.dept2:
                dept_parts.append(cand.dept2)
            if cand.dept3:
                dept_parts.append(cand.dept3)
            dept_str = ' > '.join(dept_parts)

            lines.append(f"{idx}. {cand.name} ({cand.rank})")
            lines.append(f"   부서: {dept_str}")
            lines.append(f"   담당업무: {cand.tasks[:200]}")
            lines.append("")

        return '\n'.join(lines)

    def _parse_ranking_response(self, response_content: str) -> dict:
        """LLM 랭킹 응답 파싱"""
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

            # {이름: {score, reasoning}} 형식으로 변환
            result = {}
            for eval_item in data.get('evaluations', []):
                name = eval_item.get('name', '')
                result[name] = {
                    'score': eval_item.get('score', 50),
                    'reasoning': eval_item.get('reasoning', '')
                }

            return result

        except Exception as e:
            logger.warning(f"Failed to parse ranking response: {str(e)}")
            return {}

    def _fallback_ranking(self, candidates: List[EmployeeCandidate]) -> List[RankedCandidate]:
        """
        Fallback 랭킹: 기존 RAG 점수 사용

        Args:
            candidates: 후보자 목록

        Returns:
            List[RankedCandidate]: 랭킹 결과
        """
        ranked = []
        for candidate in candidates:
            ranked.append(RankedCandidate(
                name=candidate.name,
                rank=candidate.rank,
                dept1=candidate.dept1,
                dept2=candidate.dept2,
                dept3=candidate.dept3,
                tasks=candidate.tasks,
                phone=candidate.phone,
                rag_score=candidate.score,
                llm_score=None,
                final_score=candidate.score * 100 if candidate.score else 50.0,
                reasoning="자동 평가 실패로 RAG 점수 사용"
            ))

        ranked.sort(key=lambda x: x.final_score, reverse=True)

        return ranked


# 싱글톤 인스턴스
document_summarizer_service = DocumentSummarizerService()
