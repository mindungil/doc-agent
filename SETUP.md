# 환경 설정 가이드

## .env 파일 설정

프로젝트 루트 디렉터리에 `.env` 파일이 있습니다. 이 파일은 애플리케이션의 모든 설정을 관리합니다.

### 필수 설정

#### 1. Qdrant 설정
```env
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=dept_knowledge
```

**Docker Compose 사용 시:**
- `QDRANT_URL`은 자동으로 `http://qdrant:6333`으로 설정됩니다
- 별도 설정 불필요

**로컬 개발 시:**
- Qdrant가 로컬에서 실행 중이면: `http://localhost:6333`
- 원격 Qdrant 사용 시: 해당 서버 URL

#### 2. LLM 설정
```env
LLM_API_URL=http://192.168.0.201:30010/v1/chat/completions
LLM_MODEL=/mnt/ssd16tb/MiniMaxAI--MiniMax-M2
```

**LLM 서버 변경 시:**
- `LLM_API_URL`을 새로운 서버 주소로 변경
- OpenAI 형식 API를 사용해야 합니다
- `/v1/chat/completions` 엔드포인트가 필요합니다

#### 3. 임베딩 모델
```env
EMBEDDING_MODEL=intfloat/multilingual-e5-large-instruct
```

처음 실행 시 자동으로 다운로드됩니다.

### 선택적 설정

```env
# Qdrant API 키 (필요한 경우)
QDRANT_API_KEY=

# LLM API 키 (필요한 경우)
LLM_API_KEY=
```

## 설정 확인

### 1. 환경 변수 로드 확인

Backend 시작 시 환경 변수가 올바르게 로드되는지 확인:

```bash
cd backend
python -c "from app.config import settings; print(f'Qdrant URL: {settings.qdrant_url}'); print(f'LLM URL: {settings.llm_api_url}'); print(f'LLM Model: {settings.llm_model}')"
```

### 2. Qdrant 연결 확인

```bash
# API로 확인
curl http://localhost:7000/api/documents/health/qdrant

# 직접 확인
curl http://localhost:6333/collections
```

### 3. LLM 연결 확인

문서 추천 기능을 사용하여 LLM 연결을 테스트합니다.

## 환경별 설정 예시

### 개발 환경
```env
QDRANT_URL=http://localhost:6333
LLM_API_URL=http://192.168.0.201:30010/v1/chat/completions
LLM_MODEL=/mnt/ssd16tb/MiniMaxAI--MiniMax-M2
```

### 프로덕션 환경
```env
QDRANT_URL=http://qdrant:6333
LLM_API_URL=http://192.168.0.201:30010/v1/chat/completions
LLM_MODEL=/mnt/ssd16tb/MiniMaxAI--MiniMax-M2
QDRANT_API_KEY=your-api-key
LLM_API_KEY=your-api-key
```

## 주의사항

1. **.env 파일 보안**
   - `.env` 파일은 Git에 커밋하지 마세요 (이미 .gitignore에 포함됨)
   - 프로덕션 환경에서는 환경 변수를 직접 설정하거나 보안 관리 도구 사용

2. **Docker Compose 사용 시**
   - `.env` 파일의 `QDRANT_URL`은 무시되고 `http://qdrant:6333`으로 자동 설정됩니다
   - 다른 설정은 `.env` 파일에서 읽습니다

3. **로컬 개발 시**
   - Qdrant가 실행 중이어야 합니다
   - LLM 서버에 네트워크 접근이 가능해야 합니다

