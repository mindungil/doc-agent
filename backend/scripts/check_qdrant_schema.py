"""
Qdrant 스키마 및 데이터 구조 확인 스크립트
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from qdrant_client import QdrantClient
from app.config import settings
import json

def main():
    print("=== Qdrant 스키마 확인 ===\n")

    # Qdrant 클라이언트 연결
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )

    # 컬렉션 정보
    collection_name = settings.qdrant_collection
    print(f"컬렉션: {collection_name}")

    collection_info = client.get_collection(collection_name)
    print(f"총 문서 수: {collection_info.points_count}\n")

    # 샘플 데이터 조회 (첫 5개)
    print("=== 샘플 데이터 (첫 5개) ===\n")

    # scroll을 사용하여 데이터 조회
    records, next_page_offset = client.scroll(
        collection_name=collection_name,
        limit=5,
        with_payload=True,
        with_vectors=False
    )

    for idx, record in enumerate(records, 1):
        print(f"--- 레코드 {idx} ---")
        print(f"ID: {record.id}")
        print(f"Payload keys: {list(record.payload.keys())}")
        print(f"Payload:")
        print(json.dumps(record.payload, ensure_ascii=False, indent=2))
        print()

    # "노송이" 검색
    print("\n=== '노송이' 이름으로 검색 ===\n")

    # 먼저 필터로 검색
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    try:
        # 한글 필드명으로 검색
        results = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="담당자",
                        match=MatchValue(value="노송이")
                    )
                ]
            ),
            limit=10,
            with_payload=True,
            with_vectors=False
        )

        print(f"'담당자' 필드로 검색: {len(results[0])}건")
        for record in results[0]:
            print(f"- {record.payload.get('담당자')} | {record.payload.get('부서')} | {record.payload.get('직급')}")
    except Exception as e:
        print(f"한글 필드 검색 실패: {e}")

    try:
        # 영어 필드명으로 검색
        results = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="name",
                        match=MatchValue(value="노송이")
                    )
                ]
            ),
            limit=10,
            with_payload=True,
            with_vectors=False
        )

        print(f"'name' 필드로 검색: {len(results[0])}건")
        for record in results[0]:
            print(f"- {record.payload.get('name')} | {record.payload.get('dept1')} | {record.payload.get('rank')}")
    except Exception as e:
        print(f"영어 필드 검색 실패: {e}")

if __name__ == "__main__":
    main()
