"""assigned_candidates 컬럼 추가 마이그레이션"""
import asyncio
from sqlalchemy import text
from app.database.db import AsyncSessionLocal


async def add_candidates_column():
    """assigned_candidates 컬럼을 documents 테이블에 추가"""
    async with AsyncSessionLocal() as db:
        try:
            # 컬럼 존재 확인
            result = await db.execute(
                text("PRAGMA table_info(documents)")
            )
            columns = result.fetchall()
            column_names = [col[1] for col in columns]

            if 'assigned_candidates' in column_names:
                print("✅ assigned_candidates 컬럼이 이미 존재합니다.")
                return

            # 컬럼 추가
            await db.execute(
                text("ALTER TABLE documents ADD COLUMN assigned_candidates TEXT")
            )
            await db.commit()
            print("✅ assigned_candidates 컬럼이 추가되었습니다.")

        except Exception as e:
            print(f"❌ 마이그레이션 실패: {str(e)}")
            await db.rollback()


if __name__ == "__main__":
    asyncio.run(add_candidates_column())
