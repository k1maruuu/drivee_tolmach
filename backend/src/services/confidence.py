from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfidenceResult:
    value: float
    reason: str


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return number


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 2)


def build_confidence(
    *,
    source: str,
    template_match_score: float | None = None,
    llm_confidence: Any = None,
    validation_is_valid: bool = True,
    has_warnings: bool = False,
    row_count: int | None = None,
    repaired: bool = False,
    cache_hit: bool = False,
) -> ConfidenceResult:
    """Backend-owned confidence score.

    This is separate from the LLM's self-reported confidence because the backend
    knows whether a template was used, whether SQL passed PostgreSQL EXPLAIN,
    whether the SQL had to be repaired, and whether data was returned.
    """
    reasons: list[str] = []

    if source in {"template", "template_cache"}:
        score = template_match_score if template_match_score is not None else 1.0
        score = _clamp(score)
        if cache_hit:
            reasons.append("результат взят из Redis cache")
        if score >= 1.0:
            reasons.append("вопрос совпал с готовым SQL-шаблоном")
        else:
            reasons.append(f"найден похожий SQL-шаблон, score={score}")
        reasons.append("SQL шаблона прошёл guardrails и PostgreSQL EXPLAIN")
        return ConfidenceResult(score, "; ".join(reasons))

    if source == "clarification":
        return ConfidenceResult(
            0.25,
            "запрос неоднозначный, backend не стал угадывать SQL и попросил уточнение",
        )

    # LLM-generated query.
    model_score = _to_float(llm_confidence)
    score = model_score if model_score is not None else 0.65
    reasons.append(
        f"оценка модели={score}" if model_score is not None else "модель не вернула confidence, базовая оценка=0.65"
    )

    if validation_is_valid:
        score += 0.15
        reasons.append("SQL прошёл guardrails и PostgreSQL EXPLAIN")
    else:
        score = min(score, 0.25)
        reasons.append("SQL не прошёл проверку")

    if repaired:
        score -= 0.1
        reasons.append("SQL был исправлен после первой неудачной проверки")

    if has_warnings:
        score -= 0.05
        reasons.append("есть предупреждения guardrails")

    if row_count == 0:
        score -= 0.05
        reasons.append("результат пустой, возможно фильтр слишком строгий")
    elif row_count is not None:
        reasons.append(f"вернулось строк: {row_count}")

    return ConfidenceResult(_clamp(score), "; ".join(reasons))
