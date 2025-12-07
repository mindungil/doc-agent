# 텍스트 정규화 및 토크나이저 전략

본 문서는 doc-agent 프로젝트의 문서 제목 정규화 및 토크나이저 전략을 상세히 분석합니다.

## 1. 아키텍처 개요

### 1.1 전체 흐름도

```
원본 문서 제목 (Raw Title)
    ↓
유니코드 정규화 (NFC)
    ↓
괄호 패턴 필터링
    ↓
공백 정규화
    ↓
Cleaned Title (정규화된 제목)
    ↓
형태소 분석 (Kiwi)
    ↓
명사 추출 (NNG, NNP, NNB)
    ↓
토큰 리스트 (Tokens)
    ↓
벡터 임베딩 / BM25 인덱싱
```

## 2. 텍스트 정규화 (Text Normalization)

### 2.1 구현 위치

- **파일**: `backend/app/services/text_preprocessor.py`
- **클래스**: `TextPreprocessor`
- **메서드**: `clean_title(title: str) -> str`

### 2.2 정규화 파이프라인

#### 2.2.1 유니코드 정규화 (NFC)

```python
# backend/app/services/text_preprocessor.py:49
title = unicodedata.normalize('NFC', title)
```

**목적**:
- 한글 자소 결합 문자를 정규화
- 예: `ㄱ + ㅏ + ㅁ` → `감`

**필요성**:
- 파일명, OCR 결과에서 자소 분리 현상 방지
- 문자열 비교 정확도 향상

**NFC vs NFD**:
| 방식 | 설명 | 예시 |
|------|------|------|
| NFC | 결합형 (Composed) | `감` (U+AC10) |
| NFD | 분리형 (Decomposed) | `ㄱ`(U+1100) + `ㅏ`(U+1161) + `ㅁ`(U+11B7) |

**선택 이유**: 한글은 NFC가 표준 (KS X 1001)

#### 2.2.2 괄호 패턴 필터링

```python
# backend/app/services/text_preprocessor.py:52-55
# 소괄호 처리
title = re.sub(r'\([^)]{1,3}\)', '', title)  # 3글자 이하 삭제

# 대괄호 처리
title = re.sub(r'\[[^\]]{1,3}\]', '', title)  # 3글자 이하 삭제
```

**규칙**:
1. **3글자 이하 삭제**: 메타 정보로 판단
   - 예: `(안내)`, `[참고]`, `(회람)`
2. **4글자 이상 유지**: 의미 있는 정보로 판단
   - 예: `(전 직원 공람)`, `[행정정보과]`

**실제 사례**:

| 원본 제목 | 정규화 결과 |
|-----------|-------------|
| `(전 직원 공람) 2025년 적극행정 우수사례 경진대회 개최 안내` | `(전 직원 공람) 2025년 적극행정 우수사례 경진대회 개최 안내` |
| `[참고] 적극행정 인식도 조사 안내` | `적극행정 인식도 조사 안내` |
| `적극행정 우수사례(안) 제출 요청` | `적극행정 우수사례 제출 요청` |

**설계 배경**:
- 공문서의 괄호는 대부분 **문서 유형 태그** (안내, 회람, 참고)
- 유사 문서 검색 시 태그 차이로 인한 불일치 방지
- 4글자 이상은 실질적인 수신자 정보일 가능성 고려

#### 2.2.3 공백 정규화

```python
# backend/app/services/text_preprocessor.py:58-59
title = re.sub(r'\s+', ' ', title)  # 연속 공백을 단일 공백으로
title = title.strip()  # 앞뒤 공백 제거
```

**목적**:
- 탭, 개행 문자 제거
- 연속 공백 정리
- 문자열 비교 정확도 향상

### 2.3 정규화 결과 예시

| 단계 | 예시 |
|------|------|
| **원본** | `(회람)  2025년\t적극행정  우수사례\n경진대회  개최  안내` |
| **유니코드 정규화** | `(회람)  2025년\t적극행정  우수사례\n경진대회  개최  안내` |
| **괄호 제거** | `  2025년\t적극행정  우수사례\n경진대회  개최  안내` |
| **공백 정규화** | `2025년 적극행정 우수사례 경진대회 개최 안내` |

