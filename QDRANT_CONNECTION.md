# Qdrant 연결 상태 및 설정

## 현재 연결 구조

### 1. Docker Compose 설정
```yaml
qdrant:
  image: qdrant/qdrant:latest
  ports:
    - "6333:6333"  # HTTP API
    - "6334:6334"  # gRPC
  volumes:
    - qdrant_storage:/qdrant/storage
  networks:
    - app-network

backend:
  depends_on:
    - qdrant
  environment:
    - QDRANT_URL=http://qdrant:6333  # Docker 네트워크 내부 주소
    - QDRANT_COLLECTION=dept_knowledge
```

### 2. 백엔드 연결 코드
- **위치**: `backend/app/services/rag.py`
- **클라이언트 초기화**: `RAGService.__init__()`에서 `QdrantClient` 생성
- **연결 방식**: 
  - URL: `settings.qdrant_url` (기본값: `http://localhost:6333`)
  - API Key: `settings.qdrant_api_key` (선택적)
  - 컬렉션: `settings.qdrant_collection` (기본값: `dept_knowledge`)

### 3. 현재 문제점
1. **연결 검증 없음**: QdrantClient 생성 시 실제 연결 여부 확인 안 함
2. **컬렉션 존재 확인 없음**: `dept_knowledge` 컬렉션이 존재하는지 확인 안 함
3. **헬스 체크 없음**: Qdrant 서비스 상태 확인 API 없음

## 개선 방안

### 1. 연결 테스트 메서드 추가
### 2. 컬렉션 존재 여부 확인
### 3. 헬스 체크 엔드포인트 추가

