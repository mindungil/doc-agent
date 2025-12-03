"""데이터베이스 마이그레이션 스크립트"""
import sqlite3
import sys

def migrate_database(db_path: str = "/app/data/documents.db"):
    """새로운 컬럼들을 기존 데이터베이스에 추가"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 기존 컬럼 확인
    cursor.execute("PRAGMA table_info(documents)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    print(f"기존 컬럼: {existing_columns}")

    # 추가할 컬럼 정의
    new_columns = [
        ("ocr_raw_text", "TEXT"),
        ("ocr_confidence", "REAL"),
        ("corrected_text", "TEXT"),
        ("recipient_info", "TEXT"),
        ("filtered_departments", "TEXT"),
        ("document_keywords", "TEXT"),
        ("ocr_processed_at", "TIMESTAMP"),
        ("correction_processed_at", "TIMESTAMP"),
        ("filtering_processed_at", "TIMESTAMP"),
    ]

    added_count = 0

    for column_name, column_type in new_columns:
        if column_name not in existing_columns:
            try:
                sql = f"ALTER TABLE documents ADD COLUMN {column_name} {column_type}"
                print(f"실행: {sql}")
                cursor.execute(sql)
                conn.commit()
                print(f"✓ {column_name} 컬럼 추가 완료")
                added_count += 1
            except Exception as e:
                print(f"✗ {column_name} 컬럼 추가 실패: {e}")
        else:
            print(f"- {column_name} 컬럼은 이미 존재합니다")

    conn.close()

    print(f"\n마이그레이션 완료: {added_count}개 컬럼 추가됨")
    return True

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/app/data/documents.db"
    migrate_database(db_path)
