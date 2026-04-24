from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user
from src.core.config import settings
from src.db.session import get_db
from src.models.query_log import QueryLog
from src.models.user import User
from src.schemas.analytics import AskRequest, AskResponse, SqlRequest, SqlValidationResponse
from src.services.dataset_loader import TRAIN_COLUMNS, TRAIN_COLUMN_DESCRIPTIONS, read_train_notes
from src.services.ollama_client import generate_sql
from src.services.query_executor import execute_readonly_query
from src.services.sql_guard import validate_sql_against_database

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _validation_response(validation) -> SqlValidationResponse:
    return SqlValidationResponse(
        is_valid=validation.is_valid,
        sql=validation.sql,
        normalized_sql=validation.normalized_sql,
        errors=validation.errors,
        warnings=validation.warnings,
    )


def _validation_feedback(validation) -> str:
    parts = []
    if validation.errors:
        parts.append("Errors: " + "; ".join(validation.errors))
    if validation.warnings:
        parts.append("Warnings: " + "; ".join(validation.warnings))
    parts.append("Important: table train has no column id. Use order_id and tender_id.")
    return "\n".join(parts)


@router.get("/schema")
def schema(current_user: User = Depends(get_current_user)):
    return {
        "table": "train",
        "has_id_column": False,
        "columns": TRAIN_COLUMNS,
        "column_descriptions": TRAIN_COLUMN_DESCRIPTIONS,
        "notes_md": read_train_notes(),
        "dataset_loading": "train.csv is imported into PostgreSQL table train on startup when IMPORT_TRAIN_ON_STARTUP=true. Ollama receives only schema + notes.md, not the whole CSV.",
        "semantic_notes": {
            "orders": "COUNT(DISTINCT order_id) for business order count; raw rows are order_id + tender_id combinations",
            "order_identifier": "order_id",
            "tender_identifier": "tender_id",
            "done_trips": "status_order = 'done'",
            "client_cancellations": "clientcancel_timestamp IS NOT NULL",
            "driver_cancellations": "drivercancel_timestamp IS NOT NULL",
            "price": "price_order_local",
            "date": "order_timestamp",
            "city": "city_id",
            "distance": "distance_in_meters",
            "duration": "duration_in_seconds",
        },
    }


@router.post("/sql/validate", response_model=SqlValidationResponse)
def validate_sql_endpoint(
    data: SqlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    validation = validate_sql_against_database(db, data.sql, limit=data.max_rows)
    return _validation_response(validation)


@router.post("/sql/execute")
def execute_sql_endpoint(
    data: SqlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    validation = validate_sql_against_database(db, data.sql, limit=data.max_rows)
    if not validation.is_valid or not validation.normalized_sql:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=validation.errors)

    return {
        "sql": validation.normalized_sql,
        "guardrails": _validation_response(validation),
        "result": execute_readonly_query(db, validation.normalized_sql),
    }


@router.post("/ask", response_model=AskResponse)
async def ask(
    data: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    max_rows = min(data.max_rows or settings.sql_default_limit, settings.sql_max_limit)

    generated = await generate_sql(data.question, max_rows=max_rows)
    raw_sql = str(generated["sql"])
    validation = validate_sql_against_database(db, raw_sql, limit=max_rows)

    # One automatic repair attempt: useful when the model invents columns like id.
    if not validation.is_valid:
        feedback = _validation_feedback(validation)
        generated = await generate_sql(data.question, max_rows=max_rows, validation_feedback=feedback)
        raw_sql = str(generated["sql"])
        validation = validate_sql_against_database(db, raw_sql, limit=max_rows)

    if not validation.is_valid or not validation.normalized_sql:
        log = QueryLog(
            user_id=current_user.id,
            question=data.question,
            generated_sql=raw_sql,
            status="blocked",
            error_message="; ".join(validation.errors),
            confidence=generated.get("confidence"),
        )
        db.add(log)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": validation.errors, "sql": raw_sql},
        )

    result = execute_readonly_query(db, validation.normalized_sql)

    log = QueryLog(
        user_id=current_user.id,
        question=data.question,
        generated_sql=validation.normalized_sql,
        status="ok",
        confidence=generated.get("confidence"),
    )
    db.add(log)
    db.commit()

    return AskResponse(
        question=data.question,
        sql=validation.normalized_sql,
        confidence=generated.get("confidence"),
        notes=generated.get("notes"),
        result=result,
        guardrails=_validation_response(validation),
    )
