from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    max_rows: int | None = Field(default=None, ge=1, le=1000)
    template_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional params for matched templates, for example date_from/date_to/city_id.",
    )


class SqlRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=10000)
    max_rows: int | None = Field(default=None, ge=1, le=1000)


class SqlValidationResponse(BaseModel):
    is_valid: bool
    sql: str
    normalized_sql: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


class AskResponse(BaseModel):
    question: str
    sql: str
    confidence: float | None = None
    notes: str | None = None
    result: QueryResult
    guardrails: SqlValidationResponse
    source: str = "llm"
    template_id: str | None = None
    template_title: str | None = None
    template_match_score: float | None = None
    cache_hit: bool = False
