from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
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


class QueryInterpretation(BaseModel):
    metric: str | None = None
    date_filter: str | None = None
    filters: list[str] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    sort: str | None = None
    limit: int | None = None
    used_columns: list[str] = Field(default_factory=list)
    selected_expressions: list[str] = Field(default_factory=list)
    row_logic: str | None = None
    result_shape: str | None = None
    explanation_ru: list[str] = Field(default_factory=list)


class ClarificationOption(BaseModel):
    label: str
    question: str
    template_params: dict[str, Any] = Field(default_factory=dict)


class ClarificationPayload(BaseModel):
    message_ru: str
    reason: str | None = None
    options: list[ClarificationOption] = Field(default_factory=list)


class QueryVisualization(BaseModel):
    recommended: bool = False
    type: str = Field(default="table", description="Frontend view type: metric, table, bar, line, pie")
    title: str | None = None
    x_axis: str | None = None
    y_axis: str | None = None
    series: list[str] = Field(default_factory=list)
    label_column: str | None = None
    value_column: str | None = None
    reason_ru: str | None = None
    frontend_config: dict[str, Any] = Field(default_factory=dict)


class AskResponse(BaseModel):
    question: str
    sql: str
    confidence: float | None = None
    confidence_reason: str | None = None
    notes: str | None = None
    result: QueryResult
    guardrails: SqlValidationResponse
    interpretation: QueryInterpretation | None = None
    visualization: QueryVisualization | None = None
    needs_clarification: bool = False
    clarification: ClarificationPayload | None = None
    source: str = "llm"
    template_id: str | None = None
    template_title: str | None = None
    template_match_score: float | None = None
    cache_hit: bool = False
    history_id: int | None = None
