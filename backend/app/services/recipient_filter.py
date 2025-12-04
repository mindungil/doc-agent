"""수신자 필터링 서비스"""
import json
import re
import logging
import httpx
from typing import List, Optional

from app.config import settings
from app.models.ocr_schemas import RecipientInfo
from app.models.schemas import EmployeeCandidate
from app.services.rag import rag_service
from app.exceptions import LLMServiceError

logger = logging.getLogger(__name__)


class RecipientFilterService:
    """문서 수신자 필터링 서비스"""

    def __init__(self):
        self.llm_api_url = settings.llm_api_url
        self.llm_api_key = settings.llm_api_key
        self.llm_model = settings.llm_model

        # 수신자 관련 키워드
        self.recipient_keywords = ['수신', '수신자', '수신처', '받는사람']

    async def extract_recipient_info(self, text: str) -> RecipientInfo:
        """
        문서에서 수신자 정보 추출 및 분류

        Args:
            text: 문서 텍스트

        Returns:
            RecipientInfo: 수신자 정보
        """
        # 1. 수신자 키워드 탐지
        has_recipient = self._detect_recipient_keyword(text)

        if not has_recipient:
            logger.info("No recipient keyword found")
            return RecipientInfo(
                has_recipient=False,
                is_specific=False,
                recipient_text="",
                context=""
            )

        # 2. 수신자 주변 문맥 추출
        context = self._extract_recipient_context(text)

        # 3. LLM으로 특정/포괄 분류
        try:
            classification = await self._classify_recipient_type(context)
            return classification
        except Exception as e:
            logger.error(f"Failed to classify recipient: {str(e)}")
            # 분류 실패 시 보수적으로 포괄적 대상으로 처리
            return RecipientInfo(
                has_recipient=True,
                is_specific=False,
                recipient_text=context[:200],
                context=context
            )

    def _detect_recipient_keyword(self, text: str) -> bool:
        """
        수신자 키워드 탐지

        Args:
            text: 문서 텍스트

        Returns:
            bool: 키워드 존재 여부
        """
        text_normalized = text.replace(' ', '').replace('\n', '')

        for keyword in self.recipient_keywords:
            if keyword in text_normalized:
                logger.info(f"Recipient keyword found: {keyword}")
                return True

        return False

    def _extract_recipient_context(self, text: str, window_size: int = 150) -> str:
        """
        수신자 키워드 주변 문맥 추출

        Args:
            text: 문서 텍스트
            window_size: 추출할 문자 수 (전후)

        Returns:
            str: 추출된 문맥
        """
        # 수신자 키워드를 포함한 라인 찾기
        lines = text.split('\n')
        context_lines = []

        for i, line in enumerate(lines):
            if any(keyword in line for keyword in self.recipient_keywords):
                # 해당 라인과 전후 라인 포함
                start = max(0, i - 2)
                end = min(len(lines), i + 5)
                context_lines.extend(lines[start:end])

        if context_lines:
            context = '\n'.join(context_lines)
        else:
            # 키워드 위치 기반 추출
            for keyword in self.recipient_keywords:
                pos = text.find(keyword)
                if pos != -1:
                    start = max(0, pos - window_size)
                    end = min(len(text), pos + window_size)
                    context = text[start:end]
                    break
            else:
                context = text[:500]  # fallback

        return context.strip()

    async def _classify_recipient_type(self, context: str) -> RecipientInfo:
        """
        LLM으로 수신자가 특정 대상인지 포괄적 대상인지 분류

        Args:
            context: 수신자 주변 문맥

        Returns:
            RecipientInfo: 분류 결과
        """
        system_prompt = """당신은 문서의 수신자 정보를 분석하는 전문가입니다.
문서의 수신자가 **특정 대상**인지 **포괄적 대상**인지 판단하세요.

**특정 대상 예시:**
- "수신: 정책기획과장"
- "수신자: 인사팀"
- "수신: 총무부 김철수"
- "받는사람: 재무담당자"
- "수신 전북특별자치도지사(행정정보과장) (경유)" → 행정정보과장이 명시되어 있으므로 특정 대상
- "수신: 행정정보과 (경유)" → 행정정보과가 명시되어 있으므로 특정 대상

**포괄적 대상 예시:**
- "수신: 전 부서"
- "수신: 관계 부서"
- "수신자: 전 직원"
- "수신: 해당 부서"

**판단 기준:**
- 구체적인 부서명, 직책명, 이름이 있으면 → 특정 대상 (경유 표현이 있어도 무시)
- "전", "관계", "해당", "각" 등 포괄적 표현이 있으면 → 포괄적 대상
- **(경유)**, **(참조)** 등의 표현은 무시하고 실제 수신 부서/직책명을 기준으로 판단"""

        user_prompt = f"""[문서 수신자 부분]
{context}

다음 JSON 형식으로 응답하세요:
{{
  "is_specific": true 또는 false,
  "recipient_text": "추출된 수신자 텍스트",
  "reasoning": "판단 이유 (1-2문장)"
}}

**주의:** JSON 형식만 반환하고 다른 설명은 포함하지 마세요."""

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
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

                logger.info("Calling LLM for recipient classification")
                response = await client.post(
                    self.llm_api_url,
                    json=payload,
                    headers=headers
                )

                response.raise_for_status()
                result = response.json()

                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                # JSON 파싱
                classification = self._parse_classification_response(content, context)

                logger.info(f"Recipient classification: is_specific={classification.is_specific}")
                return classification

        except Exception as e:
            logger.error(f"Recipient classification failed: {str(e)}")
            raise LLMServiceError(f"수신자 분류 실패: {str(e)}")

    def _parse_classification_response(
        self,
        response_content: str,
        fallback_context: str
    ) -> RecipientInfo:
        """
        LLM 응답 파싱

        Args:
            response_content: LLM 응답
            fallback_context: 파싱 실패 시 사용할 문맥

        Returns:
            RecipientInfo: 파싱 결과
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

            return RecipientInfo(
                has_recipient=True,
                is_specific=data.get('is_specific', False),
                recipient_text=data.get('recipient_text', '')[:500],
                context=fallback_context
            )

        except Exception as e:
            logger.warning(f"Failed to parse classification response: {str(e)}")
            return RecipientInfo(
                has_recipient=True,
                is_specific=False,
                recipient_text=response_content[:200],
                context=fallback_context
            )

    async def filter_by_recipient(
        self,
        recipient_text: str,
        top_k: int = 3
    ) -> List[EmployeeCandidate]:
        """
        RAG로 수신자 관련 직원 TOP K 검색

        Args:
            recipient_text: 수신자 텍스트
            top_k: 반환할 후보 수

        Returns:
            List[EmployeeCandidate]: 필터링된 직원 목록
        """
        try:
            logger.info(f"Filtering by recipient: {recipient_text[:100]}")

            # RAG 검색
            candidates = await rag_service.search_similar_employees(
                document_text=recipient_text,
                top_k=top_k
            )

            logger.info(f"Found {len(candidates)} candidates by recipient filter")
            return candidates

        except Exception as e:
            logger.error(f"Recipient filtering failed: {str(e)}")
            return []


# 싱글톤 인스턴스
recipient_filter_service = RecipientFilterService()
