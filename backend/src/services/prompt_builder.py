from src.services.dataset_loader import get_schema_for_prompt, read_dataset_notes
from src.services.semantic_layer import enrich_question_with_semantics, semantic_layer_for_prompt

EXAMPLES = """
Примеры правильных SQL:

Пользователь: напиши мне 50 самых дорогих заказов
Ответ SQL: SELECT order_id, tender_id, city_id, status_order, order_timestamp, price_order_local FROM incity ORDER BY price_order_local DESC NULLS LAST LIMIT 50;

Пользователь: Самая высокая цена поездки за 2025 год
Ответ SQL: SELECT MAX(price_order_local) AS max_price_order_local FROM incity WHERE order_timestamp >= TIMESTAMP '2025-01-01' AND order_timestamp < TIMESTAMP '2026-01-01';

Пользователь: Сколько заказов было за январь 2026
Ответ SQL: SELECT COUNT(DISTINCT order_id) AS orders_count FROM incity WHERE order_timestamp >= TIMESTAMP '2026-01-01' AND order_timestamp < TIMESTAMP '2026-02-01';

Пользователь: Топ 10 водителей по заказам
Ответ SQL: SELECT driver_id, COUNT(DISTINCT order_id) AS orders_count FROM incity WHERE driver_id IS NOT NULL GROUP BY driver_id ORDER BY orders_count DESC LIMIT 10;

Пользователь: Топ 10 водителей по завершённым поездкам за день
Ответ SQL: SELECT driver_id, SUM(rides_count) AS rides_count FROM driver_detail GROUP BY driver_id ORDER BY rides_count DESC LIMIT 10;

Пользователь: Активность пассажиров по дням
Ответ SQL: SELECT order_date_part, SUM(orders_count) AS orders_count, SUM(rides_count) AS rides_count FROM pass_detail GROUP BY order_date_part ORDER BY order_date_part LIMIT 100;
""".strip()


def build_sql_prompt(question: str, max_rows: int, validation_feedback: str | None = None) -> str:
    notes = read_dataset_notes()
    feedback_block = ""
    if validation_feedback:
        feedback_block = f"""

Предыдущий SQL не прошёл проверку PostgreSQL.
Исправь запрос, учитывая эту ошибку:
{validation_feedback}
""".rstrip()

    semantic_context = semantic_layer_for_prompt()
    enriched_question = enrich_question_with_semantics(question)

    return f"""
Ты backend-модуль NL2SQL для PostgreSQL.
Твоя задача: превратить вопрос пользователя в один безопасный SQL SELECT к датасетам Drivee.

Верни только JSON без markdown и без пояснений вокруг.
JSON формат: {{"sql":"...", "confidence":0.0, "notes":"..."}}

Доступные таблицы:
1. incity — детальные заказы и тендеры. Основная таблица для вопросов про заказы, отмены, цены, тендеры, поездки.
2. pass_detail — дневные агрегаты пассажиров. Используй для вопросов про активность пассажиров по дням/пользователям.
3. driver_detail — дневные агрегаты водителей. Используй для вопросов про активность водителей по дням/водителям.

Строгие правила:
1. SQL должен быть только SELECT или WITH ... SELECT.
2. Используй только таблицы incity, pass_detail, driver_detail.
3. Используй только реальные колонки из схемы ниже.
4. Не используй таблицу train: старый датасет больше не используется.
5. В таблицах нет колонки id. Для заказа используй order_id, для тендера tender_id, для пассажира user_id, для водителя driver_id.
6. Для бизнес-подсчёта заказов в incity обычно используй COUNT(DISTINCT order_id), потому что одна строка = комбинация order_id и tender_id.
7. Если пользователь просит топ/рейтинг водителей из incity, добавляй driver_id IS NOT NULL.
8. Для вопросов про завершённые поездки/выручку/средний чек обычно фильтруй status_order = 'done'.
9. Для периода по заказам используй incity.order_timestamp; по пассажирам pass_detail.order_date_part; по водителям driver_detail.tender_date_part.
10. Разрешены простые JOIN только по связям: incity.user_id = pass_detail.user_id и incity.driver_id = driver_detail.driver_id; при дневном сопоставлении добавляй DATE(incity.order_timestamp) = pass_detail.order_date_part или DATE(incity.tender_timestamp) = driver_detail.tender_date_part.
11. Нельзя INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, COPY, GRANT, REVOKE, VACUUM, CALL, DO.
12. Не используй SELECT *.
13. Если вопрос просит список строк — добавь LIMIT {max_rows}.
14. Если пользователь просит N строк, LIMIT должен быть не больше {max_rows}.
15. Если нужен год, используй полуинтервал: >= TIMESTAMP 'YYYY-01-01' AND < TIMESTAMP 'YYYY+1-01-01'.
16. Ты не видишь строки CSV и не должен придумывать данные. Ты генерируешь только SQL по схеме, semantic layer и notes.md, а backend выполнит SQL в PostgreSQL.

Фактическая схема датасетов:
{get_schema_for_prompt()}

Активный семантический слой JSON:
{semantic_context or 'semantic_layer.json не найден'}

Справочник notes.md для понимания смысла датасетов:
{notes or 'notes.md не найден'}

{EXAMPLES}{feedback_block}

Вопрос пользователя и найденные семантические подсказки:
{enriched_question}
""".strip()
