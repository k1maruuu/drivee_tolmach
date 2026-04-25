from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.schemas.analytics import QueryInterpretation, QueryVisualization

_TIME_COLUMN_NAMES = {
    "date",
    "day",
    "week",
    "month",
    "year",
    "hour",
    "order_date",
    "order_day",
    "order_week",
    "order_month",
}

_ID_COLUMN_NAMES = {
    "order_id",
    "tender_id",
    "user_id",
    "driver_id",
    "route_id",
}

_CATEGORICAL_COLUMN_NAMES = {
    "city_id",
    "status_order",
    "status_tender",
    "tariff_id",
    "hour",
}

_METRIC_NAME_MARKERS = (
    "count",
    "total",
    "sum",
    "avg",
    "average",
    "mean",
    "min",
    "max",
    "rate",
    "percent",
    "revenue",
    "price",
    "distance",
    "duration",
    "orders",
    "tenders",
    "minutes",
    "seconds",
    "km",
)


def _rows(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not result:
        return []
    rows = result.get("rows") or []
    return rows if isinstance(rows, list) else []


def _columns(result: dict[str, Any] | None) -> list[str]:
    if not result:
        return []
    columns = result.get("columns") or []
    return [str(column) for column in columns]


def _is_number(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float, Decimal)):
        return True
    if isinstance(value, str):
        stripped = value.strip().replace(",", ".")
        if not stripped:
            return False
        try:
            float(stripped)
            return True
        except ValueError:
            return False
    return False


def _looks_like_date(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (datetime, date)):
        return True
    if not isinstance(value, str):
        return False
    text = value.strip()
    if len(text) < 7:
        return False
    # Fast checks for common SQL date/timestamp string formats.
    if len(text) >= 10:
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
            return True
        except ValueError:
            pass
        try:
            datetime.strptime(text[:10], "%Y-%m-%d")
            return True
        except ValueError:
            pass
    if len(text) >= 7:
        try:
            datetime.strptime(text[:7], "%Y-%m")
            return True
        except ValueError:
            pass
    return False


def _non_null_values(rows: list[dict[str, Any]], column: str, limit: int = 20) -> list[Any]:
    values = []
    for row in rows:
        value = row.get(column)
        if value is not None:
            values.append(value)
        if len(values) >= limit:
            break
    return values


def _is_numeric_column(rows: list[dict[str, Any]], column: str) -> bool:
    if column in _ID_COLUMN_NAMES:
        return False
    values = _non_null_values(rows, column)
    if not values:
        return any(marker in column.lower() for marker in _METRIC_NAME_MARKERS)
    numeric_count = sum(1 for value in values if _is_number(value))
    return numeric_count / max(len(values), 1) >= 0.8 or any(marker in column.lower() for marker in _METRIC_NAME_MARKERS)


def _is_time_column(rows: list[dict[str, Any]], column: str) -> bool:
    lowered = column.lower()
    if lowered in _TIME_COLUMN_NAMES or lowered.endswith("_date") or lowered.endswith("_day"):
        return True
    if "date_trunc" in lowered or "timestamp" in lowered:
        return True
    values = _non_null_values(rows, column)
    if not values:
        return False
    date_count = sum(1 for value in values if _looks_like_date(value))
    return date_count / max(len(values), 1) >= 0.8


def _is_categorical_column(rows: list[dict[str, Any]], column: str) -> bool:
    if column.lower() in _CATEGORICAL_COLUMN_NAMES:
        return True
    if column in _ID_COLUMN_NAMES:
        return True
    if _is_numeric_column(rows, column) or _is_time_column(rows, column):
        return False
    values = _non_null_values(rows, column, limit=50)
    unique_count = len({str(value) for value in values})
    return unique_count <= max(20, int(len(values) * 0.9))


def _pick_title(question: str, chart_type: str, x_axis: str | None, y_axis: str | None) -> str:
    cleaned_question = question.strip().rstrip("?.!")
    if cleaned_question:
        return cleaned_question[:120]
    if chart_type == "metric":
        return y_axis or "Ключевой показатель"
    if x_axis and y_axis:
        return f"{y_axis} по {x_axis}"
    return "Результат запроса"


