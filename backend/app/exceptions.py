"""커스텀 예외 클래스"""


class DocumentProcessingError(Exception):
    """문서 처리 관련 에러"""
    pass


class TextExtractionError(DocumentProcessingError):
    """텍스트 추출 실패"""
    pass


class VectorSearchError(Exception):
    """벡터 검색 관련 에러"""
    pass


class QdrantConnectionError(VectorSearchError):
    """Qdrant 연결 실패"""
    pass


class LLMServiceError(Exception):
    """LLM 서비스 관련 에러"""
    pass


class LLMAPIError(LLMServiceError):
    """LLM API 호출 실패"""
    pass


class LLMResponseParseError(LLMServiceError):
    """LLM 응답 파싱 실패"""
    pass

