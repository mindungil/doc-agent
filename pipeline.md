# 담당자 선별 PIPELINE 상세 분석

본 문서는 doc-agent 프로젝트의 **문서 배부 담당자 자동 선별 파이프라인**을 상세히 분석합니다.

## 1. 전체 아키텍처 개요

### 1.1 Pipeline V2 구조

```
┌────────────────────────────────────────────────────────────────┐
│                    Document Input                              │
│                 (제목, OCR 텍스트)                              │
└────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────┐
│  Stage 1: 전처리 및 정규화 (Preprocessing)                     │
│  - 유니코드 정규화 (NFC)                                       │
│  - 괄호 패턴 필터링                                            │
│  - 공백 정규화                                                 │
└────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────┐
│  Stage 2: 수신자 필터링 (Recipient Filter)                     │
│  - OCR 텍스트에서 수신자 정보 추출                             │
│  - LLM 기반 명시적/묵시적 판단                                 │
│  - 부서 필터 생성                                              │
└────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────┐
│  Stage 3: 증거 수집 (Evidence Collection)                      │
│  ┌──────────────────────┐    ┌──────────────────────────────┐ │
│  │ 3-1. 과거 배부 이력  │    │ 3-2. 사무분장 규정           │ │
│  │ (Historical Search)  │    │ (Job Description Search)     │ │
│  │                      │    │                              │ │
│  │ BM25 + Levenshtein   │    │ Qdrant Vector Search         │ │
│  │ → 유사 문서 검색     │    │ → 업무 매칭                  │ │
│  └──────────────────────┘    └──────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────┐
│  Stage 4: 조기 종료 체크 (Early Stop Check)                    │
│  - Skeleton 100% 일치 OR                                       │
│  - Levenshtein 유사도 >= 90%                                   │
│  → 자동 배정 (과거 담당자 그대로)                              │
└────────────────────────────────────────────────────────────────┘
                  조기 종료 Yes ↓   No ↓
                           ↓            ↓
        ┌──────────────────┐    ┌─────────────────────────────┐
        │ 자동 배정 완료   │    │ Stage 5: LLM 추론           │
        │ (Fast-Track)     │    │ - 증거 기반 부서 추천       │
        └──────────────────┘    │ - 신뢰도 계산               │
                                │ - 담당자 선정               │
                                └─────────────────────────────┘
                                          ↓
                ┌───────────────────────────────────────────────┐
                │ Stage 6: 최종 담당자 선정                     │
                │ - RAG 후보자 검색                             │
                │ - 부서 필터 적용                              │
                │ - LLM 최종 판단                               │
                └───────────────────────────────────────────────┘
                                          ↓
                ┌───────────────────────────────────────────────┐
                │ 결과 저장 및 휴먼 피드백 수집                 │
                └───────────────────────────────────────────────┘
```

## 2. Stage 1: 전처리 및 정규화

### 2.1 구현 위치

- **파일**: `backend/app/services/pipeline_v2.py`
- **메서드**: `process_document()`, `recommend_assignee_with_pipeline()`

### 2.2 정규화 프로세스

```python
# backend/app/services/pipeline_v2.py:61-62
cleaned_title = self.preprocessor.clean_title(document.title)
logger.info(f"정규화 제목: {cleaned_title}")
```

**처리 내용**:
1. 유니코드 정규화 (NFC)
2. 괄호 패턴 필터링 (3글자 이하 제거)
3. 공백 정규화

**예시**:

| 입력 | 출력 |
|------|------|
| `(회람) 2025년  적극행정\t우수사례 경진대회` | `2025년 적극행정 우수사례 경진대회` |

## 3. Stage 2: 수신자 필터링

### 3.1 목적

**명시적 수신자**가 있는 문서는 해당 부서로만 배부되어야 합니다.

**예시**:
```
수신: 행정정보과장
제목: 2025년 정보보안 점검 계획
```
→ **무조건 행정정보과로 배부** (다른 부서 검색 불필요)

