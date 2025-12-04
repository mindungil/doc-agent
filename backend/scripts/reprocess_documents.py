#!/usr/bin/env python3
"""
멈춰있는 문서들을 재처리하는 스크립트
"""
import asyncio
import sys
import os

# 프로젝트 루트를 Python path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import select
from app.database.db import AsyncSessionLocal, DocumentModel
from app.routers.documents import process_document_async


async def reprocess_stuck_documents():
    """'업로드 완료' 상태의 문서들을 재처리"""
    async with AsyncSessionLocal() as db:
        # '업로드 완료' 상태의 문서 조회
        result = await db.execute(
            select(DocumentModel.id, DocumentModel.title, DocumentModel.status)
            .where(DocumentModel.status == "업로드 완료")
            .order_by(DocumentModel.id)
        )
        docs = result.all()

        if not docs:
            print("재처리할 문서가 없습니다.")
            return

        print(f"총 {len(docs)}개의 문서를 재처리합니다.")
        print("-" * 80)

        for doc in docs:
            print(f"문서 ID {doc.id}: {doc.title[:50]}... 재처리 시작")
            try:
                await process_document_async(doc.id)
                print(f"  ✓ 문서 ID {doc.id} 재처리 완료")
            except Exception as e:
                print(f"  ✗ 문서 ID {doc.id} 재처리 실패: {str(e)}")

        print("-" * 80)
        print("재처리 완료!")


if __name__ == "__main__":
    asyncio.run(reprocess_stuck_documents())
