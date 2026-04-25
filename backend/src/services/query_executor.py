from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.config import settings


def _apply_readonly_execution_settings(db: Session) -> None:
    timeout_ms = int(settings.sql_statement_timeout_ms)
    db.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
    db.execute(text(f"SET LOCAL idle_in_transaction_session_timeout = {timeout_ms}"))
    if settings.sql_readonly_transaction:
        db.execute(text("SET LOCAL default_transaction_read_only = on"))


def execute_readonly_query(db: Session, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute already validated SELECT SQL with DB-level safety limits.

    The caller must pass normalized SQL from sql_guard. This function still sets
    PostgreSQL transaction-level protections to prevent long or mutating queries
    even if a route accidentally bypasses validation.
    """
    bind_params = params or {}

    try:
        _apply_readonly_execution_settings(db)
        db.execute(text("EXPLAIN (FORMAT JSON) " + sql), bind_params)
        result = db.execute(text(sql), bind_params)
        rows = result.mappings().all()
        columns = list(result.keys())
        db.rollback()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"SQL execution failed: {exc}") from exc

    data = [dict(row) for row in rows]
    return {"columns": columns, "rows": data, "row_count": len(data)}
