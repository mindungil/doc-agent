"""
데이터베이스에 저장된 추천 결과 확인
"""
import sys
import os
import sqlite3
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

DB_PATH = "/app/data/documents.db"

def check_recommendations():
    """저장된 추천 결과 확인"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n" + "="*80)
    print("데이터베이스 문서 목록 (최근 10개)")
    print("="*80)

    cursor.execute("""
        SELECT id, title, status, assigned_to, recommendation_json
        FROM documents
        ORDER BY id DESC
        LIMIT 10
    """)

    rows = cursor.fetchall()

    for row in rows:
        doc_id, title, status, assigned_to, rec_json = row
        print(f"\n문서 ID: {doc_id}")
        print(f"제목: {title}")
        print(f"상태: {status}")
        print(f"배정자: {assigned_to}")

        if rec_json:
            try:
                rec_data = json.loads(rec_json)
                primary = rec_data.get("primary", {})
                print(f"추천 1순위: {primary.get('name', 'N/A')} ({primary.get('rank', 'N/A')})")
                print(f"추천 부서: {primary.get('dept1', '')} {primary.get('dept2', '')} {primary.get('dept3', '')}")

                reasoning = rec_data.get("reasoning", "")
                if reasoning:
                    print(f"추천 근거 (처음 200자): {reasoning[:200]}...")
            except Exception as e:
                print(f"추천 JSON 파싱 실패: {e}")
        else:
            print("추천 데이터 없음")

        print("-" * 80)

    # 모바일앱 관련 문서 찾기
    print("\n" + "="*80)
    print("'모바일앱' 또는 '공공앱' 포함 문서")
    print("="*80)

    cursor.execute("""
        SELECT id, title, status, assigned_to, recommendation_json
        FROM documents
        WHERE title LIKE '%모바일앱%' OR title LIKE '%공공앱%'
        ORDER BY id DESC
        LIMIT 5
    """)

    rows = cursor.fetchall()

    if not rows:
        print("해당 문서 없음")
    else:
        for row in rows:
            doc_id, title, status, assigned_to, rec_json = row
            print(f"\n📄 문서 ID: {doc_id}")
            print(f"제목: {title}")
            print(f"상태: {status}")
            print(f"배정자: {assigned_to}")

            if rec_json:
                try:
                    rec_data = json.loads(rec_json)
                    primary = rec_data.get("primary", {})
                    print(f"✅ 추천 1순위: {primary.get('name', 'N/A')} ({primary.get('rank', 'N/A')})")
                    print(f"   부서: {primary.get('dept1', '')} {primary.get('dept2', '')} {primary.get('dept3', '')}")

                    reasoning = rec_data.get("reasoning", "")
                    if "노송이" in reasoning:
                        print(f"   ⭐ 근거에 '노송이' 언급됨!")
                    if reasoning:
                        print(f"   근거 (처음 300자): {reasoning[:300]}...")
                except Exception as e:
                    print(f"❌ 추천 JSON 파싱 실패: {e}")
            else:
                print("추천 데이터 없음")

            print("-" * 80)

    conn.close()


if __name__ == "__main__":
    check_recommendations()
