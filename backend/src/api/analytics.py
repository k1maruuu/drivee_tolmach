from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user
from src.core.config import settings
from src.db.session import get_db
from src.models.query_log import QueryLog
from src.models.user import User
from src.schemas.analytics import AskRequest, AskResponse, SqlRequest, SqlValidationResponse
from src.services.clarification import analyze_question_for_clarification
from src.services.confidence import build_confidence
from src.services.dataset_loader import TRAIN_COLUMNS, TRAIN_COLUMN_DESCRIPTIONS, read_train_notes
from src.services.explainability import build_query_interpretation
from src.services.history_service import create_query_history, now_ms
from src.services.ollama_client import generate_sql
from src.services.query_executor import execute_readonly_query
from src.services.redis_cache import get_json, set_json
from src.services.sql_guard import validate_sql_against_database
from src.services.template_params import resolve_template_params
from src.services.template_service import find_matching_template, result_cache_key
from src.services.visualization import build_visualization_config

router = APIRouter(prefix="/analytics", tags=["analytics"])


EMPTY_RESULT = {"columns": [], "rows": [], "row_count": 0}


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


def _missing_template_params(template: dict, provided_params: dict) -> list[str]:
    required_params = set(template.get("params", []))
    return sorted(required_params - set(provided_params))


def _template_confidence(template: dict, *, cache_hit: bool = False):
    return build_confidence(
        source="template_cache" if cache_hit else "template",
        template_match_score=(template.get("match") or {}).get("score"),
        validation_is_valid=True,
        cache_hit=cache_hit,
    )


