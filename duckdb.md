# DuckDB 인덱싱 전략

본 문서는 doc-agent 프로젝트에서 사용하는 DuckDB의 인덱싱 전략과 데이터 관리 아키텍처를 상세히 설명합니다.

## 1. 아키텍처 개요

### 1.1 Hot-Cold Data 분리 아키텍처

본 프로젝트는 **2-Tier 데이터 아키텍처**를 채택하여 데이터를 효율적으로 관리합니다.

```
┌─────────────────────────────────────────────┐
│           DuckDB Database                   │
│                                             │
│  ┌────────────────┐    ┌─────────────────┐ │
│  │  Cold Data     │    │  Hot Data       │ │
│  │  (Parquet)     │    │  (realtime_docs)│ │
│  │  - 과거 이력   │    │  - 실시간 문서  │ │
│  │  - 읽기 전용   │    │  - 최근 데이터  │ │
│  │  - 압축 저장   │    │  - 빠른 쓰기    │ │
│  └────────────────┘    └─────────────────┘ │
│           ↓                     ↓           │
│         VIEW: all_docs (UNION ALL)          │
└─────────────────────────────────────────────┘
```

### 1.2 데이터 파티셔닝 전략

**파티셔닝 키**: `year_month` (연월 기준)

- 파일명 예시: `history_2024_01.parquet`, `history_2024_02.parquet`
- 파티션 단위: 월별 (Monthly Partitioning)
- 압축 방식: Snappy Compression

## 2. Cold Data Layer (Parquet 기반)

### 2.1 Parquet 파일 구조

**위치**: `/app/data/history/history_*.parquet`

**스키마**:
```sql
문서번호       VARCHAR
보고일자       DATE
문서구분       VARCHAR
제목           VARCHAR
수(발)신자     VARCHAR
보고자         VARCHAR
검토자         VARCHAR
상태           VARCHAR
붙임           VARCHAR
종류           VARCHAR
분리           VARCHAR
생산등록번호   VARCHAR
공개구분       VARCHAR
목록공개여부   VARCHAR
문서비공개사유 VARCHAR
외부(민원인)주소 VARCHAR
등록구분       VARCHAR
배부부서       VARCHAR
year_month     VARCHAR  -- 파티셔닝 키
```

### 2.2 Parquet 장점 활용

1. **컬럼 기반 스토리지**
   - 특정 컬럼(제목, 보고자)만 스캔 가능
   - I/O 효율 극대화

2. **압축률**
   - Snappy 압축으로 디스크 사용량 최소화
   - 쿼리 시 실시간 압축 해제

3. **Zero-Copy 읽기**
   - DuckDB의 `read_parquet()` 함수로 파일 직접 스캔
   - 메모리 복사 없이 쿼리 가능

### 2.3 뷰 생성 (cold_docs)

```python
# backend/scripts/setup_history_db.py:126-130
con.execute(f"""
    CREATE OR REPLACE VIEW cold_docs AS
    SELECT * FROM read_parquet('{parquet_pattern}')
""")
```

**특징**:
- 실제 테이블이 아닌 **가상 뷰** (Virtual View)
- 쿼리 시점에 Parquet 파일을 동적으로 읽음
- 파티션 프루닝 (Partition Pruning) 자동 적용

## 3. Hot Data Layer (realtime_docs 테이블)

### 3.1 테이블 구조

```python
# backend/scripts/setup_history_db.py:97-120
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
```

### 3.2 실시간 데이터 추가 흐름

```
신규 문서 등록
    ↓
realtime_docs 테이블 INSERT
    ↓
일정 기간 경과 또는 임계값 도달
    ↓
Parquet 파일로 병합 (ETL)
    ↓
realtime_docs 테이블 정리
```

## 4. 인덱스 전략

### 4.1 생성된 인덱스 목록

```python
# backend/scripts/setup_history_db.py:165-168
con.execute("CREATE INDEX IF NOT EXISTS idx_title ON realtime_docs(제목)")
con.execute("CREATE INDEX IF NOT EXISTS idx_dept ON realtime_docs(배부부서)")
con.execute("CREATE INDEX IF NOT EXISTS idx_reporter ON realtime_docs(보고자)")
```

### 4.2 인덱스 선정 기준

| 컬럼명 | 인덱스 타입 | 선정 이유 | 쿼리 패턴 |
|--------|-------------|-----------|-----------|
| `제목` | B-Tree | 문서 검색의 핵심 필터 | `WHERE 제목 LIKE '%키워드%'` |
| `배부부서` | B-Tree | 부서별 필터링 빈번 | `WHERE 배부부서 = '정책기획관'` |
| `보고자` | B-Tree | 담당자 이력 조회 필수 | `WHERE 보고자 = '김철수'` |

