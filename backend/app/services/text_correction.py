"""LLM 기반 OCR 텍스트 보정 서비스"""
import json
import logging
import httpx
from typing import Optional

from app.config import settings
from app.models.ocr_schemas import CorrectedText, Correction
from app.exceptions import LLMServiceError

logger = logging.getLogger(__name__)


class TextCorrectionService:
    """LLM을 사용한 OCR 텍스트 보정 서비스"""

    def __init__(self):
        self.llm_api_url = settings.llm_api_url
        self.llm_api_key = settings.llm_api_key
        self.llm_model = settings.llm_model

    async def correct_ocr_text(
        self,
        raw_text: str,
        confidence: Optional[float] = None
    ) -> CorrectedText:
        """
        LLM을 사용하여 OCR 텍스트 보정

        Args:
            raw_text: OCR 원본 텍스트
            confidence: OCR 신뢰도 (0-1)

        Returns:
            CorrectedText: 보정된 텍스트 및 보정 내역

        Raises:
            LLMServiceError: LLM 처리 실패
        """
        # 텍스트가 너무 짧거나 신뢰도가 높으면 보정 스킵
        if len(raw_text.strip()) < 10:
            logger.info("Text too short, skipping correction")
            return CorrectedText(
                corrected_text=raw_text,
                corrections=[]
            )

        if confidence and confidence > 0.95:
            logger.info(f"High confidence ({confidence}), skipping correction")
            return CorrectedText(
                corrected_text=raw_text,
                corrections=[]
            )

        try:
            # LLM 호출
            corrected_data = await self._call_llm_for_correction(raw_text)
            return corrected_data

        except Exception as e:
            logger.error(f"Text correction failed: {str(e)}")
            # 보정 실패 시 원본 텍스트 반환
            return CorrectedText(
                corrected_text=raw_text,
                corrections=[
                    Correction(
                        original="전체",
                        corrected="보정 실패",
                        reason=f"LLM 보정 실패: {str(e)}"
                    )
                ]
            )

    async def _call_llm_for_correction(self, raw_text: str) -> CorrectedText:
        """
        LLM API 호출하여 텍스트 보정

        Args:
            raw_text: 원본 텍스트

        Returns:
            CorrectedText: 보정 결과
        """
        system_prompt = """당신은 OCR 텍스트 보정 전문가입니다.
다음 OCR 결과를 분석하여 오류를 수정하세요:

1. 맞춤법 오류 수정
2. 띄어쓰기 교정
3. 문맥상 이상한 부분 수정 (예: "산업통상자윈부" → "산업통상자원부")
4. 특수문자 오류 수정
5. 원본 의미 최대한 보존

**중요:**
- 과도한 수정을 피하고, 명백한 오류만 수정하세요
- 전문 용어나 기관명은 정확하게 수정하세요
- 수정 내역을 JSON 형식으로 반환하세요"""

        user_prompt = f"""[OCR 원본 텍스트]
{raw_text[:3000]}

다음 JSON 형식으로 응답하세요:
{{
  "corrected_text": "보정된 전체 텍스트",
  "corrections": [
    {{"original": "오류 부분", "corrected": "수정된 부분", "reason": "수정 이유"}},
    ...
  ]
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
                    "temperature": 0.1,
                }

                logger.info("Calling LLM for text correction")
                response = await client.post(
                    self.llm_api_url,
                    json=payload,
                    headers=headers
                )

                response.raise_for_status()
                result = response.json()

                # LLM 응답 파싱
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                # JSON 추출 및 파싱
                corrected_data = self._parse_correction_response(content, raw_text)

                logger.info(f"Text correction completed: {len(corrected_data.corrections)} corrections")
                return corrected_data

        except httpx.TimeoutException:
            raise LLMServiceError("LLM API 타임아웃")
        except httpx.HTTPStatusError as e:
            raise LLMServiceError(f"LLM API HTTP 오류: {e.response.status_code}")
        except Exception as e:
            raise LLMServiceError(f"LLM 호출 실패: {str(e)}")

    def _parse_correction_response(
        self,
        response_content: str,
        fallback_text: str
    ) -> CorrectedText:
        """
        LLM 응답에서 JSON 추출 및 파싱

        Args:
            response_content: LLM 응답 내용
            fallback_text: 파싱 실패 시 사용할 원본 텍스트

        Returns:
            CorrectedText: 파싱된 보정 결과
        """
        try:
            # JSON 블록 추출
            content = response_content.strip()

            # ```json ... ``` 형식 처리
            if '```json' in content:
                start = content.find('```json') + 7
                end = content.find('```', start)
                content = content[start:end].strip()
            elif '```' in content:
                start = content.find('```') + 3
                end = content.find('```', start)
                content = content[start:end].strip()

            # { ... } 추출
            if not content.startswith('{'):
                start = content.find('{')
                end = content.rfind('}')
                if start != -1 and end != -1:
                    content = content[start:end + 1]

            # JSON 파싱
            data = json.loads(content)

            # Pydantic 모델로 변환
            corrections = []
            for corr in data.get('corrections', []):
                corrections.append(Correction(
                    original=corr.get('original', ''),
                    corrected=corr.get('corrected', ''),
                    reason=corr.get('reason', '')
                ))

            return CorrectedText(
                corrected_text=data.get('corrected_text', fallback_text),
                corrections=corrections
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {str(e)}, using raw response")
            # JSON 파싱 실패 시 응답 내용을 그대로 사용
            return CorrectedText(
                corrected_text=response_content if len(response_content) > 10 else fallback_text,
                corrections=[]
            )
        except Exception as e:
            logger.error(f"Failed to parse correction response: {str(e)}")
            return CorrectedText(
                corrected_text=fallback_text,
                corrections=[]
            )


# 싱글톤 인스턴스
text_correction_service = TextCorrectionService()
