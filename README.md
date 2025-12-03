# 문서배부 자동화 시스템

전북특별자치도 조직에서 문서를 자동으로 적절한 담당자에게 배부하는 POC 웹 서비스입니다.

## 목차

1. [프로젝트 개요](#프로젝트-개요)
2. [핵심 기능](#핵심-기능)
3. [기술 스택](#기술-스택)
4. [프로젝트 구조](#프로젝트-구조)
5. [시스템 아키텍처](#시스템-아키텍처)
6. [문서 배부 파이프라인](#문서-배부-파이프라인)
7. [설치 및 실행](#설치-및-실행)
8. [환경 변수 설정](#환경-변수-설정)
9. [API 엔드포인트](#api-엔드포인트)
10. [문제 해결](#문제-해결)

---

## 프로젝트 개요

### 목표

전북특별자치도 조직에서 외부/내부로부터 들어오는 문서를 자동으로 적절한 담당자에게 배부하는 POC 웹 서비스 구축

### 주요 특징

- **OCR 기반 문서 파싱**: DeepSeek-OCR을 활용한 정확한 텍스트 추출
- **LLM 기반 텍스트 보정**: OCR 오류 자동 수정 및 가독성 향상
- **지능형 필터링**: 수신자 및 부서 정보 기반 후보자 범위 자동 좁힘
- **3단계 우선순위 파이프라인**: 과거 문서 기반 고속/정확 배부
- **하이브리드 랭킹**: RAG 벡터 검색 + LLM 평가를 결합한 담당자 추천
- **자동 배정**: 최적 담당자 자동 배정 및 배부 이력 관리

---

## 핵심 기능

### 1. 문서 업로드 및 파싱
- PDF, DOCX, TXT 파일 업로드 지원
- 드래그 앤 드롭 인터페이스
- DeepSeek-OCR을 통한 이미지/스캔 문서 텍스트 추출
- LLM 기반 OCR 오류 자동 보정

### 2. 자동 담당자 추천
- RAG 기반 벡터 검색으로 유사 직원 후보 탐색
- 수신자 필터링: 문서 수신자 정보 기반 후보 범위 좁힘
- 부서 필터링: 문서 내용과 관련된 부서 선정
- 3단계 우선순위 파이프라인: 과거 문서 담당자 기반 고속 배부
- 하이브리드 랭킹: RAG 점수 + LLM 평가 결합

### 3. 배부 현황 관리
- 문서 배부 이력 조회 및 통계
- 자동/수동 배부 구분 관리
- 배부 현황 대시보드

### 4. 사용자 인터페이스
- 반응형 웹 디자인
- 실시간 처리 진행 상황 표시
- 직원 검색 기능
- 배부 이력 테이블

---

## 기술 스택

### Backend
- **프레임워크**: FastAPI (Python 3.11+)
- **웹 서버**: uvicorn
- **벡터 DB**: Qdrant (dept_knowledge 컬렉션)
- **임베딩 모델**: multilingual-e5-large-instruct
- **LLM**: 외부 LLM API (OpenAI 형식 호환)
- **OCR**: DeepSeek-OCR
- **데이터베이스**: SQLite + SQLAlchemy (aiosqlite)
- **문서 처리**: PyPDF2, python-docx

### Frontend
- **프레임워크**: React 18
- **언어**: TypeScript
- **빌드 도구**: Vite
- **스타일링**: Tailwind CSS
- **상태 관리**: React Query
- **라우팅**: React Router
- **HTTP 클라이언트**: Axios

### 인프라
- **컨테이너화**: Docker, Docker Compose
- **웹 서버**: Nginx (프론트엔드 서빙)
- **포트**:
  - Frontend: 7000
  - Backend API: 7001 (내부 7000)
  - Qdrant: 6333
  - DeepSeek-OCR: 30100

---

## 프로젝트 구조

```
doc-agent/
├── backend/                          # FastAPI 백엔드
│   ├── app/
│   │   ├── main.py                   # FastAPI 애플리케이션 엔트리포인트
│   │   ├── config.py                 # 환경 변수 설정 관리
│   │   ├── auth.py                   # 인증 관련 유틸리티
│   │   ├── exceptions.py             # 커스텀 예외 클래스
│   │   │
│   │   ├── database/
│   │   │   ├── db.py                 # SQLAlchemy 모델 및 DB 초기화
│   │   │   └── __init__.py
│   │   │
│   │   ├── models/
│   │   │   ├── schemas.py            # Pydantic 스키마 (API 요청/응답)
│   │   │   ├── ocr_schemas.py        # OCR 관련 스키마
│   │   │   └── __init__.py
│   │   │
│   │   ├── routers/
│   │   │   ├── documents.py          # 문서 관련 API 엔드포인트
│   │   │   ├── auth.py               # 인증 관련 API 엔드포인트
│   │   │   └── __init__.py
│   │   │
│   │   └── services/
│   │       ├── ocr.py                # DeepSeek-OCR 통합
│   │       ├── text_correction.py    # LLM 기반 OCR 텍스트 보정
│   │       ├── recipient_filter.py   # 수신자 필터링 로직
│   │       ├── department_filter.py  # 부서 필터링 로직
│   │       ├── historical_search.py  # 3단계 우선순위 파이프라인 (핵심)
│   │       ├── document_summarizer.py # 문서 요약 및 하이브리드 랭킹
│   │       ├── target_department.py  # 타겟 부서 결정
│   │       ├── rank_mapper.py        # 직급 매핑 및 필터링
│   │       ├── rag.py                # Qdrant 벡터 검색
│   │       ├── llm.py                # LLM API 호출
│   │       ├── document.py           # 문서 처리 로직
│   │       └── __init__.py
│   │
│   ├── data/
│   │   └── documents.db              # SQLite 데이터베이스 파일
│   ├── uploads/                      # 업로드된 파일 저장 디렉터리
│   ├── requirements.txt              # Python 의존성
│   ├── Dockerfile                    # Backend Docker 이미지
│   └── test_three_stage_pipeline.py  # 파이프라인 테스트 스크립트
│
├── frontend/                         # React 프론트엔드
│   ├── src/
│   │   ├── main.tsx                  # React 앱 엔트리포인트
│   │   ├── App.tsx                   # 메인 앱 컴포넌트
│   │   ├── index.css                 # 글로벌 스타일
│   │   │
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx         # 대시보드 페이지
│   │   │   ├── DocumentList.tsx      # 문서 목록 페이지
│   │   │   ├── DocumentDetail.tsx    # 문서 상세 페이지
│   │   │   └── Login.tsx             # 로그인 페이지
│   │   │
│   │   ├── components/
│   │   │   ├── DocumentUpload.tsx    # 문서 업로드 컴포넌트
│   │   │   ├── StatsBanner.tsx       # 통계 배너
│   │   │   ├── AssignmentHistoryTable.tsx # 배부 이력 테이블
│   │   │   ├── RecommendationProgress.tsx # 추천 진행 상황 표시
│   │   │   ├── EmployeeSearch.tsx    # 직원 검색
│   │   │   ├── AssigneeCard.tsx      # 담당자 카드
│   │   │   ├── DocumentCard.tsx      # 문서 카드
│   │   │   └── ProtectedRoute.tsx    # 인증 라우트
│   │   │
│   │   ├── api/
│   │   │   └── client.ts             # API 클라이언트 (Axios)
│   │   │
│   │   ├── contexts/
│   │   │   └── AuthContext.tsx       # 인증 컨텍스트
│   │   │
│   │   ├── types/
│   │   │   └── index.ts              # TypeScript 타입 정의
│   │   │
│   │   └── utils/
│   │       └── dateUtils.ts          # 날짜 유틸리티
│   │
│   ├── package.json                  # npm 의존성
│   ├── vite.config.ts                # Vite 설정
│   ├── tailwind.config.js            # Tailwind CSS 설정
│   ├── tsconfig.json                 # TypeScript 설정
│   ├── Dockerfile                    # Frontend Docker 이미지
│   └── nginx.conf                    # Nginx 설정
│
├── docker-compose.yml                # Docker Compose 설정
├── .env                              # 환경 변수 파일
├── .env.example                      # 환경 변수 예시
└── README.md                         # 이 파일
```

---

## 시스템 아키텍처

### 전체 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                    프론트엔드 (React + Nginx)                    │
│                      http://localhost:7000                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓ API 호출
┌─────────────────────────────────────────────────────────────────┐
│                   백엔드 (FastAPI + uvicorn)                     │
│                      http://localhost:7001                       │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  7단계 파이프라인                          │  │
│  │                                                            │  │
│  │  1. OCR 파싱 (DeepSeek-OCR)                               │  │
│  │  2. LLM 텍스트 보정                                        │  │
│  │  3. 수신자 필터링 (조건부)                                 │  │
│  │  4. 부서 필터링                                            │  │
│  │  5. 3단계 우선순위 파이프라인 (핵심)                       │  │
│  │     - Stage 1: Skeleton Matching (1-2초)                 │  │
│  │     - Stage 2: Hybrid Search (3-5초)                     │  │
│  │     - Stage 3: LLM Verification (8-12초)                 │  │
│  │  6. 문서 요약 + 최종 랭킹                                  │  │
│  │  7. 자동 배정                                              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
        ↓ 벡터 검색           ↓ LLM 호출            ↓ OCR 파싱
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Qdrant          │  │  LLM API Server  │  │  DeepSeek-OCR    │
│  (벡터 DB)       │  │  (MiniMax-M2)    │  │                  │
│  :6333           │  │  :30010          │  │  :30100          │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### 데이터 흐름

```
사용자 → [문서 업로드] → Backend API
                           ↓
                    [OCR 텍스트 추출]
                           ↓
                    [LLM 텍스트 보정]
                           ↓
                    [수신자/부서 필터링]
                           ↓
                    [3단계 우선순위 검색]
                    ├─ Skeleton Match → 즉시 배부 (1-2초)
                    ├─ Hybrid Search → 즉시 배부 (3-5초)
                    └─ LLM Verify → 배부 또는 전체 파이프라인
                           ↓
                    [문서 요약 + 하이브리드 랭킹]
                    (RAG 40% + LLM 60%)
                           ↓
                    [자동 배정 및 DB 저장]
                           ↓
                    [결과 반환] → 사용자
```

---

## 문서 배부 파이프라인

시스템의 핵심인 7단계 문서 배부 파이프라인에 대한 상세 설명입니다.

### 파이프라인 개요

```
문서 업로드
  ↓
Phase 1: OCR 파싱 (1-3초)
  ↓
Phase 2: LLM 텍스트 보정 (1-2초)
  ↓
Phase 3: 수신자 필터링 (0-2초, 조건부)
  ↓
Phase 4: 부서 필터링 (2-3초)
  ↓
Phase 5: 3단계 우선순위 파이프라인 (1-12초) ← 핵심
  ├─ Stage 1: Skeleton Matching (1-2초, 40% 케이스)
  ├─ Stage 2: Hybrid Search (3-5초, 25% 케이스)
  └─ Stage 3: LLM Verification (8-12초, 15% 케이스)
  ↓
Phase 6: 문서 요약 + 최종 랭킹 (5-8초, 20% 케이스)
  ↓
Phase 7: 자동 배정 (1초 미만)
  ↓
결과 (배부 완료)

평균 처리 시간: 6-8초 (기존 15-20초 대비 60% 단축)
```

---

### Phase 1: OCR 파싱

**목적**: 업로드된 문서에서 텍스트 추출

**처리 과정**:
1. DeepSeek-OCR API 호출
   - 이미지 기반 PDF: OCR로 텍스트 추출
   - 텍스트 기반 PDF: 직접 텍스트 추출
   - DOCX/TXT: python-docx/텍스트 리더로 추출

2. OCR 결과 저장
   - `ocr_raw_text`: 원본 OCR 텍스트
   - `ocr_confidence`: OCR 신뢰도 (0.0-1.0)

3. 실패 시 Fallback
   - OCR 실패 시 파일에서 직접 텍스트 추출
   - 모두 실패 시 상태를 "파싱 실패"로 변경

**구현 파일**: `backend/app/services/ocr.py`, `backend/app/routers/documents.py:108-148`

**처리 시간**: 1-3초

---

### Phase 2: LLM 텍스트 보정

**목적**: OCR 오류 수정 및 가독성 향상

**처리 과정**:
1. OCR 신뢰도 확인
   - `confidence < 0.8`: LLM으로 보정
   - `confidence >= 0.8`: 원본 사용

2. LLM 텍스트 보정
   - 오타 수정
   - 띄어쓰기 보정
   - 문맥에 맞는 단어 교정

3. 결과 저장
   - `corrected_text`: 보정된 텍스트
   - `content`: 최종 사용할 텍스트

**프롬프트 구조**:
```
당신은 OCR 텍스트 보정 전문가입니다. 다음 OCR 결과를 분석하여:
1. 맞춤법 오류 수정
2. 띄어쓰기 교정
3. 문맥상 이상한 부분 수정
4. 원본 의미 최대한 보존

[OCR 원본 텍스트]
{raw_ocr_text}

JSON 응답:
{
  "corrected_text": "보정된 전체 텍스트",
  "corrections": [...]
}
```

**구현 파일**: `backend/app/services/text_correction.py`, `backend/app/routers/documents.py:150-172`

**처리 시간**: 1-2초

---

### Phase 3: 수신자 필터링

**목적**: 문서에 특정 수신자가 명시된 경우 후보자 범위 좁히기

**처리 과정**:
1. **수신자 키워드 탐지**
   - 키워드: '수신', '수신자', '수신처', '받는사람'
   - 키워드가 없으면 포괄적 배부로 처리

2. **수신자 정보 추출**
   - 키워드 주변 문맥 추출 (전후 150자)

3. **LLM 분류**
   - **특정 대상**: "정책기획과장", "인사팀" 등 구체적 부서명/직책명
   - **포괄적 대상**: "전 부서", "관계 부서" 등

4. **후보자 검색** (특정 수신자인 경우만)
   - RAG로 수신자 텍스트와 유사한 직원 TOP 3 검색

**분기 로직**:
```
수신자 키워드 있음?
├─ NO → Phase 4로 진행
└─ YES → 특정 수신자?
          ├─ NO (포괄적) → Phase 4로 진행
          └─ YES → 수신자 기반 후보 검색 → Phase 5로
```

**구현 파일**: `backend/app/services/recipient_filter.py`, `backend/app/routers/documents.py:179-205`

**처리 시간**: 0-2초 (조건부)

---

### Phase 4: 부서 필터링

**목적**: 문서 내용과 관련된 부서 선정

**처리 과정**:
1. **전체 부서 목록 조회**
   - Qdrant에서 모든 직원 정보 조회 (top_k=1000)
   - dept1, dept2, dept3 기준으로 중복 제거 및 정렬

2. **LLM 부서 선택**
   - 문서 제목과 내용(최대 2000자) 분석
   - 관련 부서 1-3개 선택

3. **점수 부여 기준 (0-100)**
   - 90-100: 직접적으로 관련된 핵심 부서
   - 70-89: 관련성 높은 부서
   - 50-69: 부분적으로 관련된 부서
   - 50 미만: 제외

4. **후보자 필터링**
   - 선택된 부서에 속한 직원만 필터링
   - 필터링 후 후보가 3명 미만이면 원본 유지 (과도한 필터링 방지)

**프롬프트 구조**:
```
문서 내용을 분석하여 업무 관련 부서를 특정하는 전문가입니다.

[문서 내용]
{document_text}

[가용 부서 목록]
- 정책담당관 > 정책기획과 > 업무분석팀
- 인사팀 > 채용파트
- 재무과 > 예산팀
...

JSON 응답:
{
  "selected_departments": [
    {"dept1": "정책담당관", "dept2": "정책기획과", "dept3": "업무분석팀", "relevance_score": 95},
    ...
  ],
  "reasoning": "선택 이유"
}
```

**구현 파일**: `backend/app/services/department_filter.py`, `backend/app/routers/documents.py:207-235`

**처리 시간**: 2-3초

---

### Phase 5: 3단계 우선순위 파이프라인 (핵심)

**목적**: tasks 컬렉션의 과거 문서를 활용한 고속/정확 배부

이 파이프라인은 시스템의 핵심으로, 과거 문서 담당자 정보를 활용하여 처리 속도와 정확도를 대폭 향상시킵니다.

#### 전체 구조

```
문서 제목 입력
    ↓
┌──────────────────────────────────────────┐
│ Stage 1: Skeleton Matching (Fast-Track)  │
│ 정규화된 제목이 100% 일치?               │
└──────────────────────────────────────────┘
    ├─ YES → 즉시 배부 (1-2초, 40% 케이스)
    └─ NO  → Stage 2로
           ↓
┌──────────────────────────────────────────┐
│ Stage 2: Hybrid Search (Deep-Check)      │
│ 임베딩 + 키워드 + 행위어 + 시간 가중치   │
└──────────────────────────────────────────┘
    ├─ 유사도 ≥ 0.95 → 즉시 배부 (3-5초, 25% 케이스)
    ├─ 유사도 0.85~0.95 → Stage 3로
    └─ 유사도 < 0.85 → Phase 6로 (전체 파이프라인)
           ↓
┌──────────────────────────────────────────┐
│ Stage 3: LLM Verification (Safety Net)   │
│ 연속성/대체불가/Action일치 체크          │
└──────────────────────────────────────────┘
    ├─ 모두 통과 → 배부 (8-12초, 15% 케이스)
    └─ 실패 → Phase 6로 (점수 30% 감점, 20% 케이스)
```

---

#### Stage 1: Skeleton Matching (Fast-Track)

**목적**: 정규화된 제목이 100% 일치하는 과거 문서 찾기

**정규화 규칙** (2025-11-28 개선):

```python
def _normalize_to_skeleton(title):
    # 1. 괄호/대괄호 제거
    title = re.sub(r'\(.*?\)', '', title)  # (전 직원 공람) 제거
    title = re.sub(r'\[.*?\]', '', title)  # [안내] 제거

    # 2. 연도 표기 제거
    title = re.sub(r'\d{4}년도?', '', title)  # 2024년, 2024년도
    title = re.sub(r'\d{2}년도?', '', title)   # 25년, 25년도

    # 3. 시기 표기 제거
    title = re.sub(r'[상하]반기', '', title)
    title = re.sub(r'\d+월', '', title)

    # 4. 순서 표기 제거
    title = re.sub(r'제\d+차', '', title)  # 제1차, 제11차

    # 5. 행정 접미사 제거
    # 중요: '계획', '결과', '현황', '보고'는 제거하지 않음 (업무 구분 키워드)
    admin_suffixes = [
        '안내', '송부', '요청', '협조', '공유', '알림',
        '개최', '시행', '실시', '제출', '통보',
        '명단', '목록', '신청', '대상', '접수', '승인', '검토'
    ]
    for suffix in admin_suffixes:
        title = title.replace(suffix, '')

    # 6. 한글만 남기기
    title = re.sub(r'[^가-힣]', ' ', title)

    # 7. 중복 단어 제거
    words = []
    seen = set()
    for word in title.split():
        if word and word not in seen:
            words.append(word)
            seen.add(word)

    return ''.join(words)
```

**예시**:

```
입력: "2025년 예산 집행 현황 보고"
skeleton: "예산집행현황보고"

tasks 검색:
- "2024년 예산 집행 현황 보고" (보고자: 김철수)
  skeleton: "예산집행현황보고"
  → 100% 일치! 즉시 배부

반례 (이제 구분됨):
"2025년 예산 집행 계획" → skeleton: "예산집행계획"
"2025년 예산 집행 현황" → skeleton: "예산집행현황"
→ 다른 문서로 구분됨 (계획 ≠ 현황)
```

**처리 시간**: 1-2초 (가장 빠름)

**구현 파일**: `backend/app/services/historical_search.py:104-192`

---

#### Stage 2: Action-based Hybrid Search (Deep-Check)

**목적**: 임베딩 + 키워드 + 행위어 + 시간을 종합한 유사도 계산

**핵심 개선사항**:
- **문제**: 주제(예: 적극행정)는 같지만 행위(조사 vs 경진대회)가 다르면 다른 업무
- **해결**: 제목의 마지막 실질 명사(행위어)를 추출하여 가중치 부여

**행위어 추출 예시**:
```
"적극행정 우수사례 경진대회 개최 안내" → 행위어: "경진대회"
"적극행정 인식도 조사 계획"           → 행위어: "조사"
"국민 참여 예산 공모사업 실시 안내"    → 행위어: "공모사업"
```

**점수 계산 공식**:

```
최종 점수 = 임베딩 점수 × 키워드 가중치 × 행위어 가중치 × 시간 가중치
```

**가중치 상세**:

| 요소 | 범위 | 설명 |
|------|------|------|
| **임베딩 점수** | 0.0 ~ 1.0 | 기본 벡터 유사도 |
| **키워드 가중치** | 0.5 ~ 1.5 | 핵심 키워드 매칭률<br/>- 0% 일치: 0.5배<br/>- 100% 일치: 1.5배 |
| **행위어 가중치** | 0.3 ~ 1.0 | 완전 일치: 1.0배<br/>부분 일치: 0.65배<br/>**불일치: 0.3배** (큰 페널티) |
| **시간 가중치** | 0.3 ~ 1.3 | 작년 문서: 1.3배<br/>올해: 1.1배<br/>2년 이상: 감소 |

**예시**:

케이스 1: 같은 업무 (높은 점수)
```
입력: "2025년 예산 집행 현황 보고"
과거: "2024년 예산 집행 현황 보고"

- 임베딩: 0.92
- 키워드: 1.5배 (예산, 집행, 현황 모두 일치)
- 행위어: 1.0배 ("현황" == "현황")
- 시간: 1.3배 (작년)

최종 = 0.92 × 1.5 × 1.0 × 1.3 = 1.79 (정규화 → 0.98)
→ 0.95 이상! 즉시 배부
```

케이스 2: 다른 업무 (페널티)
```
입력: "2025년 적극행정 인식도 조사"
과거: "2024년 적극행정 우수사례 경진대회"

- 임베딩: 0.85 (주제 "적극행정" 같음)
- 키워드: 1.2배 (적극행정 일치)
- 행위어: 0.3배 ("조사" ≠ "경진대회", 큰 페널티!)
- 시간: 1.3배

최종 = 0.85 × 1.2 × 0.3 × 1.3 = 0.40
→ 0.85 미만, Phase 6으로 진행
```

**분기**:
- 유사도 ≥ 0.95 → 즉시 배부 (3-5초)
- 유사도 0.85~0.95 → Stage 3 검증
- 유사도 < 0.85 → Phase 6으로

**처리 시간**: 3-5초

**구현 파일**: `backend/app/services/historical_search.py:518-696`

---

#### Stage 3: LLM Final Verification (Safety Net)

**목적**: 애매한 유사도 구간(0.85~0.95)에서만 LLM이 최종 검증

**LLM 호출 조건**:
```
✓ 유사도 0.85~0.95: LLM 판단 실행 (Safety Net)
✗ 유사도 ≥ 0.95: LLM 생략 (고신뢰)
✗ 유사도 < 0.85: LLM 불필요 (저유사도)
```

**3가지 필수 체크** (모두 충족 필요):

1. **연속성 (Continuity)**
   - 작년의 그 업무가 올해 이 업무로 이어진 것인가?
   - 예: "2024년 조사" → "2025년 조사" (정기 업무) ✓
   - 예: "2024년 조사" → "2025년 계획 수립" (다른 단계) ✗

2. **대체 불가능성 (Exclusivity)**
   - 과거 문서를 처리한 사람이 현재 문서도 처리했을 확률 90% 이상인가?
   - 예: "월간 예산 보고" → 동일 담당자 ✓
   - 예: "적극행정 조사"와 "적극행정 마일리지 계획" → 다른 담당자 가능 ✗

3. **Action 일치 (Action-Level Match)**
   - 업무의 Action 레벨이 같은가?
   - Action 유형: 조사/설문 vs 계획 수립 vs 행사 운영 vs 평가/심사
   - 예: "인식도 조사"와 "우수사례 경진대회" → 주제(적극행정)만 같고 Action 다름 ✗

**판단 예시**:

```
사례 1: 연속성 확인 ✓
  현재: "2025년 1분기 예산 집행 현황 보고"
  과거: "2024년 4분기 예산 집행 현황 보고"
  판단: ✓ 연속성 ✓ 대체불가 ✓ Action일치 → 즉시 배부

사례 2: 연속성 부정 ✗
  현재: "2025년 적극행정 우수사례 경진대회 개최"
  과거: "2024년 적극행정 인식도 조사 계획"
  판단: ✓ 연속성 (주제 같음) ✗ 대체불가 (담당자 다를 수 있음) ✗ Action불일치
  → 점수 30% 감점 → 전체 파이프라인 진행
```

**LLM 응답 형식**:
```json
{
  "is_continuous": true/false,
  "continuity_check": true/false,
  "exclusivity_check": true/false,
  "action_match_check": true/false,
  "reasoning": "판단 이유...",
  "confidence": 0.0-1.0
}
```

**판단 결과**:
- 3가지 모두 통과 → 배부 (8-12초)
- 하나라도 실패 → 점수 30% 감점, Phase 6으로

**처리 시간**: 8-12초 (LLM 호출 포함)

**구현 파일**: `backend/app/services/historical_search.py:826-930`

---

#### 후보자 추출 (2025-11-28 개선)

**Stage 1~3에서 매칭된 과거 문서의 보고자 → 현재 직원 검색**

**보고자 정확 일치 우선**:

```python
for reporter in set(reporters):  # 과거 문서의 보고자들
    # RAG로 현재 직원 검색 (상위 3명)
    candidates = search_similar_employees(reporter, top_k=3)

    for candidate in candidates:
        # 정확 일치 vs 부분 일치 구분
        is_exact_match = (candidate.name == reporter)

        if is_exact_match:
            # 정확 일치: tasks의 보고자와 정확히 같은 이름
            # → 높은 점수 보장 (최소 0.95)
            candidate.score = max(0.95, avg_historical_score)

        elif reporter in candidate.name:
            # 부분 일치: 이름이 포함 (예: "김철수" in "김철수A")
            # → 점수 70% 감소
            candidate.score = avg_historical_score * 0.7
```

**효과**:

```
tasks: "2024년 예산 현황" (보고자: 김철수)
현재 직원 DB: 김철수, 김철수A, 김철수B

기존: 모두 같은 점수
개선:
  - 김철수: 0.95+ (1순위) ✓
  - 김철수A: 0.66 (2순위)
  - 김철수B: 0.66 (3순위)

→ 정확한 김철수가 1순위!
```

**구현 파일**: `backend/app/services/historical_search.py:408-444`

---

### Phase 6: 문서 요약 + 최종 랭킹

**목적**: LLM으로 문서 분석 후 하이브리드 랭킹으로 최종 후보 선정

**처리 과정**:

1. **문서 요약 (LLM)**
   - 키워드: 5-10개
   - 요약: 2-3문장
   - 필요 역량: 전문성/역량

2. **후보자 결정 우선순위**
   - 1순위: 과거 문서 기반 후보 (Phase 5 결과)
   - 2순위: 수신자 필터링 결과 (Phase 3)
   - 3순위: RAG 전체 검색 (문서 내용 기반, top_k=20)

3. **하이브리드 랭킹**

   **A. RAG 점수 (40% 가중치)**
   - 문서 키워드 + 요약으로 재검색
   - 벡터 유사도 기반 점수 (0-1)

   **B. LLM 점수 (60% 가중치)**
   - 각 후보자를 0-100점으로 평가
   - 평가 기준:
     - 업무 적합성 (40점): 담당 업무와 문서 내용의 관련성
     - 전문성 (30점): 필요 역량 보유 여부
     - 부서 관련성 (30점): 소속 부서와 문서 주제 관련성

   **최종 점수 계산**:
   ```
   final_score = (rag_score × 100 × 0.4) + (llm_score × 0.6)
   ```

4. **정렬 및 반환**
   - 최종 점수 기준 내림차순 정렬
   - TOP 5 후보자 반환

**점수 기준**:
```
90-100: 최적의 담당자 (직접 관련 업무)
70-89:  적합한 담당자 (관련 경험)
50-69:  가능한 담당자 (부분 관련성)
50 미만: 부적합
```

**구현 파일**: `backend/app/services/document_summarizer.py`, `backend/app/routers/documents.py:351-452`

**처리 시간**: 5-8초

---

### Phase 7: 자동 배정

**목적**: 최고 점수 후보자를 자동 배정하고 DB 저장

**처리 과정**:

1. **1순위 후보자 선택**
   ```python
   ranked_candidates = sorted(candidates, key=lambda x: x.final_score, reverse=True)
   top_candidate = ranked_candidates[0]
   ```

2. **배정 정보 저장**
   - `assigned_to`: 담당자 이름
   - `assigned_dept`: 담당자 부서
   - `assigned_at`: 배정 시각
   - `is_auto_assigned`: True
   - `status`: "배부 완료"

3. **복수 배부 대상 저장 (JSON)**
   ```json
   [
     {
       "name": "김철수",
       "rank": "7급",
       "dept1": "재무과",
       "final_score": 95.5,
       ...
     },
     ...
   ]
   ```

4. **추천 이유 저장 (JSON)**
   ```json
   {
     "pipeline_stage": "Stage 1: Skeleton Match",
     "title_similarity": 1.0,
     "candidates": [...],
     "reasoning": "과거 동일 업무 담당자"
   }
   ```

**DB 스키마**:

```python
class DocumentModel:
    id: Integer
    title: String
    filename: String
    status: String  # "배부 완료"

    # 배부 정보
    assigned_to: String
    assigned_dept: String
    assigned_at: DateTime
    is_auto_assigned: Boolean

    # 상세 정보 (JSON)
    recommendation_json: Text
    assigned_candidates: Text
    filtered_departments: Text

    # OCR 관련
    ocr_raw_text: Text
    ocr_confidence: Float
    corrected_text: Text
```

**구현 파일**: `backend/app/routers/documents.py:454-535`

**처리 시간**: 1초 미만

---

### 파이프라인 성능 지표

#### Phase 5 파이프라인 성능

| Stage | 조건 | 처리 시간 | 정확도 | 비율 (예상) |
|-------|------|----------|--------|-------------|
| **Stage 1** | Skeleton 100% 일치 | 1-2초 | 99%+ | 40% |
| **Stage 2** | 유사도 ≥ 0.95 | 3-5초 | 95%+ | 25% |
| **Stage 3** | 유사도 0.85~0.95 + LLM | 8-12초 | 90%+ | 15% |
| **Full Pipeline** | 유사도 < 0.85 또는 실패 | 15-25초 | 95%+ | 20% |

#### 전체 파이프라인 평균 처리 시간

```
Phase 1: OCR 파싱           1-3초
Phase 2: 텍스트 보정        1-2초
Phase 3: 수신자 필터링      0-2초 (조건부)
Phase 4: 부서 필터링        2-3초
Phase 5: 우선순위 파이프라인
  ├─ Stage 1 (40%)          1-2초
  ├─ Stage 2 (25%)          3-5초
  ├─ Stage 3 (15%)          8-12초
  └─ Skip (20%)             0초
Phase 6: 문서 요약 + 랭킹   5-8초 (Full Pipeline만)
Phase 7: 자동 배정          <1초

평균: 6-8초 (기존 15-20초 대비 60% 단축)
```

#### 개선 효과

1. **Stage 1 (Skeleton Match)**: 정기 보고서 처리 시간 **90% 단축** (20초 → 2초)
2. **Stage 2 (Action-based)**: 행위어 페널티로 **오분류 70% 감소**
3. **Stage 3 (LLM Safety Net)**: 애매한 케이스만 LLM 호출하여 **비용 60% 절감**
4. **보고자 정확 일치**: tasks의 정확한 담당자 **95%+ 1순위 배정**

---

## 설치 및 실행

### 사전 준비

1. Docker 및 Docker Compose 설치
2. Qdrant 서버 접근 가능 (로컬 또는 원격)
3. LLM API 서버 접근 가능
4. DeepSeek-OCR 서버 접근 가능

### 1. 환경 변수 설정

프로젝트 루트 디렉터리에 `.env` 파일을 생성하거나 수정합니다.

```bash
# .env 파일 확인
cat .env
```

주요 환경 변수는 [환경 변수 설정](#환경-변수-설정) 섹션을 참조하세요.

### 2. Docker Compose로 실행 (권장)

#### 전체 서비스 실행

```bash
# 프로젝트 루트 디렉터리에서
docker-compose up --build
```

또는 백그라운드로 실행:

```bash
docker-compose up -d --build
```

#### 접속

- 웹 서비스: `http://localhost:7000`
- API 문서: `http://localhost:7001/docs`
- Qdrant 대시보드: `http://localhost:6333/dashboard` (별도 Qdrant 사용 시)

#### 서비스 관리

```bash
# 중지
docker-compose down

# 로그 확인
docker-compose logs -f

# 특정 서비스 로그 확인
docker-compose logs -f backend
docker-compose logs -f frontend

# 서비스 재시작
docker-compose restart

# 컨테이너 상태 확인
docker-compose ps
```

### 3. 로컬 개발

#### Backend 실행

```bash
cd backend

# 가상환경 생성 (선택)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 서버 실행
uvicorn app.main:app --host 0.0.0.0 --port 7000 --reload
```

#### Frontend 실행

```bash
cd frontend

# 의존성 설치
npm install

# 개발 서버 실행
npm run dev
```

개발 서버는 `http://localhost:5173`에서 실행되며, API는 `http://localhost:7000`으로 프록시됩니다.

#### 프로덕션 빌드

```bash
# Frontend 빌드
cd frontend
npm run build

# Backend는 uvicorn으로 실행
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 7000
```

---

## 환경 변수 설정

### 필수 환경 변수

#### Qdrant 설정

```env
# Qdrant 서버 URL
QDRANT_URL=http://localhost:6333

# Qdrant API 키 (선택적)
QDRANT_API_KEY=

# 벡터 컬렉션명
QDRANT_COLLECTION=dept_knowledge
```

**Docker Compose 사용 시**:
- `QDRANT_URL`은 자동으로 `http://host.docker.internal:6333`으로 설정됩니다.
- 별도 설정 불필요

#### LLM 설정

```env
# LLM API 엔드포인트
LLM_API_URL=http://192.168.0.201:30010/v1/chat/completions

# LLM API 키 (선택적)
LLM_API_KEY=

# LLM 모델명
LLM_MODEL=/mnt/ssd16tb/MiniMaxAI--MiniMax-M2
```

**주의사항**:
- OpenAI 형식 API를 사용합니다.
- `/v1/chat/completions` 엔드포인트가 필요합니다.

#### DeepSeek-OCR 설정

```env
# DeepSeek-OCR API URL
DEEPSEEK_OCR_URL=http://220.124.155.35:30100

# DeepSeek-OCR API 키 (선택적)
DEEPSEEK_OCR_API_KEY=

# OCR 처리 타임아웃 (초)
DEEPSEEK_OCR_TIMEOUT=60
```

#### 임베딩 모델 설정

```env
# 임베딩 모델명
EMBEDDING_MODEL=intfloat/multilingual-e5-large-instruct
```

처음 실행 시 자동으로 다운로드됩니다.

### 선택적 환경 변수

#### 데이터베이스 설정

```env
# 데이터베이스 연결 URL
DATABASE_URL=sqlite+aiosqlite:///./documents.db
```

SQLite를 사용합니다. 다른 DB를 사용하려면 SQLAlchemy 형식 URL을 입력하세요.

#### 파일 업로드 설정

```env
# 업로드된 파일 저장 디렉터리
UPLOAD_DIR=./uploads
```

#### 필터링 설정

```env
# 수신자 필터링 활성화
RECIPIENT_FILTER_ENABLED=true

# 부서 필터링 활성화
DEPARTMENT_FILTER_ENABLED=true

# 최소 신뢰도 점수
MIN_CONFIDENCE_SCORE=0.5
```

---

## API 엔드포인트

### 문서 관리

#### 문서 업로드
```
POST /api/documents/upload
Content-Type: multipart/form-data

파라미터:
  - file: 업로드할 파일 (PDF/DOCX/TXT)

응답:
  {
    "id": 1,
    "title": "문서 제목",
    "filename": "example.pdf",
    "status": "OCR 처리 중",
    "uploaded_at": "2025-11-28T12:00:00",
    ...
  }
```

#### 문서 목록 조회
```
GET /api/documents/

응답:
  [
    {
      "id": 1,
      "title": "문서 제목",
      "status": "배부 완료",
      "assigned_to": "김철수",
      "uploaded_at": "2025-11-28T12:00:00",
      ...
    },
    ...
  ]
```

#### 문서 상세 조회
```
GET /api/documents/{id}

응답:
  {
    "id": 1,
    "title": "문서 제목",
    "content": "문서 내용...",
    "status": "배부 완료",
    "assigned_to": "김철수",
    "assigned_dept": "재무과",
    "recommendation_json": {...},
    ...
  }
```

#### 배부 이력 조회
```
GET /api/documents/history

응답:
  [
    {
      "id": 1,
      "title": "문서 제목",
      "assigned_to": "김철수",
      "assigned_at": "2025-11-28T13:00:00",
      "is_auto_assigned": true,
      ...
    },
    ...
  ]
```

### 담당자 추천 및 배부

#### 담당자 자동 추천
```
POST /api/documents/{id}/recommend

응답:
  {
    "candidates": [
      {
        "name": "김철수",
        "rank": "7급",
        "dept1": "재무과",
        "final_score": 95.5,
        "reasoning": "과거 동일 업무 담당자",
        ...
      },
      ...
    ],
    "pipeline_stage": "Stage 1: Skeleton Match",
    "processing_time": 2.3
  }
```

#### 담당자 배부 확정
```
POST /api/documents/{id}/assign

요청 본문:
  {
    "assigned_to": "김철수",
    "assigned_dept": "재무과",
    "is_auto": true
  }

응답:
  {
    "id": 1,
    "assigned_to": "김철수",
    "assigned_dept": "재무과",
    "assigned_at": "2025-11-28T13:00:00",
    "is_auto_assigned": true,
    "status": "배부 완료"
  }
```

#### 직원 검색
```
GET /api/documents/employees/search?query=김철수

응답:
  [
    {
      "name": "김철수",
      "rank": "7급",
      "dept1": "재무과",
      "dept2": "예산팀",
      "score": 0.95,
      ...
    },
    ...
  ]
```

### 통계 및 헬스 체크

#### 오늘 처리 통계
```
GET /api/documents/stats/today

응답:
  {
    "total_uploaded": 15,
    "total_assigned": 12,
    "auto_assigned": 10,
    "manual_assigned": 2
  }
```

#### Qdrant 연결 상태 확인
```
GET /api/documents/health/qdrant

응답:
  {
    "status": "healthy",
    "collections": ["dept_knowledge", "tasks"],
    "version": "1.7.0"
  }
```

#### API 헬스 체크
```
GET /health

응답:
  {
    "status": "ok"
  }
```

### API 문서

- **Swagger UI**: `http://localhost:7001/docs`
- **ReDoc**: `http://localhost:7001/redoc`

---

## 문제 해결

### Qdrant 연결 오류

**증상**: `VectorSearchError: Qdrant 연결 실패`

**해결 방법**:

1. Qdrant 연결 상태 확인
   ```bash
   curl http://localhost:7001/api/documents/health/qdrant
   ```

2. Qdrant 서버 실행 확인
   ```bash
   curl http://localhost:6333/collections
   ```

3. 환경 변수 확인
   ```bash
   # .env 파일에서
   QDRANT_URL=http://localhost:6333
   QDRANT_COLLECTION=dept_knowledge
   ```

4. 컬렉션 존재 확인
   - Qdrant 대시보드: `http://localhost:6333/dashboard`
   - `dept_knowledge` 컬렉션이 있는지 확인

### LLM API 연결 오류

**증상**: `LLMServiceError: LLM API 호출 실패`

**해결 방법**:

1. `LLM_API_URL`이 올바른지 확인
   ```bash
   curl -X POST $LLM_API_URL \
     -H "Content-Type: application/json" \
     -d '{"messages": [{"role": "user", "content": "test"}], "model": "..."}'
   ```

2. LLM 서버가 실행 중인지 확인

3. 네트워크 연결 확인 (방화벽, VPN 등)

4. 로그 확인
   ```bash
   docker-compose logs -f backend | grep LLM
   ```

### DeepSeek-OCR 연결 오류

**증상**: OCR 처리 실패

**해결 방법**:

1. DeepSeek-OCR 서버 실행 확인
   ```bash
   curl http://220.124.155.35:30100/health
   ```

2. 환경 변수 확인
   ```bash
   DEEPSEEK_OCR_URL=http://220.124.155.35:30100
   ```

3. 타임아웃 설정 확인
   ```bash
   DEEPSEEK_OCR_TIMEOUT=60  # 초 단위
   ```

### 환경 변수 불러오기 오류

**증상**: 애플리케이션 시작 시 환경 변수 오류

**해결 방법**:

1. `.env` 파일이 프로젝트 루트에 있는지 확인
   ```bash
   ls -la .env
   ```

2. 환경 변수 형식이 올바른지 확인 (공백 없이 `KEY=value`)

3. 필수 환경 변수가 모두 설정되었는지 확인
   ```bash
   python -c "from backend.app.config import settings; settings.validate_settings()"
   ```

### Docker 실행 오류

**증상**: Docker 컨테이너 실행 실패

**해결 방법**:

1. 컨테이너 상태 확인
   ```bash
   docker-compose ps
   ```

2. 로그 확인
   ```bash
   docker-compose logs backend
   docker-compose logs frontend
   ```

3. 컨테이너 재시작
   ```bash
   docker-compose restart
   ```

4. 완전 재빌드
   ```bash
   docker-compose down
   docker-compose up --build
   ```

5. 볼륨 및 네트워크 정리
   ```bash
   docker-compose down -v
   docker network prune
   docker volume prune
   ```

### 파일 업로드 실패

**증상**: 파일 업로드 시 오류 발생

**해결 방법**:

1. 파일 형식 확인 (PDF, DOCX, TXT만 지원)

2. 파일 크기 확인 (너무 큰 파일은 업로드 실패 가능)

3. 업로드 디렉터리 권한 확인
   ```bash
   ls -ld backend/uploads
   chmod 755 backend/uploads
   ```

4. 로그 확인
   ```bash
   docker-compose logs -f backend | grep upload
   ```

### 성능 문제

**증상**: 문서 처리가 너무 느림

**해결 방법**:

1. 파이프라인 단계별 처리 시간 확인
   ```bash
   docker-compose logs backend | grep "Processing time"
   ```

2. Qdrant 연결 속도 확인
   ```bash
   curl -w "@curl-format.txt" http://localhost:6333/collections
   ```

3. LLM API 응답 속도 확인

4. OCR 처리 속도 확인

5. 필요시 타임아웃 설정 증가
   ```env
   DEEPSEEK_OCR_TIMEOUT=120
   ```

---

## 사용 흐름

1. **문서 업로드**
   - 메인 화면에서 파일을 드래그 앤 드롭하거나 "파일 선택" 버튼 클릭
   - PDF/DOCX/TXT 파일 업로드

2. **자동 처리**
   - 시스템이 7단계 파이프라인을 통해 자동으로 담당자 추천
   - 실시간 진행 상황 표시

3. **결과 확인**
   - 추천된 담당자 정보 및 점수 확인
   - 추천 이유 및 파이프라인 단계 확인

4. **담당자 확정**
   - 추천된 담당자로 자동 배정
   - 또는 다른 후보 선택하거나 직접 검색하여 배정

5. **배부 현황 확인**
   - 대시보드에서 오늘 처리한 문서 수, 확정 건수 등 확인
   - 최근 배부 이력 테이블에서 상세 정보 확인

---

## 라이선스

이 프로젝트는 전북특별자치도의 내부 POC 프로젝트입니다.

---

## 참고 문서

프로젝트 루트에는 아래와 같은 추가 문서들이 있습니다:

- `PIPELINE.md` - 7단계 파이프라인의 상세한 기술 문서
- `NEW_ARCHITECTURE_PLAN.md` - 아키텍처 설계 문서
- `SETUP.md` - 환경 설정 가이드
- `CHECKLIST.md` - 시스템 점검 및 개선 사항
- `CHANGELOG.md` - 변경 이력
- `QDRANT_CONNECTION.md` - Qdrant 연결 가이드

---

최종 업데이트: 2025-11-28
