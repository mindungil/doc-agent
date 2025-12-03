from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float
from datetime import datetime
from app.config import settings

Base = declarative_base()


class DocumentModel(Base):
    """문서 메타데이터 모델"""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    status = Column(String, default="대기")
    content = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    assigned_to = Column(String, nullable=True)  # 대표 담당자 1명 (하위 호환)
    assigned_at = Column(DateTime, nullable=True)
    is_auto_assigned = Column(Boolean, default=False)
    recommendation_json = Column(Text, nullable=True)  # LLM 추천 결과를 JSON으로 저장

    # 복수 배부 대상 (신규)
    assigned_candidates = Column(Text, nullable=True)  # JSON: [{"name": "김철수", "rank": "7급", "dept1": "정책기획관", "score": 0.98}, ...]

    # OCR 관련 필드
    ocr_raw_text = Column(Text, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    corrected_text = Column(Text, nullable=True)

    # 필터링 정보 (JSON)
    recipient_info = Column(Text, nullable=True)
    filtered_departments = Column(Text, nullable=True)
    document_keywords = Column(Text, nullable=True)

    # 처리 시간 추적
    ocr_processed_at = Column(DateTime, nullable=True)
    correction_processed_at = Column(DateTime, nullable=True)
    filtering_processed_at = Column(DateTime, nullable=True)


engine = create_async_engine(settings.database_url, echo=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """데이터베이스 테이블 생성"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """데이터베이스 세션 의존성"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