### 3.2 구현 로직

```python
# backend/app/services/pipeline_v2.py:65-88
if ocr_text:
    try:
        # 수신자 정보 추출
        recipient_result = await self.recipient_filter.extract_recipient_info(ocr_text)

        if recipient_result:
            recipient_info = {
                'has_recipient': recipient_result.has_recipient,
                'is_specific': recipient_result.is_specific,
                'recipient_text': recipient_result.recipient_text,
                'is_explicit': recipient_result.is_specific,
                'dept_name': None
            }
```

### 3.3 수신자 정보 구조

| 필드 | 설명 | 예시 |
|------|------|------|
| `has_recipient` | 수신자 정보 존재 여부 | `True` |
| `is_specific` | 명시적 수신자 여부 | `True` / `False` |
| `recipient_text` | 추출된 수신자 텍스트 | `"행정정보과장"` |
| `dept_name` | 부서명 (파싱 결과) | `"행정정보과"` |

**명시적 vs 묵시적**:

| 유형 | 예시 | is_specific |
|------|------|-------------|
| **명시적** | `수신: 행정정보과장` | `True` |
| **묵시적** | `관련 부서는...` | `False` |

## 4. Stage 3: 증거 수집 (Evidence Collection)

### 4.1 증거 수집기 구조

**파일**: `backend/app/services/evidence_collector.py`

**두 가지 증거 소스**:

1. **문서 배부 이력** (Historical Evidence)
   - DuckDB Parquet + realtime_docs
   - BM25 인덱스 검색
   - Levenshtein Distance 정밀 검증

2. **사무분장 규정** (Job Description Evidence)
   - Qdrant 벡터 검색
   - 직원 업무 설명과 문서 제목 매칭

### 4.2 문서 배부 이력 증거 수집

#### 4.2.1 검색 파이프라인

```python
# backend/app/services/evidence_collector.py:36-78
def collect_history_evidence(self, title: str, dept_filter: Optional[str] = None):
    # 유사 문서 검색
    results, early_stopped = self.similarity_search.search_similar_documents(
        title=title,
        dept_filter=dept_filter,
        early_stop=True
    )
```

**검색 흐름**:

```
제목 입력
    ↓
정규화 (Clean Title)
    ↓
BM25 1차 필터링 (Top 50)
    ↓
Levenshtein Distance 2차 검증
    ↓
유사도 >= 90% → 조기 종료
유사도 >= 70% → 유사 문서 반환
```

#### 4.2.2 BM25 + Levenshtein 하이브리드 검색

**BM25 역할** (backend/app/services/similarity_search.py:62-68):
```python
candidates = self.bm25_system.search(
    query=cleaned_title,
    top_k=self.top_k_blocking,  # 50개
    dept_filter=dept_filter
)
```

- **키워드 매칭** 기반 후보군 확보
- **빠른 스캔** (Top 50개만)

**Levenshtein Distance 역할** (backend/app/services/similarity_search.py:77-98):
```python
for candidate in candidates:
    similarity = fuzz.ratio(cleaned_title, candidate_title)

    if early_stop and similarity >= self.threshold_high:  # 90%
        return [candidate], True  # 조기 종료
```

- **문자열 정확도** 검증
- **오탐 제거**

#### 4.2.3 조기 종료 조건

**임계값**:
- `threshold_high` = **90%** (조기 종료)
- `threshold_low` = **70%** (유사 문서)

**조기 종료 예시**:

| 입력 제목 | 과거 문서 제목 | Levenshtein 유사도 | 결과 |
|-----------|----------------|---------------------|------|
| `2025년 적극행정 우수사례 경진대회 개최 안내` | `2024년 적극행정 우수사례 경진대회 계획` | 92% | ✅ 조기 종료 |
| `2025년 적극행정 우수사례 경진대회 개최 안내` | `2024년 적극행정 인식도 조사 안내` | 65% | ❌ 일반 검색 |

