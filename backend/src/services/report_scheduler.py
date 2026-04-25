import asyncio
import calendar
from contextlib import suppress
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.session import SessionLocal
from src.models.report import SavedReport
from src.models.schedule import ReportSchedule
from src.models.user import User
from src.schemas.analytics import SqlValidationResponse
from src.services.audit_service import create_query_audit_log
from src.services.explainability import build_query_interpretation
from src.services.history_service import build_result_preview, create_query_history
from src.services.query_executor import execute_readonly_query
from src.services.sql_guard import validate_sql_against_database
from src.services.visualization import build_visualization_config


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_zoneinfo(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _as_aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return _utc_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clamped_month_date(year: int, month: int, day: int) -> datetime:
    last_day = calendar.monthrange(year, month)[1]
    return datetime(year, month, min(day, last_day))


def compute_next_run_at(
    *,
    frequency: str,
    tz_name: str,
    hour: int,
    minute: int,
    day_of_week: int | None = None,
    day_of_month: int | None = None,
    from_utc: datetime | None = None,
) -> datetime:
    """Compute next run timestamp in UTC.

    Frequency rules:
    - daily: every day at hour:minute in selected timezone
    - weekly: selected weekday at hour:minute, Monday=0
    - monthly: selected day of month at hour:minute, clamped to month length
    """
    now_utc = _as_aware_utc(from_utc)
    tz = _safe_zoneinfo(tz_name)
    now_local = now_utc.astimezone(tz)
    local_time = time(hour=hour, minute=minute, tzinfo=tz)

    if frequency == "daily":
        candidate = datetime.combine(now_local.date(), local_time)
        if candidate <= now_local:
            candidate = candidate + timedelta(days=1)
        return candidate.astimezone(timezone.utc)

    if frequency == "weekly":
        target_weekday = 0 if day_of_week is None else day_of_week
        days_ahead = (target_weekday - now_local.weekday()) % 7
        candidate_date = now_local.date() + timedelta(days=days_ahead)
        candidate = datetime.combine(candidate_date, local_time)
        if candidate <= now_local:
            candidate = candidate + timedelta(days=7)
        return candidate.astimezone(timezone.utc)

    if frequency == "monthly":
        target_day = 1 if day_of_month is None else day_of_month
        current_month_date = _clamped_month_date(now_local.year, now_local.month, target_day).date()
        candidate = datetime.combine(current_month_date, local_time)
        if candidate <= now_local:
            if now_local.month == 12:
                next_year, next_month = now_local.year + 1, 1
            else:
                next_year, next_month = now_local.year, now_local.month + 1
            next_month_date = _clamped_month_date(next_year, next_month, target_day).date()
            candidate = datetime.combine(next_month_date, local_time)
        return candidate.astimezone(timezone.utc)

    raise ValueError(f"Unsupported schedule frequency: {frequency}")


def schedule_to_dict(schedule: ReportSchedule) -> dict[str, Any]:
    return {
        "id": schedule.id,
        "report_id": schedule.report_id,
        "frequency": schedule.frequency,
        "timezone": schedule.timezone,
        "hour": schedule.hour,
        "minute": schedule.minute,
        "day_of_week": schedule.day_of_week,
        "day_of_month": schedule.day_of_month,
        "params": schedule.params or {},
        "default_max_rows": schedule.default_max_rows,
        "is_enabled": schedule.is_enabled,
        "next_run_at": schedule.next_run_at,
        "last_run_at": schedule.last_run_at,
        "last_status": schedule.last_status,
        "last_error_message": schedule.last_error_message,
        "last_row_count": schedule.last_row_count,
        "last_result_preview": schedule.last_result_preview,
        "run_count": schedule.run_count,
        "failure_count": schedule.failure_count,
        "created_at": schedule.created_at,
        "updated_at": schedule.updated_at,
    }


def _validation_response(validation) -> SqlValidationResponse:
    return SqlValidationResponse(
        is_valid=validation.is_valid,
        sql=validation.sql,
        normalized_sql=validation.normalized_sql,
        errors=validation.errors,
        warnings=validation.warnings,
    )


def execute_report_schedule(
    db: Session,
    *,
    schedule: ReportSchedule,
    current_user: User | None = None,
    manual: bool = False,
) -> dict[str, Any]:
    report = db.query(SavedReport).filter(SavedReport.id == schedule.report_id).first()
    if not report:
        schedule.last_run_at = _utc_now()
        schedule.last_status = "error"
        schedule.last_error_message = "Saved report not found"
        schedule.failure_count = (schedule.failure_count or 0) + 1
        schedule.next_run_at = compute_next_run_at(
            frequency=schedule.frequency,
            tz_name=schedule.timezone,
            hour=schedule.hour,
            minute=schedule.minute,
            day_of_week=schedule.day_of_week,
            day_of_month=schedule.day_of_month,
        )
        db.add(schedule)
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved report not found")

    owner = current_user or db.query(User).filter(User.id == schedule.user_id).first()
    params = {**(report.params or {}), **(schedule.params or {})}
    max_rows = min(
        schedule.default_max_rows or report.default_max_rows or settings.sql_default_limit,
        settings.sql_max_limit,
    )
    action = "report_schedule_run_now" if manual else "report_schedule_auto_run"

    validation = validate_sql_against_database(db, report.sql, limit=max_rows, params=params)
    if not validation.is_valid or not validation.normalized_sql:
        error_message = "; ".join(validation.errors)
        now = _utc_now()
        schedule.last_run_at = now
        schedule.last_status = "blocked"
        schedule.last_error_message = error_message
        schedule.last_row_count = None
        schedule.failure_count = (schedule.failure_count or 0) + 1
        schedule.next_run_at = compute_next_run_at(
            frequency=schedule.frequency,
            tz_name=schedule.timezone,
            hour=schedule.hour,
            minute=schedule.minute,
            day_of_week=schedule.day_of_week,
            day_of_month=schedule.day_of_month,
            from_utc=now,
        )
        db.add(schedule)
        db.commit()
        db.refresh(schedule)

        create_query_history(
            db,
            current_user=owner,
            question=report.question,
            generated_sql=report.sql,
            source="scheduled_report",
            template_id=report.template_id,
            template_title=report.template_title,
            status="blocked",
            error_message=error_message,
        )
        create_query_audit_log(
            db,
            current_user=owner,
            action=action,
            source="scheduled_report",
            status="blocked",
            question=report.question,
            sql=report.sql,
            validation=validation,
            template_id=report.template_id,
            template_title=report.template_title,
            blocked_reason=error_message,
            extra={"report_id": report.id, "schedule_id": schedule.id, "manual": manual},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": validation.errors, "sql": report.sql})

    try:
        result = execute_readonly_query(db, validation.normalized_sql, params=params)
    except HTTPException as exc:
        now = _utc_now()
        schedule.last_run_at = now
        schedule.last_status = "error"
        schedule.last_error_message = str(exc.detail)
        schedule.last_row_count = None
        schedule.failure_count = (schedule.failure_count or 0) + 1
        schedule.next_run_at = compute_next_run_at(
            frequency=schedule.frequency,
            tz_name=schedule.timezone,
            hour=schedule.hour,
            minute=schedule.minute,
            day_of_week=schedule.day_of_week,
            day_of_month=schedule.day_of_month,
            from_utc=now,
        )
        db.add(schedule)
        db.commit()
        create_query_audit_log(
            db,
            current_user=owner,
            action=action,
            source="scheduled_report",
            status="error",
            question=report.question,
            sql=report.sql,
            validation=validation,
            template_id=report.template_id,
            template_title=report.template_title,
            blocked_reason=str(exc.detail),
            extra={"report_id": report.id, "schedule_id": schedule.id, "manual": manual},
        )
        raise

    interpretation = build_query_interpretation(
        question=report.question,
        sql=validation.normalized_sql,
        source="scheduled_report",
        result=result,
    )
    visualization = build_visualization_config(
        question=report.question,
        sql=validation.normalized_sql,
        result=result,
        interpretation=interpretation,
    )

    preview = build_result_preview(result)
    now = _utc_now()
    report.last_result_preview = preview
    report.last_row_count = result.get("row_count")
    report.last_run_at = now

    schedule.last_run_at = now
    schedule.last_status = "ok"
    schedule.last_error_message = None
    schedule.last_row_count = result.get("row_count")
    schedule.last_result_preview = preview
    schedule.run_count = (schedule.run_count or 0) + 1
    schedule.next_run_at = compute_next_run_at(
        frequency=schedule.frequency,
        tz_name=schedule.timezone,
        hour=schedule.hour,
        minute=schedule.minute,
        day_of_week=schedule.day_of_week,
        day_of_month=schedule.day_of_month,
        from_utc=now,
    )
    db.add(report)
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    db.refresh(report)

    create_query_history(
        db,
        current_user=owner,
        question=report.question,
        generated_sql=validation.normalized_sql,
        source="scheduled_report",
        template_id=report.template_id,
        template_title=report.template_title,
        result=result,
        confidence=1.0 if report.source == "template" else None,
    )
    create_query_audit_log(
        db,
        current_user=owner,
        action=action,
        source="scheduled_report",
        status="ok",
        question=report.question,
        sql=report.sql,
        validation=validation,
        template_id=report.template_id,
        template_title=report.template_title,
        confidence=1.0 if report.source == "template" else None,
        row_count=result.get("row_count"),
        extra={"report_id": report.id, "schedule_id": schedule.id, "manual": manual},
    )

    return {
        "schedule": schedule,
        "report": report,
        "sql": validation.normalized_sql,
        "params": params,
        "result": result,
        "guardrails": _validation_response(validation),
        "interpretation": interpretation,
        "visualization": visualization,
    }


def run_due_report_schedules(db: Session, *, limit: int | None = None) -> dict[str, Any]:
    now = _utc_now()
    batch_size = min(limit or settings.report_scheduler_batch_size, settings.report_scheduler_batch_size)
    due_items = (
        db.query(ReportSchedule)
        .filter(ReportSchedule.is_enabled.is_(True))
        .filter(ReportSchedule.next_run_at.isnot(None))
        .filter(ReportSchedule.next_run_at <= now)
        .order_by(ReportSchedule.next_run_at.asc())
        .limit(batch_size)
        .all()
    )

    executed = 0
    failed = 0
    ids: list[int] = []
    for schedule in due_items:
        ids.append(schedule.id)
        try:
            execute_report_schedule(db, schedule=schedule, manual=False)
            executed += 1
        except Exception:
            failed += 1

    return {"checked_at": now, "executed": executed, "failed": failed, "schedule_ids": ids}


async def report_scheduler_loop() -> None:
    while True:
        await asyncio.sleep(settings.report_scheduler_interval_seconds)
        with suppress(Exception):
            with SessionLocal() as db:
                run_due_report_schedules(db)
