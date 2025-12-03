import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    def validate_settings(self):
        """필수 설정값 검증"""
        errors = []
        
        if not self.qdrant_url:
            errors.append("QDRANT_URL이 설정되지 않았습니다.")
        
        if not self.llm_api_url:
            errors.append("LLM_API_URL이 설정되지 않았습니다.")
        
        if errors:
            raise ValueError("환경 변수 설정 오류:\n" + "\n".join(f"  - {e}" for e in errors))
        
        return True
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: Optional[str] = os.getenv("QDRANT_API_KEY", None)
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "dept_knowledge")
    
    # LLM 설정
    llm_api_url: str = os.getenv("LLM_API_URL", "http://192.168.0.201:30010/v1/chat/completions")
    llm_api_key: Optional[str] = os.getenv("LLM_API_KEY", None)
    llm_model: str = os.getenv("LLM_MODEL", "/mnt/ssd16tb/MiniMaxAI--MiniMax-M2")
    
    # 임베딩 모델 설정
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large-instruct")

    # DeepSeek-OCR 설정
    deepseek_ocr_url: str = os.getenv("DEEPSEEK_OCR_URL", "http://220.124.155.35:30100")
    deepseek_ocr_api_key: Optional[str] = os.getenv("DEEPSEEK_OCR_API_KEY", None)
    deepseek_ocr_timeout: int = int(os.getenv("DEEPSEEK_OCR_TIMEOUT", "60"))

    # 데이터베이스 설정
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./documents.db")
    
    # 파일 업로드 설정
    upload_dir: str = os.getenv("UPLOAD_DIR", "./uploads")
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    
    # 관리자 계정 설정
    admin_id: str = os.getenv("ADMIN_ID", "admin")
    admin_password: str = os.environ["ADMIN_PASSWORD"]
    
    # 세션 설정
    session_secret_key: str = os.environ["SESSION_SECRET_KEY"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

