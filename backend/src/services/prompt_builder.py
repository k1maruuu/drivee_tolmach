from src.services.dataset_loader import get_train_schema_for_prompt, read_train_notes
from src.services.semantic_layer import enrich_question_with_semantics, semantic_layer_for_prompt

EXAMPLES = """
Примеры правильных SQL:

Пользователь: напиши мне 50 самых дорогих заказов
Ответ SQL: SELECT order_id, tender_id, city_id, status_order, order_timestamp, price_order_local FROM train ORDER BY price_order_local DESC NULLS LAST LIMIT 50;

Пользователь: Самая высокая цена поездки за 2025 год
Ответ SQL: SELECT MAX(price_order_local) AS max_price_order_local FROM train WHERE order_timestamp >= TIMESTAMP '2025-01-01' AND order_timestamp < TIMESTAMP '2026-01-01';

Пользователь: Сколько заказов было за январь 2026
Ответ SQL: SELECT COUNT(DISTINCT order_id) AS orders_count FROM train WHERE order_timestamp >= TIMESTAMP '2026-01-01' AND order_timestamp < TIMESTAMP '2026-02-01';

Пользователь: Покажи поездки и отмены по городам за вчера
Ответ SQL: SELECT city_id, COUNT(DISTINCT order_id) FILTER (WHERE status_order = 'done') AS done_orders, COUNT(DISTINCT order_id) FILTER (WHERE status_order = 'cancel') AS cancelled_orders FROM train WHERE order_timestamp >= CURRENT_DATE - INTERVAL '1 day' AND order_timestamp < CURRENT_DATE GROUP BY city_id ORDER BY done_orders DESC LIMIT 100;

Пользователь: Топ 10 водителей по заказам
Ответ SQL: SELECT driver_id, COUNT(DISTINCT order_id) AS orders_count FROM train WHERE driver_id IS NOT NULL GROUP BY driver_id ORDER BY orders_count DESC LIMIT 10;

Пользователь: Кто из водителей выполнил больше всего заказов?
Ответ SQL: SELECT driver_id, COUNT(DISTINCT order_id) AS done_orders FROM train WHERE driver_id IS NOT NULL AND status_order = 'done' GROUP BY driver_id ORDER BY done_orders DESC LIMIT 10;
""".strip()


def build_sql_prompt(question: str, max_rows: int, validation_feedback: str | None = None) -> str:
    notes = read_train_notes()
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
Твоя задача: превратить вопрос пользователя в один безопасный SQL SELECT к таблице train.

Верни только JSON без markdown и без пояснений вокруг.
JSON формат: {{"sql":"...", "confidence":0.0, "notes":"..."}}

Строгие правила:
1. SQL должен быть только SELECT или WITH ... SELECT.
2. Используй только таблицу train.
3. Используй только реальные колонки из списка ниже.
4. В таблице train НЕТ колонки id. Никогда не используй id.
5. Для идентификатора заказа используй order_id.
6. Для идентификатора тендера используй tender_id.
7. Нельзя INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, COPY, GRANT, REVOKE, VACUUM, CALL, DO.
8. Не используй SELECT *.
9. Если вопрос просит список строк — добавь LIMIT {max_rows}.
10. Если пользователь просит N строк, LIMIT должен быть не больше {max_rows}.
11. Если нужен год, используй полуинтервал: >= TIMESTAMP 'YYYY-01-01' AND < TIMESTAMP 'YYYY+1-01-01'.
12. Если считаешь количество заказов, обычно используй COUNT(DISTINCT order_id), потому что одна строка — это комбинация order_id и tender_id.
13. Если вопрос неоднозначный, выбери самое безопасное толкование и напиши это в notes.
14. Если пользователь просит топ/рейтинг/список водителей по заказам, обязательно добавляй WHERE driver_id IS NOT NULL. NULL driver_id — это не водитель, а отсутствие назначенного водителя.
15. Если пользователь просит выполненные заказы водителей, добавляй WHERE driver_id IS NOT NULL AND status_order = 'done'.
16. Ты не видишь строки train.csv и не должен придумывать данные. Ты генерируешь только SQL по схеме, semantic_layer.json и notes.md, а backend выполнит SQL в PostgreSQL.

Фактическая схема таблицы train:
{get_train_schema_for_prompt()}

Активный семантический слой JSON:
{semantic_context or 'semantic_layer.json не найден'}

Справочник notes.md для понимания смысла колонок:
{notes or 'notes.md не найден'}

{EXAMPLES}{feedback_block}

Вопрос пользователя и найденные семантические подсказки:
{enriched_question}
""".strip()
