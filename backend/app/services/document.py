import os
from pathlib import Path
from typing import Optional
import PyPDF2
from docx import Document as DocxDocument
from app.config import settings
from app.exceptions import TextExtractionError


async def extract_text_from_file(file_path: str, filename: str) -> str:
    """파일에서 텍스트 추출 (PDF, DOCX, TXT 지원)"""
    ext = Path(filename).suffix.lower()
    text = ""
    
    try:
        if ext == ".pdf":
            with open(file_path, "rb") as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
        
        elif ext in [".docx", ".doc"]:
            doc = DocxDocument(file_path)
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
        
        elif ext == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        
        return text.strip()
    
    except PyPDF2.errors.PdfReadError as e:
        raise TextExtractionError(f"PDF 파일 읽기 실패: {str(e)}")
    except Exception as e:
        raise TextExtractionError(f"텍스트 추출 실패 ({ext}): {str(e)}")


async def save_uploaded_file(file_content: bytes, filename: str) -> str:
    """업로드된 파일 저장 및 경로 반환"""
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_dir / filename
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    return str(file_path)