#### 4.2.4 수집된 증거 구조

```python
evidence = {
    'title': result['title'],
    'cleaned_title': result['cleaned_title'],
    'dept': result['dept'],
    'reporter': result['reporter'],
    'date': str(result['date']),
    'similarity': result['similarity'],
    'doc_no': result['doc_no']
}
```

### 4.3 사무분장 규정 증거 수집

#### 4.3.1 Qdrant 벡터 검색

```python
# backend/app/services/evidence_collector.py:80-131
def collect_job_description_evidence(self, title: str):
    # 임베딩 생성
    query_embedding = rag_service.create_query_embedding(cleaned_title)

    # Qdrant 검색
    results = self.qdrant_client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_embedding,
        limit=self.top_k_job  # 5개
    )
```

**검색 결과**:

| 필드 | 설명 | 예시 |
|------|------|------|
| `dept` | 담당 부서 | `"행정정보과 사이버보안팀"` |
| `job_description` | 업무 설명 | `"정보보안 정책 수립 및 시행"` |
| `rank` | 직급 | `"7급"` |
| `manager` | 담당자 이름 | `"김지수"` |
| `score` | 벡터 유사도 | `0.85` |

#### 4.3.2 사무분장 vs 과거 이력 우선순위

**LLM 프롬프트에서 명시** (backend/app/services/department_recommender.py:207-221):

```
2. **과거 배부 이력 중심 분석** (가장 중요!):
   - 유사도가 높은 과거 문서의 배부 부서와 보고자를 최우선으로 고려하세요.
   - 유사도 70% 이상인 문서가 있다면, 해당 문서의 배부 부서를 강하게 고려하세요.

3. **사무분장 규정 참고** (보조 자료):
   - 사무분장은 참고 자료로만 활용하세요.
   - 과거 이력이 있다면 사무분장보다 과거 이력을 우선하세요.
```

**우선순위**:
1. 과거 배부 이력 (최우선)
2. 사무분장 규정 (참고)

## 5. Stage 4: 조기 종료 (Early Stop)

### 5.1 조기 종료 조건

**두 가지 경로**:

#### 5.1.1 Skeleton 100% 일치 (backend/app/services/historical_search.py:526-563)

```python
query_skeleton = self._normalize_to_skeleton(document_title)

for result in search_results:
    hist_skeleton = self._normalize_to_skeleton(hist_title)

    if query_skeleton == hist_skeleton:
        # 완전 일치! 조기 종료
        return [hist_doc], "Stage 1: Skeleton Match (Fast-Track)"
```

**Skeleton 예시**:

| 입력 | 과거 문서 | Skeleton | 결과 |
|------|-----------|----------|------|
| `2025년 적극행정 우수사례 경진대회 개최 안내` | `2024년 적극행정 우수사례 경진대회 계획` | `적극행정우수사례경진대회` | ✅ 일치 |

#### 5.1.2 Levenshtein 유사도 >= 90% (backend/app/services/similarity_search.py:88-94)

```python
if early_stop and similarity >= self.threshold_high:  # 90%
    logger.info(f"조기 종료: 유사도 {similarity:.2f}%")
    return [candidate], True
```

### 5.2 조기 종료 시 처리

**증거 수집기 반환값** (backend/app/services/evidence_collector.py:154-184):

```python
if early_stopped and history_evidence:
    best_match = history_evidence[0]

    return {
        'early_stopped': True,
        'auto_assigned_dept': best_match['dept'],
        'reason': f"과거 유사 문서(유사도 {similarity:.2f}%)가 발견되어 자동 배정",
        'matched_document': best_match,
        'history_evidence': history_evidence,
        'job_evidence': []
    }
```

**부서 추천 엔진 반환값** (backend/app/services/department_recommender.py:57-65):

