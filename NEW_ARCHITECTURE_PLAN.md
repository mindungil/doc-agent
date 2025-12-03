# 새로운 문서 배포 시스템 아키텍처 설계

## 📋 개요

기존 시스템을 다음과 같이 전면 개편합니다:

**기존 플로우:**
```
문서 업로드 → PyPDF2/python-docx 텍스트 추출 → RAG 유사도 검색 (TOP 10) → LLM 최종 선택
```

**새로운 플로우:**
```
문서 업로드 → DeepSeek-OCR 파싱 → LLM OCR 보정
→ 1. 수신자 필터링 (RAG)
→ 2. 부서 필터링 (LLM)
→ 3. 키워드 요약 + 최종 유사도 랭킹 (RAG/LLM)
```

---

## 🏗️ 새로운 파이프라인 상세 설계

### Phase 1: DeepSeek-OCR 기반 문서 파싱

**목표:** 컨테이너로 띄워진 DeepSeek-OCR API를 사용하여 문서 이미지/PDF를 텍스트로 변환

**구현:**
- 새로운 서비스: `backend/app/services/ocr.py`
- DeepSeek-OCR API 엔드포인트 호출
- 지원 포맷: PDF, 이미지 (PNG, JPG, JPEG), DOCX (이미지 포함)
- OCR 결과: 구조화된 텍스트 (페이지별, 블록별 정보 포함)

**환경 변수 추가 (.env):**
```env
DEEPSEEK_OCR_URL=http://host.docker.internal:8000  # DeepSeek-OCR 컨테이너 주소
DEEPSEEK_OCR_API_KEY=  # Optional
```

**API 인터페이스:**
```python
async def parse_document_with_ocr(file_path: str) -> OCRResult:
    """
    DeepSeek-OCR API를 호출하여 문서 파싱

    Returns:
        OCRResult:
            - raw_text: str (전체 추출 텍스트)
            - pages: List[PageContent] (페이지별 구조화 데이터)
            - confidence: float (OCR 신뢰도)
    """
```

---

### Phase 2: LLM 기반 OCR 내용 보정

**목표:** OCR 결과의 오류를 LLM을 통해 교정 (맞춤법, 문맥, 구조 보정)

**구현:**
- `backend/app/services/llm.py`에 새 함수 추가
- OCR raw text를 LLM에 전송하여 보정

**프롬프트 설계:**
```
System: 당신은 OCR 텍스트 보정 전문가입니다. 다음 OCR 결과를 분석하여:
1. 맞춤법 오류 수정
2. 띄어쓰기 교정
3. 문맥상 이상한 부분 수정
4. 원본 의미 최대한 보존

User:
[OCR 원본 텍스트]
{raw_ocr_text}

다음 형식으로 JSON 응답:
{
  "corrected_text": "보정된 전체 텍스트",
  "corrections": [
    {"original": "오류", "corrected": "수정", "reason": "이유"}
  ]
}
```

**API 인터페이스:**
```python
async def correct_ocr_text(raw_text: str) -> CorrectedText:
    """
    LLM을 사용하여 OCR 텍스트 보정

    Returns:
        CorrectedText:
            - corrected_text: str
            - corrections: List[Correction]
    """
```

---

### Phase 3: 수신자 필터링 (RAG)

**목표:** 문서에 특정 수신자가 명시된 경우, 해당 수신자만 필터링

**로직:**
1. 보정된 텍스트에서 "수신자", "수신" 키워드 탐지
2. 키워드 주변 문맥 추출 (전후 50자)
3. LLM으로 수신자가 **특정 대상**인지 **포괄적 대상**인지 분류
   - 특정 대상 예: "수신: 정책기획과장", "수신자: 인사팀"
   - 포괄적 대상 예: "수신: 전 부서", "수신: 관계 부서"

4. **특정 대상인 경우:**
   - 수신자 텍스트를 RAG 검색하여 TOP 3 직원 추출
   - 필터링된 직원만 다음 단계로 전달

5. **포괄적 대상인 경우:**
   - 필터링 스킵, 전체 직원 대상으로 진행

**구현:**
```python
async def extract_recipient_info(text: str) -> RecipientInfo:
    """
    LLM으로 수신자 정보 추출 및 분류

    Returns:
        RecipientInfo:
            - has_recipient: bool
            - is_specific: bool (특정 대상 여부)
            - recipient_text: str (추출된 수신자 텍스트)
    """

async def filter_by_recipient(recipient_text: str) -> List[EmployeeCandidate]:
    """
    RAG로 수신자 관련 직원 TOP 3 검색
    """
```

---

### Phase 4: 부서 필터링 (LLM)

**목표:** 문서 내용을 분석하여 관련 부서 특정

**로직:**
1. Qdrant에서 전체 직원의 부서 정보(dept1, dept2, dept3) 리스트 추출
2. 중복 제거하여 unique 부서 목록 생성
3. LLM에 문서 내용 + 부서 목록 전송
4. LLM이 관련 부서 1~3개 선택