## 3. 형태소 분석 및 토크나이징

### 3.1 Kiwi 형태소 분석기 선택

**Kiwi (Korean Intelligent Word Identifier)**:
- C++ 기반 고성능 형태소 분석기
- Python 바인딩: `kiwipiepy`

**선택 이유**:

| 특징 | 설명 |
|------|------|
| **속도** | C++ 기반으로 Mecab 대비 2-3배 빠름 |
| **정확도** | 공문서/행정 용어 인식률 높음 |
| **의존성** | 시스템 사전 불필요 (패키지 내 포함) |
| **유지보수** | 활발한 개발 (2024년 현재) |

**다른 형태소 분석기 비교**:

| 분석기 | 장점 | 단점 | 선택 여부 |
|--------|------|------|-----------|
| **Kiwi** | 빠름, 공문서 인식 우수 | 메모리 사용 다소 높음 | ✅ 선택 |
| Mecab | 정확도 높음 | C++ 의존성, 느림 | ❌ |
| KoNLPy (Okt) | 간편함 | 느림, 공문서 약함 | ❌ |
| KoNLPy (Komoran) | 준수한 성능 | Kiwi보다 느림 | ❌ |

### 3.2 명사 추출 전략

#### 3.2.1 구현 로직

```python
# backend/app/services/text_preprocessor.py:73-87
if self.kiwi is not None:
    result = self.kiwi.analyze(text)

    nouns = []
    for token in result[0][0]:
        # 명사 태그: NNG(일반명사), NNP(고유명사), NNB(의존명사)
        if token[1] in ['NNG', 'NNP', 'NNB']:
            word = token[0]
            # 1글자 명사 제거 (조사 등)
            if len(word) > 1:
                nouns.append(word)

    return nouns
```

#### 3.2.2 품사 태그 선택 근거

**추출 대상 품사**:

| 품사 태그 | 설명 | 예시 | 선택 이유 |
|-----------|------|------|-----------|
| **NNG** | 일반명사 | 계획, 조사, 회의 | 문서 주제 핵심 |
| **NNP** | 고유명사 | 전라북도, 행정안전부 | 기관/지명 |
| **NNB** | 의존명사 | 것, 수, 바 | 복합명사 구성 |

**제외 품사**:

| 품사 태그 | 설명 | 예시 | 제외 이유 |
|-----------|------|------|-----------|
| VV | 동사 | 실시하다, 개최하다 | BM25 검색에 노이즈 |
| VA | 형용사 | 우수하다, 적극적 | 의미 변별력 낮음 |
| MAG | 부사 | 매우, 반드시 | 검색 불필요 |
| JKS | 주격조사 | 이, 가 | 검색 불필요 |

#### 3.2.3 1글자 명사 제거

```python
# backend/app/services/text_preprocessor.py:84-85
if len(word) > 1:
    nouns.append(word)
```

**제거 대상**:
- `의`, `것`, `수` (의존명사)
- `년`, `월`, `일` (단위 명사)

**유지 대상**:
- `적극행정`, `경진대회`, `우수사례` (2글자 이상)

**설계 이유**:
- 1글자 명사는 검색 변별력 낮음
- 조사 오인식 방지

### 3.3 토크나이징 결과 예시

**입력**:
```
2025년 적극행정 우수사례 경진대회 개최 안내
```

**Kiwi 형태소 분석 결과**:
```
2025   SN    (숫자)
년     NNB   (의존명사) → 제외 (1글자)
적극   NNG   (일반명사)
행정   NNG   (일반명사)
우수   NNG   (일반명사)
사례   NNG   (일반명사)
경진   NNG   (일반명사)
대회   NNG   (일반명사)
개최   NNG   (일반명사)
안내   NNG   (일반명사)
```

**최종 토큰 리스트**:
```python
['적극', '행정', '우수', '사례', '경진', '대회', '개최', '안내']
```

## 4. Fallback 전략 (Kiwi 실패 시)