```python
if evidence['early_stopped']:
    return {
        'recommended_dept': evidence['auto_assigned_dept'],
        'recommended_employee': evidence.get('matched_document', {}).get('reporter'),
        'confidence': 'high',
        'reasoning': evidence['reason'],
        'auto_assigned': True,
        'evidence': evidence
    }
```

### 5.3 조기 종료의 장점

1. **속도**: LLM 호출 생략 (90% 케이스)
2. **정확도**: 과거 이력 100% 신뢰
3. **비용 절감**: LLM API 호출 최소화

## 6. Stage 5: LLM 부서 추론

### 6.1 LLM 호출 조건

**조기 종료되지 않은 경우**:
- Skeleton 불일치
- Levenshtein 유사도 < 90%

### 6.2 프롬프트 구성

**파일**: `backend/app/services/department_recommender.py:139-250`

**프롬프트 구조**:

```
# 문서 배부 부서 추천 요청

## 분석 대상 문서
- 원본 제목: {title}
- 정규화 제목: {cleaned_title}

## 수신자 정보 (OCR 추출)
- 명시적 수신자: 있음/없음
- 수신 부서: {dept_name}

## 과거 문서 배부 이력 (유사도 기준 상위 문서)
### 1. 과거 문서
- 제목: {title}
- 배부 부서: {dept}
- 보고자: {reporter}
- 보고 일자: {date}
- 유사도: {similarity}%

## 사무분장 규정 (관련 업무)
### 1. 사무분장
- 부서: {dept}
- 업무 내용: {job_description}
- 직급: {rank}
- 담당자: {manager}

## 휴먼 피드백 이력 (중요!)
### 1. 피드백
- LLM 예측 (오답): {llm_predicted_dept}
- 담당자 수정 (정답): {human_corrected_dept}
- 수정 사유: {reason}

## 추론 지시사항
1. 휴먼 피드백 최우선
2. 과거 배부 이력 중심 분석 (가장 중요!)
3. 사무분장 규정 참고 (보조 자료)
4. 업무 연속성 보장
5. 부서명 정확성

## 출력 형식 (JSON)
{
  "recommended_dept": "추천 부서명",
  "recommended_employee": "추천 담당자명 또는 null",
  "confidence": "high|medium|low",
  "reasoning": "추천 근거",
  "alternative_depts": ["대안 부서1", "대안 부서2"]
}
```

### 6.3 LLM 응답 파싱

```python
# backend/app/services/department_recommender.py:253-290
def _parse_llm_response(self, content: str) -> Dict[str, Any]:
    # JSON 코드 블록 추출
    if "```json" in content:
        json_str = content.split("```json")[1].split("```")[0].strip()

    result = json.loads(json_str)

    return {
        'recommended_dept': result.get('recommended_dept', '행정정보과'),
        'recommended_employee': result.get('recommended_employee'),
        'confidence': result.get('confidence', 'medium'),
        'reasoning': result.get('reasoning', ''),
        'alternative_depts': result.get('alternative_depts', [])
    }
```

### 6.4 신뢰도 계산

| Confidence | 조건 | 의미 |
|------------|------|------|
| **high** | 과거 이력 유사도 >= 80% | 자동 배정 가능 |
| **medium** | 과거 이력 유사도 50-80% | 검토 필요 |
| **low** | 과거 이력 없음 또는 < 50% | 담당자 확인 필수 |

## 7. Stage 6: 최종 담당자 선정

### 7.1 조기 종료 케이스 (Fast-Track)

**조건**: `auto_assigned = True`

```python
# backend/app/services/pipeline_v2.py:288-346
if dept_recommendation['auto_assigned']:
    recommended_dept = dept_recommendation['recommended_dept']
    recommended_employee_name = dept_recommendation.get('recommended_employee')

    # 과거 담당자 이름으로 메타데이터 직접 검색
    primary_candidate = await rag_service.search_employee_by_name(
        recommended_employee_name
    )
