from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user
from src.core.config import settings
from src.db.session import get_db
from src.models.user import User
from src.schemas.analytics import SqlValidationResponse
from src.schemas.templates import QueryTemplateRead, TemplateExecuteRequest, TemplateExecuteResponse
from src.services.explainability import build_query_interpretation
from src.services.history_service import create_query_history, now_ms
from src.services.query_executor import execute_readonly_query
from src.services.redis_cache import get_json, set_json
from src.services.sql_guard import validate_sql_against_database
from src.services.template_params import resolve_template_params
from src.services.template_service import get_template, load_templates, result_cache_key
from src.services.visualization import build_visualization_config

router = APIRouter(prefix="/templates", tags=["query templates"])


def _validation_response(validation) -> SqlValidationResponse:
    return SqlValidationResponse(
        is_valid=validation.is_valid,
        sql=validation.sql,
        normalized_sql=validation.normalized_sql,
        errors=validation.errors,
        warnings=validation.warnings,
    )


@router.get("", response_model=list[QueryTemplateRead])
def list_query_templates(current_user: User = Depends(get_current_user)):
    """
    List ready-made prompts for frontend buttons.

    The list is cached in Redis, so the frontend can load it frequently without
    reading/parsing goodprompts.txt every time.
    """
    return load_templates()


@router.get("/{template_id}", response_model=QueryTemplateRead)
def read_query_template(template_id: str, current_user: User = Depends(get_current_user)):
    template = get_template(template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return template


@router.post("/{template_id}/execute", response_model=TemplateExecuteResponse)
def execute_query_template(
    template_id: str,
    data: TemplateExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    started_at = perf_counter()
    template = get_template(template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    required_params = set(template.get("params", []))
    provided_params = resolve_template_params(
        db,
        question=str(template.get("question", "")),
        required_params=required_params,
        provided_params=data.params or {},
    )
    missing_params = sorted(required_params - set(provided_params))
    if missing_params:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Template requires parameters",
                "missing_params": missing_params,
                "example": {name: "2026-01-01" if "date" in name else "value" for name in missing_params},
            },
        )

    max_rows = min(data.max_rows or settings.sql_default_limit, settings.sql_max_limit)
    sql = str(template["sql"])
    cache_key = result_cache_key(template_id, sql, provided_params, max_rows)

    cached = get_json(cache_key)
    if isinstance(cached, dict):
        cached["cache_hit"] = True
        cached_sql = str(cached.get("sql", sql))
        if not cached.get("interpretation") and cached.get("result"):
            cached["interpretation"] = build_query_interpretation(
                question=str(template["question"]),
                sql=cached_sql,
                source="template_cache",
                result=cached.get("result"),
            )
        if not cached.get("visualization") and cached.get("result"):
            cached["visualization"] = build_visualization_config(
                question=str(template["question"]),
                sql=cached_sql,
                result=cached.get("result"),
                interpretation=cached.get("interpretation"),
            )
        create_query_history(
            db,
            current_user=current_user,
            question=str(template["question"]),
            generated_sql=cached_sql,
            source="template_cache",
            template_id=template_id,
            template_title=str(template["title"]),
            result=cached.get("result"),
            confidence=1.0,
            execution_time_ms=now_ms(started_at),
        )
        return cached

    validation = validate_sql_against_database(db, sql, limit=max_rows, params=provided_params)
    if not validation.is_valid or not validation.normalized_sql:
        create_query_history(
            db,
            current_user=current_user,
            question=str(template["question"]),
            generated_sql=sql,
            source="template",
            template_id=template_id,
            template_title=str(template["title"]),
            status="blocked",
            error_message="; ".join(validation.errors),
            confidence=1.0,
            execution_time_ms=now_ms(started_at),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": validation.errors, "sql": sql},
        )

    result = execute_readonly_query(db, validation.normalized_sql, params=provided_params)
    interpretation = build_query_interpretation(
        question=str(template["question"]),
        sql=validation.normalized_sql,
        source="template",
        result=result,
    )
    visualization = build_visualization_config(
        question=str(template["question"]),
        sql=validation.normalized_sql,
        result=result,
        interpretation=interpretation,
    )

    response = {
        "template_id": template_id,
        "title": template["title"],
        "sql": validation.normalized_sql,
        "params": provided_params,
        "cache_hit": False,
        "result": result,
        "guardrails": _validation_response(validation),
        "interpretation": interpretation,
        "visualization": visualization,
    }
    set_json(cache_key, response, settings.template_result_cache_ttl_seconds)
    create_query_history(
        db,
        current_user=current_user,
        question=str(template["question"]),
        generated_sql=validation.normalized_sql,
        source="template",
        template_id=template_id,
        template_title=str(template["title"]),
        result=result,
        confidence=1.0,
        execution_time_ms=now_ms(started_at),
    )
    return response
