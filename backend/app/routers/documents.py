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
    Pipeline V2 문서 처리:
    1. OCR 파싱
    2. 텍스트 보정
    3. Pipeline V2 처리 (BM25 + 유사도 검색 + 증거 수집 + LLM 추론)
    4. 부서 내 담당자 찾기 (RAG 검색)
    5. 자동 배정
    """
    from sqlalchemy import text
    from app.services.pipeline_v2 import get_pipeline_v2

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

            # ==================== Phase 3: Pipeline V2 처리 ====================
            try:
                doc.status = "Pipeline V2 분석 중"
                await db.commit()

                logger.info(f"[PIPELINE_V2] Pipeline V2 호출 시작 - 제목: {doc.title}")

                # Pipeline V2 호출
                pipeline_v2 = get_pipeline_v2()
                pipeline_result = await pipeline_v2.process_document(
                    db=db,
                    document=doc,
                    ocr_text=doc.ocr_raw_text
                )

                logger.info(f"[PIPELINE_V2] Pipeline V2 완료: {pipeline_result}")

                recommendation = pipeline_result['recommendation']
                recommended_dept = recommendation['recommended_dept']
                auto_assigned = recommendation['auto_assigned']
                confidence = recommendation['confidence']
                reasoning = recommendation['reasoning']
                evidence = recommendation.get('evidence', {})

                # LLM 추론 결과에서 추천 담당자 추출
                llm_output = recommendation.get('llm_output', {})
                llm_recommended_employee = llm_output.get('recommended_employee') if llm_output else None

                # ==================== Phase 4: 부서 내 담당자 찾기 ====================
                doc.status = "담당자 검색 중"
                await db.commit()

                assigned_employee = None
                employee_dept = None

                # 1순위: LLM이 추천한 담당자 사용
                if llm_recommended_employee:
                    logger.info(f"[PIPELINE_V2] LLM 추천 담당자: {llm_recommended_employee}")

                    # RAG에서 해당 담당자 정보 조회 (검증 및 부서 정보 획득)
                    llm_employee_candidates = await rag_service.search_similar_employees(
                        llm_recommended_employee,
                        top_k=5
                    )

                    # 이름이 정확히 일치하는 직원 찾기
                    for candidate in llm_employee_candidates:
                        if candidate.name == llm_recommended_employee:
                            assigned_employee = candidate.name
                            employee_dept = f"{candidate.dept1} {candidate.dept2} {candidate.dept3}".strip()
                            logger.info(f"[PIPELINE_V2] LLM 추천 담당자 확인: {assigned_employee} ({employee_dept})")
                            break

                    if not assigned_employee:
                        logger.warning(f"[PIPELINE_V2] LLM 추천 담당자 '{llm_recommended_employee}'를 RAG에서 찾을 수 없음")

                # 2순위: 자동 배정인 경우 과거 보고자 사용
                if not assigned_employee and auto_assigned:
                    logger.info(f"[PIPELINE_V2] 자동 배정 모드 - 과거 보고자 검색 (부서: {recommended_dept})")

                    # 증거에서 과거 보고자 추출
                    history_evidence = evidence.get('history_evidence', [])

                    if history_evidence:
                        # 상위 유사 문서의 보고자 추출
                        best_match = history_evidence[0]
                        reporter = best_match.get('reporter')

                        if reporter:
                            logger.info(f"[PIPELINE_V2] 과거 보고자 발견: {reporter}")

                            # RAG에서 이름으로 직접 검색 (메타데이터 검색)
                            reporter_candidate = await rag_service.search_employee_by_name(reporter)

                            if reporter_candidate:
                                assigned_employee = reporter_candidate.name
                                employee_dept = f"{reporter_candidate.dept1} {reporter_candidate.dept2} {reporter_candidate.dept3}".strip()
                                logger.info(f"✅ [PIPELINE_V2] 과거 보고자 메타데이터 검색 성공: {assigned_employee} ({employee_dept})")
                            else:
                                logger.warning(f"❌ [PIPELINE_V2] 과거 보고자 '{reporter}'를 Qdrant에서 찾을 수 없음")

                # 3순위: 벡터 검색으로 부서 내 담당자 찾기
                if not assigned_employee:
                    logger.info(f"[PIPELINE_V2] 부서 '{recommended_dept}' 내 담당자 검색")

                    # 추천된 부서 + 문서 제목/내용으로 RAG 검색
                    search_query = f"{recommended_dept} {doc.title}"
                    if final_text:
                        search_query += f"\n{final_text[:300]}"

                    dept_candidates = await rag_service.search_similar_employees(
                        search_query,
                        top_k=20
                    )

                    # 추천된 부서로 필터링
                    dept_filtered = [
                        c for c in dept_candidates
                        if recommended_dept in f"{c.dept1} {c.dept2} {c.dept3}"
                    ]

                    if dept_filtered:
                        assigned_employee = dept_filtered[0].name
                        employee_dept = f"{dept_filtered[0].dept1} {dept_filtered[0].dept2} {dept_filtered[0].dept3}".strip()
                        logger.info(f"[PIPELINE_V2] 부서 필터링 후 담당자: {assigned_employee} ({employee_dept})")
                    elif dept_candidates:
                        # 부서 매칭 실패 시 상위 후보 사용
                        assigned_employee = dept_candidates[0].name
                        employee_dept = f"{dept_candidates[0].dept1} {dept_candidates[0].dept2} {dept_candidates[0].dept3}".strip()
                        logger.warning(f"[PIPELINE_V2] 부서 매칭 실패, 상위 후보 사용: {assigned_employee} ({employee_dept})")
                    else:
                        logger.warning(f"[PIPELINE_V2] 담당자를 찾을 수 없음")

                # ==================== Phase 5: 결과 저장 ====================
                if assigned_employee:
                    doc.assigned_to = assigned_employee
                    doc.assigned_at = now_kst()
                    doc.is_auto_assigned = auto_assigned
                    doc.status = "배부 완료"

                    # 담당자 매칭 방식 기록
                    assignment_method = "unknown"
                    if llm_recommended_employee and assigned_employee == llm_recommended_employee:
                        assignment_method = "llm_recommendation"
                    elif auto_assigned:
                        assignment_method = "auto_assigned_history"
                    else:
                        assignment_method = "vector_search"

                    # 부서 정보 저장
                    doc.filtered_departments = json.dumps({
                        "pipeline_version": "v2",
                        "recommended_dept": recommended_dept,
                        "assigned_employee": assigned_employee,
                        "employee_dept": employee_dept,
                        "assignment_method": assignment_method,  # 추가
                        "llm_recommended_employee": llm_recommended_employee,  # 추가
                        "confidence": confidence,
                        "auto_assigned": auto_assigned,
                        "reasoning": reasoning,
                        "evidence_counts": {
                            "history": len(evidence.get('history_evidence', [])),
                            "job": len(evidence.get('job_evidence', []))
                        }
                    }, ensure_ascii=False)

                    logger.info(f"✅ [PIPELINE_V2] 문서 처리 완료: {doc.id} -> {assigned_employee} ({recommended_dept})")
                else:
                    doc.status = "담당자 없음"
                    doc.filtered_departments = json.dumps({
                        "pipeline_version": "v2",
                        "recommended_dept": recommended_dept,
                        "confidence": confidence,
                        "reasoning": reasoning,
                        "error": "담당자를 찾을 수 없음"
                    }, ensure_ascii=False)
                    logger.warning(f"❌ [PIPELINE_V2] 담당자를 찾을 수 없음: {doc.id}")

                await db.commit()

            except Exception as e:
                logger.error(f"[PIPELINE_V2] 처리 실패: {e}", exc_info=True)
                doc.status = f"Pipeline V2 실패: {str(e)[:50]}"
                await db.commit()
                return

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
            # recommendation_json과 filtered_departments 컬럼 조회
            from sqlalchemy import text
            rec_result = await db.execute(
                text("SELECT recommendation_json, filtered_departments FROM documents WHERE id = :id"),
                {"id": document_id}
            )
            row = rec_result.first()
            rec_data = row[0] if row else None
            filtered_dept_data = row[1] if row and len(row) > 1 else None

            # Pipeline V2로 처리된 문서인지 확인 (filtered_departments 확인)
            if filtered_dept_data and filtered_dept_data.strip():
                try:
                    filtered_dept = json.loads(filtered_dept_data)
                    if filtered_dept.get("pipeline_version") == "v2" and filtered_dept.get("assigned_employee"):
                        # Pipeline V2 문서: filtered_departments에서 담당자 정보 추출
                        employee_name = filtered_dept["assigned_employee"]
                        employee_dept = filtered_dept.get("employee_dept", "")
                        reasoning = filtered_dept.get("reasoning", "")

                        # 부서 정보 파싱 (예: "기획조정실 행정정보과 스마트행정팀")
                        dept_parts = employee_dept.split() if employee_dept else []
                        dept1 = dept_parts[0] if len(dept_parts) > 0 else ""
                        dept2 = dept_parts[1] if len(dept_parts) > 1 else ""
                        dept3 = dept_parts[2] if len(dept_parts) > 2 else ""

                        # RAG에서 담당자 상세 정보 조회 시도
                        try:
                            employee_candidates = await rag_service.search_similar_employees(employee_name, top_k=1)
                            if employee_candidates and employee_candidates[0].name == employee_name:
                                primary_candidate = employee_candidates[0]
                            else:
                                # RAG 조회 실패 시 기본 정보로 생성
                                primary_candidate = EmployeeCandidate(
                                    name=employee_name,
                                    rank="",
                                    dept1=dept1,
                                    dept2=dept2,
                                    dept3=dept3,
                                    tasks="",
                                    phone="",
                                    score=1.0
                                )
                        except Exception:
                            # RAG 조회 실패 시 기본 정보로 생성
                            primary_candidate = EmployeeCandidate(
                                name=employee_name,
                                rank="",
                                dept1=dept1,
                                dept2=dept2,
                                dept3=dept3,
                                tasks="",
                                phone="",
                                score=1.0
                            )

                        recommendation = AssignmentRecommendation(
                            primary=primary_candidate,
                            candidates=[],
                            reasoning=reasoning
                        )
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass

            # Pipeline V2가 아닌 경우 기존 로직 사용
            if not recommendation and rec_data and rec_data.strip():
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
    """Pipeline V2를 통한 담당자 자동 추천 (증거 수집 + RAG + LLM)"""
    from app.services.pipeline_v2 import get_pipeline_v2

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
        # Pipeline V2 사용
        pipeline = get_pipeline_v2()

        logger.info(f"Pipeline V2로 문서 {document_id} 담당자 추천 시작")

        recommendation = await pipeline.recommend_assignee_with_pipeline(
            document_title=doc.title,
            document_content=doc.content,
            db=db
        )

        logger.info(f"Pipeline V2 추천 완료: {recommendation.primary.name}")

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
            except Exception as e:
                logger.error(f"추천 결과 JSON 변환 실패: {e}")

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

        logger.info(f"문서 {document_id} 추천 결과 DB 저장 완료")

        return recommendation

    except (QdrantConnectionError, VectorSearchError) as e:
        logger.error(f"벡터 검색 실패: {e}")
        await db.execute(
            text("UPDATE documents SET status = :status WHERE id = :id"),
            {"status": "오류", "id": document_id}
        )
        await db.commit()
        raise HTTPException(status_code=503, detail=f"벡터 검색 실패: {str(e)}")
    except (LLMAPIError, LLMResponseParseError) as e:
        logger.error(f"LLM 서비스 오류: {e}")
        await db.execute(
            text("UPDATE documents SET status = :status WHERE id = :id"),
            {"status": "오류", "id": document_id}
        )
        await db.commit()
        raise HTTPException(status_code=503, detail=f"LLM 서비스 오류: {str(e)}")
    except LLMServiceError as e:
        logger.error(f"LLM 처리 실패: {e}")
        await db.execute(
            text("UPDATE documents SET status = :status WHERE id = :id"),
            {"status": "오류", "id": document_id}
        )
        await db.commit()
        raise HTTPException(status_code=500, detail=f"LLM 처리 실패: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"추천 처리 중 예외 발생: {e}", exc_info=True)
        await db.execute(
            text("UPDATE documents SET status = :status WHERE id = :id"),
            {"status": "오류", "id": document_id}
        )
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

