from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.schemas.analytics import QueryInterpretation, QueryResult, QueryVisualization, SqlValidationResponse
from src.schemas.reports import SavedReportRead

ScheduleFrequency = Literal["daily", "weekly", "monthly"]


class ReportScheduleCreate(BaseModel):
    report_id: int = Field(gt=0)
    frequency: ScheduleFrequency = "weekly"
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    hour: int = Field(default=9, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    params: dict[str, Any] = Field(default_factory=dict)
    default_max_rows: int | None = Field(default=None, ge=1, le=1000)
    is_enabled: bool = True

    @model_validator(mode="after")
    def fill_defaults(self):
        if self.frequency == "weekly" and self.day_of_week is None:
            self.day_of_week = 0
        if self.frequency == "monthly" and self.day_of_month is None:
            self.day_of_month = 1
        return self


class ReportScheduleUpdate(BaseModel):
    frequency: ScheduleFrequency | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    hour: int | None = Field(default=None, ge=0, le=23)
    minute: int | None = Field(default=None, ge=0, le=59)
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    params: dict[str, Any] | None = None
    default_max_rows: int | None = Field(default=None, ge=1, le=1000)
    is_enabled: bool | None = None


class ReportScheduleRead(BaseModel):
    id: int
    report_id: int
    frequency: str
    timezone: str
    hour: int
    minute: int
    day_of_week: int | None = None
    day_of_month: int | None = None
    params: dict[str, Any]
    default_max_rows: int | None = None
    is_enabled: bool
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_status: str | None = None
    last_error_message: str | None = None
    last_row_count: int | None = None
    last_result_preview: dict[str, Any] | None = None
    run_count: int
    failure_count: int
    created_at: datetime
    updated_at: datetime
    report: SavedReportRead | None = None


class ReportScheduleExecuteResponse(BaseModel):
    schedule: ReportScheduleRead
    sql: str
    params: dict[str, Any]
    result: QueryResult
    guardrails: SqlValidationResponse
    interpretation: QueryInterpretation | None = None
    visualization: QueryVisualization | None = None


class DueSchedulesRunResponse(BaseModel):
    checked_at: datetime
    executed: int
    failed: int
    schedule_ids: list[int]
