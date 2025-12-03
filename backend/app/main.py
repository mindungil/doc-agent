from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from app.routers import documents, auth
from app.database.db import init_db
from app.config import settings
from app.exceptions import (
    DocumentProcessingError, VectorSearchError, LLMServiceError
)
import os
import logging

# 루트 로거를 INFO로 설정
logging.basicConfig(level=logging.INFO)

# SQLAlchemy 로그 레벨을 WARNING으로 설정 (INFO 로그 제거)
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

app = FastAPI(
    title="문서배부 자동화 POC",
    description="전북도청 문서 배부 자동화 프로토타입",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth.router)
app.include_router(documents.router)

# 업로드 디렉터리 생성
os.makedirs(settings.upload_dir, exist_ok=True)

# 정적 파일 서빙 (업로드된 파일)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.exception_handler(DocumentProcessingError)
async def document_processing_exception_handler(request, exc):
    """문서 처리 에러 핸들러"""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)}
    )


@app.exception_handler(VectorSearchError)
async def vector_search_exception_handler(request, exc):
    """벡터 검색 에러 핸들러"""
    return JSONResponse(
        status_code=503,
        content={"detail": f"벡터 검색 서비스 오류: {str(exc)}"}
    )


@app.exception_handler(LLMServiceError)
async def llm_service_exception_handler(request, exc):
    """LLM 서비스 에러 핸들러"""
    return JSONResponse(
        status_code=503,
        content={"detail": f"LLM 서비스 오류: {str(exc)}"}
    )


@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 초기화"""
    # 환경 변수 검증
    try:
        settings.validate_settings()
    except ValueError as e:
        import sys
        print(f"환경 변수 검증 실패: {e}", file=sys.stderr)
        sys.exit(1)
    
    # DB 초기화
    await init_db()


@app.get("/")
async def root():
    """API 헬스 체크"""
    return {"message": "문서배부 자동화 POC API", "status": "ok"}


@app.get("/health")
async def health():
    """헬스 체크"""
    return {"status": "healthy"}