**프롬프트 설계:**
```
System: 당신은 문서 내용을 분석하여 업무 관련 부서를 특정하는 전문가입니다.

User:
[문서 내용]
{document_text}

[가용 부서 목록]
- 정책담당관 > 정책기획과 > 업무분석팀
- 인사팀 > 채용파트
- 재무과 > 예산팀
...

문서 내용을 분석하여 관련 부서를 1~3개 선택하고 JSON 응답:
{
  "selected_departments": [
    {"dept1": "정책담당관", "dept2": "정책기획과", "dept3": "업무분석팀", "relevance_score": 95},
    ...
  ],
  "reasoning": "선택 이유"
}
```

**구현:**
```python
async def get_unique_departments() -> List[DepartmentInfo]:
    """
    Qdrant에서 전체 부서 정보 추출 및 중복 제거
    """

async def filter_by_department(
    document_text: str,
    available_departments: List[DepartmentInfo]
) -> List[DepartmentInfo]:
    """
    LLM으로 관련 부서 선택
    """
```

**필터링 적용:**
- 선택된 부서에 속한 직원만 후보로 유지
- 이전 단계(수신자 필터링)의 결과와 AND 조건으로 결합

---

### Phase 5: 키워드 요약 + 최종 유사도 랭킹

**목표:** 문서 핵심 키워드 추출 후, 필터링된 직원들과 유사도 기반 최종 순위 결정

**5-1. 키워드 기반 문서 요약 (LLM)**

**프롬프트:**
```
System: 문서의 핵심 키워드와 요약을 추출하는 전문가입니다.

User:
[문서 내용]
{document_text}

다음을 추출하여 JSON 응답:
{
  "keywords": ["키워드1", "키워드2", "키워드3", ...],  // 5~10개
  "summary": "문서 핵심 요약 (2-3문장)",
  "required_expertise": ["필요 역량1", "필요 역량2", ...]
}
```

**구현:**
```python
async def summarize_document_keywords(text: str) -> DocumentSummary:
    """
    LLM으로 문서 키워드 및 요약 추출
    """
```

**5-2. 최종 유사도 랭킹**

**옵션 A: RAG 기반 재검색**
- 키워드 + 요약을 쿼리로 사용
- 필터링된 직원들만 대상으로 RAG 검색
- 유사도 점수로 정렬

**옵션 B: LLM 기반 평가 (기존 방식 개선)**
- 필터링된 직원 정보 + 문서 요약 + 키워드를 LLM에 전송
- 각 직원별 매칭 점수 계산

**구현 (하이브리드 방식 권장):**
```python
async def rank_candidates(
    document_summary: DocumentSummary,
    filtered_candidates: List[EmployeeCandidate]
) -> List[RankedCandidate]:
    """
    1. RAG로 키워드 기반 유사도 점수 계산
    2. LLM으로 세부 평가 및 최종 순위 결정

    Returns:
        정렬된 후보자 목록 (점수 + 이유 포함)
    """
```

---

## 🔄 전체 플로우 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                    1. 문서 업로드 & OCR                          │
└─────────────────────────────────────────────────────────────────┘
   ↓
[파일 저장] → [DeepSeek-OCR 호출] → [OCR 텍스트 추출]
   ↓
   Status: "OCR 처리 중"

┌─────────────────────────────────────────────────────────────────┐
│                    2. LLM OCR 보정                               │
└─────────────────────────────────────────────────────────────────┘
   ↓
[OCR Raw Text] → [LLM 보정] → [Corrected Text]
   ↓
   Status: "텍스트 보정 중"

┌─────────────────────────────────────────────────────────────────┐
│                    3. 수신자 필터링 (조건부)                     │
└─────────────────────────────────────────────────────────────────┘
   ↓
[수신자 키워드 탐지] → [LLM 분류: 특정/포괄]
   ↓
   특정 대상? YES → [RAG 검색] → [TOP 3 직원]
   ↓            NO  → [필터링 스킵]
   Status: "수신자 분석 중"

┌─────────────────────────────────────────────────────────────────┐
│                    4. 부서 필터링                                │
└─────────────────────────────────────────────────────────────────┘
   ↓
[부서 목록 조회] → [LLM 부서 선택] → [해당 부서 직원 필터링]
   ↓
   Status: "부서 분석 중"

┌─────────────────────────────────────────────────────────────────┐
│                    5. 키워드 요약 & 최종 랭킹                    │
└─────────────────────────────────────────────────────────────────┘
   ↓
[LLM 키워드 추출] → [RAG 유사도 계산] → [LLM 최종 평가]
   ↓
   Status: "최종 분석 중"

┌─────────────────────────────────────────────────────────────────┐
│                    6. 자동 배정                                  │
└─────────────────────────────────────────────────────────────────┘
   ↓
[1순위 직원 자동 배정]
   ↓
   Status: "배부 완료"
