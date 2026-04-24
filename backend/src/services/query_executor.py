from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.config import settings


def execute_readonly_query(db: Session, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    bind_params = params or {}

    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        db.execute(text(f"SET LOCAL statement_timeout = {int(settings.sql_statement_timeout_ms)}"))
        db.execute(text("EXPLAIN " + sql), bind_params)
        result = db.execute(text(sql), bind_params)
        rows = result.mappings().all()
        columns = list(result.keys())
        db.rollback()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"SQL execution failed: {exc}") from exc

    data = [dict(row) for row in rows]
    return {"columns": columns, "rows": data, "row_count": len(data)}