### 4.3 인덱스 미생성 컬럼

**Cold Data (Parquet)**에는 인덱스를 생성하지 않습니다.

**이유**:
1. Parquet는 **읽기 전용 (Immutable)** 데이터
2. DuckDB의 **자동 통계 (Statistics)** 활용
   - 각 Parquet 파일의 Min/Max 값 자동 저장
   - Partition Pruning으로 필요한 파일만 스캔
3. **컬럼 기반 스토리지**로 인덱스 없이도 빠른 스캔 가능

### 4.4 인덱스 활용 쿼리 예시

**실시간 데이터 검색 (인덱스 사용)**:
```sql
-- idx_title 인덱스 활용
SELECT * FROM realtime_docs
WHERE 제목 LIKE '%적극행정%'
ORDER BY 보고일자 DESC
LIMIT 10;
```

**통합 데이터 검색 (뷰 활용)**:
```sql
-- Cold (Parquet Scan) + Hot (Index Scan)
SELECT * FROM all_docs
WHERE 배부부서 = '행정정보과'
ORDER BY 보고일자 DESC;
```

## 5. 통합 뷰 (all_docs)

### 5.1 뷰 정의

```python
# backend/scripts/setup_history_db.py:133-147
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
```

### 5.2 UNION ALL 선택 이유

- **UNION**: 중복 제거 연산 수행 (정렬 필요, 느림)
- **UNION ALL**: 중복 제거 없이 단순 결합 (빠름)

**선택 근거**:
- Cold Data와 Hot Data는 본질적으로 중복이 없음 (시간 분리)
- 정렬 오버헤드 제거로 성능 향상

## 6. 쿼리 최적화 전략

### 6.1 Partition Pruning 활용

```sql
-- year_month 필터로 파티션 프루닝
SELECT * FROM all_docs
WHERE year_month = '2024-01'
  AND 배부부서 = '행정정보과';
```

**효과**:
- 전체 Parquet 파일이 아닌 해당 월 파일만 스캔
- I/O 비용 대폭 감소

### 6.2 Projection Pushdown

```sql
-- 필요한 컬럼만 선택
SELECT 제목, 보고자, 보고일자
FROM all_docs
WHERE 배부부서 = '정책기획관';
```

**효과**:
- Parquet의 컬럼 기반 스토리지 활용
- 불필요한 컬럼 읽기 생략

### 6.3 통계 정보 활용

```sql
-- DuckDB 자동 통계 활용
SELECT 배부부서, COUNT(*) as 문서수,
       MIN(보고일자) as 최초일자,
       MAX(보고일자) as 최종일자
FROM all_docs
GROUP BY 배부부서
ORDER BY 문서수 DESC;
```

**DuckDB 자동 수집 통계**:
- Row Count
- Min/Max Values
- Null Count
- Distinct Count (HyperLogLog)

## 7. 데이터 라이프사이클

### 7.1 초기 데이터 로드

```python
# backend/scripts/setup_history_db.py:50-88
1. CSV 파일 읽기
2. 부서명 추출 (파일명 파싱)
3. 날짜 파싱 및 year_month 생성
4. 월별 그룹화
5. Parquet 파일로 저장
```

### 7.2 실시간 데이터 추가 (예상 흐름)

```
1. 신규 문서 등록
   ↓
2. realtime_docs 테이블 INSERT
   ↓
3. idx_title, idx_dept, idx_reporter 자동 업데이트
   ↓
4. all_docs 뷰를 통해 즉시 조회 가능
```

### 7.3 주기적 병합 (Cold Storage Migration)

```
1. realtime_docs가 일정 크기 도달 (예: 10,000건)
   ↓
2. realtime_docs → Parquet 파일로 Export
   ↓
3. 해당 월 Parquet 파일에 Append
   ↓
4. realtime_docs에서 병합된 데이터 삭제
   ↓
5. DuckDB 통계 정보 갱신
```

## 8. 성능 특성

### 8.1 읽기 성능

| 작업 | 예상 성능 | 최적화 요소 |
|------|-----------|-------------|
| 최근 문서 검색 (Hot) | **< 10ms** | B-Tree 인덱스 |
| 과거 문서 검색 (Cold) | **50-200ms** | Partition Pruning + Columnar Scan |
| 통합 검색 (all_docs) | **60-210ms** | Union All (중복 제거 없음) |
| 부서별 집계 | **100-300ms** | 자동 통계 활용 |

