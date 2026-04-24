import re
from typing import Any

from src.services.dataset_loader import TRAIN_COLUMNS


_STATUS_LABELS = {
    "done": "завершённые заказы/поездки",
    "cancel": "отменённые заказы",
    "delete": "удалённые заказы",
    "decline": "отклонения/отказы",
}


def _compact_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";"))


def _split_sql_expressions(text: str) -> list[str]:
    """Split a SQL expression list by commas while respecting parentheses and quotes."""
    items: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    i = 0

    while i < len(text):
        ch = text[i]
        if quote:
            current.append(ch)
            if ch == quote:
                # SQL escaped single quote: ''
                if quote == "'" and i + 1 < len(text) and text[i + 1] == "'":
                    i += 1
                    current.append(text[i])
                else:
                    quote = None
            i += 1
            continue

        if ch in {"'", '"'}:
            quote = ch
            current.append(ch)
        elif ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
        else:
            current.append(ch)
        i += 1

    item = "".join(current).strip()
    if item:
        items.append(item)
    return items


def _extract_section(sql: str, start_keyword: str, stop_keywords: list[str]) -> str | None:
    pattern = rf"\b{re.escape(start_keyword)}\b\s+(.*)"
    match = re.search(pattern, sql, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None

    value = match.group(1)
    stop_positions = []
    for keyword in stop_keywords:
        stop = re.search(rf"\b{re.escape(keyword)}\b", value, flags=re.IGNORECASE)
        if stop:
            stop_positions.append(stop.start())
    if stop_positions:
        value = value[: min(stop_positions)]
    return value.strip()


def _extract_selected_expressions(sql: str) -> list[str]:
    match = re.search(r"\bSELECT\b\s+(.*?)\s+\bFROM\b", sql, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    return _split_sql_expressions(match.group(1))


def _extract_group_by(sql: str) -> list[str]:
    section = _extract_section(sql, "GROUP BY", ["HAVING", "ORDER BY", "LIMIT", "OFFSET"])
    return _split_sql_expressions(section) if section else []


def _extract_order_by(sql: str) -> str | None:
    section = _extract_section(sql, "ORDER BY", ["LIMIT", "OFFSET"])
    return section or None


def _extract_limit(sql: str) -> int | None:
    match = re.search(r"\bLIMIT\s+(\d+)\b", sql, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _detect_used_columns(sql: str) -> list[str]:
    used = []
    for column in TRAIN_COLUMNS:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(column)}(?![A-Za-z0-9_])", sql, flags=re.IGNORECASE):
            used.append(column)
    return used


def _detect_metric(question: str, sql: str) -> str:
    q = question.lower().replace("ё", "е")
    s = sql.lower()

    if "order by price_order_local desc" in s or "сам" in q and "дорог" in q:
        return "Самые дорогие заказы по итоговой стоимости price_order_local"
    if "max(price_order_local" in s:
        return "Максимальная итоговая стоимость заказа"
    if "min(price_order_local" in s:
        return "Минимальная итоговая стоимость заказа"
    if "avg(price_order_local" in s:
        return "Средний чек по итоговой стоимости заказа"
    if "sum(price_order_local" in s:
        return "Общий оборот по итоговой стоимости заказа"
    if "avg(duration_in_seconds" in s:
        return "Средняя длительность поездки/заказа"
    if "avg(distance_in_meters" in s:
        return "Среднее расстояние поездки"
    if "count(distinct order_id" in s:
        if "status_order = 'done'" in s:
            return "Количество уникальных завершённых заказов"
        if "status_order = 'cancel'" in s:
            return "Количество уникальных отменённых заказов"
        return "Количество уникальных заказов"
    if "count(*)" in s and "status_tender = 'decline'" in s:
        return "Количество отклонений тендеров"
    if "count(*)" in s:
        return "Количество строк в таблице train"
    return "Выборка данных из таблицы train"


def _detect_date_filter(sql: str) -> str | None:
    s = _compact_sql(sql)
    timestamp_range = re.search(
        r"order_timestamp\s*>=\s*TIMESTAMP\s*'([^']+)'\s+AND\s+order_timestamp\s*<\s*TIMESTAMP\s*'([^']+)'",
        s,
        flags=re.IGNORECASE,
    )
    if timestamp_range:
        return f"order_timestamp от {timestamp_range.group(1)} включительно до {timestamp_range.group(2)} не включительно"

    simple_range = re.search(
        r"order_timestamp\s*>=\s*'([^']+)'\s+AND\s+order_timestamp\s*<\s*'([^']+)'",
        s,
        flags=re.IGNORECASE,
    )
    if simple_range:
        return f"order_timestamp от {simple_range.group(1)} включительно до {simple_range.group(2)} не включительно"

    if re.search(r"CURRENT_DATE\s*-\s*INTERVAL\s*'1\s+day'", s, flags=re.IGNORECASE):
        return "относительный период: вчера"
    if re.search(r"CURRENT_DATE\s*-\s*INTERVAL\s*'7\s+day", s, flags=re.IGNORECASE):
        return "относительный период: последние 7 дней"
    if re.search(r"CURRENT_DATE\s*-\s*INTERVAL\s*'30\s+day", s, flags=re.IGNORECASE):
        return "относительный период: последние 30 дней"
    if "date_trunc('month'" in s.lower():
        return "период по месяцу через DATE_TRUNC('month', CURRENT_DATE)"
    if "date_trunc('quarter'" in s.lower():
        return "период по кварталу через DATE_TRUNC('quarter', CURRENT_DATE)"
    if "date_trunc('year'" in s.lower():
        return "период по году через DATE_TRUNC('year', CURRENT_DATE)"
    if "order_timestamp" in s.lower() and "where" in s.lower():
        return "есть фильтр по order_timestamp"
    return None


def _detect_filters(sql: str) -> list[str]:
    s = _compact_sql(sql)
    filters: list[str] = []

    for column in ("status_order", "status_tender"):
        for value in re.findall(rf"{column}\s*=\s*'([^']+)'", s, flags=re.IGNORECASE):
            label = _STATUS_LABELS.get(value, value)
            filters.append(f"{column} = '{value}' ({label})")

    if re.search(r"driver_id\s+IS\s+NULL", s, flags=re.IGNORECASE):
        filters.append("driver_id IS NULL (без назначенного водителя)")
    if re.search(r"driver_id\s+IS\s+NOT\s+NULL", s, flags=re.IGNORECASE):
        filters.append("driver_id IS NOT NULL (есть назначенный водитель)")

    for column, label in [
        ("clientcancel_timestamp", "отмена клиентом"),
        ("drivercancel_timestamp", "отмена водителем"),
        ("cancel_before_accept_local", "отмена до принятия водителем"),
        ("driveraccept_timestamp", "принятие водителем"),
        ("driverarrived_timestamp", "прибытие водителя"),
        ("driverstarttheride_timestamp", "старт поездки"),
        ("driverdone_timestamp", "завершение поездки"),
    ]:
        if re.search(rf"{column}\s+IS\s+NOT\s+NULL", s, flags=re.IGNORECASE):
            filters.append(f"{column} IS NOT NULL ({label})")

    city_match = re.search(r"city_id\s*=\s*(:[a-zA-Z_][a-zA-Z0-9_]*|\d+|'[^']+')", s, flags=re.IGNORECASE)
    if city_match:
        filters.append(f"city_id = {city_match.group(1)}")

    return filters


def _detect_row_logic(sql: str) -> str:
    s = sql.lower()
    if "count(distinct order_id" in s:
        return "Считает уникальные заказы через COUNT(DISTINCT order_id), потому что одна строка может быть комбинацией order_id и tender_id."
    if "count(distinct tender_id" in s:
        return "Считает уникальные тендеры через COUNT(DISTINCT tender_id)."
    if "count(*)" in s:
        return "Считает строки таблицы train, то есть записи на уровне комбинации заказа и тендера."
    if "group by" in s:
        return "Группирует строки train и считает агрегированные показатели."
    return "Возвращает строки из train после фильтрации и сортировки."


def _build_explanation_ru(
    *,
    metric: str,
    date_filter: str | None,
    filters: list[str],
    group_by: list[str],
    order_by: str | None,
    limit: int | None,
    used_columns: list[str],
    source: str,
) -> list[str]:
    lines = [f"Метрика/смысл запроса: {metric}."]
    if date_filter:
        lines.append(f"Период: {date_filter}.")
    if filters:
        lines.append("Фильтры: " + "; ".join(filters) + ".")
    if group_by:
        lines.append("Группировка: " + ", ".join(group_by) + ".")
    if order_by:
        lines.append(f"Сортировка: {order_by}.")
    if limit:
        lines.append(f"Ограничение результата: LIMIT {limit}.")
    if used_columns:
        lines.append("Использованные колонки: " + ", ".join(used_columns) + ".")
    lines.append(
        "Источник SQL: готовый шаблон без вызова ИИ." if source.startswith("template") else "Источник SQL: генерация через LLM/Ollama после проверки шаблонов."
    )
    lines.append("Перед выполнением SQL прошёл guardrails и PostgreSQL EXPLAIN-проверку.")
    return lines


def build_query_interpretation(
    *,
    question: str,
    sql: str,
    source: str = "llm",
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_sql = _compact_sql(sql)
    selected_expressions = _extract_selected_expressions(normalized_sql)
    group_by = _extract_group_by(normalized_sql)
    order_by = _extract_order_by(normalized_sql)
    limit = _extract_limit(normalized_sql)
    used_columns = _detect_used_columns(normalized_sql)
    metric = _detect_metric(question, normalized_sql)
    date_filter = _detect_date_filter(normalized_sql)
    filters = _detect_filters(normalized_sql)
    row_logic = _detect_row_logic(normalized_sql)

    result_shape = None
    if result:
        columns = result.get("columns") or []
        row_count = result.get("row_count")
        if row_count == 1 and len(columns) == 1:
            result_shape = "single_metric"
        elif group_by:
            result_shape = "aggregated_table"
        else:
            result_shape = "table"

    return {
        "metric": metric,
        "date_filter": date_filter,
        "filters": filters,
        "group_by": group_by,
        "sort": order_by,
        "limit": limit,
        "used_columns": used_columns,
        "selected_expressions": selected_expressions,
        "row_logic": row_logic,
        "result_shape": result_shape,
        "explanation_ru": _build_explanation_ru(
            metric=metric,
            date_filter=date_filter,
            filters=filters,
            group_by=group_by,
            order_by=order_by,
            limit=limit,
            used_columns=used_columns,
            source=source,
        ),
    }
