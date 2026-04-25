from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.schemas.analytics import QueryInterpretation, QueryResult, QueryVisualization, SqlValidationResponse


class QueryHistoryRead(BaseModel):
    id: int
    question: str
    source: str
    template_id: str | None = None
    template_title: str | None = None
    generated_sql: str
    status: str
    error_message: str | None = None
    confidence: float | None = None
    row_count: int | None = None
    execution_time_ms: int | None = None
    result_preview: dict[str, Any] | None = None
    created_at: datetime


class SaveReportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    history_id: int | None = None
    question: str | None = Field(default=None, max_length=1000)
    sql: str | None = Field(default=None, max_length=10000)
    source: str = Field(default="manual", max_length=32)
    template_id: str | None = Field(default=None, max_length=128)
    template_title: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    default_max_rows: int = Field(default=100, ge=1, le=1000)
    # Snapshot when saving without history_id (e.g. fresh Ask response).
    result: dict[str, Any] | None = Field(default=None, description="QueryResult JSON to store as last_result_preview")
    interpretation: dict[str, Any] | None = None
    visualization: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_source_data(self):
        if self.history_id is None and (not self.question or not self.sql):
            raise ValueError("Pass history_id or both question and sql")
        return self


class SavedReportRead(BaseModel):
    id: int
    title: str
    description: str | None = None
    question: str
    source: str
    template_id: str | None = None
    template_title: str | None = None
    sql: str
    params: dict[str, Any]
    default_max_rows: int
    last_result_preview: dict[str, Any] | None = None
    last_interpretation: dict[str, Any] | None = None
    last_visualization: dict[str, Any] | None = None
    last_row_count: int | None = None
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SavedReportUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class ReportExecuteRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    max_rows: int | None = Field(default=None, ge=1, le=1000)


class ReportExecuteResponse(BaseModel):
    report: SavedReportRead
    sql: str
    params: dict[str, Any]
    result: QueryResult
    guardrails: SqlValidationResponse
    interpretation: QueryInterpretation | None = None
    visualization: QueryVisualization | None = None