### 4.1 Lazy Initialization

```python
# backend/app/services/text_preprocessor.py:19-30
@property
def kiwi(self):
    """Kiwi 형태소 분석기 (Lazy initialization)"""
    if self._kiwi is None:
        try:
            from kiwipiepy import Kiwi
            self._kiwi = Kiwi()
            logger.info("Kiwi 형태소 분석기 초기화 완료")
        except Exception as e:
            logger.error(f"Kiwi 초기화 실패: {e}")
            self._kiwi = False  # False로 설정하여 재시도 방지
    return self._kiwi if self._kiwi is not False else None
```

**설계 의도**:
- Kiwi 로딩 시간 절약 (첫 사용 시에만 초기화)
- 초기화 실패 시 재시도 방지 (`_kiwi = False`)

### 4.2 공백 기반 토크나이징 (Fallback)

```python
# backend/app/services/text_preprocessor.py:89-95
else:
    # Kiwi를 사용할 수 없을 때 fallback: 공백 기반 토크나이징
    logger.warning("Kiwi를 사용할 수 없어 fallback 토크나이징 사용")
    return [w for w in text.split() if len(w) > 1]
```

**Fallback 예시**:

| 입력 | Fallback 결과 |
|------|---------------|
| `2025년 적극행정 우수사례 경진대회` | `['2025년', '적극행정', '우수사례', '경진대회']` |

**장점**:
- 형태소 분석 실패 시에도 서비스 지속
- 한국어 띄어쓰기 기반으로 어느 정도 분리 가능

**단점**:
- 복합명사 미분리: `적극행정` → `['적극행정']` (분리 안됨)
- 조사 붙은 단어: `경진대회를` → 정규화 없이 포함

## 5. 정규화 전략 심화: Skeleton 정규화

### 5.1 개념

**Skeleton (골격) 정규화**는 **문서 제목의 핵심 의미만 추출**하여 유사 문서를 찾는 전략입니다.

**위치**: `backend/app/services/historical_search.py:104-194`

### 5.2 Skeleton 정규화 파이프라인

```python
# backend/app/services/historical_search.py:104-194
def _normalize_to_skeleton(self, title: str) -> str:
```

**변환 단계**:

```
1. 괄호/대괄호 내용 제거
   "(전 직원 공람) 2025년 적극행정 우수사례 경진대회 개최 안내"
   → "2025년 적극행정 우수사례 경진대회 개최 안내"

2. 연도 표기 제거
   "2025년 적극행정 우수사례 경진대회 개최 안내"
   → "적극행정 우수사례 경진대회 개최 안내"

3. 시기 표기 제거
   "상반기 적극행정 우수사례 경진대회 개최 안내"
   → "적극행정 우수사례 경진대회 개최 안내"

4. 순서 표기 제거
   "제11차 적극행정 우수사례 경진대회 개최 안내"
   → "적극행정 우수사례 경진대회 개최 안내"

5. 행정 접미사 제거
   "적극행정 우수사례 경진대회 개최 안내"
   → "적극행정 우수사례 경진대회"

   ※ 제거 대상: 안내, 송부, 요청, 협조, 공유, 알림, 개최, 시행, 실시

6. 한글만 남기기
   "적극행정 우수사례 경진대회"
   → "적극행정 우수사례 경진대회"

7. 중복 단어 제거
   "적극행정 적극행정 우수사례 경진대회"
   → "적극행정 우수사례 경진대회"

8. 공백 제거 (최종)
   "적극행정 우수사례 경진대회"
   → "적극행정우수사례경진대회"
```

### 5.3 Skeleton 정규화 사례

| 원본 제목 | Skeleton 결과 |
|-----------|---------------|
| `(전 직원 공람) 2025년 적극행정 우수사례 경진대회 개최 안내` | `적극행정우수사례경진대회` |
| `2024년 적극행정 우수사례 경진대회 계획` | `적극행정우수사례경진대회` |
| `[행정정보과] 제11차 적극행정 우수사례 경진대회 송부` | `적극행정우수사례경진대회` |

