from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from src.core.config import settings
from src.db.session import engine


@dataclass(frozen=True)
class DatasetSpec:
    table: str
    csv_path_setting: str
    fallback_paths: tuple[str, ...]
    columns: list[str]
    column_types: dict[str, str]
    descriptions: dict[str, str]
    indexes: list[str]


INCITY_COLUMNS = [
    "city_id",
    "order_id",
    "tender_id",
    "user_id",
    "driver_id",
    "offset_hours",
    "status_order",
    "status_tender",
    "order_timestamp",
    "tender_timestamp",
    "driveraccept_timestamp",
    "driverarrived_timestamp",
    "driverstarttheride_timestamp",
    "driverdone_timestamp",
    "clientcancel_timestamp",
    "drivercancel_timestamp",
    "order_modified_local",
    "cancel_before_accept_local",
    "distance_in_meters",
    "duration_in_seconds",
    "price_order_local",
    "price_tender_local",
    "price_start_local",
]

INCITY_TYPES = {
    "city_id": "INTEGER",
    "order_id": "TEXT",
    "tender_id": "TEXT",
    "user_id": "TEXT",
    "driver_id": "TEXT",
    "offset_hours": "INTEGER",
    "status_order": "TEXT",
    "status_tender": "TEXT",
    "order_timestamp": "TIMESTAMP",
    "tender_timestamp": "TIMESTAMP",
    "driveraccept_timestamp": "TIMESTAMP",
    "driverarrived_timestamp": "TIMESTAMP",
    "driverstarttheride_timestamp": "TIMESTAMP",
    "driverdone_timestamp": "TIMESTAMP",
    "clientcancel_timestamp": "TIMESTAMP",
    "drivercancel_timestamp": "TIMESTAMP",
    "order_modified_local": "TIMESTAMP",
    "cancel_before_accept_local": "TIMESTAMP",
    "distance_in_meters": "INTEGER",
    "duration_in_seconds": "INTEGER",
    "price_order_local": "NUMERIC(14, 2)",
    "price_tender_local": "NUMERIC(14, 2)",
    "price_start_local": "NUMERIC(14, 2)",
}

INCITY_DESCRIPTIONS = {
    "city_id": "идентификатор города",
    "order_id": "идентификатор заказа; использовать вместо id заказа",
    "tender_id": "идентификатор тендера; может быть NULL, если заказ без конкретного тендера",
    "user_id": "идентификатор пассажира/пользователя",
    "driver_id": "идентификатор водителя; NULL означает, что водитель не назначен",
    "offset_hours": "смещение локального времени города относительно UTC в часах",
    "status_order": "итоговый статус заказа",
    "status_tender": "статус тендера или процесса подбора водителя",
    "order_timestamp": "время создания заказа; основное поле дат для заказов",
    "tender_timestamp": "время создания или начала тендера",
    "driveraccept_timestamp": "время принятия заказа водителем",
    "driverarrived_timestamp": "время прибытия водителя к пассажиру",
    "driverstarttheride_timestamp": "время начала поездки",
    "driverdone_timestamp": "время завершения поездки водителем",
    "clientcancel_timestamp": "время отмены заказа пассажиром",
    "drivercancel_timestamp": "время отмены заказа водителем",
    "order_modified_local": "время последнего изменения заказа в локальном времени",
    "cancel_before_accept_local": "время отмены заказа до принятия тендера",
    "distance_in_meters": "расчётное расстояние поездки в метрах",
    "duration_in_seconds": "расчётная длительность поездки или заказа в секундах",
    "price_order_local": "итоговая стоимость заказа в локальной валюте",
    "price_tender_local": "стоимость на этапе тендера в локальной валюте",
    "price_start_local": "стартовая стоимость заказа в локальной валюте",
}

PASS_DETAIL_COLUMNS = [
    "city_id",
    "user_id",
    "order_date_part",
    "user_reg_date",
    "orders_count",
    "orders_cnt_with_tenders",
    "orders_cnt_accepted",
    "rides_count",
    "rides_time_sum_seconds",
    "online_time_sum_seconds",
    "client_cancel_after_accept",
]

PASS_DETAIL_TYPES = {
    "city_id": "INTEGER",
    "user_id": "TEXT",
    "order_date_part": "DATE",
    "user_reg_date": "DATE",
    "orders_count": "INTEGER",
    "orders_cnt_with_tenders": "INTEGER",
    "orders_cnt_accepted": "INTEGER",
    "rides_count": "INTEGER",
    "rides_time_sum_seconds": "NUMERIC(14, 2)",
    "online_time_sum_seconds": "NUMERIC(14, 2)",
    "client_cancel_after_accept": "INTEGER",
}

