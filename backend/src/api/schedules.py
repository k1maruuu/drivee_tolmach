from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_superuser, get_current_user
from src.core.config import settings
from src.db.session import get_db
from src.models.report import SavedReport
from src.models.schedule import ReportSchedule
from src.models.user import User
from src.schemas.reports import SavedReportRead
from src.schemas.schedules import (
    DueSchedulesRunResponse,
    ReportScheduleCreate,
    ReportScheduleExecuteResponse,
    ReportScheduleRead,
    ReportScheduleUpdate,
)
from src.services.report_scheduler import compute_next_run_at, execute_report_schedule, run_due_report_schedules

router = APIRouter(prefix="/report-schedules", tags=["report schedules"])


def _report_to_schema(item: SavedReport) -> SavedReportRead:
    return SavedReportRead(
        id=item.id,
        title=item.title,
        description=item.description,
        question=item.question,
        source=item.source,
        template_id=item.template_id,
        template_title=item.template_title,
        sql=item.sql,
        params=item.params or {},
        default_max_rows=item.default_max_rows,
        last_result_preview=item.last_result_preview,
        last_row_count=item.last_row_count,
        last_run_at=item.last_run_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _schedule_to_schema(item: ReportSchedule, report: SavedReport | None = None) -> ReportScheduleRead:
    return ReportScheduleRead(
        id=item.id,
        report_id=item.report_id,
        frequency=item.frequency,
        timezone=item.timezone,
        hour=item.hour,
        minute=item.minute,
        day_of_week=item.day_of_week,
        day_of_month=item.day_of_month,
        params=item.params or {},
        default_max_rows=item.default_max_rows,
        is_enabled=item.is_enabled,
        next_run_at=item.next_run_at,
        last_run_at=item.last_run_at,
        last_status=item.last_status,
        last_error_message=item.last_error_message,
        last_row_count=item.last_row_count,
        last_result_preview=item.last_result_preview,
        run_count=item.run_count,
        failure_count=item.failure_count,
        created_at=item.created_at,
        updated_at=item.updated_at,
        report=_report_to_schema(report) if report else None,
    )


@router.get("", response_model=list[ReportScheduleRead])
def list_report_schedules(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    is_enabled: bool | None = Query(default=None),
    report_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(ReportSchedule).filter(ReportSchedule.user_id == current_user.id)
    if is_enabled is not None:
        query = query.filter(ReportSchedule.is_enabled == is_enabled)
    if report_id is not None:
        query = query.filter(ReportSchedule.report_id == report_id)

    items = query.order_by(ReportSchedule.next_run_at.asc().nullslast(), ReportSchedule.created_at.desc()).offset(offset).limit(limit).all()
    reports = {
        report.id: report
        for report in db.query(SavedReport).filter(SavedReport.id.in_([item.report_id for item in items] or [0])).all()
    }
    return [_schedule_to_schema(item, reports.get(item.report_id)) for item in items]


@router.post("", response_model=ReportScheduleRead, status_code=status.HTTP_201_CREATED)
def create_report_schedule(
    data: ReportScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.query(SavedReport).filter(SavedReport.id == data.report_id, SavedReport.user_id == current_user.id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved report not found")

    next_run_at = None
    if data.is_enabled:
        next_run_at = compute_next_run_at(
            frequency=data.frequency,
            tz_name=data.timezone or settings.default_report_schedule_timezone,
            hour=data.hour,
            minute=data.minute,
            day_of_week=data.day_of_week,
            day_of_month=data.day_of_month,
        )

    schedule = ReportSchedule(
        user_id=current_user.id,
        report_id=report.id,
        frequency=data.frequency,
        timezone=data.timezone or settings.default_report_schedule_timezone,
        hour=data.hour,
        minute=data.minute,
        day_of_week=data.day_of_week,
        day_of_month=data.day_of_month,
        params=jsonable_encoder(data.params or {}),
        default_max_rows=data.default_max_rows,
        is_enabled=data.is_enabled,
        next_run_at=next_run_at,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return _schedule_to_schema(schedule, report)


@router.get("/{schedule_id}", response_model=ReportScheduleRead)
def get_report_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    schedule = db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id, ReportSchedule.user_id == current_user.id).first()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    report = db.query(SavedReport).filter(SavedReport.id == schedule.report_id).first()
    return _schedule_to_schema(schedule, report)


@router.patch("/{schedule_id}", response_model=ReportScheduleRead)
def update_report_schedule(
    schedule_id: int,
    data: ReportScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    schedule = db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id, ReportSchedule.user_id == current_user.id).first()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "params" and value is not None:
            setattr(schedule, key, jsonable_encoder(value))
        else:
            setattr(schedule, key, value)

    if schedule.frequency == "weekly" and schedule.day_of_week is None:
        schedule.day_of_week = 0
    if schedule.frequency == "monthly" and schedule.day_of_month is None:
        schedule.day_of_month = 1

    schedule.next_run_at = None
    if schedule.is_enabled:
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
    db.refresh(schedule)
    report = db.query(SavedReport).filter(SavedReport.id == schedule.report_id).first()
    return _schedule_to_schema(schedule, report)


@router.post("/{schedule_id}/run-now", response_model=ReportScheduleExecuteResponse)
def run_report_schedule_now(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    schedule = db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id, ReportSchedule.user_id == current_user.id).first()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    output = execute_report_schedule(db, schedule=schedule, current_user=current_user, manual=True)
    return ReportScheduleExecuteResponse(
        schedule=_schedule_to_schema(output["schedule"], output.get("report")),
        sql=output["sql"],
        params=output["params"],
        result=output["result"],
        guardrails=output["guardrails"],
        interpretation=output.get("interpretation"),
        visualization=output.get("visualization"),
    )


@router.post("/run-due", response_model=DueSchedulesRunResponse)
def run_due_schedules(
    limit: int | None = Query(default=None, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    result = run_due_report_schedules(db, limit=limit)
    return DueSchedulesRunResponse(**result)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    schedule = db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id, ReportSchedule.user_id == current_user.id).first()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    db.delete(schedule)
    db.commit()
    return None