**효과**:
- 연도, 순서, 행정 접미사가 달라도 **동일 Skeleton**
- Fast-Track 검색 시 **100% 일치 판단** 가능

### 5.4 보존 키워드 전략

**제거하지 않는 키워드** (`historical_search.py:156-163`):

```python
# ✅ 수정: '계획', '결과', '현황', '보고'는 업무 구분 핵심 키워드이므로 유지
admin_suffixes = [
    '안내', '송부', '요청', '협조', '공유', '알림',
    '개최', '시행', '실시', '제출', '통보',
    # '계획', '결과', '현황', '보고', '추진', '수립' → 제거하지 않음 (업무 구분용)
    '명단', '목록',
    '신청', '대상', '접수', '승인', '검토'
]
```

**이유**:
- `계획` vs `결과` → 업무 단계 구분 (다른 담당자 가능)
- `현황` vs `보고` → 문서 유형 구분

**사례**:

| 제목 | Skeleton | 구분 |
|------|----------|------|
| `적극행정 우수사례 경진대회 계획` | `적극행정우수사례경진대회계획` | 사전 계획 |
| `적극행정 우수사례 경진대회 결과` | `적극행정우수사례경진대회결과` | 사후 결과 |

## 6. 핵심 키워드 추출 (Keyword Extraction)

### 6.1 구현 위치

- **파일**: `backend/app/services/historical_search.py:196-248`
- **메서드**: `_extract_core_keywords(title: str) -> set`

### 6.2 추출 전략

```python
# backend/app/services/historical_search.py:196-248
def _extract_core_keywords(self, title: str) -> set:
```

**파이프라인**:

```
1. 괄호/대괄호 제거
2. 연도/시기 제거
3. 한글만 추출
4. 공백 기준 토큰화
5. 불용어 제거
6. 2글자 이상 필터링
```

**불용어 리스트**:

```python
stop_words = {
    # 일반 동사
    '제출', '안내', '요청', '협조', '공유', '송부', '알림', '보고',
    # 계획 관련
    '계획', '수립', '실행', '추진', '시행', '실시',
    # 시간
    '년', '월', '일',
    # 범위
    '관련', '대상', '사항',
    # 기타
    '및', '등', '의', '에', '참여', '개최'
}
```

### 6.3 키워드 추출 예시

**입력**:
```
2025년 적극행정 우수사례 경진대회 개최 안내
```

**추출 결과**:
```python
{'적극', '행정', '우수', '사례', '경진', '대회'}
```

**제거된 단어**:
- `2025년` (연도 제거)
- `개최`, `안내` (불용어)

## 7. Head Noun (행위어) 추출

### 7.1 개념

**Head Noun (행위어)**:
- 문서 제목의 **마지막 실질 명사**
- 문서의 **행위 유형**을 나타냄

**예시**:

| 제목 | Head Noun | 행위 유형 |
|------|-----------|-----------|
| `적극행정 우수사례 경진대회 개최 안내` | **경진대회** | 행사 운영 |
| `적극행정 인식도 조사 안내` | **조사** | 설문/조사 |
| `적극행정 마일리지 운영 계획 수립` | **계획** | 계획 수립 |

### 7.2 구현 로직

```python
# backend/app/services/historical_search.py:250-290
def _extract_head_noun(self, title: str) -> str:
    # 1. 괄호 제거
    # 2. 행정 접미사 제거
    # 3. 한글만 추출
    # 4. 마지막 토큰 반환
    if tokens:
        return tokens[-1]
    return ""
```

**예시**:

| 제목 | 행정 접미사 제거 후 | Head Noun |
|------|---------------------|-----------|
| `적극행정 우수사례 경진대회 개최 안내` | `적극행정 우수사례 경진대회` | `경진대회` |
| `적극행정 인식도 조사 안내` | `적극행정 인식도 조사` | `조사` |

### 7.3 행위어 유사도 계산

