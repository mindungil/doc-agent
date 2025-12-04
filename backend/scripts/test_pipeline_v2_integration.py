"""
Pipeline V2 통합 테스트
조기 종료와 일반 케이스 모두 테스트
"""
import asyncio
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.pipeline_v2 import get_pipeline_v2


async def test_early_stop_case():
    """조기 종료 케이스 테스트 (유사도 100%)"""
    print("\n" + "="*80)
    print("테스트 1: 조기 종료 케이스 (과거 유사 문서 100%)")
    print("="*80)

    pipeline = get_pipeline_v2()

    # 유사도 100%가 나올 만한 문서 제목
    title = "2025년 모바일앱(공공앱) 폐기예외 신청 안내"
    content = "공공앱 폐기예외 신청에 대한 안내 문서입니다."

    try:
        recommendation = await pipeline.recommend_assignee_with_pipeline(
            document_title=title,
            document_content=content,
            db=None  # 피드백 없이 테스트
        )

        print(f"\n✅ 추천 완료!")
        print(f"1순위 담당자: {recommendation.primary.name}")
        print(f"직급: {recommendation.primary.rank}")
        print(f"부서: {recommendation.primary.dept1} {recommendation.primary.dept2} {recommendation.primary.dept3}")
        print(f"\n추천 근거:\n{recommendation.reasoning}")

        print(f"\n다른 후보: {len(recommendation.candidates)}명")
        for i, cand in enumerate(recommendation.candidates[:3], 1):
            print(f"  {i}. {cand.name} ({cand.rank}) - {cand.dept1} {cand.dept2}")

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


async def test_normal_case():
    """일반 케이스 테스트 (유사도 낮음)"""
    print("\n" + "="*80)
    print("테스트 2: 일반 케이스 (LLM 추론 필요)")
    print("="*80)

    pipeline = get_pipeline_v2()

    # 과거 이력이 없는 새로운 문서
    title = "2026년도 신규 AI 기반 스마트시티 구축 계획"
    content = """
    전북도청에서는 2026년도에 AI 기반 스마트시티 구축을 위한
    종합 계획을 수립하고자 합니다. 주요 내용은 다음과 같습니다:

    1. AI 기반 교통 관제 시스템 구축
    2. 스마트 에너지 관리 플랫폼 도입
    3. 공공 빅데이터 분석 센터 설립

    담당 부서는 관련 업무를 검토하여 주시기 바랍니다.
    """

    try:
        recommendation = await pipeline.recommend_assignee_with_pipeline(
            document_title=title,
            document_content=content,
            db=None
        )

        print(f"\n✅ 추천 완료!")
        print(f"1순위 담당자: {recommendation.primary.name}")
        print(f"직급: {recommendation.primary.rank}")
        print(f"부서: {recommendation.primary.dept1} {recommendation.primary.dept2} {recommendation.primary.dept3}")
        print(f"담당 업무: {recommendation.primary.tasks[:100]}...")
        print(f"\n추천 근거:\n{recommendation.reasoning}")

        print(f"\n다른 후보: {len(recommendation.candidates)}명")
        for i, cand in enumerate(recommendation.candidates[:3], 1):
            print(f"  {i}. {cand.name} ({cand.rank}) - {cand.dept1} {cand.dept2}")

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """메인 테스트 실행"""
    print("\n🚀 Pipeline V2 통합 테스트 시작\n")

    # 테스트 1: 조기 종료
    await test_early_stop_case()

    # 테스트 2: 일반 케이스
    await test_normal_case()

    print("\n" + "="*80)
    print("✅ 모든 테스트 완료!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
