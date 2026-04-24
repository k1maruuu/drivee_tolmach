from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class QueryAuditLogRead(BaseModel):
    id: int
    user_id: int | None = None
    action: str
    source: str
    status: str
    question: str | None = None
    template_id: str | None = None
    template_title: str | None = None
    sql: str | None = None
    normalized_sql: str | None = None
    is_valid: bool | None = None
    blocked_reason: str | None = None
    guardrail_errors: list[str] = Field(default_factory=list)
    guardrail_warnings: list[str] = Field(default_factory=list)
    confidence: float | None = None
    row_count: int | None = None
    execution_time_ms: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class QueryAuditStats(BaseModel):
    total: int
    ok: int
    blocked: int
    error: int
    cache: int
    clarification: int
