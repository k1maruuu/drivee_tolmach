import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.core.config import settings
from src.services.dataset_loader import TRAIN_COLUMN_DESCRIPTIONS, TRAIN_COLUMN_TYPES

DEFAULT_SEMANTIC_LAYER_PATH = Path(__file__).resolve().parents[1] / "semantic" / "semantic_layer.json"


def _path() -> Path:
    configured = getattr(settings, "semantic_layer_path", None)
    return Path(configured) if configured else DEFAULT_SEMANTIC_LAYER_PATH


@lru_cache(maxsize=1)
def load_semantic_layer() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {"table": "train", "columns": {}, "metrics": {}, "synonyms": {}, "sql_rules_ru": []}
    return json.loads(path.read_text(encoding="utf-8"))


def semantic_layer_for_prompt() -> str:
    layer = load_semantic_layer()
    lines: list[str] = []
    lines.append(f"Таблица: {layer.get('table', 'train')}")

    grain = layer.get("grain") or {}
    if grain.get("ru"):
        lines.append(f"Уровень строки: {grain['ru']}")

    rules = layer.get("sql_rules_ru") or []
    if rules:
        lines.append("\nБизнес-правила SQL:")
        for rule in rules:
            lines.append(f"- {rule}")

    metrics = layer.get("metrics") or {}
    if metrics:
        lines.append("\nКанонические метрики:")
        for key, metric in metrics.items():
            title = metric.get("title_ru", key)
            sql = metric.get("sql", "")
            terms = ", ".join(metric.get("terms", [])[:6])
            suffix = f"; термины: {terms}" if terms else ""
            lines.append(f"- {key}: {title} = {sql}{suffix}")

    synonyms = layer.get("synonyms") or {}
    if synonyms:
        lines.append("\nСинонимы бизнес-языка:")
        for term, meaning in synonyms.items():
            lines.append(f"- {term} -> {meaning}")

    return "\n".join(lines).strip()


def semantic_columns_for_schema() -> dict[str, Any]:
    layer = load_semantic_layer()
    columns = layer.get("columns") or {}
    result: dict[str, Any] = {}
    for name, item in columns.items():
        result[name] = {
            "type": item.get("type") or TRAIN_COLUMN_TYPES.get(name),
            "description_ru": item.get("description_ru") or TRAIN_COLUMN_DESCRIPTIONS.get(name),
            "business_terms": item.get("business_terms", []),
            "values": item.get("values", {}),
        }
    return result


def semantic_metrics_for_schema() -> dict[str, Any]:
    return load_semantic_layer().get("metrics", {})


def semantic_synonyms_for_schema() -> dict[str, str]:
    return load_semantic_layer().get("synonyms", {})


def _normalize_ru(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9_\s-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def enrich_question_with_semantics(question: str) -> str:
    """Append compact semantic hints for Ollama without changing user intent.

    This is intentionally deterministic and small: it does not execute SQL and
    does not replace templates. It only gives the LLM extra hints such as
    "отмены -> status_order = 'cancel'".
    """
    layer = load_semantic_layer()
    normalized = _normalize_ru(question)
    hints: list[str] = []

    synonyms = layer.get("synonyms") or {}
    for term, meaning in synonyms.items():
        term_norm = _normalize_ru(term)
        if term_norm and term_norm in normalized:
            hints.append(f"{term} -> {meaning}")

    metrics = layer.get("metrics") or {}
    for key, metric in metrics.items():
        for term in metric.get("terms", []):
            term_norm = _normalize_ru(term)
            if term_norm and term_norm in normalized:
                hints.append(f"метрика {key}: {metric.get('sql')} ({metric.get('title_ru', key)})")
                break

    # Deduplicate while preserving order.
    deduped = list(dict.fromkeys(hints))[:12]
    if not deduped:
        return question

    return question + "\n\nПодсказки семантического слоя для этого вопроса:\n- " + "\n- ".join(deduped)


def describe_columns_ru(columns: list[str]) -> list[str]:
    semantic_columns = semantic_columns_for_schema()
    descriptions = []
    for column in columns:
        item = semantic_columns.get(column) or {}
        desc = item.get("description_ru") or TRAIN_COLUMN_DESCRIPTIONS.get(column)
        if desc:
            descriptions.append(f"{column} — {desc}")
    return descriptions


def detect_metric_from_semantic(question: str, sql: str) -> str | None:
    layer = load_semantic_layer()
    normalized_question = _normalize_ru(question)
    normalized_sql = sql.lower()
    for key, metric in (layer.get("metrics") or {}).items():
        metric_sql = str(metric.get("sql", "")).lower()
        metric_title = metric.get("title_ru") or key
        terms = [_normalize_ru(term) for term in metric.get("terms", [])]
        term_match = any(term and term in normalized_question for term in terms)
        sql_match = bool(metric_sql and metric_sql.replace(" ", "") in normalized_sql.replace(" ", ""))
        if term_match or sql_match:
            return str(metric_title)
    return None
