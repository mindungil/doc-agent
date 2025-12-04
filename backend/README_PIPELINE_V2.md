# Pipeline V2 구현 완료 보고서

## 개요
pipeline_v2.md 사양에 따라 행정 문서 자동 분류 시스템을 완전히 재구현했습니다.

## 구현된 주요 기능

### 1. 데이터 아키텍처
#### 문서 배부 이력 시스템 (DuckDB + Parquet)
- **파일 위치**: `backend/scripts/setup_history_db.py`
- **저장 구조**:
  - Cold Data: 월별 Parquet 파일 (`data/history/history_YYYY_MM.parquet`)
  - Hot Data: DuckDB 실시간 테이블 (`realtime_docs`)
  - 통합 뷰: `all_docs` (Cold + Hot 데이터 통합)
- **데이터 통계**:
  - 총 45,495건의 문서 로드
  - 5개 부서 (행정정보과, 정책기획관, 예산과, 법무행정과, 인구청년정책과)
  - 2025년 1월 ~ 11월 데이터

#### 사무분장 데이터 (Qdrant)
- 기존 Qdrant Vector DB 활용
- Collection: `dept_knowledge`
- 포트: 6333 (REST API), 6334 (gRPC)

### 2. 검색 인덱스 시스템 (BM25S)
#### Main + Delta Index 이원화 구조
- **파일 위치**: `backend/app/services/bm25_index.py`
- **Main Index**: 정적 인덱스 (Parquet 기반, 디스크 저장)
- **Delta Index**: 동적 인덱스 (메모리 기반, 실시간 추가)
- **병합 전략**: Threshold-based Merge
  - 임계값: 2,000건
  - 병합 주기: 6시간
  - 무중단 병합 (Double Buffering)

### 3. 전처리 및 정규화
- **파일 위치**: `backend/app/services/text_preprocessor.py`
- **기능**:
  - 괄호 패턴 검출 및 삭제 (3글자 이하만 삭제)
  - 유니코드 정규화 (NFC)
  - 공백 정규화
  - 명사 추출 (KoNLPy Okt 사용)

### 4. 문자열 유사도 검증
- **파일 위치**: `backend/app/services/similarity_search.py`
- **2단계 검색 파이프라인**:
  1. BM25S 1차 필터링 (Blocking) - Top 50개 후보군
  2. Levenshtein Distance 2차 정밀 검증
- **조기 종료**: 유사도 95% 이상 시 즉시 자동 배정

### 5. 증거 수집 (Evidence Accumulation)
- **파일 위치**: `backend/app/services/evidence_collector.py`
- **Source A - 문서 배부 이력**:
  - 유사 문서 제목, 처리 부서, 기안자, 기안 일자, 유사도 점수
- **Source B - 사무분장 규정**:
  - 담당 부서, 업무 정의, 직급, 담당자, 유사도 점수

### 6. LLM 추론 엔진
- **파일 위치**: `backend/app/services/department_recommender.py`
- **입력**: 문서 제목, 수신자 정보, 과거 이력, 사무분장, 휴먼 피드백
- **출력**: 추천 부서, 신뢰도, 추천 근거, 대안 부서
- **Fallback 로직**: LLM 실패 시 가장 많이 나온 부서 선택

### 7. 휴먼 피드백 루프
- **파일 위치**:
  - `backend/app/database/db.py` (FeedbackModel)
  - `backend/app/services/feedback_service.py`
- **피드백 데이터베이스 구조**:
  - keyword: 문서 핵심 키워드
  - reporter: 기안자
  - llm_predicted_dept: LLM 예측 부서 (오답)
  - human_corrected_dept: 담당자 수정 부서 (정답)
  - reason: 수정 사유
  - created_at: 피드백 발생 일시
- **2차 검증 로직**: LLM 추론 시 피드백 데이터를 프롬프트에 주입

### 8. 통합 파이프라인
- **파일 위치**: `backend/app/services/pipeline_v2.py`
- **처리 흐름**:
  1. 전처리 및 정규화 (Cleaned Title)
  2. 수신자 필터링 (OCR + LLM 보정)
  3. 휴먼 피드백 조회
  4. 증거 수집 (History + Job Description)
  5. LLM 추론 또는 조기 종료 (자동 배정)
  6. 결과 저장

## 설치 및 초기화

### 1. 패키지 설치
```bash
cd /home/gil/doc-agent/backend
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 데이터 초기화
```bash
python scripts/initialize_pipeline_v2.py
```

이 스크립트는 다음 작업을 수행합니다:
1. CSV 파일들을 Parquet로 변환
2. DuckDB 통합 뷰 생성
3. BM25 Main Index 빌드

## 디렉토리 구조
```
backend/
├── app/
│   ├── services/
│   │   ├── text_preprocessor.py      # 전처리 및 정규화
│   │   ├── bm25_index.py              # BM25 인덱스 시스템
│   │   ├── similarity_search.py       # 유사도 검색
│   │   ├── evidence_collector.py      # 증거 수집
│   │   ├── department_recommender.py  # 부서 추천 엔진
│   │   ├── feedback_service.py        # 휴먼 피드백 서비스
│   │   └── pipeline_v2.py             # 통합 파이프라인
│   └── database/
│       └── db.py                      # DB 모델 (FeedbackModel 추가)
├── scripts/
│   ├── setup_history_db.py            # 문서 배부 이력 DB 구축
│   └── initialize_pipeline_v2.py      # Pipeline V2 초기화
└── data/
    ├── history/                       # Parquet 파일 저장소
    │   ├── history_2025_01.parquet
    │   ├── history_2025_02.parquet
    │   └── ...
    ├── history.duckdb                 # DuckDB 파일
    └── bm25_index/                    # BM25 인덱스 저장소
        ├── main_index.pkl
        ├── main_corpus.pkl
        └── main_metadata.pkl
```

## 의존성 추가
requirements.txt에 다음 패키지 추가:
- duckdb >= 1.4.0
- pyarrow >= 21.0.0
- pandas >= 2.0.0
- bm25s >= 0.2.0
- rapidfuzz >= 3.0.0
- konlpy >= 0.6.0
- scipy >= 1.13.0

## 성능 특징
1. **빠른 검색**: BM25S Blocking으로 O(N) 전수 비교를 O(K) 후보군 비교로 감소
2. **확장성**: Main + Delta Index로 실시간 추가와 검색 성능 양립
3. **정확성**: 2단계 검증 (BM25S + Levenshtein)으로 높은 정확도
4. **학습 능력**: 휴먼 피드백 루프로 지속적 개선

## 주요 개선사항
1. **과거 이력 활용**: CSV 파일 45,495건의 문서 배부 이력 전량 활용
2. **부서별 정보 보존**: 파일명에서 부서 추출하여 배부 부서 정보 정확히 보존
3. **증거 기반 추론**: LLM에게 구체적인 증거(과거 이력 + 사무분장) 제공
4. **자동화 향상**: 유사도 95% 이상 시 조기 종료로 빠른 자동 배정
5. **피드백 학습**: 담당자 수정 사항을 DB에 저장하고 향후 추론에 활용

## TODO
- [ ] API 엔드포인트 수정 (Pipeline V2 사용)
- [ ] 배부 시간 스케줄링 로직 추가
- [ ] 프론트엔드 UI 개선
- [ ] 성능 벤치마크 테스트
- [ ] 문서화 완성

## 문의
구현 관련 질문은 코드 주석과 이 문서를 참고하세요.
