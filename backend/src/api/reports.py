from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user
from src.core.config import settings
from src.db.session import get_db
from src.models.report import QueryHistory, SavedReport
from src.models.user import User
from src.schemas.analytics import SqlValidationResponse
from src.schemas.reports import (
    QueryHistoryRead,
    ReportExecuteRequest,
    ReportExecuteResponse,
    SaveReportRequest,
    SavedReportRead,
)
from src.services.history_service import build_result_preview, create_query_history
from src.services.query_executor import execute_readonly_query
from src.services.sql_guard import validate_sql_against_database

router = APIRouter(prefix="/reports", tags=["reports"])


def _validation_response(validation) -> SqlValidationResponse:
    return SqlValidationResponse(
        is_valid=validation.is_valid,
        sql=validation.sql,
        normalized_sql=validation.normalized_sql,
        errors=validation.errors,
        warnings=validation.warnings,
    )


def _history_to_schema(item: QueryHistory) -> QueryHistoryRead:
    return QueryHistoryRead(
        id=item.id,
        question=item.question,
        source=item.source,
        template_id=item.template_id,
        template_title=item.template_title,
        generated_sql=item.generated_sql,
        status=item.status,
        error_message=item.error_message,
        confidence=item.confidence,
        row_count=item.row_count,
        execution_time_ms=item.execution_time_ms,
        result_preview=item.result_preview,
        created_at=item.created_at,
    )


def _report_to_schema(item: SavedReport) -> SavedReportRead:
    return SavedReportRead(
        id=item.id,
        title=item.title,
        description=item.description,
        question=item.question,
        source=item.source,
        template_id=item.template_id,
        template_title=item.template_title,
        sql=item.sql,
        params=item.params or {},
        default_max_rows=item.default_max_rows,
        last_result_preview=item.last_result_preview,
        last_row_count=item.last_row_count,
        last_run_at=item.last_run_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/history", response_model=list[QueryHistoryRead])
def list_query_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    source: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(QueryHistory).filter(QueryHistory.user_id == current_user.id)
    if status_filter:
        query = query.filter(QueryHistory.status == status_filter)
    if source:
        query = query.filter(QueryHistory.source == source)

    items = query.order_by(QueryHistory.created_at.desc()).offset(offset).limit(limit).all()
    return [_history_to_schema(item) for item in items]


@router.post("/save", response_model=SavedReportRead, status_code=status.HTTP_201_CREATED)
def save_report(
    data: SaveReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    history: QueryHistory | None = None
    if data.history_id is not None:
        history = (
            db.query(QueryHistory)
            .filter(QueryHistory.id == data.history_id, QueryHistory.user_id == current_user.id)
            .first()
        )
        if not history:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History item not found")
        if history.status != "ok":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only successful queries can be saved")

    question = history.question if history else str(data.question)
    sql = history.generated_sql if history else str(data.sql)
    source = history.source if history else data.source
    template_id = history.template_id if history else data.template_id
    template_title = history.template_title if history else data.template_title
    last_preview = history.result_preview if history else None
    last_row_count = history.row_count if history else None

    validation = validate_sql_against_database(db, sql, limit=data.default_max_rows, params=data.params)
    if not validation.is_valid or not validation.normalized_sql:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Report SQL did not pass validation", "errors": validation.errors, "sql": sql},
        )

    report = SavedReport(
        user_id=current_user.id,
        title=data.title,
        description=data.description,
        question=question,
        source=source,
        template_id=template_id,
        template_title=template_title,
        sql=validation.normalized_sql,
        params=jsonable_encoder(data.params or {}),
        default_max_rows=data.default_max_rows,
        last_result_preview=last_preview,
        last_row_count=last_row_count,
        last_run_at=history.created_at if history and history.status == "ok" else None,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _report_to_schema(report)


@router.get("", response_model=list[SavedReportRead])
def list_saved_reports(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = (
        db.query(SavedReport)
        .filter(SavedReport.user_id == current_user.id)
        .order_by(SavedReport.updated_at.desc(), SavedReport.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_report_to_schema(item) for item in items]


@router.get("/{report_id}", response_model=SavedReportRead)
def get_saved_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.query(SavedReport).filter(SavedReport.id == report_id, SavedReport.user_id == current_user.id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return _report_to_schema(report)


@router.post("/{report_id}/execute", response_model=ReportExecuteResponse)
def execute_saved_report(
    report_id: int,
    data: ReportExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.query(SavedReport).filter(SavedReport.id == report_id, SavedReport.user_id == current_user.id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    params = {**(report.params or {}), **(data.params or {})}
    max_rows = min(data.max_rows or report.default_max_rows or settings.sql_default_limit, settings.sql_max_limit)
    validation = validate_sql_against_database(db, report.sql, limit=max_rows, params=params)
    if not validation.is_valid or not validation.normalized_sql:
        create_query_history(
            db,
            current_user=current_user,
            question=report.question,
            generated_sql=report.sql,
            source="saved_report",
            template_id=report.template_id,
            template_title=report.template_title,
            status="blocked",
            error_message="; ".join(validation.errors),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": validation.errors, "sql": report.sql})

    result = execute_readonly_query(db, validation.normalized_sql, params=params)
    report.last_result_preview = build_result_preview(result)
    report.last_row_count = result.get("row_count")
    report.last_run_at = datetime.now(timezone.utc)
    db.add(report)
    db.commit()
    db.refresh(report)

    create_query_history(
        db,
        current_user=current_user,
        question=report.question,
        generated_sql=validation.normalized_sql,
        source="saved_report",
        template_id=report.template_id,
        template_title=report.template_title,
        result=result,
        confidence=1.0 if report.source == "template" else None,
    )

    return ReportExecuteResponse(
        report=_report_to_schema(report),
        sql=validation.normalized_sql,
        params=params,
        result=result,
        guardrails=_validation_response(validation),
    )


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.query(SavedReport).filter(SavedReport.id == report_id, SavedReport.user_id == current_user.id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    db.delete(report)
    db.commit()
    return None