```python
# backend/app/services/historical_search.py:292-328
def _calculate_action_similarity(self, title1: str, title2: str) -> float:
    head1 = self._extract_head_noun(title1)
    head2 = self._extract_head_noun(title2)

    # 완전 일치
    if head1 == head2:
        return 1.0

    # 부분 일치
    if head1 in head2 or head2 in head1:
        return 0.5

    # 완전 불일치
    return 0.0
```

**사례**:

| title1 행위어 | title2 행위어 | 유사도 |
|--------------|--------------|--------|
| `경진대회` | `경진대회` | 1.0 |
| `조사` | `경진대회` | 0.0 |
| `공모사업` | `사업` | 0.5 (부분 일치) |

## 8. BM25 인덱싱 적용

### 8.1 BM25 코퍼스 구성

```python
# backend/app/services/bm25_index.py:105-123
for _, row in df.iterrows():
    title = row['제목']

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
```

**BM25 입력 데이터**:

| 문서 ID | 원본 제목 | Cleaned Title | Tokens |
|---------|-----------|---------------|--------|
| 1 | `(회람) 2025년 적극행정 우수사례 경진대회 개최 안내` | `2025년 적극행정 우수사례 경진대회 개최 안내` | `['적극', '행정', '우수', '사례', '경진', '대회', '개최', '안내']` |
| 2 | `[참고] 적극행정 인식도 조사 안내` | `적극행정 인식도 조사 안내` | `['적극', '행정', '인식', '조사', '안내']` |

### 8.2 BM25 검색 흐름

```
사용자 쿼리: "적극행정 경진대회"
    ↓
정규화: "적극행정 경진대회"
    ↓
토큰화: ['적극', '행정', '경진', '대회']
    ↓
BM25 스코어링
    ↓
상위 K개 반환
```

**BM25 스코어 계산**:
- TF (Term Frequency): 문서 내 키워드 빈도
- IDF (Inverse Document Frequency): 키워드 희소성
- 문서 길이 정규화

## 9. 벡터 임베딩 (Qdrant)

### 9.1 임베딩 모델

**모델**: `sentence-transformers` (설정: `app/config.py`)

**임베딩 생성 위치**:

```python
# backend/app/services/historical_search.py:98-102
def _create_query_embedding(self, text: str) -> List[float]:
    query_text = f"query: {text}"
    embedding = self.embedding_model.encode(query_text, normalize_embeddings=True)
    return embedding.tolist()
```

### 9.2 쿼리 프리픽스 전략

```python
query_text = f"query: {text}"
```

**이유**:
- 일부 임베딩 모델은 쿼리와 문서를 구분하여 학습
- `query:` 프리픽스로 검색 의도 명시

### 9.3 임베딩 정규화 (Normalization)

```python
normalize_embeddings=True
```

**효과**:
- 벡터 크기를 1로 정규화
- 코사인 유사도 계산이 내적(dot product)으로 간소화
- 검색 속도 향상

## 10. 정규화 전략 비교표

| 전략 | 목적 | 활용 시점 | 결과 형태 |
|------|------|-----------|-----------|
| **Clean Title** | 기본 정규화 | 모든 검색 | 공백 포함 문자열 |
| **Tokenize** | 형태소 단위 분리 | BM25 인덱싱 | 토큰 리스트 |
| **Skeleton** | 핵심 의미 추출 | Fast-Track 검색 | 공백 없는 문자열 |
| **Core Keywords** | 핵심 키워드 추출 | 하이브리드 검색 | 키워드 집합 (set) |
| **Head Noun** | 행위어 추출 | Action 유사도 | 단일 명사 |

## 11. 사용 사례별 정규화 전략

### 11.1 Fast-Track 검색 (조기 종료)

**목표**: 과거 문서와 100% 일치하는 Skeleton 찾기

```python
# backend/app/services/historical_search.py:526-563
query_skeleton = self._normalize_to_skeleton(document_title)

for result in search_results:
    hist_skeleton = self._normalize_to_skeleton(hist_title)

    if query_skeleton == hist_skeleton:
        # 완전 일치! 조기 종료
        return [hist_doc], "Stage 1: Skeleton Match"
```

**예시**:

