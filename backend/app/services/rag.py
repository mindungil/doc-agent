from typing import List
import asyncio
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from app.config import settings
from app.models.schemas import EmployeeCandidate
from app.exceptions import QdrantConnectionError, VectorSearchError


class RAGService:
    """Qdrant 벡터 검색을 통한 유사 직원 검색 서비스"""
    def __init__(self):
        self.qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        self.embedding_model = SentenceTransformer(settings.embedding_model)
        self.collection_name = settings.qdrant_collection
        self._verify_connection()
    
    def _verify_connection(self):
        """Qdrant 연결 및 컬렉션 존재 여부 확인"""
        try:
            collections = self.qdrant_client.get_collections()
            collection_names = [col.name for col in collections.collections]
            
            if self.collection_name not in collection_names:
                raise QdrantConnectionError(
                    f"컬렉션 '{self.collection_name}'이 존재하지 않습니다. "
                    f"사용 가능한 컬렉션: {', '.join(collection_names) if collection_names else '없음'}"
                )
        except Exception as e:
            raise QdrantConnectionError(f"Qdrant 연결 확인 중 오류: {str(e)}")
    
    def check_health(self) -> dict:
        """Qdrant 연결 상태 확인"""
        try:
            collections = self.qdrant_client.get_collections()
            collection_info = self.qdrant_client.get_collection(self.collection_name)
            
            return {
                "status": "healthy",
                "qdrant_url": settings.qdrant_url,
                "collection_name": self.collection_name,
                "collection_exists": True,
                "collection_points_count": collection_info.points_count,
                "available_collections": [col.name for col in collections.collections]
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    def create_query_embedding(self, text: str) -> List[float]:
        """쿼리 텍스트를 임베딩으로 변환 (multilingual-e5-large-instruct는 "query: " 접두사 필요)"""
        query_text = f"query: {text}"
        embedding = self.embedding_model.encode(query_text, normalize_embeddings=True)
        return embedding.tolist()
    
    async def search_employee_by_name(
        self,
        employee_name: str
    ) -> EmployeeCandidate:
        """메타데이터로 담당자 이름 직접 검색

        Args:
            employee_name: 검색할 직원 이름

        Returns:
            EmployeeCandidate 또는 None
        """
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            # 이름으로 필터링
            name_filter = Filter(
                must=[
                    FieldCondition(
                        key="name",
                        match=MatchValue(value=employee_name)
                    )
                ]
            )

            # Qdrant 스크롤 검색 (필터만 사용, 벡터 없음)
            search_results = await asyncio.to_thread(
                self.qdrant_client.scroll,
                collection_name=self.collection_name,
                scroll_filter=name_filter,
                limit=1
            )

            # scroll 결과는 (points, next_page_offset) 튜플
            points, _ = search_results

            if points:
                payload = points[0].payload
                return EmployeeCandidate(
                    name=payload.get("name", ""),
                    rank=payload.get("rank", ""),
                    dept1=payload.get("dept1", ""),
                    dept2=payload.get("dept2", ""),
                    dept3=payload.get("dept3", ""),
                    tasks=payload.get("tasks", ""),
                    phone=payload.get("phone", ""),
                    score=None  # 메타데이터 검색이므로 점수 없음
                )

            return None

        except Exception as e:
            raise VectorSearchError(f"이름 검색 중 오류 발생: {str(e)}")

    async def search_similar_employees(
        self,
        document_text: str,
        top_k: int = 10,
        dept_filter: str = None
    ) -> List[EmployeeCandidate]:
        """문서 텍스트와 유사한 직원을 벡터 검색으로 찾기

        Args:
            document_text: 검색할 문서 텍스트
            top_k: 상위 K개 결과
            dept_filter: 부서 필터 (dept1, dept2, dept3 중 하나라도 포함되면 매칭)
        """
        try:
            # 임베딩 생성 (CPU 집약적 작업을 별도 스레드에서 실행)
            query_embedding = await asyncio.to_thread(
                self.create_query_embedding, document_text
            )

            # Qdrant 필터 구성
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            query_filter = None
            if dept_filter:
                # dept1, dept2, dept3 중 하나라도 dept_filter를 포함하면 매칭
                query_filter = Filter(
                    should=[
                        FieldCondition(
                            key="dept1",
                            match=MatchValue(value=dept_filter)
                        ),
                        FieldCondition(
                            key="dept2",
                            match=MatchValue(value=dept_filter)
                        ),
                        FieldCondition(
                            key="dept3",
                            match=MatchValue(value=dept_filter)
                        ),
                    ]
                )

            # Qdrant 검색 (동기 작업을 별도 스레드에서 실행)
            search_results = await asyncio.to_thread(
                self.qdrant_client.search,
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k,
                query_filter=query_filter
            )
        except Exception as e:
            raise VectorSearchError(f"벡터 검색 중 오류 발생: {str(e)}")
        
        candidates = []
        for result in search_results:
            payload = result.payload
            candidate = EmployeeCandidate(
                name=payload.get("name", ""),
                rank=payload.get("rank", ""),
                dept1=payload.get("dept1", ""),
                dept2=payload.get("dept2", ""),
                dept3=payload.get("dept3", ""),
                tasks=payload.get("tasks", ""),
                phone=payload.get("phone", ""),
                score=result.score,
            )
            candidates.append(candidate)

        return candidates


# 싱글톤 인스턴스
rag_service = RAGService()