PASS_DETAIL_DESCRIPTIONS = {
    "city_id": "идентификатор города",
    "user_id": "идентификатор пассажира",
    "order_date_part": "локальная дата дневных метрик пассажира",
    "user_reg_date": "дата регистрации пассажира",
    "orders_count": "количество уникальных заказов пассажира за день",
    "orders_cnt_with_tenders": "количество заказов пассажира с тендерами",
    "orders_cnt_accepted": "количество заказов пассажира, принятых водителями",
    "rides_count": "количество завершённых поездок пассажира",
    "rides_time_sum_seconds": "суммарная длительность поездок пассажира за день в секундах",
    "online_time_sum_seconds": "суммарное время онлайн пассажира в секундах",
    "client_cancel_after_accept": "количество отмен пассажиром после принятия заказа водителем",
}

DRIVER_DETAIL_COLUMNS = [
    "city_id",
    "driver_id",
    "tender_date_part",
    "driver_reg_date",
    "orders",
    "orders_cnt_with_tenders",
    "orders_cnt_accepted",
    "rides_count",
    "rides_time_sum_seconds",
    "online_time_sum_seconds",
    "client_cancel_after_accept",
]

DRIVER_DETAIL_TYPES = {
    "city_id": "INTEGER",
    "driver_id": "TEXT",
    "tender_date_part": "DATE",
    "driver_reg_date": "DATE",
    "orders": "INTEGER",
    "orders_cnt_with_tenders": "INTEGER",
    "orders_cnt_accepted": "INTEGER",
    "rides_count": "INTEGER",
    "rides_time_sum_seconds": "NUMERIC(14, 2)",
    "online_time_sum_seconds": "NUMERIC(14, 2)",
    "client_cancel_after_accept": "INTEGER",
}

DRIVER_DETAIL_DESCRIPTIONS = {
    "city_id": "идентификатор города",
    "driver_id": "идентификатор водителя",
    "tender_date_part": "локальная дата дневных метрик водителя",
    "driver_reg_date": "дата регистрации водителя",
    "orders": "количество заказов, связанных с водителем за день",
    "orders_cnt_with_tenders": "количество заказов с тендерами",
    "orders_cnt_accepted": "количество принятых заказов",
    "rides_count": "количество завершённых поездок водителя",
    "rides_time_sum_seconds": "суммарная длительность поездок водителя за день в секундах",
    "online_time_sum_seconds": "суммарное время водителя онлайн за день в секундах",
    "client_cancel_after_accept": "количество отмен пассажиром после принятия заказа водителем",
}

DATASETS: dict[str, DatasetSpec] = {
    "incity": DatasetSpec(
        table="incity",
        csv_path_setting="incity_csv_path",
        fallback_paths=("/data/incity2.csv", "/data/train.csv"),
        columns=INCITY_COLUMNS,
        column_types=INCITY_TYPES,
        descriptions=INCITY_DESCRIPTIONS,
        indexes=[
            "CREATE INDEX IF NOT EXISTS ix_incity_city_id ON incity(city_id);",
            "CREATE INDEX IF NOT EXISTS ix_incity_order_id ON incity(order_id);",
            "CREATE INDEX IF NOT EXISTS ix_incity_tender_id ON incity(tender_id);",
            "CREATE INDEX IF NOT EXISTS ix_incity_user_id ON incity(user_id);",
            "CREATE INDEX IF NOT EXISTS ix_incity_driver_id ON incity(driver_id);",
            "CREATE INDEX IF NOT EXISTS ix_incity_order_timestamp ON incity(order_timestamp);",
            "CREATE INDEX IF NOT EXISTS ix_incity_tender_timestamp ON incity(tender_timestamp);",
            "CREATE INDEX IF NOT EXISTS ix_incity_status_order ON incity(status_order);",
            "CREATE INDEX IF NOT EXISTS ix_incity_status_tender ON incity(status_tender);",
            "CREATE INDEX IF NOT EXISTS ix_incity_price_order_local ON incity(price_order_local);",
        ],
    ),
    "pass_detail": DatasetSpec(
        table="pass_detail",
        csv_path_setting="pass_detail_csv_path",
        fallback_paths=(),
        columns=PASS_DETAIL_COLUMNS,
        column_types=PASS_DETAIL_TYPES,
        descriptions=PASS_DETAIL_DESCRIPTIONS,
        indexes=[
            "CREATE INDEX IF NOT EXISTS ix_pass_detail_city_id ON pass_detail(city_id);",
            "CREATE INDEX IF NOT EXISTS ix_pass_detail_user_id ON pass_detail(user_id);",
            "CREATE INDEX IF NOT EXISTS ix_pass_detail_order_date_part ON pass_detail(order_date_part);",
        ],
    ),
    "driver_detail": DatasetSpec(
        table="driver_detail",
        csv_path_setting="driver_detail_csv_path",
        fallback_paths=(),
        columns=DRIVER_DETAIL_COLUMNS,
        column_types=DRIVER_DETAIL_TYPES,
        descriptions=DRIVER_DETAIL_DESCRIPTIONS,
        indexes=[
            "CREATE INDEX IF NOT EXISTS ix_driver_detail_city_id ON driver_detail(city_id);",
            "CREATE INDEX IF NOT EXISTS ix_driver_detail_driver_id ON driver_detail(driver_id);",
            "CREATE INDEX IF NOT EXISTS ix_driver_detail_tender_date_part ON driver_detail(tender_date_part);",
        ],
    ),
}

