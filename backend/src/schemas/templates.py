from typing import Any

from pydantic import BaseModel, Field

from src.schemas.analytics import QueryInterpretation, QueryResult, QueryVisualization, SqlValidationResponse


class QueryTemplateRead(BaseModel):
    id: str
    title: str
    question: str
    sql: str
    params: list[str] = Field(default_factory=list)
    category: str
    description: str


class TemplateExecuteRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    max_rows: int | None = Field(default=None, ge=1, le=1000)


class TemplateExecuteResponse(BaseModel):
    template_id: str
    title: str
    sql: str
    params: dict[str, Any]
    cache_hit: bool
    confidence: float | None = None
    confidence_reason: str | None = None
    result: QueryResult
    guardrails: SqlValidationResponse
    interpretation: QueryInterpretation | None = None
    visualization: QueryVisualization | None = None