```

**흐름**:

```
조기 종료 (유사도 >= 90%)
    ↓
과거 보고자 이름 추출
    ↓
Qdrant 메타데이터 검색 (이름 정확 일치)
    ↓
Primary Candidate 설정
    ↓
해당 부서 추가 후보 검색
    ↓
결과 반환
```

### 7.2 일반 케이스 (LLM 기반)

**조건**: `auto_assigned = False`

```python
# backend/app/services/pipeline_v2.py:348-421
# 1. RAG 후보자 검색 (부서 필터 없음)
rag_candidates = await rag_service.search_similar_employees(document_text, top_k=20)

# 2. 추천 부서에 속한 후보 우선 배치
dept_matched_candidates = [
    c for c in rag_candidates
    if recommended_dept in f"{c.dept1} {c.dept2} {c.dept3}"
]

# 3. LLM 최종 판단
llm_recommendation = await self.llm_service.recommend_assignee(
    document_title=document_title,
    document_content=document_content,
    candidates=reordered_candidates[:10]
)
```

**흐름**:

```
LLM 부서 추천 완료
    ↓
RAG 후보자 검색 (Top 20)
    ↓
추천 부서 후보 우선순위 배치
    ↓
LLM 최종 담당자 선정 (Top 10 중)
    ↓
결과 반환
```

### 7.3 RAG 후보자 검색

**파일**: `backend/app/services/rag.py`

**검색 쿼리**:
```python
document_text = f"{document_title}\n\n{document_content}"
```

**Qdrant 검색**:
```python
results = self.qdrant_client.search(
    collection_name="employees",
    query_vector=query_embedding,
    limit=top_k
)
```

**후보자 정보**:

| 필드 | 설명 |
|------|------|
| `name` | 직원 이름 |
| `rank` | 직급 |
| `dept1` | 1차 부서 |
| `dept2` | 2차 부서 |
| `dept3` | 3차 부서 |
| `tasks` | 담당 업무 |
| `score` | 벡터 유사도 |

### 7.4 LLM 최종 판단

**프롬프트 예시**:

```
# 문서 배부 담당자 추천

## 문서 정보
- 제목: 2025년 적극행정 우수사례 경진대회 개최 안내
- 내용: ...

## 추천 부서
- 부서: 정책기획관 (신뢰도: high)

## 후보자 목록
1. 김철수 (7급, 정책기획관, 적극행정 추진)
2. 이영희 (8급, 정책기획관, 우수사례 발굴)
3. 박민수 (9급, 행정정보과, 문서 관리)

## 지시사항
위 후보자 중 가장 적합한 담당자를 선정하고, 그 이유를 설명하세요.

## 출력 형식 (JSON)
{
  "primary": {"name": "김철수", "rank": "7급", ...},
  "candidates": [...],
  "reasoning": "선정 이유"
}
```

## 8. 3단계 우선순위 파이프라인 (Three-Stage Pipeline)

### 8.1 개요

**파일**: `backend/app/services/historical_search.py:490-713`

**3단계 전략**:

```
Stage 1: Skeleton Matching (Fast-Track)
    → 100% 일치 시 즉시 반환
    ↓ (일치 없음)
Stage 2: Action-based Hybrid Search (Deep-Check)
    → 임베딩 + 키워드 + 행위어 + 시간 종합 점수
    ↓ (유사도 0.85~0.95)
Stage 3: LLM Final Verification (Safety Net)
    → 연속성 판단 (3가지 체크)
```

### 8.2 Stage 1: Skeleton Matching

**목표**: 정규화된 골격이 100% 일치하는 과거 문서 찾기

```python
# backend/app/services/historical_search.py:526-563
query_skeleton = self._normalize_to_skeleton(document_title)