```

---

## 📁 파일 구조 변경

### 새로 생성할 파일:

```
backend/app/services/
├── ocr.py                      # DeepSeek-OCR 통합
├── text_correction.py          # LLM OCR 보정
├── recipient_filter.py         # 수신자 필터링 로직
├── department_filter.py        # 부서 필터링 로직
└── document_summarizer.py      # 키워드 요약 로직

backend/app/models/
└── ocr_schemas.py              # OCR 관련 Pydantic 모델
```

### 수정할 파일:

```
backend/app/services/
└── document.py                 # 기존 extract_text_from_file 대체

backend/app/routers/
└── documents.py                # process_document_async 로직 전면 수정

backend/app/config.py           # 새 환경 변수 추가
backend/app/models/schemas.py   # 새 데이터 모델 추가

.env                            # DeepSeek-OCR URL 추가
```

---

## 🗄️ 데이터베이스 스키마 확장

### DocumentModel 새 필드 추가:

```python
class DocumentModel(Base):
    # ... 기존 필드 ...

    # OCR 관련
    ocr_raw_text: str = None              # OCR 원본 텍스트
    ocr_confidence: float = None          # OCR 신뢰도
    corrected_text: str = None            # 보정된 텍스트

    # 필터링 정보
    recipient_info: str = None            # 수신자 정보 (JSON)
    filtered_departments: str = None      # 필터링된 부서 (JSON)
    document_keywords: str = None         # 추출된 키워드 (JSON)

    # 처리 시간 추적
    ocr_processed_at: datetime = None
    correction_processed_at: datetime = None
    filtering_processed_at: datetime = None
```

---

## ⚙️ 환경 변수 추가

`.env` 파일에 추가:

```env
# DeepSeek-OCR 설정
DEEPSEEK_OCR_URL=http://host.docker.internal:8000
DEEPSEEK_OCR_API_KEY=
DEEPSEEK_OCR_TIMEOUT=60  # OCR 처리 타임아웃 (초)

# 필터링 설정
RECIPIENT_FILTER_ENABLED=true
DEPARTMENT_FILTER_ENABLED=true
MIN_CONFIDENCE_SCORE=0.5  # 최소 신뢰도 점수
```

---

## 🔧 구현 순서

1. **Phase 1**: DeepSeek-OCR 통합 (`ocr.py`)
2. **Phase 2**: LLM OCR 보정 (`text_correction.py`)
3. **Phase 3**: 수신자 필터링 (`recipient_filter.py`)
4. **Phase 4**: 부서 필터링 (`department_filter.py`)
5. **Phase 5**: 키워드 요약 및 랭킹 (`document_summarizer.py`)
6. **Integration**: 전체 파이프라인 통합 (`document.py` 수정)
7. **Testing**: 엔드투엔드 테스트 및 검증

---

## 🎯 예상 효과

1. **정확도 향상**: OCR + LLM 보정으로 텍스트 추출 품질 향상
2. **정밀한 필터링**: 수신자/부서 필터링으로 불필요한 후보 제거
3. **효율성**: 필터링 후 소수 후보만 평가 → LLM 비용 절감
4. **해석 가능성**: 각 단계별 필터링 이유 저장 → 투명성 증가
5. **확장성**: 모듈화된 구조로 향후 필터 추가 용이

---

## 🚨 주의사항

1. **DeepSeek-OCR 컨테이너 필수**: 구현 전 OCR 서비스 가동 확인
2. **LLM 호출 증가**: 기존 1회 → 신규 4~5회 (보정, 수신자 분류, 부서 선택, 키워드, 평가)
3. **처리 시간 증가**: 전체 파이프라인 20~40초 예상
4. **에러 핸들링**: 각 단계별 fallback 로직 필요
5. **성능 모니터링**: 각 단계별 소요 시간 로깅 권장

---

## 📊 성능 최적화 방안

1. **병렬 처리**:
   - 수신자 필터링 + 부서 필터링 동시 실행 가능
   - LLM 호출 배치 처리 고려

2. **캐싱**:
   - 부서 목록 캐싱 (자주 변경되지 않음)
   - LLM 응답 캐싱 (동일 문서 재처리 시)

3. **조건부 실행**:
   - 수신자 필터링: 특정 키워드 없으면 스킵
   - 부서 필터링: 이미 충분히 좁혀진 경우 스킵

---

## ✅ 완료 체크리스트

- [ ] DeepSeek-OCR API 연동 확인
- [ ] OCR 서비스 구현 및 테스트
- [ ] LLM 보정 프롬프트 최적화
- [ ] 수신자 필터링 로직 구현
- [ ] 부서 필터링 로직 구현
- [ ] 키워드 요약 및 랭킹 구현
- [ ] 전체 파이프라인 통합
- [ ] 데이터베이스 마이그레이션
- [ ] 프론트엔드 상태 표시 업데이트
- [ ] 엔드투엔드 테스트
- [ ] 성능 벤치마크
- [ ] 문서화 업데이트
