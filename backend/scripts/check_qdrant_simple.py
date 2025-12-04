"""
Qdrant 스키마 및 데이터 구조 확인 (간소화 버전)
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from app.config import settings
import json

def main():
    print("=== Qdrant 데이터 확인 ===\n")

    # Qdrant 클라이언트 연결
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )

    collection_name = settings.qdrant_collection
    print(f"컬렉션: {collection_name}\n")

    # 샘플 데이터 조회 (scroll 사용)
    print("=== 샘플 데이터 (첫 3개) ===\n")

    try:
        records, next_page_offset = client.scroll(
            collection_name=collection_name,
            limit=3,
            with_payload=True,
            with_vectors=False
        )

        for idx, record in enumerate(records, 1):
            print(f"--- 레코드 {idx} ---")
            print(f"Payload keys: {list(record.payload.keys())}")
            print("Payload values:")
            for key, value in record.payload.items():
                if isinstance(value, str) and len(value) > 100:
                    print(f"  {key}: {value[:100]}...")
                else:
                    print(f"  {key}: {value}")
            print()
    except Exception as e:
        print(f"샘플 조회 실패: {e}\n")

    # "노송이" 검색 - 한글 필드명
    print("=== '노송이' 검색 (한글 필드) ===\n")
    try:
        results, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="담당자",
                        match=MatchValue(value="노송이")
                    )
                ]
            ),
            limit=3,
            with_payload=True,
            with_vectors=False
        )

        print(f"'담당자=노송이' 검색 결과: {len(results)}건\n")
        for record in results:
            print(f"담당자: {record.payload.get('담당자')}")
            print(f"부서: {record.payload.get('부서')}")
            print(f"직급: {record.payload.get('직급')}")
            print(f"업무내용: {record.payload.get('업무내용', '')[:50]}...")
            print()
    except Exception as e:
        print(f"한글 필드 검색 실패: {e}\n")

    # "노송이" 검색 - 영어 필드명
    print("=== '노송이' 검색 (영어 필드) ===\n")
    try:
        results, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="name",
                        match=MatchValue(value="노송이")
                    )
                ]
            ),
            limit=3,
            with_payload=True,
            with_vectors=False
        )

        print(f"'name=노송이' 검색 결과: {len(results)}건\n")
        for record in results:
            print(f"name: {record.payload.get('name')}")
            print(f"dept1: {record.payload.get('dept1')}")
            print(f"rank: {record.payload.get('rank')}")
            print(f"tasks: {record.payload.get('tasks', '')[:50]}...")
            print()
    except Exception as e:
        print(f"영어 필드 검색 실패: {e}\n")

if __name__ == "__main__":
    main()
