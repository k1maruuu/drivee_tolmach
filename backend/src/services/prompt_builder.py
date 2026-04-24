from src.services.dataset_loader import get_train_schema_for_prompt, read_train_notes

EXAMPLES = """
Примеры правильных SQL:

Пользователь: напиши мне 50 самых дорогих заказов
Ответ SQL: SELECT order_id, tender_id, city_id, status_order, order_timestamp, price_order_local FROM train ORDER BY price_order_local DESC NULLS LAST LIMIT 50;

Пользователь: Самая высокая цена поездки за 2025 год
Ответ SQL: SELECT MAX(price_order_local) AS max_price_order_local FROM train WHERE order_timestamp >= TIMESTAMP '2025-01-01' AND order_timestamp < TIMESTAMP '2026-01-01';

Пользователь: Сколько заказов было за январь 2026
Ответ SQL: SELECT COUNT(DISTINCT order_id) AS orders_count FROM train WHERE order_timestamp >= TIMESTAMP '2026-01-01' AND order_timestamp < TIMESTAMP '2026-02-01';

Пользователь: Покажи поездки и отмены по городам за вчера
Ответ SQL: SELECT city_id, COUNT(DISTINCT order_id) FILTER (WHERE status_order = 'done') AS done_orders, COUNT(DISTINCT order_id) FILTER (WHERE status_order <> 'done') AS cancelled_orders FROM train WHERE order_timestamp >= CURRENT_DATE - INTERVAL '1 day' AND order_timestamp < CURRENT_DATE GROUP BY city_id ORDER BY done_orders DESC LIMIT 100;
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

Фактическая схема таблицы train:
{get_train_schema_for_prompt()}

Справочник notes.md для понимания смысла колонок:
{notes or 'notes.md не найден'}

Бизнес-термины:
- заказы = DISTINCT order_id или строки train, если пользователь явно просит строки
- тендеры / подбор водителя = tender_id и status_tender
- выполненные поездки = status_order = 'done'
- отмены клиента = clientcancel_timestamp IS NOT NULL
- отмены водителя = drivercancel_timestamp IS NOT NULL
- итоговая стоимость / цена заказа = price_order_local
- стартовая стоимость = price_start_local
- стоимость на этапе тендера = price_tender_local
- дата заказа = order_timestamp
- город = city_id
- длительность = duration_in_seconds
- расстояние = distance_in_meters

{EXAMPLES}{feedback_block}

Вопрос пользователя: {question}
""".strip()
