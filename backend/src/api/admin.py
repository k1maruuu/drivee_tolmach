from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_superuser
from src.db.session import get_db
from src.models.audit import QueryAuditLog
from src.models.user import User
from src.schemas.audit import QueryAuditLogRead, QueryAuditStats

router = APIRouter(prefix="/admin", tags=["admin"])


def _audit_to_schema(item: QueryAuditLog) -> QueryAuditLogRead:
    return QueryAuditLogRead(
        id=item.id,
        user_id=item.user_id,
        action=item.action,
        source=item.source,
        status=item.status,
        question=item.question,
        template_id=item.template_id,
        template_title=item.template_title,
        sql=item.sql,
        normalized_sql=item.normalized_sql,
        is_valid=item.is_valid,
        blocked_reason=item.blocked_reason,
        guardrail_errors=item.guardrail_errors or [],
        guardrail_warnings=item.guardrail_warnings or [],
        confidence=item.confidence,
        row_count=item.row_count,
        execution_time_ms=item.execution_time_ms,
        extra=item.extra or {},
        created_at=item.created_at,
    )


@router.get("/query-audit-logs", response_model=list[QueryAuditLogRead])
def list_query_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    source: str | None = Query(default=None),
    action: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    is_valid: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    query = db.query(QueryAuditLog)
    if status_filter:
        query = query.filter(QueryAuditLog.status == status_filter)
    if source:
        query = query.filter(QueryAuditLog.source == source)
    if action:
        query = query.filter(QueryAuditLog.action == action)
    if user_id is not None:
        query = query.filter(QueryAuditLog.user_id == user_id)
    if is_valid is not None:
        query = query.filter(QueryAuditLog.is_valid == is_valid)

    items = query.order_by(QueryAuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return [_audit_to_schema(item) for item in items]


@router.get("/query-audit-logs/stats", response_model=QueryAuditStats)
def get_query_audit_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    rows = db.query(QueryAuditLog.status, func.count(QueryAuditLog.id)).group_by(QueryAuditLog.status).all()
    counts = {status: count for status, count in rows}
    return QueryAuditStats(
        total=sum(counts.values()),
        ok=counts.get("ok", 0),
        blocked=counts.get("blocked", 0),
        error=counts.get("error", 0),
        cache=counts.get("cache", 0),
        clarification=counts.get("clarification", 0),
    )


@router.get("/query-audit-logs/{audit_id}", response_model=QueryAuditLogRead)
def get_query_audit_log(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    item = db.query(QueryAuditLog).filter(QueryAuditLog.id == audit_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit log not found")
    return _audit_to_schema(item)