| 쿼리 | 과거 문서 | Skeleton 일치 | 결과 |
|------|-----------|---------------|------|
| `2025년 적극행정 우수사례 경진대회 개최 안내` | `2024년 적극행정 우수사례 경진대회 계획` | `적극행정우수사례경진대회` | ✅ Fast-Track |

### 11.2 하이브리드 검색 (Deep-Check)

**목표**: 임베딩 + 키워드 + 행위어 종합 점수

```python
# backend/app/services/historical_search.py:567-639
# 1. 키워드 커버리지
keyword_coverage = self._calculate_keyword_coverage(core_keywords, hist_title)

# 2. 행위어 유사도
action_similarity = self._calculate_action_similarity(document_title, hist_title)

# 3. 최종 점수
final_score = base_score * keyword_weight * action_weight * time_weight
```

**점수 계산 예시**:

| 요소 | 값 | 가중치 |
|------|-----|--------|
| 임베딩 점수 | 0.85 | 1.0x |
| 키워드 커버리지 | 80% | 1.3x |
| 행위어 유사도 | 100% | 1.0x |
| 시간 가중치 (작년) | - | 1.3x |
| **최종 점수** | **1.44** | - |

### 11.3 BM25 검색

**목표**: 키워드 매칭 기반 문서 랭킹

```python
# backend/app/services/bm25_index.py:187-231
query_tokens = self.preprocessor.tokenize(query)

main_results, main_scores = self.main_index.retrieve([query_tokens], k=top_k)
```

**활용**:
- 부서 필터링과 결합
- Top-K Blocking (1차 후보군)

## 12. 성능 최적화 전략

### 12.1 Lazy Initialization

```python
# backend/app/services/text_preprocessor.py:19-30
@property
def kiwi(self):
    if self._kiwi is None:
        from kiwipiepy import Kiwi
        self._kiwi = Kiwi()
```

**효과**:
- 서비스 시작 시간 단축
- 메모리 사용 최적화

### 12.2 싱글톤 패턴

```python
# backend/app/services/text_preprocessor.py:135-143
_preprocessor = None

def get_preprocessor() -> TextPreprocessor:
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = TextPreprocessor()
    return _preprocessor
```

**효과**:
- Kiwi 인스턴스 재사용
- 메모리 절약

## 13. 확장 가능성

### 13.1 커스텀 불용어 사전

현재 불용어는 하드코딩되어 있으나, 향후 외부 파일로 관리 가능:

```python
# 향후 개선 방향
STOPWORDS_PATH = "/app/config/stopwords.txt"

def load_stopwords():
    with open(STOPWORDS_PATH, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f)
```

### 13.2 도메인 특화 사전

**행정 용어 사전 추가**:

```python
ADMIN_TERMS = {
    '적극행정': ['적극행정', '적극 행정'],  # 동의어
    '경진대회': ['경진대회', '경연대회'],
    '우수사례': ['우수사례', '모범사례', '우수 사례']
}
```

### 13.3 다국어 지원

현재 한국어 전용이나, 향후 영어 문서 처리 시:

```python
if detect_language(text) == 'ko':
    return self.kiwi_tokenize(text)
elif detect_language(text) == 'en':
    return self.english_tokenize(text)
```

## 14. 핵심 설계 원칙 요약

1. **단계별 정규화**: Clean → Tokenize → Keywords → Skeleton
2. **Fallback 보장**: Kiwi 실패 시 공백 기반 토크나이징
3. **명사 중심 추출**: NNG, NNP, NNB만 선택 (동사/형용사 제외)
4. **행정 용어 최적화**: 괄호 패턴, 접미사, 불용어 행정 문서 특화
5. **다층 검색 지원**: BM25(키워드) + 벡터(의미) + Skeleton(정확 일치)
6. **성능 최적화**: Lazy Init + 싱글톤 패턴

## 참고 파일

- `backend/app/services/text_preprocessor.py`: 정규화 및 토크나이저
- `backend/app/services/historical_search.py`: Skeleton, 키워드, 행위어 추출
- `backend/app/services/bm25_index.py`: BM25 인덱싱
- `backend/app/services/rag.py`: 벡터 임베딩