# Backward-compatible aliases for old imports in API/explainability code.
TRAIN_COLUMNS = INCITY_COLUMNS
TRAIN_COLUMN_TYPES = INCITY_TYPES
TRAIN_COLUMN_DESCRIPTIONS = INCITY_DESCRIPTIONS


def _create_table_sql(spec: DatasetSpec) -> str:
    cols = ",\n    ".join(f"{name} {spec.column_types[name]}" for name in spec.columns)
    return f"CREATE TABLE IF NOT EXISTS {spec.table} (\n    {cols}\n);"


def _existing_columns(conn, table_name: str) -> list[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table_name
            ORDER BY ordinal_position
            """
        ),
        {"table_name": table_name},
    ).scalars().all()
    return [str(row) for row in rows]


def _csv_path_for(spec: DatasetSpec) -> Path | None:
    primary = Path(str(getattr(settings, spec.csv_path_setting)))
    candidates = [primary] + [Path(path) for path in spec.fallback_paths]
    for path in candidates:
        if path.exists():
            return path
    return None


def ensure_dataset_table(spec: DatasetSpec) -> None:
    with engine.begin() as conn:
        existing_columns = _existing_columns(conn, spec.table)
        if existing_columns and existing_columns != spec.columns:
            conn.execute(text(f"DROP TABLE IF EXISTS {spec.table} CASCADE"))
        conn.execute(text(_create_table_sql(spec)))
        for sql in spec.indexes:
            conn.execute(text(sql))


def get_table_count(table_name: str) -> int:
    with engine.begin() as conn:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())


def import_dataset_csv_if_needed(spec: DatasetSpec) -> None:
    ensure_dataset_table(spec)
    if not settings.import_datasets_on_startup:
        return
    if get_table_count(spec.table) > 0:
        return
    csv_path = _csv_path_for(spec)
    if not csv_path:
        return

    columns = ", ".join(spec.columns)
    copy_sql = f"""
        COPY {spec.table} ({columns})
        FROM STDIN WITH (FORMAT csv, DELIMITER ',', HEADER true, NULL '')
    """
    raw_connection = engine.raw_connection()
    try:
        with raw_connection.cursor() as cursor:
            with csv_path.open("r", encoding="utf-8") as csv_file:
                cursor.copy_expert(copy_sql, csv_file)
        raw_connection.commit()
    except Exception:
        raw_connection.rollback()
        raise
    finally:
        raw_connection.close()


def import_all_datasets_if_needed() -> None:
    for spec in DATASETS.values():
        import_dataset_csv_if_needed(spec)


# Old entrypoint name kept for compatibility with older init_db.py imports.
def import_train_csv_if_needed() -> None:
    import_all_datasets_if_needed()


def read_dataset_notes() -> str:
    path = Path(settings.dataset_notes_path)
    if not path.exists():
        # Backward compatibility with older .env name.
        path = Path(getattr(settings, "train_notes_path", "/data/notes.md"))
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def read_train_notes() -> str:
    return read_dataset_notes()


def get_schema_for_prompt() -> str:
    blocks: list[str] = []
    for spec in DATASETS.values():
        lines = [f"Таблица {spec.table}:"]
        for name in spec.columns:
            lines.append(f"- {name} ({spec.column_types[name]}) — {spec.descriptions.get(name, '')}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def get_train_schema_for_prompt() -> str:
    # Backward-compatible name; now returns all active dataset tables.
    return get_schema_for_prompt()


def schema_payload() -> dict:
    tables = {}
    for spec in DATASETS.values():
        tables[spec.table] = {
            "columns": spec.columns,
            "column_types": spec.column_types,
            "column_descriptions": spec.descriptions,
        }
    return {
        "main_table": "incity",
        "tables": tables,
        "relations": [
            "incity.user_id = pass_detail.user_id",
            "incity.driver_id = driver_detail.driver_id",
            "DATE(incity.order_timestamp) = pass_detail.order_date_part для дневных метрик пассажира",
            "DATE(incity.tender_timestamp) = driver_detail.tender_date_part для дневных метрик водителя",
        ],
    }
