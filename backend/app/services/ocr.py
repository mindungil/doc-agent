"""DeepSeek-OCR 통합 서비스"""
import os
import httpx
import logging
from typing import Optional
from pathlib import Path

from app.config import settings
from app.models.ocr_schemas import OCRResult, PageContent
from app.exceptions import TextExtractionError

logger = logging.getLogger(__name__)


class OCRService:
    """DeepSeek-OCR API 클라이언트"""

    def __init__(self):
        self.base_url = settings.deepseek_ocr_url.rstrip('/')
        self.api_key = settings.deepseek_ocr_api_key
        self.timeout = settings.deepseek_ocr_timeout

    async def parse_document_with_ocr(
        self,
        file_path: str,
        filename: str
    ) -> OCRResult:
        """
        DeepSeek-OCR API를 호출하여 문서 파싱

        Args:
            file_path: 파일 경로
            filename: 파일명

        Returns:
            OCRResult: OCR 결과

        Raises:
            TextExtractionError: OCR 처리 실패
        """
        try:
            file_ext = Path(filename).suffix.lower()

            # 파일 타입에 따라 적절한 엔드포인트 선택
            if file_ext == '.pdf':
                endpoint = '/text/pdf'
            elif file_ext in ['.hwp', '.hwpx']:
                endpoint = '/text/hwp'
            elif file_ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']:
                endpoint = '/ocr'
            else:
                # 지원하지 않는 형식은 일반 OCR 시도
                logger.warning(f"Unsupported file type {file_ext}, trying general OCR")
                endpoint = '/ocr'

            # OCR API 호출
            result = await self._call_ocr_api(file_path, endpoint)

            return result

        except Exception as e:
            logger.error(f"OCR processing failed for {filename}: {str(e)}")
            raise TextExtractionError(f"OCR 처리 실패: {str(e)}")

    async def _call_ocr_api(
        self,
        file_path: str,
        endpoint: str
    ) -> OCRResult:
        """
        OCR API 호출 (내부 메서드)

        Args:
            file_path: 파일 경로
            endpoint: API 엔드포인트

        Returns:
            OCRResult: OCR 결과
        """
        url = f"{self.base_url}{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 파일 읽기
                with open(file_path, 'rb') as f:
                    files = {'file': (os.path.basename(file_path), f, 'application/octet-stream')}

                    # 헤더 구성
                    headers = {}
                    if self.api_key:
                        headers['Authorization'] = f'Bearer {self.api_key}'

                    # API 호출
                    logger.info(f"Calling OCR API: {url}")
                    response = await client.post(
                        url,
                        files=files,
                        headers=headers
                    )

                    response.raise_for_status()
                    result_data = response.json()

                    logger.info(f"OCR API response received: {len(str(result_data))} bytes")

                    # 응답 파싱
                    return self._parse_ocr_response(result_data)

        except httpx.TimeoutException:
            raise TextExtractionError(f"OCR API 타임아웃 ({self.timeout}초)")
        except httpx.HTTPStatusError as e:
            raise TextExtractionError(f"OCR API HTTP 오류: {e.response.status_code}")
        except Exception as e:
            raise TextExtractionError(f"OCR API 호출 실패: {str(e)}")

    def _parse_ocr_response(self, response_data: dict) -> OCRResult:
        """
        DeepSeek-OCR API 응답을 OCRResult로 변환

        실제 응답 형식:
        {
          "text": "전체 텍스트",
          "metadata": {"source": "파일명", "type": "pdf_ocr", "model": "...", "total_pages": N},
          "pages": [{"page": 1, "text": "페이지 텍스트"}, ...]
        }
        """
        try:
            if 'text' in response_data:
                raw_text = response_data['text']
                metadata = response_data.get('metadata', {})
                pages_data = response_data.get('pages', [])

                # 페이지 데이터 파싱
                pages = []
                if pages_data:
                    for page_data in pages_data:
                        if isinstance(page_data, dict):
                            pages.append(PageContent(
                                page_number=page_data.get('page', page_data.get('page_number', 1)),
                                text=page_data.get('text', ''),
                                confidence=page_data.get('confidence'),
                                blocks=page_data.get('blocks')
                            ))
                        elif isinstance(page_data, str):
                            pages.append(PageContent(
                                page_number=len(pages) + 1,
                                text=page_data,
                                confidence=None,
                                blocks=None
                            ))

                # confidence는 metadata나 전체 응답에서 추출
                confidence = response_data.get('confidence') or metadata.get('confidence')

                return OCRResult(
                    raw_text=raw_text,
                    pages=pages if pages else None,
                    confidence=confidence,
                    metadata=metadata if metadata else None
                )

            # result 필드가 있는 경우 (재귀 처리)
            elif 'result' in response_data:
                return self._parse_ocr_response(response_data['result'])

            # 문자열인 경우
            elif isinstance(response_data, str):
                return OCRResult(
                    raw_text=response_data,
                    pages=None,
                    confidence=None,
                    metadata=None
                )

            # 알 수 없는 형식
            else:
                logger.warning(f"Unknown OCR response format: {response_data}")
                raw_text = str(response_data)
                return OCRResult(
                    raw_text=raw_text,
                    pages=None,
                    confidence=None,
                    metadata=response_data if isinstance(response_data, dict) else None
                )

        except Exception as e:
            logger.error(f"Failed to parse OCR response: {str(e)}")
            return OCRResult(
                raw_text=str(response_data),
                pages=None,
                confidence=None,
                metadata={'parse_error': str(e)}
            )

    async def check_health(self) -> dict:
        """
        OCR 서비스 상태 확인

        Returns:
            dict: 상태 정보
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/")
                response.raise_for_status()
                return {
                    "status": "healthy",
                    "url": self.base_url,
                    "response": response.json()
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "url": self.base_url,
                "error": str(e)
            }


# 싱글톤 인스턴스
ocr_service = OCRService()
