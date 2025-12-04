"""
RAG 검색 결과 디버깅
노송이가 검색 결과에 포함되는지 확인
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.rag import rag_service


async def debug_rag_search():
    """RAG 검색 디버깅"""
    print("\n" + "="*80)
    print("RAG 검색 디버깅: 노송이가 검색 결과에 포함되는지 확인")
    print("="*80)

    title = "2025년 모바일앱(공공앱) 폐기예외 신청 안내"
    content = "공공앱 폐기예외 신청에 대한 안내 문서입니다."
    document_text = f"{title}\n\n{content}"

    print(f"\n📄 검색 쿼리: {document_text}\n")

    # 상위 20명 검색
    candidates = await rag_service.search_similar_employees(document_text, top_k=20)

    print(f"\n✅ 검색 결과: {len(candidates)}명\n")
    print("="*80)

    # 노송이가 포함되어 있는지 확인
    nosong_found = False
    nosong_rank = None

    for i, cand in enumerate(candidates, 1):
        print(f"{i:2d}. {cand.name:8s} ({cand.rank:15s}) - {cand.dept1:15s} {cand.dept2:20s} - 점수: {cand.score:.4f}")
        print(f"    업무: {cand.tasks[:100]}...")

        if cand.name == "노송이":
            nosong_found = True
            nosong_rank = i
            print(f"    ⭐ 노송이 발견! 순위: {i}위")
        print()

    print("="*80)
    if nosong_found:
        print(f"✅ 노송이가 {nosong_rank}위에서 발견되었습니다.")
    else:
        print(f"❌ 노송이가 상위 20명 검색 결과에 없습니다.")
        print(f"   → RAG 검색이 노송이의 업무와 문서 내용의 유사도를 낮게 평가한 것으로 보입니다.")


if __name__ == "__main__":
    asyncio.run(debug_rag_search())
