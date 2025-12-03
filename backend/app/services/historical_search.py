"""과거 문서 배부 이력 기반 검색 서비스"""
import asyncio
import json
import logging
import httpx
from typing import List, Optional, Tuple
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.models.schemas import EmployeeCandidate
from app.models.ocr_schemas import SelectedDepartment
from app.services.rag import rag_service
from app.services.rank_mapper import rank_mapper
from app.exceptions import VectorSearchError, LLMServiceError

logger = logging.getLogger(__name__)


class HistoricalDocument:
    """과거 문서 정보"""
    def __init__(self, payload: dict, score: float):
        self.title = payload.get("제목", "")
        self.reporter = payload.get("보고자", "")
        self.department = payload.get("소속부서", "")
        self.sender = payload.get("수(발)신자", "")
        self.report_date = payload.get("보고일자", "")
        self.doc_type = payload.get("문서구분", "")
        self.score = score


class HistoricalSearchService:
    """과거 문서 배부 이력을 활용한 검색 서비스"""

    def __init__(self):
        self.qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        self.embedding_model = SentenceTransformer(settings.embedding_model)
        self.tasks_collection = "tasks"

    async def search_similar_historical_documents(
        self,
        document_text: str,
        document_title: str = "",
        top_k: int = 5
    ) -> List[HistoricalDocument]:
        """
        과거 유사 문서 검색

        Args:
            document_text: 문서 내용
            document_title: 문서 제목
            top_k: 반환할 문서 수

        Returns:
            List[HistoricalDocument]: 유사한 과거 문서 목록
        """
        try:
            # 쿼리 텍스트 구성 (제목 가중치 높임)
            if document_title:
                query_text = f"{document_title}\n{document_title}\n{document_text[:1000]}"
            else:
                query_text = document_text[:1500]

            # 임베딩 생성
            query_embedding = await asyncio.to_thread(
                self._create_query_embedding,
                query_text
            )

            # Qdrant 검색
            search_results = await asyncio.to_thread(
                self.qdrant_client.search,
                collection_name=self.tasks_collection,
                query_vector=query_embedding,
                limit=top_k,
            )

            # 결과 파싱
            historical_docs = []
            for result in search_results:
                doc = HistoricalDocument(result.payload, result.score)
                historical_docs.append(doc)
                logger.info(
                    f"유사 과거 문서: {doc.title[:50]} "
                    f"(보고자: {doc.reporter}, 부서: {doc.department}, "
                    f"유사도: {doc.score:.3f})"
                )

            return historical_docs

        except Exception as e:
            logger.error(f"과거 문서 검색 실패: {str(e)}")
            raise VectorSearchError(f"과거 문서 검색 중 오류: {str(e)}")

    def _create_query_embedding(self, text: str) -> List[float]:
        """쿼리 임베딩 생성"""
        query_text = f"query: {text}"
        embedding = self.embedding_model.encode(query_text, normalize_embeddings=True)
        return embedding.tolist()

    def _normalize_to_skeleton(self, title: str) -> str:
        """
        제목을 정규화된 골격(Skeleton)으로 변환

        변환 과정:
        1. 연도 제거 (2024년, 25년 등)
        2. 괄호 내용 제거 ((전 직원 공람), [안내] 등)
        3. 행정 접미사 제거 (안내, 송부, 요청, 개최, 알림, 계획 등)
        4. 공백 제거

        예시:
        - "(전 직원 공람) 2025년 적극행정 우수사례 경진대회 개최 안내"
          → "적극행정우수사례경진대회"
        - "2024년 적극행정 우수사례 경진대회 계획"
          → "적극행정우수사례경진대회"

        Args:
            title: 문서 제목

        Returns:
            str: 정규화된 골격 문자열
        """
        import re

        logger.info(f"[Skeleton] 입력 제목: {title}")
        skeleton = title

        # 1. 괄호/대괄호 내용 제거
        skeleton = re.sub(r'\(.*?\)', '', skeleton)
        skeleton = re.sub(r'\[.*?\]', '', skeleton)
        skeleton = re.sub(r'【.*?】', '', skeleton)
        logger.info(f"[Skeleton] 1. 괄호 제거 후: {skeleton}")

        # 2. 연도 표기 제거 (다양한 형식)
        skeleton = re.sub(r'\d{4}년도?', '', skeleton)  # 2024년, 2024년도
        skeleton = re.sub(r'\d{2}년도?', '', skeleton)   # 25년, 25년도
        skeleton = re.sub(r"'\d{2}", '', skeleton)        # '24
        logger.info(f"[Skeleton] 2. 연도 제거 후: {skeleton}")

        # 3. 시기 표기 제거
        skeleton = re.sub(r'[상하]반기', '', skeleton)
        skeleton = re.sub(r'\d+월', '', skeleton)
        skeleton = re.sub(r'\d+분기', '', skeleton)
        logger.info(f"[Skeleton] 3. 시기 제거 후: {skeleton}")

        # 3-1. 순서 표기 제거 (제N차 → 숫자 제거 후 "제차" 남는 것 방지)
        before = skeleton
        skeleton = re.sub(r'제\d+차', '', skeleton)  # 제11차, 제1차 등
        if before != skeleton:
            logger.info(f"[Skeleton] 3-1. 순서 표기 제거: '{before}' → '{skeleton}'")

        # 4. 행정 접미사 제거 (공문서 특화)
        # ✅ 수정: '계획', '결과', '현황', '보고'는 업무 구분 핵심 키워드이므로 유지
        admin_suffixes = [
            '안내', '송부', '요청', '협조', '공유', '알림',
            '개최', '시행', '실시', '제출', '통보',
            # '계획', '결과', '현황', '보고', '추진', '수립' → 제거하지 않음 (업무 구분용)
            '명단', '목록',
            '신청', '대상', '접수', '승인', '검토'
        ]
        removed_suffixes = []
        for suffix in admin_suffixes:
            if suffix in skeleton:
                removed_suffixes.append(suffix)
                skeleton = skeleton.replace(suffix, '')
        if removed_suffixes:
            logger.info(f"[Skeleton] 4. 접미사 제거: {removed_suffixes}")
            logger.info(f"[Skeleton] 4. 접미사 제거 후: {skeleton}")

        # 5. 접속사 제거 (및, 또는, 등)
        conjunctions = ['및', '또는', '등']
        for conj in conjunctions:
            skeleton = skeleton.replace(conj, ' ')  # 공백으로 치환해서 단어 분리
        logger.info(f"[Skeleton] 5. 접속사 제거 후: {skeleton}")

        # 6. 한글만 남기기 (영문, 숫자, 특수문자 제거)
        skeleton = re.sub(r'[^가-힣]', ' ', skeleton)  # 공백으로 치환
        logger.info(f"[Skeleton] 6. 한글만 남기기: {skeleton}")

        # 7. 중복 단어 제거 (순서 유지)
        # 공백으로 분리 후 중복 제거
        words = []
        seen = set()
        for word in skeleton.split():
            if word and word not in seen:
                words.append(word)
                seen.add(word)
        skeleton = ''.join(words)
        logger.info(f"[Skeleton] 7. 최종 Skeleton: '{skeleton}'")

        return skeleton

    def _extract_core_keywords(self, title: str) -> set:
        """
        핵심 키워드 추출 (공문서 특화)

        제거 대상:
        - 괄호/대괄호 내용 (예: "(전 직원 공람)")
        - 연도 표기 (예: "2025년")
        - 시기 표기 (예: "상반기", "하반기")
        - 일반 공문 동사 (예: "제출", "안내", "요청")

        Args:
            title: 문서 제목

        Returns:
            set: 2글자 이상 핵심 키워드 집합
        """
        import re

        # 1. 전처리
        cleaned = title
        cleaned = re.sub(r'\(.*?\)', '', cleaned)       # 괄호 제거
        cleaned = re.sub(r'\[.*?\]', '', cleaned)       # 대괄호 제거
        cleaned = re.sub(r'\d{4}년', '', cleaned)       # 연도 제거
        cleaned = re.sub(r'[상하]반기', '', cleaned)     # 시기 제거
        cleaned = re.sub(r'\d+월', '', cleaned)         # 월 제거

        # 2. 확장된 불용어 (공문서 특화)
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

        # 3. 한글만 추출
        cleaned = re.sub(r'[^가-힣\s]', ' ', cleaned)

        # 4. 토큰화 및 필터링
        tokens = cleaned.split()

        # 5. 불용어 제거 + 2글자 이상
        keywords = {
            token for token in tokens
            if len(token) >= 2 and token not in stop_words
        }

        return keywords

    def _extract_head_noun(self, title: str) -> str:
        """
        제목에서 마지막 실질 명사(Head Noun) 추출

        행위어를 찾기 위해 제목의 맨 마지막 유의미한 명사를 추출합니다.

        예시:
        - "적극행정 우수사례 경진대회 개최 안내" → "경진대회"
        - "적극행정 인식도 조사 안내" → "조사"
        - "국민 참여 예산 공모사업 실시 계획" → "공모사업"

        Args:
            title: 문서 제목

        Returns:
            str: 마지막 실질 명사 (행위어)
        """
        import re

        # 1. 전처리
        cleaned = title
        cleaned = re.sub(r'\(.*?\)', '', cleaned)
        cleaned = re.sub(r'\[.*?\]', '', cleaned)

        # 2. 행정 접미사 제거
        admin_suffixes = [
            '안내', '송부', '요청', '협조', '공유', '알림', '보고',
            '개최', '시행', '실시', '추진', '수립', '제출', '통보',
            '계획', '결과', '현황', '명단', '목록'
        ]
        for suffix in admin_suffixes:
            cleaned = cleaned.replace(suffix, '')

        # 3. 한글만 추출하여 토큰화
        cleaned = re.sub(r'[^가-힣\s]', ' ', cleaned)
        tokens = [t for t in cleaned.split() if len(t) >= 2]

        # 4. 마지막 토큰 반환 (가장 핵심적인 행위어)
        if tokens:
            return tokens[-1]
        return ""

    def _calculate_action_similarity(self, title1: str, title2: str) -> float:
        """
        두 제목의 행위(Action) 유사도 계산

        로직:
        1. 각 제목에서 Head Noun(행위어) 추출
        2. 두 행위어가 같으면 1.0, 다르면 0.0
        3. 행위어가 서로 포함 관계면 0.5 (부분 일치)

        예시:
        - "경진대회" vs "경진대회" → 1.0
        - "조사" vs "경진대회" → 0.0
        - "공모사업" vs "사업" → 0.5

        Args:
            title1: 첫 번째 제목
            title2: 두 번째 제목

        Returns:
            float: 0.0 ~ 1.0 (행위 유사도)
        """
        head1 = self._extract_head_noun(title1)
        head2 = self._extract_head_noun(title2)

        if not head1 or not head2:
            return 0.5  # 추출 실패 시 중립

        # 완전 일치
        if head1 == head2:
            return 1.0

        # 부분 일치 (포함 관계)
        if head1 in head2 or head2 in head1:
            return 0.5

        # 완전 불일치
        return 0.0

    def _calculate_keyword_coverage(self, query_keywords: set, target_title: str) -> float:
        """
        키워드 커버리지 계산

        방법:
        1. 정확 매칭: 쿼리 키워드와 타겟 키워드가 정확히 일치
        2. 부분 매칭: 쿼리 키워드가 타겟 제목에 포함 (substring)

        Args:
            query_keywords: 쿼리에서 추출한 키워드 집합
            target_title: 타겟 문서 제목

        Returns:
            float: 0.0 ~ 1.0 (매칭된 키워드 비율)
        """
        if not query_keywords:
            return 0.5  # 키워드 없으면 중립

        # 타겟 제목에서도 키워드 추출
        target_keywords = self._extract_core_keywords(target_title)

        # 방법 1: 정확한 토큰 매칭 (교집합)
        exact_matched = len(query_keywords & target_keywords)
        exact_coverage = exact_matched / len(query_keywords)

        # 방법 2: 부분 매칭 (substring 포함)
        partial_matched = 0
        for qk in query_keywords:
            # 쿼리 키워드가 타겟 제목에 포함되거나
            # 타겟 키워드 중 하나와 겹치면 카운트
            if qk in target_title or any(qk in tk or tk in qk for tk in target_keywords):
                partial_matched += 1

        partial_coverage = partial_matched / len(query_keywords)

        # 결합: 정확 매칭 70%, 부분 매칭 30%
        final_coverage = (exact_coverage * 0.7) + (partial_coverage * 0.3)

        return final_coverage

    async def get_candidates_from_historical_docs(
        self,
        historical_docs: List[HistoricalDocument],
        min_score: float = 0.5
    ) -> List[EmployeeCandidate]:
        """
        과거 문서 이력에서 후보자 추출

        Args:
            historical_docs: 과거 유사 문서 목록
            min_score: 최소 유사도 점수

        Returns:
            List[EmployeeCandidate]: 추출된 직원 후보 목록
        """
        if not historical_docs:
            logger.warning("과거 문서가 없습니다")
            return []

        # 보고자와 부서 정보 수집
        reporters = []
        departments = []

        for doc in historical_docs:
            if doc.score >= min_score:
                if doc.reporter:
                    reporters.append(doc.reporter)
                if doc.department:
                    departments.append(doc.department)

        logger.info(f"추출된 보고자: {reporters}")
        logger.info(f"추출된 부서: {departments}")

        if not reporters and not departments:
            logger.warning("과거 문서에서 보고자/부서 정보를 찾을 수 없습니다")
            return []

        # 보고자 이름으로 직원 검색
        candidates = []

        # 1. 보고자 이름으로 직접 검색
        for reporter in set(reporters):  # 중복 제거
            try:
                search_query = f"{reporter}"
                reporter_candidates = await rag_service.search_similar_employees(
                    search_query,
                    top_k=3
                )

                # 이름이 일치하는 직원 필터링
                for candidate in reporter_candidates:
                    # 과거 문서 유사도 계산
                    matching_docs = [d for d in historical_docs if d.reporter == reporter]
                    if not matching_docs:
                        continue

                    avg_historical_score = sum(d.score for d in matching_docs) / len(matching_docs)

                    # ✅ 정확 일치 vs 부분 일치 구분
                    is_exact_match = (candidate.name == reporter)

                    if is_exact_match:
                        # 정확 일치: tasks의 보고자와 정확히 같은 이름
                        # → 높은 점수 보장 (최소 0.95, 또는 과거 점수가 더 높으면 그대로)
                        candidate.score = max(0.95, avg_historical_score)
                        candidates.append(candidate)
                        logger.info(f"✅ 보고자 정확 일치: {candidate.name} (점수: {candidate.score:.3f})")

                    elif reporter in candidate.name or candidate.name in reporter:
                        # 부분 일치: 이름이 포함되어 있음 (예: "김철수" in "김철수A")
                        # → 점수를 낮춤 (70%)
                        candidate.score = avg_historical_score * 0.7
                        candidates.append(candidate)
                        logger.info(f"⚠️  보고자 부분 일치: {candidate.name} (점수: {candidate.score:.3f})")

            except Exception as e:
                logger.error(f"보고자 검색 실패 ({reporter}): {str(e)}")

        # 2. 부서 정보로 추가 검색 (보완)
        if not candidates and departments:
            for dept in set(departments):
                try:
                    dept_candidates = await rag_service.search_similar_employees(
                        dept,
                        top_k=5
                    )

                    # 부서가 일치하는 직원 필터링
                    for candidate in dept_candidates:
                        if (dept in (candidate.dept1 or "") or
                            dept in (candidate.dept2 or "") or
                            dept in (candidate.dept3 or "")):
                            candidates.append(candidate)
                            logger.info(f"부서 매칭: {candidate.name} ({candidate.dept1})")

                except Exception as e:
                    logger.error(f"부서 검색 실패 ({dept}): {str(e)}")

        # 중복 제거 (이름 기준)
        unique_candidates = {}
        for candidate in candidates:
            if candidate.name not in unique_candidates:
                unique_candidates[candidate.name] = candidate
            else:
                # 점수가 더 높은 것으로 유지
                if candidate.score and (
                    not unique_candidates[candidate.name].score or
                    candidate.score > unique_candidates[candidate.name].score
                ):
                    unique_candidates[candidate.name] = candidate

        final_candidates = list(unique_candidates.values())

        # 점수순 정렬
        final_candidates.sort(key=lambda c: c.score or 0, reverse=True)

        logger.info(f"과거 문서 기반 후보자 {len(final_candidates)}명 추출 완료")

        return final_candidates

    async def search_with_three_stage_pipeline(
        self,
        document_title: str,
        document_summary: str = "",
        top_k: int = 3
    ) -> tuple[List[HistoricalDocument], str]:
        """
        3단계 우선순위 파이프라인

        Stage 1: Skeleton Matching (Fast-Track)
        - 정규화된 골격이 100% 일치하면 즉시 반환
        - 연도, 괄호, 접미사 모두 제거 후 비교

        Stage 2: Action-based Hybrid Search (Deep-Check)
        - 임베딩 + 키워드 + 행위어 유사도
        - 행위어가 다르면 페널티 적용

        Stage 3: LLM Final Verification (Safety Net)
        - 유사도 0.85~0.95 구간만 LLM 판단
        - 3가지 체크: 연속성, 대체불가능성, Action 일치

        Args:
            document_title: 문서 제목
            document_summary: 문서 요약 (Stage 3 LLM 판단용)
            top_k: 반환할 문서 수

        Returns:
            (과거 문서 목록, 처리 단계 설명)
        """
        import re

        if not document_title or len(document_title.strip()) < 3:
            logger.warning("제목이 너무 짧아 검색 불가")
            return [], "제목이 너무 짧음"

        try:
            # ===== Stage 1: Skeleton Matching (Fast-Track) =====
            logger.info("=== Stage 1: Skeleton Matching ===")
            query_skeleton = self._normalize_to_skeleton(document_title)
            logger.info(f"입력 제목 Skeleton: '{query_skeleton}'")

            if len(query_skeleton) >= 4:  # 최소 4글자 이상이어야 의미 있음
                # Qdrant에서 상위 20개 검색
                query_text = f"{document_title}\n{document_title}"
                query_embedding = await asyncio.to_thread(
                    self._create_query_embedding,
                    query_text
                )

                search_results = await asyncio.to_thread(
                    self.qdrant_client.search,
                    collection_name=self.tasks_collection,
                    query_vector=query_embedding,
                    limit=20,
                )

                # Skeleton 일치 확인
                exact_matches = []
                for result in search_results:
                    hist_title = result.payload.get("제목", "")
                    hist_skeleton = self._normalize_to_skeleton(hist_title)

                    if query_skeleton == hist_skeleton:
                        # 완전 일치! 즉시 반환
                        hist_doc = HistoricalDocument(result.payload, 1.0)  # 100% 매칭
                        exact_matches.append(hist_doc)
                        logger.info(
                            f"✅ Skeleton 일치: {hist_title[:50]} "
                            f"(보고자: {hist_doc.reporter})"
                        )

                if exact_matches:
                    logger.info(f"🚀 Stage 1 완료: {len(exact_matches)}개 완전 일치 발견")
                    return exact_matches[:top_k], "Stage 1: Skeleton Match (Fast-Track)"

            logger.info("❌ Stage 1: 완전 일치 없음 → Stage 2로 진행")

            # ===== Stage 2: Action-based Hybrid Search (Deep-Check) =====
            logger.info("=== Stage 2: Action-based Hybrid Search ===")

            # 연도 추출
            year_match = re.search(r'(\d{4})년', document_title)
            current_year = int(year_match.group(1)) if year_match else None

            # 핵심 키워드 추출
            core_keywords = self._extract_core_keywords(document_title)
            logger.info(f"추출된 핵심 키워드: {core_keywords}")

            # 임베딩 검색 (넉넉하게 30개)
            query_text = f"{document_title}\n{document_title}"
            query_embedding = await asyncio.to_thread(
                self._create_query_embedding,
                query_text
            )

            search_results = await asyncio.to_thread(
                self.qdrant_client.search,
                collection_name=self.tasks_collection,
                query_vector=query_embedding,
                limit=30,
            )

            # 재점수화 (임베딩 + 키워드 + 행위어 + 시간)
            scored_results = []

            for result in search_results:
                hist_title = result.payload.get("제목", "")
                hist_reporter = result.payload.get("보고자", "")

                # 1. 키워드 커버리지
                keyword_coverage = self._calculate_keyword_coverage(
                    core_keywords,
                    hist_title
                )

                # 2. 행위어 유사도 (신규)
                action_similarity = self._calculate_action_similarity(
                    document_title,
                    hist_title
                )

                # 3. 시간 가중치
                hist_year_match = re.search(r'(\d{4})년', hist_title)
                hist_year = int(hist_year_match.group(1)) if hist_year_match else None

                time_weight = 1.0
                if current_year and hist_year:
                    diff = current_year - hist_year
                    if diff == 1:
                        time_weight = 1.3
                    elif diff == 0:
                        time_weight = 1.1
                    elif diff < 0:
                        time_weight = 0.3
                    else:
                        time_weight = max(0.7, 1.0 - (diff * 0.05))

                # 4. 최종 점수 계산
                base_score = result.score

                # 키워드 가중치 (0.5 ~ 1.5)
                keyword_weight = 0.5 + (keyword_coverage * 1.0)

                # 행위어 가중치 (0.3 ~ 1.0)
                # 행위어가 완전히 다르면 큰 페널티 (0.3배)
                # 행위어가 같으면 보너스 (1.0배)
                action_weight = 0.3 + (action_similarity * 0.7)

                # 최종 점수 = base * keyword * action * time
                final_score = base_score * keyword_weight * action_weight * time_weight

                hist_doc = HistoricalDocument(result.payload, final_score)

                scored_results.append({
                    'doc': hist_doc,
                    'final_score': final_score,
                    'base_score': base_score,
                    'keyword_coverage': keyword_coverage,
                    'keyword_weight': keyword_weight,
                    'action_similarity': action_similarity,
                    'action_weight': action_weight,
                    'time_weight': time_weight
                })

            # 정렬
            scored_results.sort(key=lambda x: x['final_score'], reverse=True)

            # 로깅
            logger.info(f"\n=== Stage 2 결과 (입력: {document_title[:50]}) ===")
            for i, res in enumerate(scored_results[:5], 1):
                doc = res['doc']
                logger.info(
                    f"[순위 {i}] {doc.title[:50]}\n"
                    f"  보고자: {doc.reporter} | 부서: {doc.department}\n"
                    f"  임베딩: {res['base_score']:.3f} | "
                    f"키워드: {res['keyword_coverage']:.2f}({res['keyword_weight']:.2f}x) | "
                    f"행위어: {res['action_similarity']:.2f}({res['action_weight']:.2f}x) | "
                    f"시간: {res['time_weight']:.2f}x | "
                    f"최종: {res['final_score']:.3f}"
                )

            # ===== Stage 3: LLM Final Verification (Safety Net) =====
            # 최고 점수가 0.85~0.95 구간인 경우에만 LLM 검증
            if scored_results:
                max_score = scored_results[0]['final_score']

                if 0.85 <= max_score < 0.95:
                    logger.info("=== Stage 3: LLM Final Verification ===")
                    logger.info(f"유사도 {max_score:.3f} → LLM 연속성 판단")

                    best_doc = scored_results[0]['doc']

                    # LLM 연속성 판단
                    is_continuous, reasoning = await self.check_topic_continuity_with_llm(
                        current_title=document_title,
                        current_summary=document_summary or document_title,
                        historical_title=best_doc.title,
                        historical_reporter=best_doc.reporter,
                        historical_department=best_doc.department
                    )

                    if is_continuous:
                        logger.info("✅ LLM 연속성 확인 → Stage 2 결과 신뢰")
                        return [r['doc'] for r in scored_results[:top_k]], "Stage 2 + Stage 3: LLM 연속성 확인"
                    else:
                        logger.warning("❌ LLM 연속성 부정 → 결과 신뢰도 하락")
                        # 연속성이 없다고 판단되면 점수를 낮춤
                        for res in scored_results:
                            res['final_score'] *= 0.7  # 30% 감점
                        scored_results.sort(key=lambda x: x['final_score'], reverse=True)
                        return [r['doc'] for r in scored_results[:top_k]], "Stage 2 (LLM 연속성 부정)"

                elif max_score >= 0.95:
                    logger.info(f"✅ 고유사도 ({max_score:.3f}) → LLM 생략")
                    return [r['doc'] for r in scored_results[:top_k]], "Stage 2: High Confidence"
                else:
                    logger.info(f"⚠️ 저유사도 ({max_score:.3f}) → LLM 불필요")
                    return [r['doc'] for r in scored_results[:top_k]], "Stage 2: Low Confidence"

            return [r['doc'] for r in scored_results[:top_k]], "Stage 2: Hybrid Search"

        except Exception as e:
            logger.error(f"3단계 파이프라인 실패: {str(e)}")
            return [], f"오류: {str(e)}"

    async def search_by_title_only(
        self,
        document_title: str,
        top_k: int = 3
    ) -> List[HistoricalDocument]:
        """
        하이브리드 제목 검색: 임베딩 + 키워드 매칭 + 시간 연속성

        전략:
        1. 임베딩으로 넓은 후보군 확보 (문맥적 유사성)
        2. 키워드 일치도로 정확성 검증 (오답 필터링)
        3. 연도 차이로 시계열 연속성 반영 (정기 보고서 우선)

        Args:
            document_title: 문서 제목
            top_k: 반환할 문서 수

        Returns:
            List[HistoricalDocument]: 재점수화된 과거 문서 목록
        """
        import re

        if not document_title or len(document_title.strip()) < 3:
            logger.warning("제목이 너무 짧아 검색 불가")
            return []

        try:
            # Step 1: 연도 추출
            year_match = re.search(r'(\d{4})년', document_title)
            current_year = int(year_match.group(1)) if year_match else None

            # Step 2: 핵심 키워드 추출
            core_keywords = self._extract_core_keywords(document_title)
            logger.info(f"추출된 핵심 키워드: {core_keywords}")

            # Step 3: 임베딩 검색 (넉넉하게 20개)
            query_text = f"{document_title}\n{document_title}"
            query_embedding = await asyncio.to_thread(
                self._create_query_embedding,
                query_text
            )

            search_results = await asyncio.to_thread(
                self.qdrant_client.search,
                collection_name=self.tasks_collection,
                query_vector=query_embedding,
                limit=20,  # 후보군 확대
            )

            # Step 4: 재점수화
            scored_results = []

            for result in search_results:
                hist_title = result.payload.get("제목", "")
                hist_reporter = result.payload.get("보고자", "")

                # 4-1. 키워드 커버리지 계산
                keyword_coverage = self._calculate_keyword_coverage(
                    core_keywords,
                    hist_title
                )

                # 4-2. 시간 가중치 계산
                hist_year_match = re.search(r'(\d{4})년', hist_title)
                hist_year = int(hist_year_match.group(1)) if hist_year_match else None

                time_weight = 1.0
                if current_year and hist_year:
                    diff = current_year - hist_year

                    if diff == 1:      # 작년 문서 (가장 강력한 후보)
                        time_weight = 1.3
                    elif diff == 0:    # 동일 연도 (다른 담당자)
                        time_weight = 1.1
                    elif diff < 0:     # 미래 문서 (데이터 오류 가능성)
                        time_weight = 0.3
                        logger.warning(f"미래 문서 발견: {hist_title} (연도: {hist_year})")
                    else:              # 2년 이상 과거
                        # 오래된 문서는 감점 (매년 담당자 변동 가능)
                        time_weight = max(0.7, 1.0 - (diff * 0.05))

                # 4-3. 최종 점수 계산
                # 기본 점수 = 임베딩 유사도
                base_score = result.score

                # 키워드 가중치 (0.5~1.5 범위)
                # 키워드 0% 매칭 → 0.5배, 100% 매칭 → 1.5배
                keyword_weight = 0.5 + (keyword_coverage * 1.0)

                # 최종 점수 = base * keyword * time
                # 키워드 매칭이 낮으면 자동으로 페널티 (곱셈 효과)
                final_score = base_score * keyword_weight * time_weight

                # HistoricalDocument의 score를 final_score로 설정 (중요!)
                hist_doc = HistoricalDocument(result.payload, final_score)

                scored_results.append({
                    'doc': hist_doc,
                    'final_score': final_score,
                    'base_score': base_score,
                    'keyword_coverage': keyword_coverage,
                    'keyword_weight': keyword_weight,
                    'time_weight': time_weight
                })

            # Step 5: 정렬
            scored_results.sort(key=lambda x: x['final_score'], reverse=True)

            # Step 6: 로깅 (디버깅용)
            logger.info(f"\n=== 하이브리드 검색 결과 (입력: {document_title[:50]}) ===")
            for i, res in enumerate(scored_results[:5], 1):
                doc = res['doc']
                logger.info(
                    f"[순위 {i}] {doc.title[:50]}\n"
                    f"  보고자: {doc.reporter} | 부서: {doc.department}\n"
                    f"  임베딩: {res['base_score']:.3f} | "
                    f"키워드: {res['keyword_coverage']:.2f}({res['keyword_weight']:.2f}x) | "
                    f"시간: {res['time_weight']:.2f}x | "
                    f"최종: {res['final_score']:.3f}"
                )

            # Step 7: 상위 top_k 반환
            return [r['doc'] for r in scored_results[:top_k]]

        except Exception as e:
            logger.error(f"제목 기반 검색 실패: {str(e)}")
            return []

    async def check_topic_continuity_with_llm(
        self,
        current_title: str,
        current_summary: str,
        historical_title: str,
        historical_reporter: str,
        historical_department: str
    ) -> Tuple[bool, str]:
        """
        LLM을 사용하여 주제 연속성 판단

        Args:
            current_title: 현재 문서 제목
            current_summary: 현재 문서 요약
            historical_title: 과거 문서 제목
            historical_reporter: 과거 보고자
            historical_department: 과거 부서

        Returns:
            (연속성 여부, 판단 이유)
        """
        system_prompt = """당신은 행정 문서의 업무 연속성을 판단하는 전문가입니다.

**판단 기준 (3가지 조건을 모두 만족해야 True):**

1. **연속성 (Continuity):**
   - 작년의 그 업무가 올해 이 업무로 이어진 것인가?
   - 정기 보고서, 반복 업무, 연속 프로젝트
   - 예: "2024년 조사" → "2025년 조사" (O)

2. **대체 불가능성 (Exclusivity):**
   - 과거 문서를 처리한 사람이 현재 문서도 처리했을 확률이 90% 이상인가?
   - 예: "적극행정 조사"와 "적극행정 마일리지 계획"은 다른 담당자일 수 있음 (X)

3. **세부 주제 일치 (Action-Level Match):**
   - 업무의 Action 레벨이 같은가?
   - "조사/설문" vs "계획 수립" vs "행사 운영" vs "평가/심사" → 다른 Action
   - 예: "인식도 조사"와 "우수사례 경진대회"는 주제(적극행정)만 같고 Action이 다름 (X)

**False 판정 사례:**
- 같은 주제어("적극행정")를 공유하지만 서로 다른 업무
- 단순 유사 키워드 (예: "조사"와 "검토"는 다름)
- 일회성 행사 vs 정기 보고
- 부서가 다른 경우 (예: 정책기획관 vs 인구청년정책과)"""

        user_prompt = f"""[현재 문서]
제목: {current_title}
요약: {current_summary}

[과거 유사 문서]
제목: {historical_title}
과거 보고자: {historical_reporter}
소속 부서: {historical_department}

**질문:**
위 두 문서가 **동일 담당자**가 처리해야 하는 **연속 업무**인가요?

**체크리스트:**
1. 연속성: 작년 업무 → 올해 업무? (정기/반복 업무인가?)
2. 대체 불가능성: 동일 담당자 처리 확률 90% 이상인가?
3. Action 일치: 업무 유형(조사/계획/행사/평가 등)이 같은가?

다음 JSON 형식으로만 응답:
{{
  "is_continuous": true 또는 false,
  "continuity_check": true/false (연속성),
  "exclusivity_check": true/false (대체 불가능성),
  "action_match_check": true/false (Action 일치),
  "reasoning": "판단 이유 (3가지 기준별로 설명)",
  "confidence": 0.0~1.0 (확신도)
}}

**주의:** 3가지 체크가 모두 true여야만 is_continuous=true"""

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                headers = {"Content-Type": "application/json"}
                if settings.llm_api_key:
                    headers["Authorization"] = f"Bearer {settings.llm_api_key}"

                payload = {
                    "model": settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.1,
                }

                logger.info("LLM 주제 연속성 판단 호출")
                response = await client.post(
                    settings.llm_api_url,
                    json=payload,
                    headers=headers
                )

                response.raise_for_status()
                result = response.json()

                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                # JSON 파싱
                is_continuous, reasoning = self._parse_continuity_response(content)

                logger.info(f"주제 연속성: {is_continuous}, 이유: {reasoning[:100]}")
                return is_continuous, reasoning

        except Exception as e:
            logger.error(f"LLM 주제 연속성 판단 실패: {str(e)}")
            # 실패 시 보수적으로 False 반환
            return False, f"판단 실패: {str(e)}"

    def _parse_continuity_response(self, response_content: str) -> Tuple[bool, str]:
        """LLM 응답 파싱"""
        try:
            # JSON 블록 추출
            content = response_content.strip()

            if '```json' in content:
                start = content.find('```json') + 7
                end = content.find('```', start)
                content = content[start:end].strip()
            elif '```' in content:
                start = content.find('```') + 3
                end = content.find('```', start)
                content = content[start:end].strip()

            if not content.startswith('{'):
                start = content.find('{')
                end = content.rfind('}')
                if start != -1 and end != -1:
                    content = content[start:end + 1]

            data = json.loads(content)

            is_continuous = data.get('is_continuous', False)
            reasoning = data.get('reasoning', '')
            confidence = data.get('confidence', 0.5)

            # 3가지 체크 결과 확인 (추가 안전장치)
            continuity_check = data.get('continuity_check', False)
            exclusivity_check = data.get('exclusivity_check', False)
            action_match_check = data.get('action_match_check', False)

            # 3가지 중 하나라도 False면 연속성 없음
            if not (continuity_check and exclusivity_check and action_match_check):
                is_continuous = False
                logger.info(
                    f"체크 실패 - 연속성: {continuity_check}, "
                    f"대체불가: {exclusivity_check}, "
                    f"Action일치: {action_match_check}"
                )

            # confidence가 낮으면 False로 처리 (기존 로직 유지)
            if confidence < 0.7:  # 0.6 → 0.7로 상향 (더 엄격)
                is_continuous = False
                logger.info(f"신뢰도 부족: {confidence:.2f} < 0.7")

            return is_continuous, reasoning

        except Exception as e:
            logger.warning(f"응답 파싱 실패: {str(e)}, 원본: {response_content[:200]}")
            return False, response_content[:200]

    async def search_and_get_candidates(
        self,
        document_text: str,
        document_title: str = "",
        top_k_docs: int = 5,
        min_score: float = 0.5
    ) -> tuple[List[HistoricalDocument], List[EmployeeCandidate]]:
        """
        과거 문서 검색 및 후보자 추출 (원스톱)

        Returns:
            (과거 문서 목록, 후보자 목록)
        """
        # 1. 유사 과거 문서 검색
        historical_docs = await self.search_similar_historical_documents(
            document_text,
            document_title,
            top_k_docs
        )

        # 2. 과거 문서에서 후보자 추출
        candidates = await self.get_candidates_from_historical_docs(
            historical_docs,
            min_score
        )

        return historical_docs, candidates

    async def filter_by_current_department(
        self,
        past_reporters: List[str],
        target_dept: SelectedDepartment
    ) -> List[EmployeeCandidate]:
        """
        부서 일치 필터링: 과거 보고자 중 현재 타겟 부서에 있는 사람만 선택

        Logic:
        1. 과거 보고자 이름으로 현재 직원 정보 조회 (Qdrant employees 컬렉션)
        2. 현재 부서가 타겟 부서와 일치하는지 확인
        3. 일치하는 사람만 반환

        Args:
            past_reporters: 과거 보고자 이름 리스트
            target_dept: 타겟 부서 정보

        Returns:
            List[EmployeeCandidate]: 현재 타겟 부서에 있는 직원 목록
        """
        if not past_reporters or not target_dept:
            logger.warning("부서 필터링 불가: 과거 보고자 또는 타겟 부서 없음")
            return []

        survivors = []

        for reporter_name in past_reporters:
            try:
                # 현재 직원 정보 조회
                current_employees = await rag_service.search_similar_employees(
                    document_text=reporter_name,
                    top_k=5
                )

                # 이름이 정확히 일치하는 직원 찾기
                for emp in current_employees:
                    if emp.name == reporter_name:
                        # 부서 일치 확인
                        if self._match_department(emp, target_dept):
                            survivors.append(emp)
                            logger.info(
                                f"✅ 부서 일치: {emp.name} ({emp.dept1})"
                            )
                        else:
                            logger.info(
                                f"❌ 부서 불일치: {emp.name} "
                                f"(현재: {emp.dept1}, 타겟: {target_dept.dept1})"
                            )
                        break  # 동명이인 없다고 가정

            except Exception as e:
                logger.error(f"직원 조회 실패 ({reporter_name}): {str(e)}")

        logger.info(f"부서 필터링 결과: {len(survivors)}명 생존")
        return survivors

    def _match_department(
        self,
        employee: EmployeeCandidate,
        target_dept: SelectedDepartment
    ) -> bool:
        """
        직원의 현재 부서가 타겟 부서와 일치하는지 확인

        매칭 조건:
        - target_dept의 dept1/dept2/dept3이 ">" 구분자로 경로 형식인 경우 파싱
        - 타겟 부서가 직원의 dept1, dept2, dept3 중 하나라도 일치하면 매칭

        Args:
            employee: 직원 정보
            target_dept: 타겟 부서

        Returns:
            bool: 일치 여부
        """
        # target_dept가 경로 형식인지 확인 (예: "기획조정실 > 행정정보과 > 사이버보안팀")
        if target_dept.dept1 and " > " in target_dept.dept1:
            # 경로 파싱
            parts = [p.strip() for p in target_dept.dept1.split(" > ")]
            target_d1 = parts[0] if len(parts) > 0 else None
            target_d2 = parts[1] if len(parts) > 1 else None
            target_d3 = parts[2] if len(parts) > 2 else None
        else:
            # 일반 형식
            target_d1 = target_dept.dept1
            target_d2 = target_dept.dept2
            target_d3 = target_dept.dept3

        # 타겟 부서들을 리스트로 수집
        target_depts = []
        if target_d1:
            target_depts.append(target_d1)
        if target_d2:
            target_depts.append(target_d2)
        if target_d3:
            target_depts.append(target_d3)

        # 직원 부서들을 리스트로 수집
        emp_depts = []
        if employee.dept1:
            emp_depts.append(employee.dept1)
        if employee.dept2:
            emp_depts.append(employee.dept2)
        if employee.dept3:
            emp_depts.append(employee.dept3)

        # 타겟 부서 중 하나라도 직원 부서와 일치하면 True
        for target in target_depts:
            if target in emp_depts:
                return True

        return False

    def filter_by_working_level(
        self,
        candidates: List[EmployeeCandidate],
        threshold: int = 7
    ) -> List[EmployeeCandidate]:
        """
        직급 필터링: 실무자(Working Level)만 선택

        Logic:
        1. 직급 레벨 계산 (rank_mapper 사용)
        2. threshold 이상인 직급만 선택 (기본값 7 = 7급 이하)
        3. 실무자가 없으면 원본 반환 (팀장급만 있는 경우 대비)

        Args:
            candidates: 후보자 목록
            threshold: 실무자 기준 (기본값 7 = 7급 이하)

        Returns:
            List[EmployeeCandidate]: 실무자 목록
        """
        if not candidates:
            return []

        working_level = []

        for candidate in candidates:
            rank_level = rank_mapper.get_rank_level(candidate.rank)

            if rank_level >= threshold:
                working_level.append(candidate)
                logger.info(
                    f"✅ 실무자 선택: {candidate.name} "
                    f"({candidate.rank}, 레벨={rank_level})"
                )
            else:
                logger.info(
                    f"❌ 관리자 제외: {candidate.name} "
                    f"({candidate.rank}, 레벨={rank_level})"
                )

        # 실무자가 없으면 원본 반환 (안전장치)
        if not working_level:
            logger.warning(
                "실무자가 없어 전체 후보 반환 "
                f"(모두 {threshold}급 이상 관리자)"
            )
            return candidates

        logger.info(f"직급 필터링 결과: {len(working_level)}명 실무자 선택")
        return working_level


# 싱글톤 인스턴스
historical_search_service = HistoricalSearchService()
