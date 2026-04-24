from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user
from src.core.config import settings
from src.db.session import get_db
from src.models.user import User
from src.schemas.analytics import SqlValidationResponse
from src.schemas.templates import QueryTemplateRead, TemplateExecuteRequest, TemplateExecuteResponse
from src.services.query_executor import execute_readonly_query
from src.services.redis_cache import get_json, set_json
from src.services.sql_guard import validate_sql_against_database
from src.services.template_service import get_template, load_templates, result_cache_key

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
    template = get_template(template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    required_params = set(template.get("params", []))
    provided_params = data.params or {}
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
    if cached is not None:
        cached["cache_hit"] = True
        return cached

    validation = validate_sql_against_database(db, sql, limit=max_rows, params=provided_params)
    if not validation.is_valid or not validation.normalized_sql:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": validation.errors, "sql": sql},
        )

    result = execute_readonly_query(db, validation.normalized_sql, params=provided_params)

    response = {
        "template_id": template_id,
        "title": template["title"],
        "sql": validation.normalized_sql,
        "params": provided_params,
        "cache_hit": False,
        "result": result,
        "guardrails": _validation_response(validation),
    }
    set_json(cache_key, response, settings.template_result_cache_ttl_seconds)
    return response
