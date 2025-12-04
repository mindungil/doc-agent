"""
실제 API 엔드포인트를 호출하여 전체 플로우 테스트
"""
import asyncio
import httpx
import json

API_BASE = "http://localhost:8000"

async def test_recommend_api():
    """추천 API 직접 호출 테스트"""
    print("\n" + "="*80)
    print("실제 API 엔드포인트 테스트")
    print("="*80)

    # 모바일앱 문서가 있는지 확인
    async with httpx.AsyncClient() as client:
        # 문서 목록 조회
        print("\n1. 문서 목록 조회...")
        response = await client.get(f"{API_BASE}/api/documents/")

        if response.status_code != 200:
            print(f"❌ 문서 목록 조회 실패: {response.status_code}")
            return

        docs = response.json()
        print(f"✅ 총 {len(docs)}개 문서 발견")

        # 모바일앱 문서 찾기
        target_doc = None
        for doc in docs:
            if "모바일앱" in doc["title"] or "공공앱" in doc["title"]:
                target_doc = doc
                print(f"\n📄 대상 문서 발견:")
                print(f"   ID: {doc['id']}")
                print(f"   제목: {doc['title']}")
                print(f"   상태: {doc['status']}")
                break

        if not target_doc:
            print("\n❌ 모바일앱 관련 문서를 찾을 수 없습니다.")
            print("   테스트를 위해 문서를 먼저 업로드하세요.")
            return

        doc_id = target_doc["id"]

        # 추천 API 호출
        print(f"\n2. 문서 {doc_id} 추천 API 호출 중...")
        print(f"   POST {API_BASE}/api/documents/{doc_id}/recommend")

        try:
            response = await client.post(
                f"{API_BASE}/api/documents/{doc_id}/recommend",
                timeout=120.0
            )

            if response.status_code != 200:
                print(f"\n❌ 추천 API 실패: {response.status_code}")
                print(f"   응답: {response.text}")
                return

            recommendation = response.json()

            print(f"\n✅ 추천 API 성공!")
            print(f"\n추천 결과:")
            print(json.dumps(recommendation, indent=2, ensure_ascii=False))

            # 문서 상세 다시 조회
            print(f"\n3. 문서 {doc_id} 상세 조회...")
            response = await client.get(f"{API_BASE}/api/documents/{doc_id}")

            if response.status_code == 200:
                doc_detail = response.json()
                print(f"\n문서 상세:")
                print(f"   상태: {doc_detail['status']}")
                if doc_detail.get("recommendation"):
                    primary = doc_detail["recommendation"]["primary"]
                    print(f"   1순위: {primary['name']} ({primary['rank']})")
                    print(f"   부서: {primary['dept1']} {primary['dept2']} {primary['dept3']}")
                    print(f"   근거: {doc_detail['recommendation']['reasoning'][:200]}...")
                else:
                    print(f"   추천 정보 없음")

        except httpx.TimeoutException:
            print("\n❌ 요청 타임아웃 (120초 초과)")
        except Exception as e:
            print(f"\n❌ 오류 발생: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_recommend_api())