for result in search_results:
    hist_skeleton = self._normalize_to_skeleton(hist_title)

    if query_skeleton == hist_skeleton:
        hist_doc = HistoricalDocument(result.payload, 1.0)  # 100% 매칭
        exact_matches.append(hist_doc)
```

**효과**:
- **즉시 반환** (Stage 2, 3 생략)
- **연도, 순서, 접미사 차이 무시**

### 8.3 Stage 2: Action-based Hybrid Search

**목표**: 다차원 점수 계산

```python
# backend/app/services/historical_search.py:592-639
# 1. 키워드 커버리지
keyword_coverage = self._calculate_keyword_coverage(core_keywords, hist_title)

# 2. 행위어 유사도
action_similarity = self._calculate_action_similarity(document_title, hist_title)

# 3. 시간 가중치
time_weight = calculate_time_weight(current_year, hist_year)

# 4. 최종 점수
final_score = base_score * keyword_weight * action_weight * time_weight
```

**점수 계산 예시**:

| 요소 | 값 | 가중치 | 설명 |
|------|-----|--------|------|
| **임베딩 점수** | 0.85 | 1.0x | Qdrant 벡터 유사도 |
| **키워드 커버리지** | 80% | 1.3x | 핵심 키워드 매칭률 |
| **행위어 유사도** | 100% (경진대회) | 1.0x | Head Noun 일치 |
| **시간 가중치** | 작년 문서 | 1.3x | 연속성 보너스 |
| **최종 점수** | **1.44** | - | - |

**키워드 가중치**:
```python
keyword_weight = 0.5 + (keyword_coverage * 1.0)
```
- 0% 매칭 → 0.5배
- 100% 매칭 → 1.5배

**행위어 가중치**:
```python
action_weight = 0.3 + (action_similarity * 0.7)
```
- 완전 불일치 → 0.3배 (큰 페널티)
- 완전 일치 → 1.0배

**시간 가중치**:

| 연도 차이 | 가중치 | 이유 |
|-----------|--------|------|
| 작년 (diff=1) | **1.3x** | 연속 업무 가능성 최고 |
| 금년 (diff=0) | **1.1x** | 동일 연도 다른 담당자 |
| 미래 (diff<0) | **0.3x** | 데이터 오류 의심 |
| 2년 이상 과거 | **0.7~1.0x** | 담당자 변동 가능성 |

### 8.4 Stage 3: LLM Final Verification

**목표**: 유사도 0.85~0.95 구간에서 연속성 판단

```python
# backend/app/services/historical_search.py:672-700
if 0.85 <= max_score < 0.95:
    is_continuous, reasoning = await self.check_topic_continuity_with_llm(
        current_title=document_title,
        current_summary=document_summary,
        historical_title=best_doc.title,
        historical_reporter=best_doc.reporter,
        historical_department=best_doc.department
    )

    if is_continuous:
        return [r['doc'] for r in scored_results[:top_k]], "Stage 2 + Stage 3: LLM 연속성 확인"
    else:
        # 연속성 없으면 30% 감점
        for res in scored_results:
            res['final_score'] *= 0.7
```

**LLM 연속성 판단 기준** (backend/app/services/historical_search.py:864-915):

```
1. 연속성 (Continuity):
   - 작년의 그 업무가 올해 이 업무로 이어진 것인가?

2. 대체 불가능성 (Exclusivity):
   - 과거 문서를 처리한 사람이 현재 문서도 처리했을 확률이 90% 이상인가?

3. 세부 주제 일치 (Action-Level Match):
   - 업무의 Action 레벨이 같은가?
   - "조사" vs "계획" vs "행사" → 다른 Action
