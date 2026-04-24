from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class ReportSchedule(Base):
    __tablename__ = "report_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("saved_reports.id", ondelete="CASCADE"), nullable=False, index=True)

    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="weekly")  # daily/weekly/monthly
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    hour: Mapped[int] = mapped_column(Integer, nullable=False, default=9)
    minute: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    day_of_week: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Monday=0 ... Sunday=6
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1..31

    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    default_max_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_result_preview: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
