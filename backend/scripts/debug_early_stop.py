"""
조기 종료 케이스 디버깅 스크립트
노송이가 RAG 후보에 있는지, 이름 매칭이 왜 실패하는지 확인
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.pipeline_v2 import get_pipeline_v2


async def debug_early_stop():
    """조기 종료 케이스 디버깅"""
    print("\n" + "="*80)
    print("조기 종료 케이스 디버깅: 노송이 매칭 확인")
    print("="*80)

    pipeline = get_pipeline_v2()

    title = "2025년 모바일앱(공공앱) 폐기예외 신청 안내"
    content = "공공앱 폐기예외 신청에 대한 안내 문서입니다."

    print(f"\n📄 문서 제목: {title}")
    print(f"📝 문서 내용: {content}\n")

    try:
        recommendation = await pipeline.recommend_assignee_with_pipeline(
            document_title=title,
            document_content=content,
            db=None
        )

        print(f"\n" + "="*80)
        print("최종 추천 결과")
        print("="*80)
        print(f"1순위 담당자: {recommendation.primary.name}")
        print(f"직급: {recommendation.primary.rank}")
        print(f"부서: {recommendation.primary.dept1} {recommendation.primary.dept2} {recommendation.primary.dept3}")
        print(f"\n추천 근거 (처음 500자):\n{recommendation.reasoning[:500]}...")

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_early_stop())