```

**3가지 체크 모두 True여야 연속성 인정**

**False 판정 사례**:
- `적극행정 조사` vs `적극행정 경진대회` → Action 불일치
- `정책기획관` vs `인구청년정책과` → 부서 불일치

## 9. 휴먼 피드백 루프

### 9.1 피드백 저장

**트리거**: 담당자가 LLM 추천을 수정한 경우

```python
# backend/app/services/pipeline_v2.py:138-194
async def handle_human_correction(
    self,
    db: AsyncSession,
    document_id: int,
    corrected_dept: str,
    reason: Optional[str] = None
):
    # LLM 예측과 다른 경우에만 피드백 저장
    if llm_predicted_dept and llm_predicted_dept != corrected_dept:
        await self.feedback_service.add_feedback(
            db=db,
            keyword=cleaned_title,
            reporter=None,
            llm_predicted_dept=llm_predicted_dept,
            human_corrected_dept=corrected_dept,
            reason=reason,
            document_id=document_id,
            document_title=document.title
        )
```

### 9.2 피드백 데이터 구조

**테이블**: `feedbacks` (backend/app/database/db.py:44-56)

| 컬럼 | 설명 |
|------|------|
| `keyword` | 문서 핵심 키워드 (정규화된 제목) |
| `reporter` | 보고자 이름 |
| `llm_predicted_dept` | LLM 예측 부서 (오답) |
| `human_corrected_dept` | 담당자 수정 부서 (정답) |
| `reason` | 수정 사유 |
| `document_id` | 원본 문서 ID |
| `document_title` | 원본 문서 제목 |
| `created_at` | 피드백 생성 시각 |

### 9.3 피드백 활용

**조회 시점**: Stage 5 LLM 추론 전

```python
# backend/app/services/pipeline_v2.py:90-99
feedback_data = await self.feedback_service.get_feedback_for_inference(
    db=db,
    keyword=cleaned_title,
    reporter=None,
    limit=5
)
```

**LLM 프롬프트에 포함**:

```
## 휴먼 피드백 이력 (중요!)
**주의**: 과거에 이 키워드/보고자에 대해 LLM 추천이 수정된 이력이 있습니다.

### 1. 피드백
- LLM 예측 (오답): 행정정보과
- 담당자 수정 (정답): 정책기획관
- 수정 사유: 적극행정은 정책기획관 고유 업무
```

**효과**:
- **동일 오류 반복 방지**
- **도메인 지식 학습**

## 10. 배부 전략

### 10.1 자동 배정 vs 검토 필요

**자동 배정 조건**:
```python
# backend/app/services/pipeline_v2.py:117-124
if recommendation['auto_assigned']:
    document.assigned_to = recommendation['recommended_dept']
    document.assigned_at = datetime.utcnow()
    document.status = "자동배정"
else:
    document.status = "검토필요"
```

**자동 배정 기준**:
1. 조기 종료 (Skeleton 일치 OR Levenshtein >= 90%)
2. LLM confidence = "high" (과거 이력 유사도 >= 80%)

### 10.2 일괄 배부 처리

```python
# backend/app/services/pipeline_v2.py:195-239
async def batch_distribute(self, db: AsyncSession, auto_confirm: bool = False):
    # 대기 중인 문서 조회
    documents = await db.execute(
        select(DocumentModel).where(
            DocumentModel.status.in_(["자동배정", "검토필요"])
        )
    )

    for doc in documents:
        if doc.is_auto_assigned and auto_confirm:
            doc.status = "확정"
```

**배부 상태 흐름**:

```
신규 등록 → 대기
    ↓
Pipeline 실행
    ↓
자동배정 / 검토필요
    ↓
(시간 경과 또는 담당자 확인)
    ↓
확정
```

## 11. 성능 최적화 전략

### 11.1 조기 종료 (Early Stop)

**효과**:
- **LLM 호출 90% 감소**
- **응답 시간 < 100ms** (vs 일반 케이스 2-3초)

### 11.2 BM25 Blocking

**효과**:
- DuckDB 전체 스캔 대신 **Top 50개**만 Levenshtein 검증
- 검색 시간 **10배 단축**

### 11.3 RAG 후보자 우선순위 배치

```python
# backend/app/services/pipeline_v2.py:381-394
dept_matched_candidates = [
    c for c in rag_candidates
    if recommended_dept in f"{c.dept1} {c.dept2} {c.dept3}"
]

