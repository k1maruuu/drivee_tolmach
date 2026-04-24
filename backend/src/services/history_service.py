from time import perf_counter
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from src.models.report import QueryHistory
from src.models.user import User


def now_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def build_result_preview(result: dict[str, Any] | None, preview_rows: int = 20) -> dict[str, Any] | None:
    if not result:
        return None

    rows = result.get("rows") or []
    preview = {
        "columns": result.get("columns") or [],
        "rows": rows[:preview_rows],
        "preview_row_count": min(len(rows), preview_rows),
        "row_count": result.get("row_count", len(rows)),
        "truncated": len(rows) > preview_rows,
    }
    return jsonable_encoder(preview)


def create_query_history(
    db: Session,
    *,
    current_user: User | None,
    question: str,
    generated_sql: str,
    source: str,
    status: str = "ok",
    template_id: str | None = None,
    template_title: str | None = None,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
    confidence: float | None = None,
    execution_time_ms: int | None = None,
) -> QueryHistory:
    history = QueryHistory(
        user_id=current_user.id if current_user else None,
        question=question,
        source=source,
        template_id=template_id,
        template_title=template_title,
        generated_sql=generated_sql,
        status=status,
        error_message=error_message,
        confidence=confidence,
        row_count=(result or {}).get("row_count") if result else None,
        execution_time_ms=execution_time_ms,
        result_preview=build_result_preview(result),
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    return history