def _execute_matched_template(
    *,
    template: dict,
    question: str,
    max_rows: int,
    params: dict,
    db: Session,
    current_user: User,
) -> AskResponse:
    """Execute template directly from /analytics/ask without calling Ollama."""
    started_at = perf_counter()
    missing_params = _missing_template_params(template, params)
    if missing_params:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Найден готовый шаблон, поэтому запрос не отправлен в ИИ. Для запуска шаблона нужны параметры.",
                "template_id": template.get("id"),
                "template_title": template.get("title"),
                "missing_params": missing_params,
                "example": {name: "2026-01-01" if "date" in name else "value" for name in missing_params},
            },
        )

    sql = str(template["sql"])
    cache_key = result_cache_key(str(template["id"]), sql, params, max_rows)
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        cached_result = cached.get("result")
        cached_guardrails = cached.get("guardrails")
        if cached_result and cached_guardrails:
            cached_sql = str(cached.get("sql", sql))
            interpretation = cached.get("interpretation") or build_query_interpretation(
                question=question,
                sql=cached_sql,
                source="template_cache",
                result=cached_result,
            )
            visualization = cached.get("visualization") or build_visualization_config(
                question=question,
                sql=cached_sql,
                result=cached_result,
                interpretation=interpretation,
            )
            confidence = _template_confidence(template, cache_hit=True)
            create_query_history(
                db,
                current_user=current_user,
                question=question,
                generated_sql=cached_sql,
                source="template_cache",
                template_id=str(template.get("id")),
                template_title=str(template.get("title")),
                result=cached_result,
                confidence=confidence.value,
                execution_time_ms=now_ms(started_at),
            )
            return AskResponse(
                question=question,
                sql=cached_sql,
                confidence=confidence.value,
                confidence_reason=confidence.reason,
                notes="Найден и выполнен готовый шаблон. ИИ/Ollama не вызывалась. Результат взят из Redis cache.",
                result=cached_result,
                guardrails=cached_guardrails,
                interpretation=interpretation,
                visualization=visualization,
                source="template",
                template_id=str(template.get("id")),
                template_title=str(template.get("title")),
                template_match_score=(template.get("match") or {}).get("score"),
                cache_hit=True,
            )

    validation = validate_sql_against_database(db, sql, limit=max_rows, params=params)
    if not validation.is_valid or not validation.normalized_sql:
        error_message = "; ".join(validation.errors)
        log = QueryLog(
            user_id=current_user.id,
            question=question,
            generated_sql=sql,
            status="template_blocked",
            error_message=error_message,
            confidence=0.0,
        )
        db.add(log)
        db.commit()
        create_query_history(
            db,
            current_user=current_user,
            question=question,
            generated_sql=sql,
            source="template",
            template_id=str(template.get("id")),
            template_title=str(template.get("title")),
            status="blocked",
            error_message=error_message,
            confidence=0.0,
            execution_time_ms=now_ms(started_at),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": validation.errors, "sql": sql, "template_id": template.get("id")},
        )

    result = execute_readonly_query(db, validation.normalized_sql, params=params)
    guardrails = _validation_response(validation)
    interpretation = build_query_interpretation(
        question=question,
        sql=validation.normalized_sql,
        source="template",
        result=result,
    )
    visualization = build_visualization_config(
        question=question,
        sql=validation.normalized_sql,
        result=result,
        interpretation=interpretation,
    )
    confidence = _template_confidence(template, cache_hit=False)
    execution_time_ms = now_ms(started_at)

    response_payload = {
        "template_id": template.get("id"),
        "title": template.get("title"),
        "sql": validation.normalized_sql,
        "params": params,
        "cache_hit": False,
        "result": result,
        "guardrails": guardrails,
        "interpretation": interpretation,
        "visualization": visualization,
        "confidence": confidence.value,
        "confidence_reason": confidence.reason,
    }
    set_json(cache_key, response_payload, settings.template_result_cache_ttl_seconds)

    log = QueryLog(
        user_id=current_user.id,
        question=question,
        generated_sql=validation.normalized_sql,
        status="template_ok",
        confidence=confidence.value,
    )
    db.add(log)
    db.commit()
    create_query_history(
        db,
        current_user=current_user,
        question=question,
        generated_sql=validation.normalized_sql,
        source="template",
        template_id=str(template.get("id")),
        template_title=str(template.get("title")),
        result=result,
        confidence=confidence.value,
        execution_time_ms=execution_time_ms,
    )

    return AskResponse(
        question=question,
        sql=validation.normalized_sql,
        confidence=confidence.value,
        confidence_reason=confidence.reason,
        notes="Найден и выполнен готовый шаблон. ИИ/Ollama не вызывалась.",
        result=result,
        guardrails=guardrails,
        interpretation=interpretation,
        visualization=visualization,
        source="template",
        template_id=str(template.get("id")),
        template_title=str(template.get("title")),
        template_match_score=(template.get("match") or {}).get("score"),
        cache_hit=False,
    )


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
    started_at = perf_counter()
    validation = validate_sql_against_database(db, data.sql, limit=data.max_rows)
    if not validation.is_valid or not validation.normalized_sql:
        create_query_history(
            db,
            current_user=current_user,
            question="Manual SQL execution",
            generated_sql=data.sql,
            source="manual_sql",
            status="blocked",
            error_message="; ".join(validation.errors),
            execution_time_ms=now_ms(started_at),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=validation.errors)

    result = execute_readonly_query(db, validation.normalized_sql)
    interpretation = build_query_interpretation(
        question="Manual SQL execution",
        sql=validation.normalized_sql,
        source="manual_sql",
        result=result,
    )
    visualization = build_visualization_config(
        question="Manual SQL execution",
        sql=validation.normalized_sql,
        result=result,
        interpretation=interpretation,
    )
    confidence = build_confidence(
        source="manual_sql",
        validation_is_valid=True,
        has_warnings=bool(validation.warnings),
        row_count=result.get("row_count"),
    )
    create_query_history(
        db,
        current_user=current_user,
        question="Manual SQL execution",
        generated_sql=validation.normalized_sql,
        source="manual_sql",
        result=result,
        confidence=confidence.value,
        execution_time_ms=now_ms(started_at),
    )
    return {
        "sql": validation.normalized_sql,
        "confidence": confidence.value,
        "confidence_reason": confidence.reason,
        "guardrails": _validation_response(validation),
        "interpretation": interpretation,
        "visualization": visualization,
        "result": result,
    }


