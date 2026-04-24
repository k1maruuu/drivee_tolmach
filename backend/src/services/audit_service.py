from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from src.models.audit import QueryAuditLog
from src.models.user import User


def _validation_value(validation: Any, attr: str, default: Any = None) -> Any:
    if validation is None:
        return default
    return getattr(validation, attr, default)


def create_query_audit_log(
    db: Session,
    *,
    current_user: User | None,
    action: str,
    source: str,
    status: str | None = None,
    question: str | None = None,
    sql: str | None = None,
    normalized_sql: str | None = None,
    validation: Any | None = None,
    template_id: str | None = None,
    template_title: str | None = None,
    blocked_reason: str | None = None,
    confidence: float | None = None,
    row_count: int | None = None,
    execution_time_ms: int | None = None,
    extra: dict[str, Any] | None = None,
) -> QueryAuditLog | None:
    """Persist a best-effort audit record.

    This helper intentionally never raises to API handlers. Audit logging must
    not break the user path if the database transaction is already rolled back
    or if an optional value cannot be serialized.
    """
    errors = list(_validation_value(validation, "errors", []) or [])
    warnings = list(_validation_value(validation, "warnings", []) or [])
    is_valid = _validation_value(validation, "is_valid", None)
    normalized = normalized_sql or _validation_value(validation, "normalized_sql", None)
    raw_sql = sql if sql is not None else _validation_value(validation, "sql", None)

    if blocked_reason is None and errors:
        blocked_reason = "; ".join(errors)

    if status is None:
        if is_valid is False or errors:
            status = "blocked"
        else:
            status = "ok"

    try:
        audit = QueryAuditLog(
            user_id=current_user.id if current_user else None,
            action=action,
            source=source,
            status=status,
            question=question,
            template_id=template_id,
            template_title=template_title,
            sql=raw_sql,
            normalized_sql=normalized,
            is_valid=is_valid,
            blocked_reason=blocked_reason,
            guardrail_errors=jsonable_encoder(errors),
            guardrail_warnings=jsonable_encoder(warnings),
            confidence=confidence,
            row_count=row_count,
            execution_time_ms=execution_time_ms,
            extra=jsonable_encoder(extra or {}),
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)
        return audit
    except Exception:
        db.rollback()
        return None
