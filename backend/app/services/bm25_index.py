"""
BM25S 검색 인덱스 시스템 (Main + Delta Index)
"""
import bm25s
import duckdb
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import threading
import logging
from .text_preprocessor import get_preprocessor


logger = logging.getLogger(__name__)


class BM25IndexSystem:
    """BM25S 인덱스 시스템 (Main + Delta 이원화 구조)"""

    def __init__(
        self,
        db_path: str = "/app/data/history.duckdb",
        index_dir: str = "/app/data/bm25_index",
        delta_threshold: int = 2000,  # Delta Index 병합 임계값
        merge_interval_hours: int = 6  # 병합 주기 (시간)
    ):
        self.db_path = db_path
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.delta_threshold = delta_threshold
        self.merge_interval_hours = merge_interval_hours

        # 전처리기
        self.preprocessor = get_preprocessor()

        # Main Index (정적, 디스크 기반)
        self.main_index: Optional[bm25s.BM25] = None
        self.main_corpus: List[str] = []
        self.main_metadata: List[Dict[str, Any]] = []

        # Delta Index (동적, 메모리 기반)
        self.delta_index: Optional[bm25s.BM25] = None
        self.delta_corpus: List[str] = []
        self.delta_metadata: List[Dict[str, Any]] = []

        # 병합 상태
        self.last_merge_time: Optional[datetime] = None
        self._merge_lock = threading.Lock()

        # 초기화
        self._load_main_index()

    def _load_main_index(self):
        """Main Index 로드 (디스크에서)"""
        main_index_file = self.index_dir / "main_index.pkl"
        main_corpus_file = self.index_dir / "main_corpus.pkl"
        main_metadata_file = self.index_dir / "main_metadata.pkl"

        if main_index_file.exists():
            logger.info("Main Index 로드 중...")
            with open(main_index_file, 'rb') as f:
                self.main_index = pickle.load(f)
            with open(main_corpus_file, 'rb') as f:
                self.main_corpus = pickle.load(f)
            with open(main_metadata_file, 'rb') as f:
                self.main_metadata = pickle.load(f)
            logger.info(f"Main Index 로드 완료: {len(self.main_corpus)} 문서")
        else:
            logger.info("Main Index가 없습니다. 빌드가 필요합니다.")
            self.build_main_index()

    def build_main_index(self, force: bool = False):
        """Main Index 빌드 (전체 Parquet 데이터 기반)

        Args:
            force: 강제 재빌드 여부
        """
        if self.main_index is not None and not force:
            logger.info("Main Index가 이미 존재합니다.")
            return

        logger.info("Main Index 빌드 시작...")

        # DuckDB에서 전체 데이터 로드
        con = duckdb.connect(':memory:')

        # Parquet 파일 직접 읽기 (컨테이너 내부 경로)
        query = """
            SELECT 제목, 배부부서, 보고자, 보고일자, 문서번호
            FROM '/app/data/history/history_*.parquet'
            ORDER BY 보고일자 DESC
        """

        df = con.execute(query).fetchdf()
        con.close()

        logger.info(f"문서 {len(df)}건 로드 완료")

        # 코퍼스 및 메타데이터 구성
        corpus = []
        metadata = []

        for _, row in df.iterrows():
            title = row['제목']
            if not isinstance(title, str):
                continue

            # 제목 정규화
            cleaned_title = self.preprocessor.clean_title(title)
            # 토큰화
            tokens = self.preprocessor.tokenize(cleaned_title)

            corpus.append(tokens)
            metadata.append({
                'title': title,
                'cleaned_title': cleaned_title,
                'dept': row['배부부서'],
                'reporter': row['보고자'],
                'date': row['보고일자'],
                'doc_no': row['문서번호']
            })

        logger.info("BM25 인덱스 생성 중...")
        # BM25 인덱스 생성
        self.main_index = bm25s.BM25()
        self.main_index.index(corpus)

        self.main_corpus = corpus
        self.main_metadata = metadata

        # 디스크에 저장
        self._save_main_index()

        self.last_merge_time = datetime.now()
        logger.info(f"Main Index 빌드 완료: {len(corpus)} 문서")

    def _save_main_index(self):
        """Main Index 저장 (디스크에)"""
        logger.info("Main Index 저장 중...")
        with open(self.index_dir / "main_index.pkl", 'wb') as f:
            pickle.dump(self.main_index, f)
        with open(self.index_dir / "main_corpus.pkl", 'wb') as f:
            pickle.dump(self.main_corpus, f)
        with open(self.index_dir / "main_metadata.pkl", 'wb') as f:
            pickle.dump(self.main_metadata, f)
        logger.info("Main Index 저장 완료")

    def add_document(self, title: str, dept: str, reporter: str, date: str, doc_no: str):
        """새 문서를 Delta Index에 추가

        Args:
            title: 문서 제목
            dept: 배부 부서
            reporter: 보고자
            date: 보고 일자
            doc_no: 문서 번호
        """
        # 제목 정규화 및 토큰화
        cleaned_title = self.preprocessor.clean_title(title)
        tokens = self.preprocessor.tokenize(cleaned_title)

        # Delta에 추가
        self.delta_corpus.append(tokens)
        self.delta_metadata.append({
            'title': title,
            'cleaned_title': cleaned_title,
            'dept': dept,
            'reporter': reporter,
            'date': date,
            'doc_no': doc_no
        })

        # Delta Index 재빌드 (빠름)
        if len(self.delta_corpus) > 0:
            self.delta_index = bm25s.BM25()
            self.delta_index.index(self.delta_corpus)

        logger.info(f"Delta Index에 문서 추가: {doc_no} (총 {len(self.delta_corpus)}건)")

        # 병합 조건 체크
        if len(self.delta_corpus) >= self.delta_threshold:
            logger.info(f"Delta Index 크기 임계값 초과: {len(self.delta_corpus)} >= {self.delta_threshold}")
            self.merge_delta_to_main()

    def search(self, query: str, top_k: int = 50, dept_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """검색 수행 (Main + Delta)

        Args:
            query: 검색 쿼리
            top_k: 상위 K개 결과
            dept_filter: 부서 필터 (옵션)

        Returns:
            검색 결과 리스트
        """
        # 쿼리 토큰화
        query_tokens = self.preprocessor.tokenize(query)

        results = []

        # Main Index 검색
        if self.main_index is not None and len(self.main_corpus) > 0:
            main_results, main_scores = self.main_index.retrieve([query_tokens], k=top_k)
            for i, (idx, score) in enumerate(zip(main_results[0], main_scores[0])):
                if idx < len(self.main_metadata):
                    meta = self.main_metadata[idx].copy()
                    meta['score'] = float(score)
                    meta['source'] = 'main'
                    results.append(meta)

        # Delta Index 검색
        if self.delta_index is not None and len(self.delta_corpus) > 0:
            delta_results, delta_scores = self.delta_index.retrieve([query_tokens], k=top_k)
            for i, (idx, score) in enumerate(zip(delta_results[0], delta_scores[0])):
                if idx < len(self.delta_metadata):
                    meta = self.delta_metadata[idx].copy()
                    meta['score'] = float(score)
                    meta['source'] = 'delta'
                    results.append(meta)

        # 점수순 정렬
        results.sort(key=lambda x: x['score'], reverse=True)

        # 부서 필터링
        if dept_filter:
            results = [r for r in results if r['dept'] == dept_filter]

        # 상위 K개 반환
        return results[:top_k]

    def merge_delta_to_main(self):
        """Delta Index를 Main Index에 병합 (무중단 병합)"""
        with self._merge_lock:
            if len(self.delta_corpus) == 0:
                logger.info("Delta Index가 비어있습니다. 병합 생략.")
                return

            logger.info(f"Delta Index 병합 시작: {len(self.delta_corpus)}건")

            # 1. Delta 데이터를 DuckDB realtime_docs에 저장 (Hot Data)
            # (여기서는 생략 - 별도 프로세스에서 처리)

            # 2. 전체 데이터 재빌드
            self.build_main_index(force=True)

            # 3. Delta 초기화
            self.delta_index = None
            self.delta_corpus = []
            self.delta_metadata = []

            logger.info("Delta Index 병합 완료")

    def get_stats(self) -> Dict[str, Any]:
        """인덱스 통계 반환"""
        return {
            'main_docs': len(self.main_corpus),
            'delta_docs': len(self.delta_corpus),
            'total_docs': len(self.main_corpus) + len(self.delta_corpus),
            'last_merge': self.last_merge_time.isoformat() if self.last_merge_time else None,
            'delta_threshold': self.delta_threshold
        }


# 싱글톤 인스턴스
_bm25_system = None


def get_bm25_system() -> BM25IndexSystem:
    """BM25 인덱스 시스템 싱글톤 인스턴스 반환"""
    global _bm25_system
    if _bm25_system is None:
        _bm25_system = BM25IndexSystem()
    return _bm25_system
