import hashlib
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from src.core.config import settings
from src.services.redis_cache import get_json, set_json

TEMPLATES_CACHE_KEY = "drivee:templates:v4:list"
TEMPLATE_MATCH_CACHE_PREFIX = "drivee:template_match:v4:"


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
    return f"drivee:template_result:v4:{digest}"


def _normalize_question(text: str) -> str:
    """Normalize a user question for deterministic template lookup.

    This is intentionally strict. It should catch exact/safe reusable prompts,
    but it should not aggressively guess, because a false match is worse than
    sending the question to LLM.
    """
    normalized = text.lower().replace("ё", "е")
    normalized = re.sub(r"[«»\"'`.,!?;:()\[\]{}<>/\\|+*=#№%$@^&~\-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # UI/user filler words. Removing them lets templates match phrases like
    # "покажи мне топ 10..." and "топ 10..." without using the LLM.
    stop_words = {
        "мне",
        "пожалуйста",
        "плиз",
        "давай",
        "выведи",
        "вывести",
        "покажи",
        "показать",
        "напиши",
        "дай",
        "получи",
        "получить",
        "сделай",
        "отобрази",
    }
    tokens = [token for token in normalized.split() if token not in stop_words]
    return " ".join(tokens)


def _token_set_score(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0

    intersection = left_tokens & right_tokens
    precision = len(intersection) / len(left_tokens)
    recall = len(intersection) / len(right_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _template_match_cache_key(question: str) -> str:
    digest = hashlib.sha256(_normalize_question(question).encode("utf-8")).hexdigest()
    return f"{TEMPLATE_MATCH_CACHE_PREFIX}{digest}"


def find_matching_template(question: str) -> dict[str, Any] | None:
    """Return a ready SQL template before calling Ollama.

    Matching order:
    1. exact normalized question match;
    2. conservative fuzzy match.

    The function uses Redis cache for the match decision, but the actual SQL
    template is always loaded from the templates list, so frontend buttons and
    /analytics/ask use the same source of truth.
    """
    query_norm = _normalize_question(question)
    if not query_norm:
        return None

    cache_key = _template_match_cache_key(question)
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        template_id = cached.get("template_id")
        template = get_template(str(template_id)) if template_id else None
        if template:
            template["match"] = cached
            return template
        if cached.get("template_id") is None:
            return None

    templates = load_templates()
    best_template: dict[str, Any] | None = None
    best_score = 0.0
    best_type = "none"

    for template in templates:
        template_norm = _normalize_question(str(template.get("question", "")))
        if not template_norm:
            continue

        if query_norm == template_norm:
            best_template = template
            best_score = 1.0
            best_type = "exact"
            break

        sequence_score = SequenceMatcher(None, query_norm, template_norm).ratio()
        token_score = _token_set_score(query_norm, template_norm)
        score = max(sequence_score, token_score)

        if score > best_score:
            best_score = score
            best_template = template
            best_type = "fuzzy"

    threshold = getattr(settings, "template_match_threshold", 0.88)
    if not best_template or best_score < threshold:
        set_json(cache_key, {"template_id": None, "score": best_score, "match_type": "none"}, 600)
        return None

    match_info = {
        "template_id": best_template["id"],
        "score": round(best_score, 4),
        "match_type": best_type,
        "matched_question": best_template["question"],
    }
    set_json(cache_key, match_info, settings.templates_cache_ttl_seconds)

    result = dict(best_template)
    result["match"] = match_info
    return result