### 8.2 쓰기 성능

| 작업 | 예상 성능 | 특징 |
|------|-----------|------|
| realtime_docs INSERT | **< 5ms** | 인덱스 3개 업데이트 |
| Parquet Export | **1-5초 / 10,000건** | 일괄 처리 |

### 8.3 디스크 사용량

- **Parquet (Snappy 압축)**: 원본 CSV 대비 **60-70% 수준**
- **DuckDB 인덱스**: 데이터 크기의 약 **10-15%**

## 9. BM25 인덱스와의 연계

### 9.1 BM25 인덱스 빌드 소스

```python
# backend/app/services/bm25_index.py:86-98
query = """
    SELECT 제목, 배부부서, 보고자, 보고일자, 문서번호
    FROM '/app/data/history/history_*.parquet'
    ORDER BY 보고일자 DESC
"""
```

**연계 흐름**:
```
DuckDB Parquet (Cold Data)
    ↓ (전체 스캔)
BM25 Main Index 빌드
    ↓
디스크 저장 (Pickle)
    ↓
검색 서비스 로드
```

### 9.2 DuckDB vs BM25 역할 분담

| 시스템 | 역할 | 강점 |
|--------|------|------|
| **DuckDB** | 구조화 데이터 저장 및 필터링 | SQL, 집계, 파티셔닝 |
| **BM25** | 전문 검색 (Full-Text Search) | 키워드 매칭, 문서 랭킹 |

**쿼리 예시**:
```python
# DuckDB: 부서 필터링 + 날짜 범위
duckdb.execute("""
    SELECT 문서번호, 제목, 보고자
    FROM all_docs
    WHERE 배부부서 = '행정정보과'
      AND 보고일자 BETWEEN '2024-01-01' AND '2024-12-31'
""")

# BM25: 제목 키워드 검색
bm25_system.search(
    query="적극행정 우수사례 경진대회",
    top_k=50,
    dept_filter="행정정보과"
)
```

## 10. 모니터링 및 유지보수

### 10.1 통계 조회

```sql
-- 부서별 문서 통계
SELECT
    배부부서,
    COUNT(*) as 문서수,
    MIN(보고일자) as 최초일자,
    MAX(보고일자) as 최종일자
FROM all_docs
GROUP BY 배부부서
ORDER BY 문서수 DESC;
```

### 10.2 인덱스 상태 확인

```sql
-- DuckDB 인덱스 조회
SELECT * FROM duckdb_indexes();
```

### 10.3 파티션 상태 확인

```bash
# Parquet 파일 목록 및 크기
ls -lh /app/data/history/history_*.parquet
```

## 11. 확장성 고려사항

### 11.1 데이터 증가 시 대응

**현재 (수만 건)**:
- Parquet 월별 파티셔닝
- realtime_docs 인덱스 3개

**향후 (수십만 건 이상)**:
- 연도별 Parquet 재파티셔닝 고려
- realtime_docs 파티션 테이블 전환 (PARTITION BY year_month)
- 추가 인덱스: `idx_date` (보고일자)

### 11.2 쿼리 패턴 변화 대응

**현재 인덱스 최적화 쿼리**:
- 제목 검색
- 부서별 필터링
- 보고자 이력 조회

**향후 추가 고려 인덱스**:
- `idx_date`: 날짜 범위 쿼리 빈번 시
- `idx_docno`: 문서번호 직접 조회 시

## 12. 핵심 설계 원칙 요약

1. **Hot-Cold Separation**: 실시간 데이터와 과거 이력 분리로 성능 최적화
2. **Columnar Storage**: Parquet의 컬럼 기반 스토리지로 I/O 효율 극대화
3. **Partition Pruning**: 월별 파티셔닝으로 불필요한 스캔 제거
4. **Selective Indexing**: Hot Data에만 인덱스 생성, Cold Data는 통계 활용
5. **Zero-Copy Read**: DuckDB의 Parquet 직접 스캔으로 메모리 효율 향상
6. **Hybrid Search**: DuckDB(구조화 필터링) + BM25(전문 검색) 역할 분담

## 참고 파일

- `backend/scripts/setup_history_db.py`: DuckDB 초기화 및 인덱스 생성
- `backend/app/services/bm25_index.py`: BM25 인덱스 시스템
- `backend/scripts/initialize_pipeline_v2.py`: 파이프라인 초기화
