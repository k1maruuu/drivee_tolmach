from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class QueryAuditLog(Base):
    """Detailed audit trail for SQL guardrails and query execution.

    Unlike QueryHistory, this table is intended for admins and technical experts:
    it stores blocked reasons, guardrail errors/warnings and execution metadata.
    """

    __tablename__ = "query_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # ask/validate/execute/template/report
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # llm/template/cache/manual_sql/...
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # ok/blocked/error/cache/clarification

    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    template_title: Mapped[str | None] = mapped_column(Text, nullable=True)

    sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    guardrail_errors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    guardrail_warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