def build_visualization_config(
    *,
    question: str,
    sql: str,
    result: dict[str, Any],
    interpretation: QueryInterpretation | dict[str, Any] | None = None,
) -> QueryVisualization:
    """
    Build a frontend-friendly chart recommendation.

    Backend does not render charts. It only tells the frontend which view is safer
    and more useful: metric card, table, bar chart, or line chart.
    """
    columns = _columns(result)
    rows = _rows(result)
    row_count = int(result.get("row_count", len(rows)) or 0) if result else 0

    if not columns:
        return QueryVisualization(
            recommended=False,
            type="table",
            title="Нет данных для визуализации",
            reason_ru="SQL выполнился, но результат не содержит колонок.",
            frontend_config={"component": "DataTable"},
        )

    if row_count == 0:
        return QueryVisualization(
            recommended=False,
            type="table",
            title="Нет строк в результате",
            reason_ru="Запрос вернул 0 строк, поэтому лучше показать пустую таблицу с колонками.",
            frontend_config={"component": "DataTable", "columns": columns},
        )

    numeric_columns = [column for column in columns if _is_numeric_column(rows, column)]
    time_columns = [column for column in columns if _is_time_column(rows, column)]
    categorical_columns = [column for column in columns if _is_categorical_column(rows, column)]

    # One-row aggregate: best shown as a KPI card, optionally with extra fields.
    if row_count == 1 and numeric_columns:
        value_column = numeric_columns[0]
        return QueryVisualization(
            recommended=True,
            type="metric",
            title=_pick_title(question, "metric", None, value_column),
            x_axis=None,
            y_axis=value_column,
            value_column=value_column,
            series=[value_column],
            reason_ru="Результат состоит из одной строки и числового показателя — лучше показать KPI-карточку.",
            frontend_config={
                "component": "MetricCard",
                "value_key": value_column,
                "secondary_keys": [column for column in columns if column != value_column],
            },
        )

    # Time series: line chart.
    if time_columns and numeric_columns:
        x_axis = time_columns[0]
        y_columns = [column for column in numeric_columns if column != x_axis] or numeric_columns[:1]
        return QueryVisualization(
            recommended=True,
            type="line",
            title=_pick_title(question, "line", x_axis, y_columns[0]),
            x_axis=x_axis,
            y_axis=y_columns[0],
            series=y_columns[:3],
            reason_ru="Есть временная колонка и числовые показатели — лучше показать линейный график динамики.",
            frontend_config={
                "component": "LineChart",
                "x_key": x_axis,
                "y_keys": y_columns[:3],
                "data_key": "rows",
            },
        )

    # Category + metric: bar chart.
    if categorical_columns and numeric_columns:
        x_axis = next((column for column in categorical_columns if column not in _ID_COLUMN_NAMES), categorical_columns[0])
        y_columns = [column for column in numeric_columns if column != x_axis] or numeric_columns[:1]
        return QueryVisualization(
            recommended=True,
            type="bar",
            title=_pick_title(question, "bar", x_axis, y_columns[0]),
            x_axis=x_axis,
            y_axis=y_columns[0],
            series=y_columns[:3],
            reason_ru="Есть категориальная колонка и числовой показатель — лучше показать столбчатую диаграмму.",
            frontend_config={
                "component": "BarChart",
                "x_key": x_axis,
                "y_keys": y_columns[:3],
                "data_key": "rows",
            },
        )

    # Several numeric values over many rows without a clear dimension are still safer as table.
    if len(columns) <= 3 and numeric_columns:
        value_column = numeric_columns[0]
        label_column = next((column for column in columns if column != value_column), None)
        return QueryVisualization(
            recommended=True,
            type="bar" if label_column else "metric",
            title=_pick_title(question, "bar", label_column, value_column),
            x_axis=label_column,
            y_axis=value_column,
            label_column=label_column,
            value_column=value_column,
            series=[value_column],
            reason_ru="Результат компактный и содержит числовой показатель — его можно визуализировать.",
            frontend_config={
                "component": "BarChart" if label_column else "MetricCard",
                "x_key": label_column,
                "y_keys": [value_column],
                "data_key": "rows",
            },
        )

    return QueryVisualization(
        recommended=False,
        type="table",
        title=_pick_title(question, "table", None, None),
        reason_ru="Нет очевидной пары измерение + числовая метрика, поэтому безопаснее показать таблицу.",
        frontend_config={"component": "DataTable", "columns": columns, "data_key": "rows"},
    )
