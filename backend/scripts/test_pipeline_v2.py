"""
Pipeline V2 테스트 스크립트
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from app.services.text_preprocessor import get_preprocessor
from app.services.bm25_index import get_bm25_system
from app.services.similarity_search import get_similarity_search
from app.services.evidence_collector import get_evidence_collector
from app.services.department_recommender import get_department_recommender
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_preprocessor():
    """전처리기 테스트"""
    logger.info("\n=== 전처리기 테스트 ===")

    preprocessor = get_preprocessor()

    test_titles = [
        "2025년도 예산편성 기본지침(안) 제출",
        "[긴급]청사관리 안내문(참고)",
        "지방세 체납자 명단 공개 관련 의견조회(회신)",
        "공무원 복무관리 및 징계양정 등에 관한 규정 개정(안) 입법예고"
    ]

    for title in test_titles:
        cleaned = preprocessor.clean_title(title)
        tokens = preprocessor.tokenize(cleaned)
        logger.info(f"원본: {title}")
        logger.info(f"정규화: {cleaned}")
        logger.info(f"토큰: {tokens}\n")


def test_bm25_search():
    """BM25 검색 테스트"""
    logger.info("\n=== BM25 검색 테스트 ===")

    bm25_system = get_bm25_system()

    # 통계
    stats = bm25_system.get_stats()
    logger.info(f"BM25 통계: {stats}")

    # 검색 테스트
    query = "예산편성 기본지침"
    results = bm25_system.search(query, top_k=5)

    logger.info(f"\n검색어: '{query}'")
    logger.info(f"결과 {len(results)}건:")
    for i, result in enumerate(results, 1):
        logger.info(
            f"{i}. [{result['dept']}] {result['cleaned_title']} "
            f"(점수: {result['score']:.4f})"
        )


def test_similarity_search():
    """유사도 검색 테스트"""
    logger.info("\n=== 유사도 검색 테스트 ===")

    similarity_search = get_similarity_search()

    test_title = "2025년도 예산편성 기본지침"
    results, early_stopped = similarity_search.search_similar_documents(
        title=test_title,
        dept_filter=None,
        early_stop=True
    )

    logger.info(f"검색어: '{test_title}'")
    logger.info(f"조기 종료: {early_stopped}")
    logger.info(f"결과 {len(results)}건:")
    for i, result in enumerate(results[:5], 1):
        logger.info(
            f"{i}. [{result['dept']}] {result['title']} "
            f"(유사도: {result['similarity']:.2f}%)"
        )


async def test_evidence_collector():
    """증거 수집기 테스트"""
    logger.info("\n=== 증거 수집기 테스트 ===")

    evidence_collector = get_evidence_collector()

    test_title = "2025년도 예산편성 기본지침"
    evidence = evidence_collector.collect_all_evidence(
        title=test_title,
        dept_filter=None
    )

    logger.info(f"검색어: '{test_title}'")
    logger.info(f"조기 종료: {evidence['early_stopped']}")
    logger.info(f"자동 배정 부서: {evidence.get('auto_assigned_dept', 'N/A')}")
    logger.info(f"문서 배부 이력 증거: {len(evidence['history_evidence'])}건")
    logger.info(f"사무분장 증거: {len(evidence['job_evidence'])}건")

    # 상위 3건 이력 출력
    logger.info("\n[문서 배부 이력 상위 3건]")
    for i, doc in enumerate(evidence['history_evidence'][:3], 1):
        logger.info(
            f"{i}. [{doc['dept']}] {doc['title']} "
            f"(유사도: {doc['similarity']:.2f}%, 보고자: {doc['reporter']})"
        )


async def test_department_recommender():
    """부서 추천 엔진 테스트"""
    logger.info("\n=== 부서 추천 엔진 테스트 ===")

    recommender = get_department_recommender()

    test_cases = [
        {
            "title": "2025년도 예산편성 기본지침",
            "recipient_info": None
        },
        {
            "title": "지방세 체납자 명단 공개",
            "recipient_info": {"is_explicit": True, "dept_name": "예산과"}
        },
        {
            "title": "청사관리 안내문",
            "recipient_info": None
        }
    ]

    for test in test_cases:
        logger.info(f"\n[테스트] 제목: {test['title']}")

        result = recommender.recommend_department(
            title=test['title'],
            recipient_info=test['recipient_info'],
            feedback_data=None
        )

        logger.info(f"추천 부서: {result['recommended_dept']}")
        logger.info(f"신뢰도: {result['confidence']}")
        logger.info(f"자동 배정: {result['auto_assigned']}")
        logger.info(f"추천 근거: {result['reasoning']}")


async def main():
    """메인 테스트 함수"""
    logger.info("Pipeline V2 통합 테스트 시작\n")

    # 1. 전처리기 테스트
    test_preprocessor()

    # 2. BM25 검색 테스트
    test_bm25_search()

    # 3. 유사도 검색 테스트
    test_similarity_search()

    # 4. 증거 수집기 테스트
    await test_evidence_collector()

    # 5. 부서 추천 엔진 테스트
    await test_department_recommender()

    logger.info("\n=== 모든 테스트 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())
