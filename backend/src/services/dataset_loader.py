from pathlib import Path

from sqlalchemy import text

from src.core.config import settings
from src.db.session import engine

# train.csv now has a header row with this exact order.
# Important: there is no id column. Use order_id for orders and tender_id for tenders.
TRAIN_COLUMNS = [
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

TRAIN_COLUMN_TYPES = {
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

TRAIN_COLUMN_DESCRIPTIONS = {
    "city_id": "идентификатор города",
    "order_id": "анонимизированный идентификатор заказа; используй вместо id заказа",
    "tender_id": "анонимизированный идентификатор тендера/подбора водителя",
    "user_id": "анонимизированный идентификатор пользователя",
    "driver_id": "анонимизированный идентификатор водителя",
    "offset_hours": "смещение локального времени города относительно UTC в часах",
    "status_order": "итоговый статус заказа",
    "status_tender": "статус тендера или процесса подбора водителя",
    "order_timestamp": "время создания заказа",
    "tender_timestamp": "время создания или начала тендера",
    "driveraccept_timestamp": "время принятия заказа водителем",
    "driverarrived_timestamp": "время прибытия водителя",
    "driverstarttheride_timestamp": "время начала поездки",
    "driverdone_timestamp": "время завершения поездки",
    "clientcancel_timestamp": "время отмены заказа клиентом",
    "drivercancel_timestamp": "время отмены заказа водителем",
    "order_modified_local": "время последнего изменения заказа",
    "cancel_before_accept_local": "время отмены до принятия заказа, если такое событие было",
    "distance_in_meters": "расстояние поездки в метрах",
    "duration_in_seconds": "длительность поездки или заказа в секундах",
    "price_order_local": "итоговая стоимость заказа в локальной валюте",
    "price_tender_local": "стоимость на этапе тендера в локальной валюте",
    "price_start_local": "стартовая стоимость заказа в локальной валюте",
}

CREATE_TRAIN_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS train (
    city_id INTEGER,
    order_id TEXT,
    tender_id TEXT,
    user_id TEXT,
    driver_id TEXT,
    offset_hours INTEGER,
    status_order TEXT,
    status_tender TEXT,
    order_timestamp TIMESTAMP,
    tender_timestamp TIMESTAMP,
    driveraccept_timestamp TIMESTAMP,
    driverarrived_timestamp TIMESTAMP,
    driverstarttheride_timestamp TIMESTAMP,
    driverdone_timestamp TIMESTAMP,
    clientcancel_timestamp TIMESTAMP,
    drivercancel_timestamp TIMESTAMP,
    order_modified_local TIMESTAMP,
    cancel_before_accept_local TIMESTAMP,
    distance_in_meters INTEGER,
    duration_in_seconds INTEGER,
    price_order_local NUMERIC(14, 2),
    price_tender_local NUMERIC(14, 2),
    price_start_local NUMERIC(14, 2)
);
"""

INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS ix_train_city_id ON train(city_id);",
    "CREATE INDEX IF NOT EXISTS ix_train_order_id ON train(order_id);",
    "CREATE INDEX IF NOT EXISTS ix_train_tender_id ON train(tender_id);",
    "CREATE INDEX IF NOT EXISTS ix_train_user_id ON train(user_id);",
    "CREATE INDEX IF NOT EXISTS ix_train_driver_id ON train(driver_id);",
    "CREATE INDEX IF NOT EXISTS ix_train_order_timestamp ON train(order_timestamp);",
    "CREATE INDEX IF NOT EXISTS ix_train_status_order ON train(status_order);",
    "CREATE INDEX IF NOT EXISTS ix_train_status_tender ON train(status_tender);",
    "CREATE INDEX IF NOT EXISTS ix_train_price_order_local ON train(price_order_local);",
]


def get_train_schema_for_prompt() -> str:
    lines = []
    for name in TRAIN_COLUMNS:
        col_type = TRAIN_COLUMN_TYPES[name]
        description = TRAIN_COLUMN_DESCRIPTIONS.get(name, "")
        lines.append(f"- {name} ({col_type}) — {description}")
    return "\n".join(lines)


def read_train_notes() -> str:
    path = Path(settings.train_notes_path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _existing_train_columns(conn) -> list[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'train'
            ORDER BY ordinal_position
            """
        )
    ).scalars().all()
    return [str(row) for row in rows]


def ensure_train_table() -> None:
    with engine.begin() as conn:
        existing_columns = _existing_train_columns(conn)
        if existing_columns and existing_columns != TRAIN_COLUMNS:
            # Dev/MVP behavior: if an earlier prototype created/imported train
            # with a wrong order of columns, rebuild it from the new train.csv.
            conn.execute(text("DROP TABLE IF EXISTS train CASCADE"))

        conn.execute(text(CREATE_TRAIN_TABLE_SQL))
        for sql in INDEX_SQL:
            conn.execute(text(sql))


def get_train_count() -> int:
    with engine.begin() as conn:
        return int(conn.execute(text("SELECT COUNT(*) FROM train")).scalar_one())


def import_train_csv_if_needed() -> None:
    ensure_train_table()

    if not settings.import_train_on_startup:
        return

    if get_train_count() > 0:
        return

    csv_path = Path(settings.train_csv_path)
    if not csv_path.exists():
        return

    columns = ", ".join(TRAIN_COLUMNS)
    copy_sql = f"""
        COPY train ({columns})
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