@router.post("/ask", response_model=AskResponse)
async def ask(
    data: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    started_at = perf_counter()
    max_rows = min(data.max_rows or settings.sql_default_limit, settings.sql_max_limit)

    # 1) First try reusable templates from goodprompts.txt.
    # If a template is matched, we execute its SQL directly and do NOT call Ollama.
    matched_template = find_matching_template(data.question)
    if matched_template:
        template_params = resolve_template_params(
            db,
            question=data.question,
            required_params=matched_template.get("params", []),
            provided_params=data.template_params or {},
        )
        missing_params = _missing_template_params(matched_template, template_params)
        if not missing_params:
            return _execute_matched_template(
                template=matched_template,
                question=data.question,
                max_rows=max_rows,
                params=template_params,
                db=db,
                current_user=current_user,
            )
        # If a parameterized template matched but the user did not provide a
        # concrete period and we could not infer one, do not return 400 from
        # /analytics/ask. Fallback to ambiguity check / Ollama instead.

    # 2) If there is no safe template and the question is clearly ambiguous,
    # ask for clarification instead of letting the LLM guess a business metric.
    clarification = analyze_question_for_clarification(data.question)
    if clarification.needs_clarification:
        confidence = build_confidence(source="clarification")
        QueryLogEntry = QueryLog(
            user_id=current_user.id,
            question=data.question,
            generated_sql="",
            status="needs_clarification",
            error_message=clarification.reason,
            confidence=confidence.value,
        )
        db.add(QueryLogEntry)
        db.commit()
        create_query_history(
            db,
            current_user=current_user,
            question=data.question,
            generated_sql="",
            source="clarification",
            status="needs_clarification",
            error_message=clarification.reason,
            confidence=confidence.value,
            execution_time_ms=now_ms(started_at),
        )
        return AskResponse(
            question=data.question,
            sql="",
            confidence=confidence.value,
            confidence_reason=confidence.reason,
            notes="Запрос неоднозначный. Backend не вызвал Ollama и не стал угадывать SQL.",
            result=EMPTY_RESULT,
            guardrails=SqlValidationResponse(
                is_valid=False,
                sql="",
                normalized_sql=None,
                errors=["needs_clarification"],
                warnings=[],
            ),
            interpretation=None,
            visualization=None,
            needs_clarification=True,
            clarification=clarification.to_payload(),
            source="clarification",
            cache_hit=False,
        )

    # 3) Fallback to Ollama only when there is no suitable template and no
    # obvious ambiguity.
    generated = await generate_sql(data.question, max_rows=max_rows)
    raw_sql = str(generated["sql"])
    validation = validate_sql_against_database(db, raw_sql, limit=max_rows)
    repaired = False

    # One automatic repair attempt: useful when the model invents columns like id.
    if not validation.is_valid:
        repaired = True
        feedback = _validation_feedback(validation)
        generated = await generate_sql(data.question, max_rows=max_rows, validation_feedback=feedback)
        raw_sql = str(generated["sql"])
        validation = validate_sql_against_database(db, raw_sql, limit=max_rows)

    if not validation.is_valid or not validation.normalized_sql:
        error_message = "; ".join(validation.errors)
        confidence = build_confidence(
            source="llm",
            llm_confidence=generated.get("confidence"),
            validation_is_valid=False,
            has_warnings=bool(validation.warnings),
            repaired=repaired,
        )
        log = QueryLog(
            user_id=current_user.id,
            question=data.question,
            generated_sql=raw_sql,
            status="blocked",
            error_message=error_message,
            confidence=confidence.value,
        )
        db.add(log)
        db.commit()
        create_query_history(
            db,
            current_user=current_user,
            question=data.question,
            generated_sql=raw_sql,
            source="llm",
            status="blocked",
            error_message=error_message,
            confidence=confidence.value,
            execution_time_ms=now_ms(started_at),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": validation.errors, "sql": raw_sql, "confidence": confidence.value, "confidence_reason": confidence.reason},
        )

    result = execute_readonly_query(db, validation.normalized_sql)
    interpretation = build_query_interpretation(
        question=data.question,
        sql=validation.normalized_sql,
        source="llm",
        result=result,
    )
    visualization = build_visualization_config(
        question=data.question,
        sql=validation.normalized_sql,
        result=result,
        interpretation=interpretation,
    )
    confidence = build_confidence(
        source="llm",
        llm_confidence=generated.get("confidence"),
        validation_is_valid=True,
        has_warnings=bool(validation.warnings),
        row_count=result.get("row_count"),
        repaired=repaired,
    )
    execution_time_ms = now_ms(started_at)

    log = QueryLog(
        user_id=current_user.id,
        question=data.question,
        generated_sql=validation.normalized_sql,
        status="ok",
        confidence=confidence.value,
    )
    db.add(log)
    db.commit()
    create_query_history(
        db,
        current_user=current_user,
        question=data.question,
        generated_sql=validation.normalized_sql,
        source="llm",
        result=result,
        confidence=confidence.value,
        execution_time_ms=execution_time_ms,
    )

    return AskResponse(
        question=data.question,
        sql=validation.normalized_sql,
        confidence=confidence.value,
        confidence_reason=confidence.reason,
        notes=generated.get("notes"),
        result=result,
        guardrails=_validation_response(validation),
        interpretation=interpretation,
        visualization=visualization,
        source="llm",
        cache_hit=False,
    )
