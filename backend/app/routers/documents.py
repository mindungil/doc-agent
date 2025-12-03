import os
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List

# KST timezone (UTC+9)
KST = timezone(timedelta(hours=9))

def now_kst():
    """한국 시간(KST) 현재 시각 반환"""
    return datetime.now(KST)

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Query
from app.auth import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.database.db import get_db, DocumentModel, AsyncSessionLocal, engine

logger = logging.getLogger(__name__)
from app.models.schemas import (
    Document, DocumentDetail, AssignmentRecommendation,
    AssignmentRequest, StatsResponse, EmployeeCandidate
)
from app.services.document import extract_text_from_file, save_uploaded_file
from app.services.rag import RAGService
from app.services.llm import LLMService
from app.services.ocr import ocr_service
from app.services.text_correction import text_correction_service
from app.services.recipient_filter import recipient_filter_service
from app.services.department_filter import department_filter_service
from app.services.document_summarizer import document_summarizer_service
from app.services.historical_search import historical_search_service
from app.services.target_department import target_dept_service
from app.config import settings
from app.exceptions import (
    TextExtractionError, VectorSearchError, QdrantConnectionError,
    LLMServiceError, LLMAPIError, LLMResponseParseError
)

router = APIRouter(prefix="/api/documents", tags=["documents"])

rag_service = RAGService()
llm_service = LLMService()


async def has_recommendation_json_column(db: AsyncSession) -> bool:
    """recommendation_json 컬럼이 존재하는지 확인"""
    try:
        from sqlalchemy import text
        result = await db.execute(
            text("PRAGMA table_info(documents)")
        )
        columns = result.fetchall()
        column_names = [col[1] for col in columns]
        return 'recommendation_json' in column_names
    except Exception:
        return False


async def ensure_recommendation_json_column(db: AsyncSession):
    """recommendation_json 컬럼이 없으면 추가"""
    try:
        has_column = await has_recommendation_json_column(db)
        if not has_column:
            from sqlalchemy import text
            # SQLite는 ALTER TABLE ADD COLUMN을 지원하지만, 트랜잭션 내에서 실행해야 함
            await db.execute(
                text("ALTER TABLE documents ADD COLUMN recommendation_json TEXT")
            )
            await db.commit()
            print(f"[INFO] recommendation_json 컬럼이 추가되었습니다.")
    except Exception as e:
        # 컬럼이 이미 존재하거나 다른 오류 발생 시 무시
        print(f"[WARN] recommendation_json 컬럼 추가 실패: {str(e)}")
        try:
            await db.rollback()
        except:
            pass


