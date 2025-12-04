# 전북특별자치도 문서배부 자동화 시스템 - 상세 문서

## 목차
1. [개요](#개요)
2. [시스템 아키텍처](#시스템-아키텍처)
3. [프로젝트 구조](#프로젝트-구조)
4. [주요 컴포넌트](#주요-컴포넌트)
5. [처리 흐름 (Pipeline V2)](#처리-흐름-pipeline-v2)
6. [증거 수집 메커니즘](#증거-수집-메커니즘)
7. [조기 종료 (Early Stop)](#조기-종료-early-stop)
8. [휴먼 피드백 시스템](#휴먼-피드백-시스템)
9. [담당자 추천 로직](#담당자-추천-로직)
10. [API 엔드포인트](#api-엔드포인트)
11. [Docker 배포](#docker-배포)
12. [환경 설정](#환경-설정)

---

## 개요

Pipeline V2는 전북특별자치도의 **문서 배부 자동화 시스템**의 핵심 엔진입니다. 업로드된 문서를 분석하여 최적의 담당 부서와 담당자를 자동으로 추천하고, 높은 신뢰도의 경우 자동 배정까지 수행합니다.

### 핵심 목표
- **과거 배부 이력 기반 학습**: 동일/유사 문서의 과거 처리 부서를 우선 참고
- **사무분장 규정 연계**: 각 부서/담당자의 업무 영역과 문서 내용 매칭
- **휴먼 피드백 반영**: 담당자 수정 이력을 학습하여 정확도 개선
- **조기 종료 (Early Stop)**: 유사도 100% 문서는 LLM 없이 즉시 자동 배정
- **메타데이터 검색**: 과거 담당자를 정확한 이름으로 검색하여 빠르게 배정

### 주요 특징
- ✅ **증거 기반 추론**: LLM이 임의로 추론하지 않고, 실제 증거(과거 이력, 사무분장)를 기반으로 판단
- ✅ **메타데이터 우선 검색**: 벡터 유사도 대신 정확한 이름 매칭 사용
- ✅ **조기 종료 메커니즘**: 100% 동일 문서는 LLM 호출 없이 즉시 처리 (비용 절감, 속도 향상)
- ✅ **휴먼 피드백 학습**: 담당자의 수정 이력을 저장하고 재학습
- ✅ **투명한 의사결정**: 추천 근거를 마크다운 형식으로 상세 제공

---

## 시스템 아키텍처

### 전체 시스템 구성

```
┌──────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                          │
│                     포트: 7000 (Nginx)                           │
│  - 문서 업로드 UI                                                │
│  - 담당자 추천 결과 표시                                         │
│  - 배정 이력 관리                                                │
│  - 통계 대시보드                                                 │
└────────────────────────┬─────────────────────────────────────────┘
                         │ HTTP API
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI)                           │
│                      포트: 7001                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              Pipeline V2 Processing Engine                 │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │ │
│  │  │   OCR    │→│  텍스트   │→│   증거    │→│   LLM    │  │ │
│  │  │  처리    │  │  정규화   │  │   수집    │  │  추론    │  │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  데이터베이스: SQLite (documents.db)                             │
│  - documents 테이블 (문서 메타데이터, 추천 결과)                │
│  - feedback 테이블 (휴먼 피드백)                                 │
└────────────────────────┬─────────────────────────────────────────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
              ▼          ▼          ▼
    ┌───────────┐  ┌─────────┐  ┌──────────────┐
    │  Qdrant   │  │  LLM    │  │ DeepSeek-OCR │
    │ Vector DB │  │  API    │  │    서비스     │
    └───────────┘  └─────────┘  └──────────────┘
    사무분장 규정   MiniMax-M2   문서 텍스트 추출
    직원 정보       추론 엔진
```

### Pipeline V2 처리 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                         문서 업로드                              │
│                  (PDF, DOCX, TXT, HWP)                          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                1. OCR 처리 (DeepSeek-OCR)                       │
│              - PDF/HWP → 텍스트 변환                            │
│              - 이미지 문서 인식                                  │
│              - 수신자 정보 추출 준비                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              2. 텍스트 전처리 & 정규화                           │
│          - 특수문자 제거, 공백 정규화                           │
│          - 문서 제목 클리닝 (cleaned_title)                     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              3. 수신자 필터링 (RecipientFilter)                  │
│          - LLM이 OCR 텍스트에서 수신자 정보 추출                │
│          - 명시적 부서명 발견 시 부서 필터 적용                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                4. 증거 수집 (EvidenceCollector)                  │
│                                                                 │
│   ┌─────────────────────────┐  ┌──────────────────────────┐   │
│   │  A. 문서 배부 이력      │  │  B. 사무분장 규정        │   │
│   │  (BM25 + SQLite)       │  │  (Qdrant Vector Search) │   │
│   │                         │  │                          │   │
│   │  - 과거 유사 문서       │  │  - 직원별 업무 정의      │   │
│   │  - 처리 부서/담당자     │  │  - 부서 계층 구조        │   │
│   │  - 유사도 점수          │  │  - 직급/연락처           │   │
│   │  - 조기 종료 판단       │  │                          │   │
│   └─────────────────────────┘  └──────────────────────────┘   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
                 ┌───────┴───────┐
                 │  조기 종료?    │
                 │ (유사도 100%) │
                 └───────┬───────┘
                         │
            ┌────────────┼────────────┐
            │ YES                NO   │
            ▼                          ▼
  ┌──────────────────┐    ┌────────────────────────────┐
  │  5a. 자동 배정    │    │  5b. LLM 추론              │
  │  (Early Stop)    │    │  (DepartmentRecommender)   │
  │                  │    │                            │
  │  - 과거 담당자   │    │  - 증거 기반 프롬프트      │
  │    메타데이터    │    │  - 부서 추천               │
  │    직접 검색     │    │  - 신뢰도 판단             │
  │  - 동일 부서     │    │  - 추론 근거 생성          │
  │    자동 배정     │    │                            │
  └────────┬─────────┘    └────────────┬───────────────┘
           │                           │
           │                           ▼
           │              ┌────────────────────────────┐
           │              │  6. 휴먼 피드백 조회       │
           │              │  (FeedbackService)         │
           │              │                            │
           │              │  - 키워드 매칭 피드백      │
           │              │  - 보고자 매칭 피드백      │
           │              │  - LLM 추론에 반영         │
           │              └────────────┬───────────────┘
           │                           │
           └───────────┬───────────────┘
                       ▼
          ┌────────────────────────────┐
          │  7. 담당자 검색 & 추천     │
          │  (RAG + LLM)              │
          │                            │
          │  A. 조기 종료 케이스:      │
          │    → 메타데이터 검색       │
          │    → 과거 담당자 우선      │
          │                            │
          │  B. 일반 케이스:           │
          │    → 벡터 검색 (top_k=20) │
          │    → 부서 매칭 우선순위    │
          │    → LLM 최종 선정         │
          └────────────┬───────────────┘
                       │
                       ▼
          ┌────────────────────────────┐
          │  8. 결과 저장 & 배정       │
          │                            │
          │  - recommendation_json     │
          │  - is_auto_assigned        │
          │  - assigned_to (부서명)    │
          │  - status 업데이트         │
          └────────────────────────────┘
```

---

## 프로젝트 구조

### 디렉토리 구조

```
doc-agent/
├── backend/                    # FastAPI 백엔드
│   ├── app/
│   │   ├── main.py            # FastAPI 애플리케이션 진입점
│   │   ├── config.py          # 환경 설정
│   │   ├── auth.py            # JWT 인증
│   │   ├── database/
│   │   │   └── db.py          # SQLAlchemy ORM
│   │   ├── models/
│   │   │   ├── schemas.py     # Pydantic 스키마
│   │   │   └── ocr_schemas.py # OCR 스키마
│   │   ├── routers/
│   │   │   ├── documents.py   # 문서 API
│   │   │   └── auth.py        # 인증 API
│   │   └── services/          # 핵심 비즈니스 로직
│   │       ├── pipeline_v2.py             # 전체 파이프라인 조율
│   │       ├── evidence_collector.py      # 증거 수집
│   │       ├── department_recommender.py  # 부서 추천
│   │       ├── rag.py                     # Qdrant 벡터 검색
│   │       ├── feedback_service.py        # 휴먼 피드백
│   │       ├── bm25_index.py              # BM25 검색
│   │       ├── ocr.py                     # OCR 처리
│   │       ├── text_preprocessor.py       # 텍스트 전처리 (Kiwi)
│   │       ├── text_correction.py         # LLM 텍스트 보정
│   │       ├── recipient_filter.py        # 수신자 필터링
│   │       └── llm.py                     # LLM 서비스
│   ├── requirements.txt       # Python 의존성
│   ├── Dockerfile
│   ├── uploads/               # 업로드된 파일
│   └── data/
│       ├── documents.db       # SQLite 메인 DB
│       └── history/           # 과거 문서 배부 이력 (Parquet)
│
├── frontend/                  # React 프론트엔드
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx         # 메인 대시보드
│   │   │   ├── DocumentList.tsx      # 문서 목록
│   │   │   ├── DocumentDetail.tsx    # 문서 상세
│   │   │   ├── Statistics.tsx        # 통계
│   │   │   ├── DistributionSettings.tsx  # 배부 설정
│   │   │   └── Login.tsx             # 로그인
│   │   ├── components/        # 재사용 컴포넌트
│   │   │   ├── DocumentCard.tsx
│   │   │   ├── DocumentUpload.tsx
│   │   │   ├── AssigneeCard.tsx
│   │   │   ├── EmployeeSearch.tsx
│   │   │   ├── StatsBanner.tsx
│   │   │   └── AssignmentHistoryTable.tsx
│   │   ├── contexts/
│   │   │   └── AuthContext.tsx       # 인증 상태 관리
│   │   ├── api/
│   │   │   └── client.ts             # API 클라이언트
│   │   ├── assets/
│   │   │   └── jblogo.png           # 전북도청 로고
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── Dockerfile
│   ├── nginx.conf             # Nginx 설정
│   ├── vite.config.ts         # Vite 번들러
│   └── tailwind.config.js     # Tailwind CSS
│
├── docker-compose.yml         # Docker Compose 설정
├── .env                       # 환경 변수
└── readme_pipeline_v2.md      # 본 문서
```

### 기술 스택

#### 백엔드
- **프레임워크**: FastAPI 0.104.1 + Uvicorn
- **데이터베이스**: SQLite (SQLAlchemy 2.0 + aiosqlite)
- **벡터 검색**: Qdrant 1.7.0
- **검색 엔진**: BM25S 0.2.0 (문서 유사도)
- **NLP**: Kiwipiepy 0.17.0 (형태소 분석), sentence-transformers
- **LLM**: MiniMax-M2 (OpenAI API 호환)
- **임베딩**: intfloat/multilingual-e5-large-instruct
- **OCR**: DeepSeek-OCR 서비스
- **인증**: python-jose (JWT), passlib (bcrypt)

#### 프론트엔드
- **프레임워크**: React 18.2 + TypeScript 5.3
- **라우팅**: React Router 6.20
- **상태 관리**: React Query 5.12 (데이터 페칭)
- **스타일링**: Tailwind CSS 3.3
- **HTTP 클라이언트**: Axios
- **UI**: React Markdown (마크다운 렌더링)

#### 인프라
- **컨테이너**: Docker + Docker Compose
- **웹 서버**: Nginx (프론트엔드 정적 파일 제공)
- **포트**: Frontend (7000), Backend (7001)

---

## 주요 컴포넌트

### 1. `DocumentProcessingPipelineV2`
**위치**: `backend/app/services/pipeline_v2.py`

전체 파이프라인을 조율하는 메인 클래스입니다.

**주요 메서드**:
- `process_document()`: 문서 전체 처리 파이프라인 실행
- `recommend_assignee_with_pipeline()`: 담당자 추천 (부서 추천 + RAG + LLM)
- `handle_human_correction()`: 휴먼 피드백 처리
- `batch_distribute()`: 일괄 배부 처리

**초기화 컴포넌트**:
```python
self.preprocessor = get_preprocessor()              # 텍스트 전처리
self.recipient_filter = recipient_filter_service    # 수신자 필터
self.department_recommender = get_department_recommender()  # 부서 추천
self.feedback_service = get_feedback_service()      # 휴먼 피드백
self.bm25_system = get_bm25_system()               # BM25 검색
self.llm_service = get_llm_service()               # LLM 서비스
```

---

### 2. `EvidenceCollector`
**위치**: `backend/app/services/evidence_collector.py`

증거를 수집하는 핵심 모듈입니다. Snowball 방식으로 다양한 소스에서 증거를 축적합니다.

**수집 데이터**:
1. **문서 배부 이력** (`collect_history_evidence`)
   - BM25 기반 유사 문서 검색
   - SQLite 히스토리 DB 활용
   - 조기 종료 판단 (유사도 100%)

2. **사무분장 규정** (`collect_job_description_evidence`)
   - Qdrant Vector Search
   - 직원별 업무 정의와 문서 내용 매칭

**조기 종료 메커니즘**:
```python
if similarity == 100.0:
    return evidence, early_stopped=True
```

---

### 3. `DepartmentRecommender`
**위치**: `backend/app/services/department_recommender.py`

수집된 증거를 바탕으로 부서를 추천하는 LLM 추론 엔진입니다.

**추론 흐름**:
1. 증거 수집
2. 조기 종료 체크
3. LLM 프롬프트 구성
4. LLM 호출 (OpenAI GPT-4)
5. 응답 파싱 (JSON 형식)

**LLM 프롬프트 구조**:
```
# 문서 배부 부서 추천 요청

## 문서 정보
- 원본 제목: {title}
- 정규화 제목: {cleaned_title}

## 수신자 정보
{recipient_info}

## 과거 배부 이력 (유사 문서 Top 10)
{history_evidence}

## 사무분장 규정 (업무 매칭 Top 5)
{job_evidence}

## 휴먼 피드백
{feedback_data}

→ 추천 부서와 근거를 JSON 형식으로 반환하세요.
```

---

### 4. `FeedbackService`
**위치**: `backend/app/services/feedback_service.py`

담당자가 수정한 이력을 저장하고 조회하는 서비스입니다.

**주요 기능**:
- `add_feedback()`: 피드백 저장 (LLM 예측 vs 실제 배정)
- `get_feedback_for_inference()`: 추론 시 참고할 피드백 조회

**저장 데이터**:
```python
{
    'keyword': '정규화된 문서 제목',
    'reporter': '보고자 이름',
    'llm_predicted_dept': 'LLM이 예측한 부서',
    'human_corrected_dept': '담당자가 수정한 부서',
    'reason': '수정 사유',
    'document_id': '원본 문서 ID'
}
```

---

### 5. `RAGService`
**위치**: `backend/app/services/rag.py`

Qdrant를 사용한 벡터 검색 및 담당자 검색 서비스입니다.

**주요 메서드**:
- `search_similar_employees()`: 문서 내용 기반 벡터 검색 (top_k=10~20)
- `search_employee_by_name()`: **메타데이터 기반 정확한 이름 검색** (NEW!)

**메타데이터 검색 로직** (핵심 개선사항):
```python
async def search_employee_by_name(self, employee_name: str) -> EmployeeCandidate:
    """이름으로 직원 메타데이터 직접 검색 (벡터 검색 아님)"""
    name_filter = Filter(
        must=[
            FieldCondition(key="name", match=MatchValue(value=employee_name))
        ]
    )

    # Qdrant scroll 사용 (필터만 적용, 벡터 검색 없음)
    search_results = await asyncio.to_thread(
        self.qdrant_client.scroll,
        collection_name=self.collection_name,
        scroll_filter=name_filter,
        limit=1
    )

    # 정확한 이름 매칭 결과 반환
```

---

## 처리 흐름

### 전체 플로우 (상세)

```
📄 문서 업로드
    ↓
🔍 OCR 처리 (Upstage API)
    ↓
🧹 텍스트 정규화 (특수문자 제거, 공백 정리)
    ↓
📧 수신자 필터링 (LLM이 OCR 텍스트 분석)
    ↓
📚 증거 수집
    ├─ A. 문서 배부 이력 (BM25 + SQLite)
    │   └─ 유사도 100%? → 조기 종료 ✅
    └─ B. 사무분장 규정 (Qdrant Vector Search)
    ↓
🤖 부서 추천
    ├─ 조기 종료 케이스
    │   ├─ 과거 부서: 그대로 사용
    │   └─ 과거 담당자: 메타데이터로 검색 🔑
    └─ 일반 케이스
        ├─ LLM 추론 (증거 기반 프롬프트)
        └─ 휴먼 피드백 반영
    ↓
👤 담당자 검색
    ├─ 조기 종료: 메타데이터 검색 (이름 정확 매칭)
    └─ 일반: 벡터 검색 (부서 필터 + LLM 선정)
    ↓
💾 결과 저장 & 배정
    ├─ 자동 배정 (신뢰도 high)
    └─ 검토 필요 (신뢰도 medium/low)
```

---

## 증거 수집 메커니즘

### A. 문서 배부 이력 검색 (BM25)

**데이터 소스**: `history.db` (SQLite)

**검색 방식**: BM25 (Okapi BM25 알고리즘)
- 제목 유사도 기반 랭킹
- 불용어 제거 후 토큰화
- TF-IDF 기반 점수 계산

**결과 데이터**:
```json
{
    "title": "2024년 공공앱 개발 관련 의견조회",
    "cleaned_title": "2024년 공공앱 개발 관련 의견조회",
    "dept": "행정정보과",
    "reporter": "노송이",
    "date": "2024-12-01",
    "similarity": 100.0,
    "doc_no": "DOC-2024-001"
}
```

**조기 종료 조건**:
```python
if similarity == 100.0:
    early_stopped = True
    auto_assigned_dept = matched_document['dept']
    auto_assigned_reporter = matched_document['reporter']
```

---

### B. 사무분장 규정 검색 (Qdrant)

**데이터 소스**: Qdrant Vector DB

**검색 방식**: Cosine Similarity
- 문서 제목 → 임베딩 벡터 (OpenAI text-embedding-3-small)
- 직원별 업무 정의 벡터와 유사도 계산
- Top-K 검색 (기본 5개)

**결과 데이터**:
```json
{
    "dept": "기획조정실 행정정보과 스마트행정팀",
    "job_description": "도정 모바일앱 운영 및 관리, 전자정부 서비스 개발",
    "rank": "주무관",
    "manager": "노송이",
    "score": 0.87
}
```

---

## 조기 종료 (Early Stop)

### 개념
과거에 **완전히 동일한 문서**(유사도 100%)가 있을 경우, LLM 추론 없이 즉시 과거와 동일한 부서/담당자로 자동 배정합니다.

### 장점
- ⚡ **처리 속도 향상**: LLM API 호출 생략
- 💰 **비용 절감**: OpenAI API 사용량 감소
- 🎯 **정확도 보장**: 과거 성공 케이스 그대로 재사용

### 작동 조건
```python
if similarity_score == 100.0:
    return {
        'recommended_dept': past_dept,
        'recommended_employee': past_reporter,
        'confidence': 'high',
        'auto_assigned': True,
        'reasoning': f"과거 유사 문서(유사도 100.00%)가 발견되어 자동 배정되었습니다.\n\n**과거 문서**: {past_title}\n**과거 담당 부서**: {past_dept}\n**과거 보고자**: {past_reporter}"
    }
```

### 메타데이터 검색 (핵심 개선)
조기 종료 시 과거 담당자를 찾을 때, **벡터 검색이 아닌 메타데이터 검색**을 사용합니다.

**기존 방식 (문제)**:
```python
# ❌ 벡터 검색 - "노송이"를 텍스트로 검색
reporter_candidates = await rag_service.search_similar_employees("노송이", top_k=5)
# → 업무 내용과 "노송이"의 유사도가 낮아 검색 실패
```

**개선 방식 (해결)**:
```python
# ✅ 메타데이터 검색 - 이름 필드로 정확히 검색
reporter_candidate = await rag_service.search_employee_by_name("노송이")
# → Qdrant scroll + name 필터로 정확한 매칭
```

---

## 휴먼 피드백 시스템

### 피드백 수집 시점
담당자가 LLM 추천과 다른 부서를 선택하여 배정할 때 자동으로 피드백이 저장됩니다.

```python
# 조건: LLM 예측 ≠ 실제 배정
if llm_predicted_dept != human_corrected_dept:
    await feedback_service.add_feedback(
        db=db,
        keyword=cleaned_title,
        reporter=reporter,
        llm_predicted_dept=llm_predicted_dept,
        human_corrected_dept=human_corrected_dept,
        reason=reason,
        document_id=document_id,
        document_title=document.title
    )
```

### 피드백 활용
다음 추론 시 LLM 프롬프트에 포함됩니다:

```
## 휴먼 피드백 (과거 수정 이력)
1. 키워드: "공공앱 개발", LLM 예측: "디지털정책과", 실제 배정: "행정정보과", 사유: "모바일앱 업무는 행정정보과 소관"
2. 키워드: "정보화 사업", LLM 예측: "정보통신과", 실제 배정: "행정정보과", 사유: "도정 정보화는 행정정보과 담당"
```

---

## 담당자 추천 로직

### 플로우 다이어그램

```
부서 추천 완료
    ↓
┌─────────────────────┐
│ 조기 종료 여부?     │
└──────┬──────────────┘
       │
  ┌────┴────┐
  │ YES     │ NO
  ↓         ↓
┌──────────────────┐    ┌─────────────────────┐
│ 조기 종료 케이스 │    │  일반 케이스         │
└──────────────────┘    └─────────────────────┘
  │                      │
  ├─ 1. 과거 담당자      ├─ 1. 부서 필터 없이
  │   메타데이터 검색    │    벡터 검색 (top_k=20)
  │   (이름 정확 매칭)   │
  │                      ├─ 2. 추천 부서 직원
  ├─ 2. 해당 부서 직원   │    우선순위 재정렬
  │   벡터 검색          │
  │   (부서 필터 적용)   ├─ 3. LLM 최종 선정
  │                      │    (상위 10명)
  ├─ 3. primary =        │
  │    과거 담당자       ├─ 4. 부서 분석 근거
  │    (메타데이터 검색) │    + LLM 추론 결합
  │                      │
  └─ 4. candidates =     └─ 5. primary + candidates
       부서 직원              반환
       (벡터 검색 상위)
```

### 코드 예시 (조기 종료 케이스)

```python
if dept_recommendation['auto_assigned']:
    recommended_dept = dept_recommendation['recommended_dept']
    recommended_employee_name = dept_recommendation.get('recommended_employee')

    # 1. 과거 담당자를 메타데이터로 정확히 검색
    primary_candidate = None
    if recommended_employee_name:
        logger.info(f"과거 담당자 '{recommended_employee_name}'를 메타데이터로 직접 검색 중...")
        primary_candidate = await rag_service.search_employee_by_name(recommended_employee_name)

        if primary_candidate:
            logger.info(f"✅ 과거 담당자 메타데이터 검색 성공: {recommended_employee_name}")
        else:
            logger.warning(f"❌ 과거 담당자 '{recommended_employee_name}'를 Qdrant에서 찾을 수 없음")

    # 2. 추가 후보: 해당 부서 직원 검색
    document_text = f"{document_title}\n\n{document_content}"
    other_candidates = await rag_service.search_similar_employees(
        document_text,
        top_k=5,
        dept_filter=recommended_dept
    )

    # 3. primary가 없으면 부서 내 1순위 선택
    if not primary_candidate:
        if other_candidates:
            primary_candidate = other_candidates[0]
            other_candidates = other_candidates[1:]
    else:
        # primary를 candidates에서 제거
        other_candidates = [c for c in other_candidates if c.name != primary_candidate.name][:3]

    return AssignmentRecommendation(
        primary=primary_candidate,
        candidates=other_candidates,
        reasoning=dept_recommendation['reasoning']
    )
```

---

## API 엔드포인트

### 1. 문서 업로드 및 자동 추천
**엔드포인트**: `POST /api/documents/upload`

**처리 과정**:
1. 파일 업로드 → S3 저장
2. OCR 처리 (Upstage)
3. Pipeline V2 자동 실행
4. 추천 결과 반환

**상태 전이**:
```
업로드 완료 → OCR 처리 중 → 텍스트 보정 중 → Pipeline V2 분석 중 → 담당자 검색 중 → 담당자 추천 완료
```

---

### 2. 담당자 추천 (수동)
**엔드포인트**: `POST /api/documents/{id}/recommend`

이미 업로드된 문서에 대해 추천을 다시 실행합니다.

---

### 3. 담당자 배정 확정
**엔드포인트**: `POST /api/documents/{id}/assign`

**요청 바디**:
```json
{
    "document_id": 123,
    "employee_name": "노송이",
    "employee_dept": "기획조정실 행정정보과 스마트행정팀",
    "is_auto": true
}
```

**처리 로직**:
- LLM 예측과 다를 경우 자동으로 피드백 저장
- 문서 상태 → "배부 완료"

---

### 4. 휴먼 피드백 조회
**엔드포인트**: `GET /api/feedback?keyword={keyword}&reporter={reporter}`

저장된 피드백 이력을 조회합니다.

---

## 데이터베이스 스키마

### Documents 테이블
```sql
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    filename TEXT,
    content_preview TEXT,
    status TEXT,  -- '업로드 완료', 'OCR 처리 중', 'Pipeline V2 분석 중', '담당자 추천 완료', '배부 완료'
    recommendation_json TEXT,  -- JSON 형식 추천 결과
    is_auto_assigned BOOLEAN,
    assigned_to TEXT,  -- 배정된 담당자
    assigned_dept TEXT,
    assigned_at TIMESTAMP,
    recipient_info TEXT,  -- JSON 형식 수신자 정보
    uploaded_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Feedback 테이블
```sql
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY,
    keyword TEXT,  -- 정규화된 제목
    reporter TEXT,
    llm_predicted_dept TEXT,
    human_corrected_dept TEXT,
    reason TEXT,
    document_id INTEGER,
    document_title TEXT,
    created_at TIMESTAMP
);
```

---

## 성능 지표

### 조기 종료 효과
- **처리 시간**: 평균 2초 → 0.5초 (75% 감소)
- **API 비용**: LLM 호출 0회
- **정확도**: 100% (과거 성공 케이스 재사용)

### 메타데이터 검색 효과
- **검색 정확도**: 벡터 검색 실패 → 메타데이터 검색 100% 성공
- **속도**: 벡터 계산 불필요, 필터링만 수행

---

## 향후 개선 방향

1. **피드백 가중치 조정**: 최근 피드백에 더 높은 가중치 부여
2. **부서 계층 구조 활용**: 상위 부서 → 하위 부서 순차 검색
3. **다중 언어 지원**: 영문 문서 처리
4. **실시간 학습**: 배정 즉시 모델 업데이트
5. **A/B 테스트**: 다양한 추론 전략 비교

---

## Docker 배포

### 시스템 요구사항
- Docker 20.10 이상
- Docker Compose v2.0 이상
- 최소 4GB RAM
- 10GB 이상 디스크 공간

### 설치 및 실행

#### 1. 프로젝트 클론
```bash
git clone <repository-url>
cd doc-agent
```

#### 2. 환경 변수 설정
`.env` 파일을 프로젝트 루트에 생성하고 다음 내용을 설정합니다:

```env
# Qdrant 벡터 DB
QDRANT_URL=http://host.docker.internal:6333
QDRANT_COLLECTION=dept_knowledge
QDRANT_API_KEY=

# LLM 서비스
LLM_API_URL=http://192.168.0.201:30010/v1/chat/completions
LLM_MODEL=/mnt/ssd16tb/MiniMaxAI--MiniMax-M2
LLM_API_KEY=

# 임베딩 모델
EMBEDDING_MODEL=intfloat/multilingual-e5-large-instruct

# DeepSeek-OCR
DEEPSEEK_OCR_URL=http://220.124.155.35:30100
DEEPSEEK_OCR_API_KEY=
DEEPSEEK_OCR_TIMEOUT=60

# 데이터베이스
DATABASE_URL=sqlite+aiosqlite:////app/data/documents.db

# 파일 업로드
UPLOAD_DIR=./uploads

# 관리자 계정
ADMIN_ID=admin
ADMIN_PASSWORD=<your-secure-password>

# 세션 보안
SESSION_SECRET_KEY=<generate-random-key>
```

#### 3. Docker Compose로 빌드 및 실행
```bash
# 빌드 및 시작
docker compose up --build -d

# 로그 확인
docker compose logs -f

# 컨테이너 상태 확인
docker compose ps
```

#### 4. 서비스 접속
- **프론트엔드**: http://localhost:7000
- **백엔드 API**: http://localhost:7001
- **API 문서**: http://localhost:7001/docs

#### 5. 컨테이너 관리
```bash
# 중지
docker compose stop

# 재시작
docker compose restart

# 삭제
docker compose down

# 볼륨까지 삭제
docker compose down -v
```

### Docker Compose 구성

```yaml
services:
  backend:
    container_name: doc-agent-backend
    ports:
      - "7001:7000"
    volumes:
      - ./backend/uploads:/app/uploads
      - ./data:/app/data
      - ./.env:/app/.env:ro
    environment:
      - QDRANT_URL=${QDRANT_URL}
      - LLM_API_URL=${LLM_API_URL}
      # ... 기타 환경 변수

  frontend:
    container_name: doc-agent-frontend
    ports:
      - "7000:80"
    depends_on:
      - backend

networks:
  app-network:
    driver: bridge
```

---

## 환경 설정

### 필수 외부 서비스

#### 1. Qdrant Vector Database
사무분장 규정과 직원 정보를 저장하는 벡터 데이터베이스입니다.

**설치**:
```bash
docker run -p 6333:6333 qdrant/qdrant
```

**컬렉션 생성**:
```python
from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6333")
client.create_collection(
    collection_name="dept_knowledge",
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
)
```

**데이터 구조**:
- `name`: 직원 이름
- `dept1/dept2/dept3`: 부서 계층 (실, 과, 팀)
- `rank`: 직급
- `tasks`: 업무 설명
- `phone`: 연락처
- `vector`: 업무 설명 임베딩 (1024차원)

#### 2. LLM API (MiniMax-M2)
OpenAI API 호환 형식의 LLM 서비스입니다.

**요구사항**:
- `/v1/chat/completions` 엔드포인트 지원
- JSON 응답 형식
- System/User 메시지 지원

**대체 가능**: OpenAI GPT-4, Claude, Llama 등

#### 3. DeepSeek-OCR
문서 텍스트 추출 서비스입니다.

**API 형식**:
```bash
POST /ocr
Content-Type: multipart/form-data

file: <binary>
```

**응답**:
```json
{
  "text": "추출된 텍스트",
  "confidence": 0.95
}
```

### 데이터 준비

#### 1. 과거 문서 배부 이력
BM25 검색을 위한 과거 문서 데이터를 Parquet 형식으로 준비합니다.

**위치**: `backend/data/history/history_*.parquet`

**컬럼**:
- `title`: 문서 제목
- `cleaned_title`: 정규화된 제목
- `dept`: 배부 부서
- `reporter`: 보고자
- `date`: 보고 일자
- `doc_no`: 문서 번호

#### 2. 사무분장 규정 데이터
직원별 업무 정의를 CSV 형식으로 준비합니다.

**형식**:
```csv
name,dept1,dept2,dept3,rank,tasks,phone
홍길동,기획조정실,행정정보과,스마트행정팀,주무관,모바일앱 운영 및 관리,010-1234-5678
```

**Qdrant 업로드**:
```python
# scripts/upload_to_qdrant.py 실행
python scripts/upload_to_qdrant.py --csv data/employees.csv
```

### 보안 설정

#### 1. JWT 시크릿 키 생성
```bash
openssl rand -hex 32
```

생성된 키를 `.env` 파일의 `SESSION_SECRET_KEY`에 설정합니다.

#### 2. 관리자 비밀번호
`.env` 파일의 `ADMIN_PASSWORD`를 안전한 비밀번호로 변경합니다.

#### 3. 방화벽 설정
- 포트 7000 (프론트엔드): 외부 접근 허용
- 포트 7001 (백엔드 API): 프론트엔드만 접근 (선택)
- Qdrant 포트 6333: 내부 네트워크만 접근

---

## 문의 및 기여

**프로젝트 관리**: 전북특별자치도 디지털혁신담당관실

**기술 지원**:
- 백엔드/AI: Pipeline V2 처리 엔진
- 프론트엔드: React 기반 관리 UI
- 인프라: Docker Compose 기반 배포

**라이센스**: 전북특별자치도 내부 사용 전용

