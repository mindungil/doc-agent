"""
문서 배부 이력 데이터베이스 구축 스크립트
CSV 파일들을 Parquet로 변환하고 DuckDB에서 통합 뷰를 생성합니다.
"""
import os
import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime
import re


class HistoryDatabaseSetup:
    """문서 배부 이력 데이터베이스 설정"""

    def __init__(self, csv_dir: str = "/home/gil/doc-agent/csv",
                 parquet_dir: str = "/home/gil/doc-agent/data/history",
                 db_path: str = "/home/gil/doc-agent/data/history.duckdb"):
        self.csv_dir = Path(csv_dir)
        self.parquet_dir = Path(parquet_dir)
        self.db_path = db_path

        # 디렉토리 생성
        self.parquet_dir.mkdir(parents=True, exist_ok=True)

    def extract_dept_from_filename(self, filename: str) -> str:
        """파일명에서 부서명 추출

        예: '2025년 법무행정과 접수문서 목록.csv' -> '법무행정과'
        """
        import unicodedata
        # 유니코드 정규화
        filename = unicodedata.normalize('NFC', filename)

        # 패턴: YYYY년 [부서명] 접수문서 목록.csv
        pattern = r'(\d{4})년\s+(.+?)\s+접수문서\s+목록\.csv'
        match = re.search(pattern, filename)
        if match:
            dept = match.group(2).strip()
            return dept

        # Fallback: 직접 검색
        depts = ['법무행정과', '행정정보과', '예산과', '정책기획관', '인구청년정책과']
        for dept in depts:
            if dept in filename:
                return dept

        return "unknown"

    def csv_to_parquet(self):
        """CSV 파일들을 Parquet로 변환"""
        print("=== CSV 파일을 Parquet로 변환 중 ===")

        for csv_file in self.csv_dir.glob("*.csv"):
            filename = csv_file.name
            dept_name = self.extract_dept_from_filename(filename)
            print(f"처리 중: {filename} (부서: {dept_name})")

            # CSV 읽기
            df = pd.read_csv(csv_file)

            # 부서 컬럼 추가
            df['배부부서'] = dept_name

            # 보고일자를 날짜 형식으로 변환
            df['보고일자'] = pd.to_datetime(df['보고일자'], format='%Y.%m.%d', errors='coerce')

            # 연월 컬럼 추가 (파티셔닝용)
            df['year_month'] = df['보고일자'].dt.to_period('M').astype(str)

            # Parquet로 저장 (월별로 파티셔닝)
            for year_month, group in df.groupby('year_month'):
                if pd.isna(year_month):
                    continue

                parquet_file = self.parquet_dir / f"history_{year_month.replace('-', '_')}.parquet"

                # 기존 파일이 있으면 병합
                if parquet_file.exists():
                    existing_df = pd.read_parquet(parquet_file)
                    combined_df = pd.concat([existing_df, group], ignore_index=True)
                    combined_df.to_parquet(parquet_file, index=False, compression='snappy')
                    print(f"  병합: {parquet_file.name} ({len(group)} 행 추가)")
                else:
                    group.to_parquet(parquet_file, index=False, compression='snappy')
                    print(f"  생성: {parquet_file.name} ({len(group)} 행)")

        print("\n=== 변환 완료 ===")

    def create_duckdb_views(self):
        """DuckDB에서 통합 뷰 생성"""
        print("\n=== DuckDB 통합 뷰 생성 중 ===")

        con = duckdb.connect(self.db_path)

        # 1. 실시간 테이블 생성 (Hot Data)
        con.execute("""
            CREATE TABLE IF NOT EXISTS realtime_docs (
                문서번호 VARCHAR,
                보고일자 DATE,
                문서구분 VARCHAR,
                제목 VARCHAR,
                "수(발)신자" VARCHAR,
                보고자 VARCHAR,
                검토자 VARCHAR,
                상태 VARCHAR,
                붙임 VARCHAR,
                종류 VARCHAR,
                분리 VARCHAR,
                생산등록번호 VARCHAR,
                공개구분 VARCHAR,
                목록공개여부 VARCHAR,
                문서비공개사유 VARCHAR,
                "외부(민원인)주소" VARCHAR,
                등록구분 VARCHAR,
                배부부서 VARCHAR,
                year_month VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("실시간 테이블 생성 완료")

        # 2. Parquet 파일들을 읽는 뷰 생성
        parquet_pattern = str(self.parquet_dir / "history_*.parquet")

        con.execute(f"""
            CREATE OR REPLACE VIEW cold_docs AS
            SELECT * FROM read_parquet('{parquet_pattern}')
        """)
        print(f"Cold Data 뷰 생성 완료: {parquet_pattern}")

        # 3. 통합 뷰 생성 (Cold + Hot)
        con.execute("""
            CREATE OR REPLACE VIEW all_docs AS
            SELECT
                문서번호, 보고일자, 문서구분, 제목, "수(발)신자", 보고자, 검토자,
                상태, 붙임, 종류, 분리, 생산등록번호, 공개구분, 목록공개여부,
                문서비공개사유, "외부(민원인)주소", 등록구분, 배부부서, year_month
            FROM cold_docs
            UNION ALL
            SELECT
                문서번호, 보고일자, 문서구분, 제목, "수(발)신자", 보고자, 검토자,
                상태, 붙임, 종류, 분리, 생산등록번호, 공개구분, 목록공개여부,
                문서비공개사유, "외부(민원인)주소", 등록구분, 배부부서, year_month
            FROM realtime_docs
        """)
        print("통합 뷰 생성 완료")

        # 4. 통계 확인
        stats = con.execute("""
            SELECT
                배부부서,
                COUNT(*) as 문서수,
                MIN(보고일자) as 최초일자,
                MAX(보고일자) as 최종일자
            FROM all_docs
            GROUP BY 배부부서
            ORDER BY 문서수 DESC
        """).fetchdf()

        print("\n=== 부서별 문서 통계 ===")
        print(stats)

        # 5. 인덱스 생성 (검색 최적화)
        con.execute("CREATE INDEX IF NOT EXISTS idx_title ON realtime_docs(제목)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_dept ON realtime_docs(배부부서)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_reporter ON realtime_docs(보고자)")
        print("\n인덱스 생성 완료")

        con.close()
        print("\n=== DuckDB 설정 완료 ===")

    def run(self):
        """전체 프로세스 실행"""
        print("문서 배부 이력 데이터베이스 구축을 시작합니다.\n")
        self.csv_to_parquet()
        self.create_duckdb_views()
        print("\n모든 작업이 완료되었습니다!")


if __name__ == "__main__":
    setup = HistoryDatabaseSetup()
    setup.run()
