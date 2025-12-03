#!/usr/bin/env python3
"""
3단계 우선순위 파이프라인 테스트 스크립트

Stage 1: Skeleton Matching (Fast-Track)
Stage 2: Action-based Hybrid Search (Deep-Check)
Stage 3: LLM Final Verification (Safety Net)
"""

import asyncio
import sys
import os

# 프로젝트 경로 추가
sys.path.insert(0, '/home/gil/document-distribution-poc/backend')

from app.services.historical_search import historical_search_service


async def test_three_stage_pipeline():
    """3단계 파이프라인 테스트"""

    print("=" * 80)
    print("3단계 우선순위 파이프라인 테스트")
    print("=" * 80)

    # 테스트 케이스 1: Skeleton 완전 일치 (Stage 1 예상)
    print("\n[테스트 1] Skeleton 완전 일치 - Stage 1 Fast-Track 예상")
    print("-" * 80)
    title1 = "(전 직원 공람) 2025년 적극행정 우수사례 경진대회 개최 안내"
    print(f"입력 제목: {title1}")

    # Skeleton 확인
    skeleton1 = historical_search_service._normalize_to_skeleton(title1)
    print(f"입력 Skeleton: '{skeleton1}'")

    docs1, stage1 = await historical_search_service.search_with_three_stage_pipeline(
        title1,
        top_k=3
    )

    print(f"\n처리 단계: {stage1}")
    print(f"검색 결과: {len(docs1)}개")
    for i, doc in enumerate(docs1[:3], 1):
        doc_skeleton = historical_search_service._normalize_to_skeleton(doc.title)
        print(f"  [{i}] {doc.title[:80]}")
        print(f"      Skeleton: '{doc_skeleton}'")
        print(f"      보고자: {doc.reporter}, 부서: {doc.department}, 점수: {doc.score:.3f}")

    # 테스트 케이스 2: 유사하지만 행위가 다름 (Stage 2 + 행위어 페널티 예상)
    print("\n[테스트 2] 주제는 같지만 행위가 다름 - Stage 2 행위어 페널티 예상")
    print("-" * 80)
    title2 = "2025년 적극행정 인식도 조사 계획"
    print(f"입력 제목: {title2}")

    docs2, stage2 = await historical_search_service.search_with_three_stage_pipeline(
        title2,
        top_k=3
    )

    print(f"\n처리 단계: {stage2}")
    print(f"검색 결과: {len(docs2)}개")
    for i, doc in enumerate(docs2[:3], 1):
        print(f"  [{i}] {doc.title[:60]}")
        print(f"      보고자: {doc.reporter}, 부서: {doc.department}, 점수: {doc.score:.3f}")

    # 테스트 케이스 3: 애매한 유사도 (Stage 3 LLM 판단 예상)
    print("\n[테스트 3] 애매한 유사도 - Stage 3 LLM 판단 예상")
    print("-" * 80)
    title3 = "2024년 적극행정 추진 현황 보고"
    summary3 = "적극행정 관련 업무 추진 현황을 보고하는 문서입니다."
    print(f"입력 제목: {title3}")

    docs3, stage3 = await historical_search_service.search_with_three_stage_pipeline(
        title3,
        document_summary=summary3,
        top_k=3
    )

    print(f"\n처리 단계: {stage3}")
    print(f"검색 결과: {len(docs3)}개")
    for i, doc in enumerate(docs3[:3], 1):
        print(f"  [{i}] {doc.title[:60]}")
        print(f"      보고자: {doc.reporter}, 부서: {doc.department}, 점수: {doc.score:.3f}")

    # 테스트 케이스 4: Skeleton 정규화 테스트
    print("\n[테스트 4] Skeleton 정규화 테스트")
    print("-" * 80)
    test_titles = [
        "(전 직원 공람) 2025년 적극행정 우수사례 경진대회 개최 안내",
        "2024년 적극행정 우수사례 경진대회 계획",
        "[중요] 25년 적극행정 우수사례 경진대회 실시",
    ]

    for title in test_titles:
        skeleton = historical_search_service._normalize_to_skeleton(title)
        print(f"  원본: {title}")
        print(f"  Skeleton: '{skeleton}'")
        print()

    # 테스트 케이스 5: 행위어 추출 테스트
    print("\n[테스트 5] 행위어(Head Noun) 추출 테스트")
    print("-" * 80)
    test_titles_action = [
        "적극행정 우수사례 경진대회 개최 안내",
        "적극행정 인식도 조사 계획",
        "국민 참여 예산 공모사업 실시 안내",
        "직원 만족도 설문 조사 요청",
    ]

    for title in test_titles_action:
        head_noun = historical_search_service._extract_head_noun(title)
        print(f"  제목: {title}")
        print(f"  행위어: '{head_noun}'")
        print()

    print("=" * 80)
    print("테스트 완료")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_three_stage_pipeline())