async def process_document_async(document_id: int):
    """
    새로운 문서 처리 파이프라인:
    1. DeepSeek-OCR 파싱
    2. LLM OCR 보정
    3. 수신자 필터링 (조건부)
    4. 부서 필터링
    5. 문서 요약 + 최종 랭킹
    6. 자동 배정
    """
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        try:
            # 문서 조회
            result = await db.execute(
                select(DocumentModel).where(DocumentModel.id == document_id)
            )
            doc = result.scalar_one_or_none()

            if not doc:
                return

            file_path = os.path.join(settings.upload_dir, doc.filename)

            # ==================== Phase 1: OCR 파싱 ====================
            try:
                doc.status = "OCR 처리 중"
                await db.commit()

                ocr_result = await ocr_service.parse_document_with_ocr(
                    file_path, doc.filename
                )

                doc.ocr_raw_text = ocr_result.raw_text
                doc.ocr_confidence = ocr_result.confidence
                doc.ocr_processed_at = now_kst()
                await db.commit()

            except Exception as e:
                logger.warning(f"OCR 실패, 원본 파일 읽기 시도: {str(e)}")
                # OCR 실패 시 원본 파일을 직접 읽기 시도
                try:
                    if file_path.endswith('.txt'):
                        with open(file_path, 'r', encoding='utf-8') as f:
                            raw_text = f.read()
                    else:
                        # 기타 파일은 extract_text_from_file 사용
                        raw_text = await extract_text_from_file(file_path)

                    if raw_text and len(raw_text.strip()) > 0:
                        doc.ocr_raw_text = raw_text
                        doc.ocr_confidence = 0.0  # OCR 없이 읽었으므로 신뢰도 0
                        doc.ocr_processed_at = now_kst()
                        doc.status = "OCR 우회 (원본 읽기)"
                        await db.commit()
                        logger.info(f"원본 파일 읽기 성공: {len(raw_text)} 글자")
                    else:
                        doc.status = f"OCR 실패: {str(e)[:50]}"
                        await db.commit()
                        return
                except Exception as read_error:
                    logger.error(f"원본 파일 읽기 실패: {str(read_error)}")
                    doc.status = f"파일 읽기 실패: {str(read_error)[:50]}"
                    await db.commit()
                    return

            # ==================== Phase 2: LLM 텍스트 보정 ====================
            try:
                doc.status = "텍스트 보정 중"
                await db.commit()

                corrected = await text_correction_service.correct_ocr_text(
                    doc.ocr_raw_text,
                    doc.ocr_confidence
                )

                doc.corrected_text = corrected.corrected_text
                doc.content = corrected.corrected_text  # 기존 content 필드도 업데이트
                doc.correction_processed_at = now_kst()
                await db.commit()

            except Exception as e:
                # 보정 실패 시 OCR 원본 사용
                doc.corrected_text = doc.ocr_raw_text
                doc.content = doc.ocr_raw_text
                doc.correction_processed_at = now_kst()
                await db.commit()

            final_text = doc.corrected_text or doc.ocr_raw_text

            if not final_text or len(final_text.strip()) < 10:
                doc.status = "내용 없음"
                await db.commit()
                return

            # ==================== Phase 3: 수신자 필터링 ====================
            try:
                doc.status = "수신자 분석 중"
                await db.commit()

                recipient_info = await recipient_filter_service.extract_recipient_info(final_text)

                # 수신자 정보 저장
                doc.recipient_info = json.dumps({
                    "has_recipient": recipient_info.has_recipient,
                    "is_specific": recipient_info.is_specific,
                    "recipient_text": recipient_info.recipient_text
                }, ensure_ascii=False)

                # 특정 수신자인 경우 필터링
                recipient_candidates = []
                if recipient_info.has_recipient and recipient_info.is_specific:
                    recipient_candidates = await recipient_filter_service.filter_by_recipient(
                        recipient_info.recipient_text,
                        top_k=3
                    )

                await db.commit()

            except Exception as e:
                # 수신자 필터링 실패 시 계속 진행
                recipient_candidates = []

            # ==================== Phase 4: 부서 필터링 ====================
            try:
                doc.status = "부서 분석 중"
                await db.commit()

                dept_filter_result = await department_filter_service.filter_by_department(
                    final_text,
                    doc.title
                )

                # 부서 정보 저장
                doc.filtered_departments = json.dumps({
                    "selected_departments": [
                        {
                            "dept1": d.dept1,
                            "dept2": d.dept2,
                            "dept3": d.dept3,
                            "relevance_score": d.relevance_score
                        }
                        for d in dept_filter_result.selected_departments
                    ],
                    "reasoning": dept_filter_result.reasoning
                }, ensure_ascii=False)
                doc.filtering_processed_at = now_kst()

                await db.commit()

            except Exception as e:
                dept_filter_result = None

            # ==================== Phase 5: 3단계 우선순위 파이프라인 ====================
            try:
                doc.status = "제목 유사도 분석 중"
                await db.commit()

                # 3단계 우선순위 파이프라인 실행
                # Stage 1: Skeleton Matching (Fast-Track)
                # Stage 2: Action-based Hybrid Search (Deep-Check)
                # Stage 3: LLM Final Verification (Safety Net)
                quick_summary = final_text[:500] if len(final_text) > 500 else final_text

                logger.info(f"[PIPELINE_START] 3단계 파이프라인 호출 시작 - 제목: {doc.title}")
                try:
                    title_similar_docs, pipeline_stage = await historical_search_service.search_with_three_stage_pipeline(
                        doc.title,
                        document_summary=quick_summary,
                        top_k=3
                    )
                    logger.info(f"[PIPELINE_SUCCESS] 3단계 파이프라인 완료 - 단계: {pipeline_stage}")
                except Exception as pipeline_error:
                    logger.error(f"[PIPELINE_ERROR] 3단계 파이프라인 오류: {str(pipeline_error)}", exc_info=True)
                    # 예외 발생 시 빈 결과와 오류 메시지 반환
                    title_similar_docs = []
                    pipeline_stage = f"오류: {str(pipeline_error)}"

                # 최고 유사도 확인
                max_title_score = title_similar_docs[0].score if title_similar_docs else 0.0
                logger.info(f"파이프라인 단계: {pipeline_stage}, 제목 최고 유사도: {max_title_score:.3f}")

                # ===== 파이프라인 결과 기반 분기 처리 =====
                skip_pipeline = False
                auto_assign_reason = ""
                historical_candidates = []

                # Stage 1 (Skeleton Match) 또는 고유사도(>= 0.95)인 경우 즉시 배부
                if "Stage 1" in pipeline_stage or max_title_score >= 0.95:
                    logger.info(f"🎯 Fast-Track: {pipeline_stage} (유사도: {max_title_score:.3f})")

                    # 모든 보고자 추출
                    reporters = []
                    for doc_item in title_similar_docs:
                        if doc_item.reporter:
                            reporters.append(doc_item.reporter)

                    logger.info(f"추출된 보고자: {reporters}")

                    # 부서 필터링 없이 과거 담당자 바로 사용
                    historical_candidates = await historical_search_service.get_candidates_from_historical_docs(
                        title_similar_docs,
                        min_score=max_title_score
                    )

                    # 직급 필터링 (실무자만)
                    if historical_candidates:
                        historical_candidates = historical_search_service.filter_by_working_level(
                            historical_candidates,
                            threshold=7
                        )

                    logger.info(f"과거 담당자 직급 필터링 후: {len(historical_candidates)}명")

                    if historical_candidates:
                        skip_pipeline = True
                        auto_assign_reason = f"{pipeline_stage} (유사도: {max_title_score:.3f})"

                        doc.filtered_departments = json.dumps({
                            "auto_assign_type": "fast_track",
                            "pipeline_stage": pipeline_stage,
                            "title_score": max_title_score,
                            "candidate_count": len(historical_candidates)
                        }, ensure_ascii=False)

                        logger.info(f"Fast-Track 배부: {[c.name for c in historical_candidates]}")

                # Stage 2/3 (LLM 연속성 확인) 또는 중간 유사도인 경우
                elif "Stage 3" in pipeline_stage or 0.75 <= max_title_score < 0.95:
                    logger.info(f"✅ {pipeline_stage} (유사도: {max_title_score:.3f})")

                    # 부서 필터링 없이 과거 담당자 바로 사용
                    historical_candidates = await historical_search_service.get_candidates_from_historical_docs(
                        title_similar_docs,
                        min_score=0.75
                    )

                    # 직급 필터링 (실무자만)
                    if historical_candidates:
                        historical_candidates = historical_search_service.filter_by_working_level(
                            historical_candidates,
                            threshold=7
                        )

                    if historical_candidates:
                        skip_pipeline = True
                        auto_assign_reason = f"{pipeline_stage} (유사도: {max_title_score:.3f})"

                        doc.filtered_departments = json.dumps({
                            "auto_assign_type": "verified",
                            "pipeline_stage": pipeline_stage,
                            "title_score": max_title_score,
                            "candidate_count": len(historical_candidates)
                        }, ensure_ascii=False)

                        logger.info(f"검증 완료 배부: {[c.name for c in historical_candidates]}")
                    else:
                        logger.info(f"❌ 후보자 없음 - 전체 파이프라인 진행")

                # 저유사도 또는 연속성 부정 → 전체 파이프라인 진행
                else:
                    logger.info(f"📊 {pipeline_stage} (유사도: {max_title_score:.3f}) - 전체 파이프라인 진행")
                    historical_candidates = []

                doc.status = "최종 분석 중"
                await db.commit()

                # ===== skip_pipeline에 따른 분기 처리 =====
                if skip_pipeline and historical_candidates:
                    # 🚀 고속 경로: 즉시 배부 (RAG, 부서 필터링, LLM 랭킹 생략)
                    logger.info("⚡ 고속 경로: 하위 파이프라인 생략하고 즉시 배부")

                    # 간단한 랭킹 (과거 유사도 기반)
                    from app.models.ocr_schemas import RankedCandidate
                    ranked_candidates = []

                    for idx, candidate in enumerate(historical_candidates[:5]):
                        ranked_candidates.append(RankedCandidate(
                            name=candidate.name,
                            rank=candidate.rank,
                            dept1=candidate.dept1,
                            dept2=candidate.dept2,
                            dept3=candidate.dept3,
                            tasks=candidate.tasks,
                            phone=candidate.phone,
                            rag_score=candidate.score,
                            llm_score=None,
                            final_score=(candidate.score or 0.9) * 100,
                            reasoning=auto_assign_reason
                        ))

                    # 간단한 요약만 저장
                    doc.document_keywords = json.dumps({
                        "keywords": [doc.title],
                        "summary": auto_assign_reason,
                        "required_expertise": [],
                        "fast_track": True
                    }, ensure_ascii=False)

                    logger.info(f"고속 배부 완료: {ranked_candidates[0].name}")

                else:
                    # 📊 일반 경로: 전체 파이프라인 진행
                    logger.info("📊 일반 경로: 전체 파이프라인 진행")

                    # 문서 요약
                    doc_summary = await document_summarizer_service.summarize_document_keywords(
                        final_text,
                        doc.title
                    )

                    # 키워드 저장
                    doc.document_keywords = json.dumps({
                        "keywords": doc_summary.keywords,
                        "summary": doc_summary.summary,
                        "required_expertise": doc_summary.required_expertise,
                        "fast_track": False
                    }, ensure_ascii=False)

                    # 후보자 결정 우선순위:
                    # 1순위: 과거 문서 기반 후보
                    # 2순위: 수신자 필터링 결과
                    # 3순위: RAG 전체 검색
                    base_candidates = []

                    if historical_candidates:
                        logger.info(f"1순위: 과거 문서 기반 후보 {len(historical_candidates)}명 사용")
                        base_candidates = historical_candidates
                    elif recipient_candidates:
                        logger.info(f"2순위: 수신자 필터링 후보 {len(recipient_candidates)}명 사용")
                        base_candidates = recipient_candidates
                    else:
                        logger.info("3순위: RAG 전체 검색 사용")
                        base_candidates = await rag_service.search_similar_employees(
                            f"{doc.title}\n{final_text}",
                            top_k=20
                        )

                    # 부서 필터링 적용 (선택적)
                    if dept_filter_result and dept_filter_result.selected_departments:
                        filtered_candidates = department_filter_service.filter_candidates_by_departments(
                            base_candidates,
                            dept_filter_result.selected_departments
                        )
                        # 필터링 후 후보가 너무 적으면 원본 유지
                        if len(filtered_candidates) < 3 and len(base_candidates) >= 3:
                            logger.warning("부서 필터링 후 후보가 부족하여 원본 사용")
                            filtered_candidates = base_candidates
                    else:
                        filtered_candidates = base_candidates

                    if not filtered_candidates:
                        # 필터링 후 후보가 없으면 원본 사용
                        filtered_candidates = base_candidates[:10]

                    # 최종 랭킹
                    ranked_candidates = await document_summarizer_service.rank_candidates(
                        doc_summary,
                        filtered_candidates,
                        final_text,
                        use_hybrid=True
                    )

                await db.commit()

            except Exception as e:
                doc.status = f"분석 실패: {str(e)[:50]}"
                await db.commit()
                return

            # ==================== Phase 6: 자동 배정 ====================
            if ranked_candidates:
                try:
                    top_candidate = ranked_candidates[0]

                    # EmployeeCandidate 형식으로 변환
                    employee_candidates = []
                    for rc in ranked_candidates:
                        employee_candidates.append(EmployeeCandidate(
                            name=rc.name,
                            rank=rc.rank,
                            dept1=rc.dept1,
                            dept2=rc.dept2,
                            dept3=rc.dept3,
                            tasks=rc.tasks,
                            phone=rc.phone,
                            score=rc.final_score / 100.0  # 0-1 범위로 변환
                        ))

                    # 추천 결과 저장
                    recommendation_dict = {
                        "primary": {
                            "name": top_candidate.name,
                            "rank": top_candidate.rank,
                            "dept1": top_candidate.dept1,
                            "dept2": top_candidate.dept2,
                            "dept3": top_candidate.dept3,
                            "tasks": top_candidate.tasks,
                            "phone": top_candidate.phone,
                            "score": top_candidate.final_score,
                        },
                        "candidates": [
                            {
                                "name": c.name,
                                "rank": c.rank,
                                "dept1": c.dept1,
                                "dept2": c.dept2,
                                "dept3": c.dept3,
                                "tasks": c.tasks,
                                "phone": c.phone,
                                "score": c.final_score,
                            }
                            for c in ranked_candidates[:5]
                        ],
                        "reasoning": top_candidate.reasoning,
                    }

                    doc.recommendation_json = json.dumps(recommendation_dict, ensure_ascii=False)

                    # 복수 배부 대상 저장 (신규)
                    assigned_candidates_list = []
                    for rc in ranked_candidates[:5]:  # 상위 5명까지
                        assigned_candidates_list.append({
                            "name": rc.name,
                            "rank": rc.rank,
                            "dept1": rc.dept1,
                            "dept2": rc.dept2,
                            "dept3": rc.dept3,
                            "tasks": rc.tasks[:100],  # 간략히
                            "phone": rc.phone,
                            "final_score": rc.final_score,
                            "rag_score": rc.rag_score,
                            "llm_score": rc.llm_score
                        })
                    doc.assigned_candidates = json.dumps(assigned_candidates_list, ensure_ascii=False)

                    # 대표 담당자는 1순위 (하위 호환)
                    doc.assigned_to = top_candidate.name
                    doc.assigned_at = now_kst()
                    doc.is_auto_assigned = True
                    doc.status = "배부 완료"

                    logger.info(f"✅ 자동 배정 완료: {len(assigned_candidates_list)}명에게 배부")

                    await db.commit()

                except Exception as e:
                    doc.status = f"배정 실패: {str(e)[:50]}"
                    await db.commit()
            else:
                doc.status = "담당자 없음"
                await db.commit()

        except Exception as e:
            # 전체 오류 처리
            try:
                async with AsyncSessionLocal() as error_db:
                    await error_db.execute(
                        text("UPDATE documents SET status = :status WHERE id = :id"),
                        {"status": f"처리 오류: {str(e)[:50]}", "id": document_id}
                    )
                    await error_db.commit()
            except Exception:
                pass


