import re

from src.core.config import settings

# Numbers that a business user can naturally write in Russian questions.
_RU_UNITS = {
    "один": 1,
    "одна": 1,
    "одно": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
}
_RU_TEENS = {
    "десять": 10,
    "одиннадцать": 11,
    "двенадцать": 12,
    "тринадцать": 13,
    "четырнадцать": 14,
    "пятнадцать": 15,
    "шестнадцать": 16,
    "семнадцать": 17,
    "восемнадцать": 18,
    "девятнадцать": 19,
}
_RU_TENS = {
    "двадцать": 20,
    "тридцать": 30,
    "сорок": 40,
    "пятьдесят": 50,
    "шестьдесят": 60,
    "семьдесят": 70,
    "восемьдесят": 80,
    "девяносто": 90,
}
_RU_HUNDREDS = {
    "сто": 100,
    "двести": 200,
    "триста": 300,
    "четыреста": 400,
    "пятьсот": 500,
    "шестьсот": 600,
    "семьсот": 700,
    "восемьсот": 800,
    "девятьсот": 900,
}

_LIMIT_CONTEXT = r"(?:топ|top|top\s*-|первые|последние|лучшие|худшие|самые|выведи|покажи|дай|напиши|limit)"


def _clamp_limit(value: int | None) -> int | None:
    if value is None:
        return None
    if value < 1:
        return None
    return min(value, settings.sql_max_limit)


def _parse_ru_number(text: str) -> int | None:
    words = re.findall(r"[а-яё]+", text.lower())
    best: int | None = None
    for i, word in enumerate(words):
        if word in _RU_HUNDREDS:
            value = _RU_HUNDREDS[word]
            if i + 1 < len(words) and words[i + 1] in _RU_TENS:
                value += _RU_TENS[words[i + 1]]
                if i + 2 < len(words) and words[i + 2] in _RU_UNITS:
                    value += _RU_UNITS[words[i + 2]]
            elif i + 1 < len(words) and words[i + 1] in _RU_TEENS:
                value += _RU_TEENS[words[i + 1]]
            elif i + 1 < len(words) and words[i + 1] in _RU_UNITS:
                value += _RU_UNITS[words[i + 1]]
            best = value
            break
        if word in _RU_TENS:
            value = _RU_TENS[word]
            if i + 1 < len(words) and words[i + 1] in _RU_UNITS:
                value += _RU_UNITS[words[i + 1]]
            best = value
            break
        if word in _RU_TEENS:
            best = _RU_TEENS[word]
            break
    return _clamp_limit(best)


def extract_requested_limit(question: str) -> int | None:
    """Return an explicit row limit from a natural-language question.

    Examples:
    - "топ 66 водителей" -> 66
    - "top-10 cities" -> 10
    - "покажи 50 самых дорогих заказов" -> 50
    - "первые двадцать заказов" -> 20
    """
    q = question.lower().replace("ё", "е")

    patterns = [
        rf"\b(?:топ|top)\s*[-:]?\s*(\d{{1,4}})\b",
        rf"\b(?:первые|последние|лучшие|худшие)\s+(\d{{1,4}})\b",
        rf"\b(?:покажи|выведи|дай|напиши)\s+(\d{{1,4}})\s+(?:самых|самые|первых|последних|лучших|худших|строк|записей|водителей|заказов|городов|пользователей)\b",
        rf"\b(\d{{1,4}})\s+(?:самых|самые|первых|последних|лучших|худших|строк|записей|водителей|заказов|городов|пользователей)\b",
        rf"\blimit\s+(\d{{1,4}})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, q, flags=re.IGNORECASE)
        if match:
            return _clamp_limit(int(match.group(1)))

    # Word numbers are only interpreted when the question has an explicit list/ranking context.
    if re.search(_LIMIT_CONTEXT, q, flags=re.IGNORECASE):
        return _parse_ru_number(q)
    return None


def effective_ask_limit(question: str) -> int:
    """Limit used by /analytics/ask.

    The API no longer accepts max_rows. If the user asks for "top N", N wins;
    otherwise we use SQL_DEFAULT_LIMIT as a safe default cap.
    """
    return extract_requested_limit(question) or settings.sql_default_limit


def apply_question_limit_to_sql(sql: str, question: str) -> str:
    """For matched templates, let the user's explicit top-N override template LIMIT.

    Example: template has LIMIT 10, user asks "топ 66 водителей" -> LIMIT 66.
    This is only an upper display limit; guardrails still cap it by SQL_MAX_LIMIT.
    """
    requested_limit = extract_requested_limit(question)
    if requested_limit is None:
        return sql
    cleaned = sql.strip().rstrip(";")
    if re.search(r"\bLIMIT\s+\d+\s*$", cleaned, flags=re.IGNORECASE):
        return re.sub(r"\bLIMIT\s+\d+\s*$", f"LIMIT {requested_limit}", cleaned, flags=re.IGNORECASE)
    return f"{cleaned} LIMIT {requested_limit}"
