import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.core.config import settings
from src.services.redis_cache import get_json, set_json

TEMPLATES_CACHE_KEY = "drivee:templates:v1:list"


@dataclass(frozen=True)
class QueryTemplate:
    id: str
    title: str
    question: str
    sql: str
    params: list[str]
    category: str
    description: str


def _normalize_template_sql(sql: str) -> str:
    sql = sql.strip().rstrip(";")
    sql = re.sub(r"\banonymized_incity_orders\b", "train", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s+", " ", sql)
    return sql


def _detect_params(sql: str) -> list[str]:
    return sorted(set(re.findall(r":([a-zA-Z_][a-zA-Z0-9_]*)", sql)))


def _slug(text: str, idx: int) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"tpl_{idx:03d}_{digest}"


def _category(question: str, sql: str) -> str:
    q = question.lower()
    s = sql.lower()
    if "город" in q or "city_id" in s:
        return "cities"
    if "водител" in q or "driver_id" in s:
        return "drivers"
    if "пользовател" in q or "user_id" in s:
        return "users"
    if "цена" in q or "стоимость" in q or "чек" in q or "price_" in s or "revenue" in s:
        return "money"
    if "время" in q or "дл" in q or "час" in q or "timestamp" in s or "duration" in s:
        return "time"
    if "процент" in q or "rate" in s or "конвер" in q:
        return "conversion"
    if "тендер" in q or "tender" in s or "отклон" in q:
        return "tenders"
    return "orders"


def _parse_goodprompts_file() -> list[QueryTemplate]:
    path = Path(settings.good_prompts_path)
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    pairs: list[tuple[str, str]] = []
    current_question: str | None = None
    current_sql: list[str] = []

    def flush() -> None:
        nonlocal current_question, current_sql
        if current_question and current_sql:
            sql = "\n".join(current_sql).strip()
            if sql:
                pairs.append((current_question, sql))
        current_question = None
        current_sql = []

    question_re = re.compile(r'^\s*"(.+?)"\s*->\s*$')

    for line in lines:
        match = question_re.match(line)
        if match:
            flush()
            current_question = match.group(1).strip()
            continue

        if current_question is not None:
            if line.strip():
                current_sql.append(line)
            elif current_sql:
                flush()

    flush()

    templates: list[QueryTemplate] = []
    for idx, (question, sql) in enumerate(pairs, start=1):
        normalized_sql = _normalize_template_sql(sql)
        params = _detect_params(normalized_sql)
        templates.append(
            QueryTemplate(
                id=_slug(question, idx),
                title=question,
                question=question,
                sql=normalized_sql,
                params=params,
                category=_category(question, normalized_sql),
                description=(
                    "Готовый шаблон с параметрами: " + ", ".join(params)
                    if params
                    else "Готовый шаблон без параметров"
                ),
            )
        )

    return templates


def load_templates(force_reload: bool = False) -> list[dict[str, Any]]:
    if not force_reload:
        cached = get_json(TEMPLATES_CACHE_KEY)
        if isinstance(cached, list):
            return cached

    templates = [asdict(template) for template in _parse_goodprompts_file()]
    set_json(TEMPLATES_CACHE_KEY, templates, settings.templates_cache_ttl_seconds)
    return templates


def warm_template_cache() -> None:
    load_templates(force_reload=True)


def get_template(template_id: str) -> dict[str, Any] | None:
    for template in load_templates():
        if template.get("id") == template_id:
            return template
    return None


def result_cache_key(template_id: str, sql: str, params: dict[str, Any], max_rows: int) -> str:
    payload = f"{template_id}|{sql}|{params}|{max_rows}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"drivee:template_result:v1:{digest}"