@router.post("/upload", response_model=Document)
async def upload_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """문서 업로드 (즉시 완료, 파싱/선별은 백그라운드 처리)"""
    file_content = await file.read()
    if len(file_content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="파일 크기는 10MB를 초과할 수 없습니다.")
    
    # 파일 저장
    file_path = await save_uploaded_file(file_content, file.filename)
    
    # 문서 레코드 생성 (즉시 완료)
    # recommendation_json 컬럼이 없을 수 있으므로 raw SQL 사용
    title = os.path.splitext(file.filename)[0]
    from sqlalchemy import text
    
    result = await db.execute(
        text("""
            INSERT INTO documents (title, filename, status, content, uploaded_at, assigned_to, assigned_at, is_auto_assigned)
            VALUES (:title, :filename, :status, :content, :uploaded_at, :assigned_to, :assigned_at, :is_auto_assigned)
        """),
        {
            "title": title,
            "filename": file.filename,
            "status": "업로드 완료",
            "content": "",
            "uploaded_at": now_kst(),
            "assigned_to": None,
            "assigned_at": None,
            "is_auto_assigned": False
        }
    )
    await db.commit()
    
    # 생성된 ID 가져오기
    doc_id_result = await db.execute(
        text("SELECT id FROM documents WHERE filename = :filename ORDER BY uploaded_at DESC LIMIT 1"),
        {"filename": file.filename}
    )
    doc_id = doc_id_result.scalar_one()
    
    # 생성된 문서 정보 조회
    result = await db.execute(
        select(
            DocumentModel.id,
            DocumentModel.title,
            DocumentModel.filename,
            DocumentModel.status,
            DocumentModel.uploaded_at,
            DocumentModel.assigned_to,
            DocumentModel.assigned_at,
            DocumentModel.is_auto_assigned
        ).where(DocumentModel.id == doc_id)
    )
    doc_row = result.first()
    
    db_document_id = doc_id
    
    # 백그라운드에서 파싱 및 담당자 선별 처리
    asyncio.create_task(process_document_async(db_document_id))
    
    return Document(
        id=doc_row.id,
        title=doc_row.title,
        filename=doc_row.filename,
        status=doc_row.status,
        uploaded_at=doc_row.uploaded_at,
        assigned_to=doc_row.assigned_to,
        assigned_at=doc_row.assigned_at,
        is_auto_assigned=doc_row.is_auto_assigned
    )


