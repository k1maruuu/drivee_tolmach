import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

_MONTHS_RU = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "ма": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}


def _iso(day: date) -> str:
    return day.isoformat()


def _parse_iso_date(value: str) -> date | None:
    try:
        parts = [int(part) for part in value.split("-")]
        if len(parts) != 3:
            return None
        return date(parts[0], parts[1], parts[2])
    except Exception:
        return None


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def _dataset_date_bounds(db: Session) -> tuple[date, date] | None:
    row = db.execute(
        text("SELECT MIN(order_timestamp)::date AS min_day, MAX(order_timestamp)::date AS max_day FROM incity")
    ).mappings().first()
    if not row or row["min_day"] is None or row["max_day"] is None:
        return None
    return row["min_day"], row["max_day"]


def _explicit_date_params(question: str) -> dict[str, Any]:
    q = question.lower().replace("ё", "е")

    # Range: с 2026-01-01 до 2026-01-31. End date is treated as inclusive in
    # natural language, so SQL receives exclusive date_to = next day.
    range_match = re.search(r"(?:с|от)\s+(\d{4}-\d{2}-\d{2})\s+(?:до|по)\s+(\d{4}-\d{2}-\d{2})", q)
    if range_match:
        start = _parse_iso_date(range_match.group(1))
        end = _parse_iso_date(range_match.group(2))
        if start and end:
            return {"date_from": _iso(start), "date_to": _iso(end + timedelta(days=1))}

    # Single ISO day: 2026-01-05.
    single_date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", q)
    if single_date_match:
        start = _parse_iso_date(single_date_match.group(1))
        if start:
            return {"date_from": _iso(start), "date_to": _iso(start + timedelta(days=1))}

    # Russian month + year: январь 2026, за январь 2026.
    for month_key, month_number in _MONTHS_RU.items():
        if month_key in q:
            year_match = re.search(r"\b(20\d{2})\b", q)
            if year_match:
                start, end = _month_bounds(int(year_match.group(1)), month_number)
                return {"date_from": _iso(start), "date_to": _iso(end)}

    # Year: за 2026 / в 2026 году.
    year_match = re.search(r"\b(20\d{2})\b", q)
    if year_match:
        year = int(year_match.group(1))
        return {"date_from": f"{year}-01-01", "date_to": f"{year + 1}-01-01"}

    today = date.today()
    if "вчера" in q:
        start = today - timedelta(days=1)
        return {"date_from": _iso(start), "date_to": _iso(today)}

    if "сегодня" in q:
        return {"date_from": _iso(today), "date_to": _iso(today + timedelta(days=1))}

    return {}



def _parse_city_id(question: str) -> int | None:
    q = question.lower().replace("ё", "е")
    patterns = [
        r"\bcity_id\s*[=:]?\s*(\d+)\b",
        r"\bгород(?:е|а|у|ом)?\s*[№#]?[=:]?\s*(\d+)\b",
        r"\bcity\s*[=:]?\s*(\d+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            return int(match.group(1))
    return None


def _default_city_id(db: Session) -> int | None:
    """Use the busiest available city as a safe demo default.

    Some template buttons are intentionally generic, for example
    "Сколько завершенных заказов было в конкретном городе?".
    If the frontend did not pass city_id yet, returning the busiest city lets
    the template run instead of failing with Bad Request, while the returned
    params clearly show which city_id was used.
    """
    row = db.execute(
        text(
            """
            SELECT city_id
            FROM incity
            WHERE city_id IS NOT NULL
            GROUP BY city_id
            ORDER BY COUNT(DISTINCT order_id) DESC
            LIMIT 1
            """
        )
    ).scalar()
    return int(row) if row is not None else None


def resolve_template_params(
    db: Session,
    *,
    question: str,
    required_params: list[str] | set[str],
    provided_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge user params, dates extracted from question, and safe defaults.

    This prevents frontend template buttons from failing with Bad Request just
    because a template contains :date_from/:date_to. Priority:
    1. explicit params from frontend;
    2. dates found in the user's question;
    3. dataset-aware defaults for generic demo templates.
    """
    required = set(required_params)
    params: dict[str, Any] = dict(provided_params or {})

    if "city_id" in required and "city_id" not in params:
        parsed_city_id = _parse_city_id(question)
        if parsed_city_id is not None:
            params["city_id"] = parsed_city_id
        else:
            default_city_id = _default_city_id(db)
            if default_city_id is not None:
                params["city_id"] = default_city_id

    if not {"date_from", "date_to"}.issubset(required):
        return params

    extracted = _explicit_date_params(question)
    for key, value in extracted.items():
        params.setdefault(key, value)

    if "date_from" in params and "date_to" in params:
        return params

    q = question.lower().replace("ё", "е")
    bounds = _dataset_date_bounds(db)
    if not bounds:
        return params

    min_day, max_day = bounds

    # Generic "за день" template button: use the latest available dataset day,
    # not the real current day, so demo data does not return empty results.
    if "день" in q:
        params.setdefault("date_from", _iso(max_day))
        params.setdefault("date_to", _iso(max_day + timedelta(days=1)))
        return params

    # Generic "за период" template button: use the whole available dataset
    # period if frontend did not pass a specific range.
    if "период" in q:
        params.setdefault("date_from", _iso(min_day))
        params.setdefault("date_to", _iso(max_day + timedelta(days=1)))
        return params

    return params