reordered_candidates = dept_matched_candidates + other_candidates_list
```

**효과**:
- LLM이 상위 후보에서 정답 발견 확률 **80% 이상**

## 12. 전체 파이프라인 성능 지표

### 12.1 처리 시간

| 단계 | 평균 시간 | 비율 |
|------|-----------|------|
| 전처리 및 정규화 | < 1ms | 0.03% |
| 수신자 필터링 (OCR 있을 때) | 200-500ms | 10% |
| 증거 수집 (BM25 + Qdrant) | 100-300ms | 10% |
| **조기 종료 (90% 케이스)** | **< 100ms** | **100%** |
| LLM 부서 추론 | 1-2초 | 50% |
| RAG 후보자 검색 | 200-500ms | 15% |
| LLM 최종 판단 | 1-2초 | 50% |
| **전체 (일반 케이스)** | **3-5초** | - |

### 12.2 정확도

| 지표 | 목표 | 실제 (예상) |
|------|------|-------------|
| 자동 배정 비율 | 80% | 85-90% |
| 자동 배정 정확도 | 95% | 97-99% |
| 검토 필요 정확도 (LLM) | 80% | 75-85% |
| 전체 정확도 | 90% | 92-95% |

## 13. 핵심 설계 원칙 요약

1. **조기 종료 우선**: Skeleton/Levenshtein으로 90% 케이스 Fast-Track
2. **증거 기반 추론**: 과거 이력 > 사무분장 > LLM 추측
3. **다층 검증**: BM25 → Levenshtein → LLM 3단계 필터링
4. **휴먼 피드백 학습**: 수정 이력을 프롬프트에 반영
5. **시간 연속성 고려**: 작년 문서 가중치 상향
6. **행위어 구분**: 조사/계획/행사 등 Action 레벨 구분
7. **부서 우선순위**: RAG 후보 중 추천 부서 직원 우선 배치

## 14. 주요 파일 목록

| 파일 | 역할 |
|------|------|
| `backend/app/services/pipeline_v2.py` | 메인 파이프라인 오케스트레이션 |
| `backend/app/services/evidence_collector.py` | 증거 수집 (과거 이력 + 사무분장) |
| `backend/app/services/similarity_search.py` | BM25 + Levenshtein 검색 |
| `backend/app/services/historical_search.py` | 3단계 파이프라인 + Skeleton |
| `backend/app/services/department_recommender.py` | LLM 부서 추론 |
| `backend/app/services/rag.py` | RAG 후보자 검색 |
| `backend/app/services/llm.py` | LLM 서비스 (최종 판단) |
| `backend/app/services/feedback_service.py` | 휴먼 피드백 관리 |
| `backend/app/services/bm25_index.py` | BM25 인덱스 시스템 |
| `backend/app/services/text_preprocessor.py` | 텍스트 정규화 |
| `backend/app/database/db.py` | 데이터베이스 모델 |

## 15. 향후 개선 방향

### 15.1 실시간 피드백 강화

현재는 피드백을 **프롬프트에만 반영**하지만, 향후:
- **Fine-tuning 데이터 생성**
- **주기적 모델 재학습**

### 15.2 부서 이동 추적

담당자가 부서를 이동한 경우:
- 현재: 과거 보고자 검색 시 **부서 불일치** 발생
- 개선: 인사 이동 이력 DB 연계

### 15.3 다중 담당자 지원

현재는 Primary 1명 선정이지만, 향후:
- **복수 배부** (참조/협조)
- **권한별 구분** (결재/검토/참고)

### 15.4 실시간 모니터링

- 자동 배정 정확도 대시보드
- 피드백 빈도 높은 키워드 알림
- LLM 응답 시간 추적
