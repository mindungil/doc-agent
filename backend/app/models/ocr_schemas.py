"""OCR 관련 데이터 모델"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class PageContent(BaseModel):
    """페이지별 OCR 결과"""
    page_number: int = Field(..., description="페이지 번호")
    text: str = Field(..., description="추출된 텍스트")
    confidence: Optional[float] = Field(None, description="신뢰도 (0-1)")
    blocks: Optional[List[Dict[str, Any]]] = Field(None, description="텍스트 블록 정보")


class OCRResult(BaseModel):
    """DeepSeek-OCR API 응답 모델"""
    raw_text: str = Field(..., description="전체 추출 텍스트")
    pages: Optional[List[PageContent]] = Field(None, description="페이지별 구조화 데이터")
    confidence: Optional[float] = Field(None, description="전체 OCR 신뢰도")
    metadata: Optional[Dict[str, Any]] = Field(None, description="추가 메타데이터")


class Correction(BaseModel):
    """OCR 보정 항목"""
    original: str = Field(..., description="원본 텍스트")
    corrected: str = Field(..., description="수정된 텍스트")
    reason: str = Field(..., description="수정 이유")


class CorrectedText(BaseModel):
    """LLM OCR 보정 결과"""
    corrected_text: str = Field(..., description="보정된 전체 텍스트")
    corrections: List[Correction] = Field(default_factory=list, description="보정 내역")


class RecipientInfo(BaseModel):
    """수신자 정보"""
    has_recipient: bool = Field(..., description="수신자 정보 존재 여부")
    is_specific: bool = Field(False, description="특정 수신자 여부 (True=특정, False=포괄)")
    recipient_text: str = Field("", description="추출된 수신자 텍스트")
    context: str = Field("", description="수신자 주변 문맥")


class DepartmentInfo(BaseModel):
    """부서 정보"""
    dept1: Optional[str] = Field(None, description="1차 부서")
    dept2: Optional[str] = Field(None, description="2차 부서")
    dept3: Optional[str] = Field(None, description="3차 부서")
    relevance_score: Optional[float] = Field(None, description="관련도 점수")


class SelectedDepartment(BaseModel):
    """LLM이 선택한 부서"""
    dept1: str
    dept2: Optional[str] = None
    dept3: Optional[str] = None
    relevance_score: float = Field(..., ge=0, le=100, description="관련도 점수 (0-100)")
    reasoning: str = Field("", description="선택 이유")


class DepartmentFilterResult(BaseModel):
    """부서 필터링 결과"""
    selected_departments: List[SelectedDepartment] = Field(..., description="선택된 부서 목록")
    reasoning: str = Field(..., description="전체 선택 이유")


class DocumentSummary(BaseModel):
    """문서 요약 결과"""
    keywords: List[str] = Field(..., description="핵심 키워드 (5-10개)")
    summary: str = Field(..., description="문서 핵심 요약 (2-3문장)")
    required_expertise: List[str] = Field(default_factory=list, description="필요 역량")


class RankedCandidate(BaseModel):
    """최종 순위가 매겨진 후보자"""
    name: str
    rank: str
    dept1: Optional[str] = None
    dept2: Optional[str] = None
    dept3: Optional[str] = None
    tasks: Optional[str] = None
    phone: Optional[str] = None

    # 점수 정보
    rag_score: Optional[float] = Field(None, description="RAG 유사도 점수")
    llm_score: Optional[float] = Field(None, description="LLM 평가 점수")
    final_score: float = Field(..., description="최종 점수")

    # 평가 정보
    reasoning: str = Field("", description="선정 이유")