@router.get("/", response_model=List[Document])
async def list_documents(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """문서 목록 조회"""
    # recommendation_json 컬럼이 없을 수 있으므로 명시적으로 필요한 컬럼만 선택
    result = await db.execute(
        select(
            DocumentModel.id,
            DocumentModel.title,
            DocumentModel.filename,
            DocumentModel.status,
            DocumentModel.uploaded_at,
            DocumentModel.assigned_to,
            DocumentModel.assigned_at,
            DocumentModel.is_auto_assigned
        )
        .order_by(DocumentModel.uploaded_at.desc())
        .offset(skip)
        .limit(limit)
    )
    documents = result.all()
    
    # recommendation_json에서 부서 정보 추출 (있는 경우만)
    documents_with_dept = []
    has_recommendation_column = await has_recommendation_json_column(db)
    
    for doc in documents:
        assigned_dept = None
        if has_recommendation_column and doc.assigned_to:
            try:
                from sqlalchemy import text
                rec_result = await db.execute(
                    text("SELECT recommendation_json FROM documents WHERE id = :id"),
                    {"id": doc.id}
                )
                rec_data = rec_result.scalar_one_or_none()
                if rec_data:
                    recommendation_data = json.loads(rec_data)
                    primary = recommendation_data.get("primary", {})
                    dept_parts = [primary.get("dept1", ""), primary.get("dept2", ""), primary.get("dept3", "")]
                    assigned_dept = " ".join([d for d in dept_parts if d])
            except Exception:
                pass
        
        doc_dict = {
            "id": doc.id,
            "title": doc.title,
            "filename": doc.filename,
            "status": doc.status,
            "uploaded_at": doc.uploaded_at,
            "assigned_to": doc.assigned_to,
            "assigned_at": doc.assigned_at,
            "is_auto_assigned": doc.is_auto_assigned,
        }
        if assigned_dept:
            doc_dict["assigned_dept"] = assigned_dept
        
        documents_with_dept.append(doc_dict)
    
    return documents_with_dept


@router.get("/employees/search", response_model=List[EmployeeCandidate])
async def search_employees(
    query: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """직원 검색 (Qdrant 벡터 검색)"""
    if not query or len(query.strip()) == 0:
        raise HTTPException(status_code=400, detail="검색어를 입력해주세요.")
    
    try:
        candidates = await rag_service.search_similar_employees(query, top_k=limit)
        return candidates
    except (QdrantConnectionError, VectorSearchError) as e:
        raise HTTPException(status_code=503, detail=f"직원 검색 실패: {str(e)}")


@router.get("/history")
async def get_assignment_history(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """배부 완료된 문서 이력 조회"""
    # recommendation_json 컬럼이 없을 수 있으므로 명시적으로 필요한 컬럼만 선택
    # assigned_to가 설정되어 있거나 상태가 "배부 완료"인 문서 조회
    result = await db.execute(
        select(
            DocumentModel.id,
            DocumentModel.title,
            DocumentModel.filename,
            DocumentModel.status,
            DocumentModel.uploaded_at,
            DocumentModel.assigned_to,
            DocumentModel.assigned_at,
            DocumentModel.is_auto_assigned
        )
        .where(
            or_(
                and_(
                    DocumentModel.assigned_to.isnot(None),
                    DocumentModel.assigned_to != "",
                    DocumentModel.assigned_at.isnot(None)
                ),
                DocumentModel.status == "배부 완료"
            )
        )
        .order_by(
            func.coalesce(DocumentModel.assigned_at, DocumentModel.uploaded_at).desc(),
            DocumentModel.uploaded_at.desc()
        )
        .offset(skip)
        .limit(limit)
    )
    documents = result.all()
    
    # list_documents와 동일한 방식으로 dict 반환 (datetime은 그대로 유지)
    return [
        {
            "id": doc.id,
            "title": doc.title,
            "filename": doc.filename,
            "status": doc.status,
            "uploaded_at": doc.uploaded_at,
            "assigned_to": doc.assigned_to,
            "assigned_at": doc.assigned_at,
            "is_auto_assigned": doc.is_auto_assigned
        }
        for doc in documents
    ]


@router.get("/stats/today", response_model=StatsResponse)
async def get_today_stats(
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """오늘 처리한 문서 통계 조회"""
    today = now_kst().date()
    total_result = await db.execute(
        select(func.count(DocumentModel.id))
        .where(func.date(DocumentModel.uploaded_at) == today)
    )
    total_documents_today = total_result.scalar() or 0
    
    assigned_result = await db.execute(
        select(func.count(DocumentModel.id))
        .where(
            func.date(DocumentModel.uploaded_at) == today,
            DocumentModel.assigned_to.isnot(None)
        )
    )
    assigned_count = assigned_result.scalar() or 0
    
    auto_result = await db.execute(
        select(func.count(DocumentModel.id))
        .where(
            func.date(DocumentModel.uploaded_at) == today,
            DocumentModel.is_auto_assigned == True
        )
    )
    auto_assigned_count = auto_result.scalar() or 0
    manual_assigned_count = assigned_count - auto_assigned_count
    
    return StatsResponse(
        total_documents_today=total_documents_today,
        assigned_count=assigned_count,
        auto_assigned_count=auto_assigned_count,
        manual_assigned_count=manual_assigned_count
    )


@router.get("/health/qdrant")
async def check_qdrant_health():
    """Qdrant 연결 상태 확인"""
    health_status = rag_service.check_health()
    if health_status["status"] == "error":
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=health_status.get("error", "Qdrant 연결 실패"))
    return health_status


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """문서 상세 정보 조회"""
    # recommendation_json 컬럼이 없을 수 있으므로 필요한 컬럼만 선택
    result = await db.execute(
        select(
            DocumentModel.id,
            DocumentModel.title,
            DocumentModel.filename,
            DocumentModel.status,
            DocumentModel.content,
            DocumentModel.uploaded_at,
            DocumentModel.assigned_to,
            DocumentModel.assigned_at,
            DocumentModel.is_auto_assigned
        ).where(DocumentModel.id == document_id)
    )
    doc = result.first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    
    content_preview = doc.content[:500] if doc.content else None
    
    # recommendation_json은 별도로 조회 (컬럼이 있을 때만)
    recommendation = None
    has_recommendation_column = await has_recommendation_json_column(db)
    
    if has_recommendation_column:
        try:
            # recommendation_json 컬럼이 있는지 확인하기 위해 별도 쿼리
            # SQLAlchemy의 text를 사용하여 안전하게 조회
            from sqlalchemy import text
            rec_result = await db.execute(
                text("SELECT recommendation_json FROM documents WHERE id = :id"),
                {"id": document_id}
            )
            rec_data = rec_result.scalar_one_or_none()
            if rec_data and rec_data.strip():
                try:
                    recommendation_data = json.loads(rec_data)
                    if recommendation_data and "primary" in recommendation_data:
                        recommendation = AssignmentRecommendation(
                            primary=EmployeeCandidate(**recommendation_data["primary"]),
                            candidates=[EmployeeCandidate(**c) for c in recommendation_data.get("candidates", [])],
                            reasoning=recommendation_data.get("reasoning", ""),
                        )
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    # JSON 파싱 실패 시 무시
                    pass
        except Exception as e:
            # recommendation_json 컬럼이 없거나 파싱 실패 시 무시
            pass
    
    return DocumentDetail(
        id=doc.id,
        title=doc.title,
        filename=doc.filename,
        status=doc.status,
        uploaded_at=doc.uploaded_at,
        assigned_to=doc.assigned_to,
        assigned_at=doc.assigned_at,
        is_auto_assigned=doc.is_auto_assigned,
        content_preview=content_preview,
        recommendation=recommendation
    )


@router.post("/{document_id}/recommend", response_model=AssignmentRecommendation)
async def recommend_assignee(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """RAG + LLM을 통한 담당자 자동 추천"""
    # 필요한 컬럼만 선택
    result = await db.execute(
        select(
            DocumentModel.id,
            DocumentModel.title,
            DocumentModel.content,
            DocumentModel.status
        ).where(DocumentModel.id == document_id)
    )
    doc = result.first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    
    if not doc.content:
        raise HTTPException(status_code=400, detail="문서 내용이 없습니다.")
    
    # 상태 업데이트 (raw SQL 사용)
    from sqlalchemy import text
    await db.execute(
        text("UPDATE documents SET status = :status WHERE id = :id"),
        {"status": "RAG 분석 중", "id": document_id}
    )
    await db.commit()
    
    try:
        document_text = f"{doc.title}\n\n{doc.content}"
        candidates = await rag_service.search_similar_employees(document_text, top_k=10)
        
        if not candidates:
            await db.execute(
                text("UPDATE documents SET status = :status WHERE id = :id"),
                {"status": "오류", "id": document_id}
            )
            await db.commit()
            raise HTTPException(status_code=404, detail="유사한 직원을 찾을 수 없습니다.")
        
        await db.execute(
            text("UPDATE documents SET status = :status WHERE id = :id"),
            {"status": "LLM 분석 중", "id": document_id}
        )
        await db.commit()
        
        recommendation = await llm_service.recommend_assignee(
            document_title=doc.title,
            document_content=doc.content,
            candidates=candidates
        )
        
        # 추천 결과를 JSON으로 저장 (컬럼이 없으면 추가)
        await ensure_recommendation_json_column(db)
        recommendation_json_str = None
        has_recommendation_column = await has_recommendation_json_column(db)
        
        if has_recommendation_column:
            try:
                recommendation_dict = {
                    "primary": {
                        "name": recommendation.primary.name,
                        "rank": recommendation.primary.rank,
                        "dept1": recommendation.primary.dept1,
                        "dept2": recommendation.primary.dept2,
                        "dept3": recommendation.primary.dept3,
                        "tasks": recommendation.primary.tasks,
                        "phone": recommendation.primary.phone,
                        "score": recommendation.primary.score,
                    },
                    "candidates": [
                        {
                            "name": c.name,
                            "rank": c.rank,
                            "dept1": c.dept1,
                            "dept2": c.dept2,
                            "dept3": c.dept3,
                            "tasks": c.tasks,
                            "phone": c.phone,
                            "score": c.score,
                        }
                        for c in recommendation.candidates
                    ],
                    "reasoning": recommendation.reasoning,
                }
                recommendation_json_str = json.dumps(recommendation_dict, ensure_ascii=False)
            except Exception:
                pass
        
        # 상태 및 recommendation_json 업데이트
        if has_recommendation_column and recommendation_json_str:
            await db.execute(
                text("""
                    UPDATE documents 
                    SET status = :status, 
                        recommendation_json = :recommendation_json
                    WHERE id = :id
                """),
                {
                    "status": "담당자 추천 완료",
                    "recommendation_json": recommendation_json_str,
                    "id": document_id
                }
            )
        else:
            await db.execute(
                text("UPDATE documents SET status = :status WHERE id = :id"),
                {"status": "담당자 추천 완료", "id": document_id}
            )
        await db.commit()
        return recommendation
    
    except (QdrantConnectionError, VectorSearchError) as e:
        doc.status = "오류"
        await db.commit()
        raise HTTPException(status_code=503, detail=f"벡터 검색 실패: {str(e)}")
    except (LLMAPIError, LLMResponseParseError) as e:
        doc.status = "오류"
        await db.commit()
        raise HTTPException(status_code=503, detail=f"LLM 서비스 오류: {str(e)}")
    except LLMServiceError as e:
        doc.status = "오류"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"LLM 처리 실패: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        doc.status = "오류"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"추천 처리 중 오류 발생: {str(e)}")


@router.post("/{document_id}/assign", response_model=Document)
async def assign_document(
    document_id: int,
    assignment: AssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """문서를 특정 담당자에게 배부 확정"""
    result = await db.execute(
        select(DocumentModel).where(DocumentModel.id == document_id)
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")

    doc.assigned_to = assignment.employee_name
    doc.assigned_at = now_kst()
    doc.status = "배부 완료"
    doc.is_auto_assigned = assignment.is_auto
    
    await db.commit()
    await db.refresh(doc)
    
    return Document(
        id=doc.id,
        title=doc.title,
        filename=doc.filename,
        status=doc.status,
        uploaded_at=doc.uploaded_at,
        assigned_to=doc.assigned_to,
        assigned_at=doc.assigned_at,
        is_auto_assigned=doc.is_auto_assigned
    )

