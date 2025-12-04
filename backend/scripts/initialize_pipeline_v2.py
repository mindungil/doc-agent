"""
Pipeline V2 초기화 스크립트
1. CSV 데이터를 Parquet로 변환 및 DuckDB 구축
2. BM25 Main Index 빌드
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from setup_history_db import HistoryDatabaseSetup
from app.services.bm25_index import get_bm25_system
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """초기화 메인 함수"""
    logger.info("=== Pipeline V2 초기화 시작 ===")

    # 1. 문서 배부 이력 데이터베이스 구축
    logger.info("\n[1/2] 문서 배부 이력 데이터베이스 구축...")
    db_setup = HistoryDatabaseSetup()
    db_setup.run()

    # 2. BM25 Main Index 빌드
    logger.info("\n[2/2] BM25 Main Index 빌드...")
    bm25_system = get_bm25_system()

    # 통계 확인
    stats = bm25_system.get_stats()
    logger.info(f"BM25 인덱스 통계: {stats}")

    logger.info("\n=== Pipeline V2 초기화 완료 ===")


if __name__ == "__main__":
    main()
