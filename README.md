# Drivee NL2SQL Backend

Минимальный backend для MVP: пользователь пишет вопрос обычным языком, backend просит Ollama `qwen3:4b` сгенерировать SQL, валидирует SQL через guardrails + PostgreSQL `EXPLAIN`, выполняет только безопасный `SELECT` по таблице `train` и возвращает результат.

## Что внутри

```text
backend/                 # FastAPI backend
data/train.csv           # dataset с header-строкой
data/notes.md            # справочник смысла колонок для LLM
data/goodprompts.txt     # шаблоны готовых запросов
docker-compose.yml       # Postgres + Redis + Backend, заготовка под frontend
.env.example             # пример env
```

## Важно про Ollama и данные

Backend **не отправляет в Ollama весь train.csv и строки таблицы**.  
В prompt отправляются только:

- фактическая схема таблицы `train`;
- `notes.md` со смыслом колонок;
- бизнес-правила;
- вопрос пользователя.

Данные лежат в PostgreSQL. Ollama генерирует только SQL, потом backend проверяет и выполняет SQL в базе.

## Запуск

```bash
cp .env.example .env
ollama pull qwen3:4b
ollama serve
docker compose up --build
```

Swagger:

```text
http://localhost:8000/docs
```

## Авторизация OAuth2

В Swagger нажми **Authorize**:

```text
username: admin@example.com
password: admin123
```

Или через curl:

```bash
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=admin123"
```

## Dataset

`data/train.csv` импортируется в PostgreSQL при старте, если:

```env
IMPORT_TRAIN_ON_STARTUP=true
```

Таблица называется:

```text
train
```

Колонки:

```text
city_id, order_id, tender_id, user_id, driver_id, offset_hours,
status_order, status_tender, order_timestamp, tender_timestamp,
driveraccept_timestamp, driverarrived_timestamp,
driverstarttheride_timestamp, driverdone_timestamp,
clientcancel_timestamp, drivercancel_timestamp, order_modified_local,
cancel_before_accept_local, distance_in_meters, duration_in_seconds,
price_order_local, price_tender_local, price_start_local
```

Если меняешь `train.csv` или порядок колонок, лучше пересоздать volume базы:

```bash
docker compose down -v
docker compose up --build
```

## Основной endpoint NL → SQL

```text
POST /api/analytics/ask
```

Пример:

```json
{
  "question": "напиши топ 100 самый дорогой заказ за 2026",
  "max_rows": 1
}
```

Backend ограничит результат по `max_rows`, даже если LLM попробует поставить больший `LIMIT`.

## SQL guardrails

Backend блокирует:

- `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `COPY` и другие опасные команды;
- обращения к таблицам кроме `train`;
- SQL, который не проходит PostgreSQL `EXPLAIN`;
- SQL с несуществующими колонками.

Проверка:

```text
POST /api/analytics/sql/validate
```

Выполнение безопасного SQL:

```text
POST /api/analytics/sql/execute
```

## Шаблоны запросов для фронта

Шаблоны берутся из `data/goodprompts.txt`, автоматически заменяют старое имя таблицы `anonymized_incity_orders` на `train` и кэшируются в Redis.

Получить список кнопок для фронта:

```text
GET /api/templates
```

Получить один шаблон:

```text
GET /api/templates/{template_id}
```

Выполнить шаблон:

```text
POST /api/templates/{template_id}/execute
```

Для шаблонов без параметров:

```json
{
  "max_rows": 100
}
```

Для шаблонов с параметрами:

```json
{
  "params": {
    "date_from": "2026-01-01",
    "date_to": "2026-02-01"
  },
  "max_rows": 100
}
```

Результаты выполнения шаблонов тоже кэшируются в Redis на время:

```env
TEMPLATE_RESULT_CACHE_TTL_SECONDS=600
```

## Подключение к Postgres через pgAdmin

```text
Host: localhost
Port: 5432
Database: drivee
User: drivee
Password: drivee
Table: train
```

## Если Ollama не видна из Docker

В `.env` должно быть:

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

Если backend запускаешь без Docker:

```env
OLLAMA_BASE_URL=http://localhost:11434
```

## Проверка шаблонов перед Ollama

`POST /api/analytics/ask` теперь работает так:

1. Сначала backend ищет вопрос в шаблонах из `data/goodprompts.txt`.
2. Если найден точный или очень близкий шаблон, SQL шаблона сразу валидируется через guardrails и PostgreSQL `EXPLAIN`.
3. Если шаблон валиден, backend выполняет SQL и возвращает результат. Ollama в этом сценарии не вызывается.
4. Если шаблон не найден, backend отправляет вопрос в Ollama и работает по обычному NL→SQL сценарию.

В ответе появился признак источника:

```json
{
  "source": "template",
  "template_id": "tpl_001_...",
  "template_title": "Сколько всего было заказов?",
  "template_match_score": 1.0,
  "cache_hit": false
}
```

Если `source = template`, значит ИИ/Ollama не вызывалась. Если `cache_hit = true`, результат взят из Redis.

Для шаблонов с параметрами можно передавать их прямо в `/api/analytics/ask`:

```json
{
  "question": "Сколько заказов было за день?",
  "max_rows": 1,
  "template_params": {
    "date_from": "2026-01-01",
    "date_to": "2026-01-02"
  }
}
```

Порог похожести шаблона регулируется в `.env`:

```env
TEMPLATE_MATCH_THRESHOLD=0.88
```

## История запросов и сохранение отчётов

Backend теперь сохраняет пользовательскую историю аналитических запросов и позволяет сохранять удачные запросы как отчёты для повторного использования.

### История запросов

Каждый успешный или заблокированный запрос из `/api/analytics/ask`, `/api/analytics/sql/execute`, `/api/templates/{template_id}/execute` и повторного запуска сохранённого отчёта попадает в историю.

```http
GET /api/reports/history
```

Поддерживаются параметры:

```text
limit=50
offset=0
status=ok | blocked
source=llm | template | template_cache | manual_sql | saved_report
```

В истории хранятся:

- исходный вопрос;
- источник ответа: шаблон, ИИ, cache, ручной SQL или сохранённый отчёт;
- сгенерированный SQL;
- статус выполнения;
- preview первых строк результата;
- количество строк;
- время выполнения;
- confidence.

### Сохранить отчёт из истории

```http
POST /api/reports/save
```

Пример:

```json
{
  "title": "Самые дорогие заказы 2026",
  "description": "Быстрый отчёт для демо",
  "history_id": 1,
  "default_max_rows": 100
}
```

### Сохранить отчёт вручную

```json
{
  "title": "Заказы по городам",
  "question": "Сколько заказов было по каждому городу?",
  "sql": "SELECT city_id, COUNT(DISTINCT order_id) AS total_orders FROM train GROUP BY city_id ORDER BY total_orders DESC",
  "source": "manual",
  "default_max_rows": 100
}
```

### Получить каталог отчётов

```http
GET /api/reports
GET /api/reports/{report_id}
```

### Повторно выполнить сохранённый отчёт

```http
POST /api/reports/{report_id}/execute
```

Тело запроса можно оставить пустым:

```json
{}
```

Или передать параметры, если сохранённый SQL был параметризован:

```json
{
  "params": {
    "date_from": "2026-01-01",
    "date_to": "2026-02-01"
  },
  "max_rows": 100
}
```

### Удалить отчёт

```http
DELETE /api/reports/{report_id}
```

## Step 2: Explainability / interpretation

`POST /api/analytics/ask` now returns an `interpretation` block. It explains how backend understood the request and the generated SQL:

```json
{
  "interpretation": {
    "metric": "Самые дорогие заказы по итоговой стоимости price_order_local",
    "date_filter": "order_timestamp от 2026-01-01 включительно до 2027-01-01 не включительно",
    "filters": [],
    "group_by": [],
    "sort": "price_order_local DESC NULLS LAST",
    "limit": 100,
    "used_columns": ["order_id", "price_order_local", "order_timestamp"],
    "selected_expressions": ["order_id", "price_order_local"],
    "row_logic": "Возвращает строки из train после фильтрации и сортировки.",
    "result_shape": "table",
    "explanation_ru": [
      "Метрика/смысл запроса: Самые дорогие заказы по итоговой стоимости price_order_local.",
      "Период: order_timestamp от 2026-01-01 включительно до 2027-01-01 не включительно.",
      "Сортировка: price_order_local DESC NULLS LAST.",
      "Ограничение результата: LIMIT 100.",
      "Перед выполнением SQL прошёл guardrails и PostgreSQL EXPLAIN-проверку."
    ]
  }
}
```

The same interpretation is also returned by:

- `POST /api/templates/{template_id}/execute`
- `POST /api/reports/{report_id}/execute`
- `POST /api/analytics/sql/execute`

Use this block on frontend as a "Система поняла запрос так" panel.

## Step 3: Visualization config для фронта

Backend теперь возвращает блок `visualization`. Он не рисует график сам, а подсказывает frontend-у, какой компонент лучше показать: `metric`, `table`, `bar` или `line`.

Пример ответа:

```json
{
  "visualization": {
    "recommended": true,
    "type": "bar",
    "title": "Покажи топ-10 городов по числу отмен",
    "x_axis": "city_id",
    "y_axis": "canceled_orders",
    "series": ["canceled_orders"],
    "label_column": null,
    "value_column": null,
    "reason_ru": "Есть категориальная колонка и числовой показатель — лучше показать столбчатую диаграмму.",
    "frontend_config": {
      "component": "BarChart",
      "x_key": "city_id",
      "y_keys": ["canceled_orders"],
      "data_key": "rows"
    }
  }
}
```

Где появляется `visualization`:

- `POST /api/analytics/ask`
- `POST /api/analytics/sql/execute`
- `POST /api/templates/{template_id}/execute`
- `POST /api/reports/{report_id}/execute`

Логика выбора:

- 1 строка + числовой показатель → `metric`
- дата/день/неделя/месяц + число → `line`
- город/статус/час + число → `bar`
- если непонятно, что рисовать → `table`

Frontend может брать `result.rows` как данные, а ключи брать из `visualization.frontend_config`.

## Step 4: уточняющие вопросы и confidence

`POST /api/analytics/ask` теперь перед вызовом Ollama проверяет, не является ли вопрос слишком неоднозначным. Если вопрос нельзя безопасно интерпретировать, backend возвращает `needs_clarification=true` и список готовых вариантов для фронта.

Пример неоднозначного вопроса:

```json
{
  "question": "покажи лучшие города",
  "max_rows": 100
}
```

Пример ответа:

```json
{
  "source": "clarification",
  "needs_clarification": true,
  "confidence": 0.25,
  "confidence_reason": "запрос неоднозначный, backend не стал угадывать SQL и попросил уточнение",
  "clarification": {
    "message_ru": "Что считать лучшим городом?",
    "reason": "ambiguous_city_ranking_metric",
    "options": [
      {"label": "По количеству заказов", "question": "Покажи города по количеству заказов", "template_params": {}},
      {"label": "По обороту", "question": "Покажи города по сумме price_order_local для завершенных заказов", "template_params": {}},
      {"label": "По среднему чеку", "question": "Покажи средний чек по городам", "template_params": {}}
    ]
  }
}
```

Фронт может показать `clarification.options` как кнопки. При клике отправляй `option.question` обратно в `/api/analytics/ask`.

Также в обычном ответе теперь есть:

```json
{
  "confidence": 0.87,
  "confidence_reason": "SQL прошёл guardrails и PostgreSQL EXPLAIN; вернулось строк: 10"
}
```

`confidence` считается backend-ом, а не только моделью: учитываются шаблон, cache hit, EXPLAIN-проверка, guardrails, автопочинка SQL и пустой результат.

## Step 5: Admin audit logs for guardrails

Added technical audit trail for SQL validation and query execution.

New admin-only endpoints:

```text
GET /api/admin/query-audit-logs
GET /api/admin/query-audit-logs/{audit_id}
GET /api/admin/query-audit-logs/stats
```

Only `is_superuser=true` users can access them. The default seeded user from `.env` is a superuser.

Each audit log stores:

- action: `ask`, `validate`, `execute`, `template_execute`, `report_save`, `report_execute`
- source: `llm`, `template`, `template_cache`, `manual_sql`, `saved_report`, `clarification`
- status: `ok`, `blocked`, `cache`, `clarification`, `error`
- original SQL and normalized SQL
- guardrail errors and warnings
- blocked reason
- row count, confidence, execution time
- template/report metadata when available

Useful demo checks:

```sql
DROP TABLE train;
SELECT id FROM train;
SELECT COUNT(DISTINCT order_id) FROM train WHERE status_order = 'delete';
```

The first two should be blocked and visible in `/api/admin/query-audit-logs?status=blocked`.
The third should pass because `'delete'` is a safe status value inside quotes, not a SQL DELETE command.

## Step 6: Heavy SQL protection / performance guardrails

Added stronger protection against queries that can overload PostgreSQL.

Now backend blocks or limits:

- `SELECT *` — explicit columns only;
- `CROSS JOIN` and comma joins;
- multiple references to `train` / self-joins;
- large `OFFSET`;
- row-locking clauses like `FOR UPDATE`;
- expensive helpers like `pg_sleep()` and `generate_series()`;
- `ORDER BY random()`;
- queries that exceed PostgreSQL `EXPLAIN` cost/row thresholds.

DB-level protections are applied before validation and execution:

```env
SQL_STATEMENT_TIMEOUT_MS=5000
SQL_READONLY_TRANSACTION=true
SQL_MAX_LIMIT=500
SQL_MAX_OFFSET=1000
SQL_MAX_TRAIN_REFERENCES=1
SQL_MAX_EXPLAIN_TOTAL_COST=2000000
SQL_MAX_EXPLAIN_PLAN_ROWS=2000000
SQL_BLOCK_SELECT_STAR=true
SQL_BLOCK_CROSS_JOIN=true
```

Safe queries still work, but the backend automatically adds/reduces `LIMIT` and returns warnings in `guardrails.warnings`, for example:

```json
{
  "warnings": [
    "LIMIT 100 was added automatically.",
    "EXPLAIN estimate: total_cost=12345.67, plan_rows=50000."
  ]
}
```

Test blocked examples:

```sql
SELECT * FROM train;
SELECT COUNT(*) FROM train a CROSS JOIN train b;
SELECT order_id FROM train ORDER BY random();
SELECT order_id FROM train OFFSET 100000 LIMIT 10;
```

## Шаг 7: расписание сохраненных отчетов

Теперь сохраненные отчеты можно запускать по расписанию без нового запроса к LLM.
Расписание использует уже сохраненный SQL отчета, каждый запуск заново проходит guardrails/EXPLAIN и выполняется только как readonly SELECT.

### Endpoints

```text
GET    /api/report-schedules
POST   /api/report-schedules
GET    /api/report-schedules/{schedule_id}
PATCH  /api/report-schedules/{schedule_id}
POST   /api/report-schedules/{schedule_id}/run-now
DELETE /api/report-schedules/{schedule_id}
POST   /api/report-schedules/run-due        # admin/manual trigger
```

### Пример создания расписания

```json
{
  "report_id": 1,
  "frequency": "weekly",
  "timezone": "Asia/Yakutsk",
  "day_of_week": 0,
  "hour": 9,
  "minute": 0,
  "default_max_rows": 100,
  "params": {},
  "is_enabled": true
}
```

`day_of_week`: понедельник = 0, воскресенье = 6.
Для `frequency = "daily"` день недели не нужен.
Для `frequency = "monthly"` используй `day_of_month` от 1 до 31.

### Как это работает

1. Пользователь сохраняет отчет через `POST /api/reports/save`.
2. Фронт создает расписание через `POST /api/report-schedules`.
3. Backend раз в `REPORT_SCHEDULER_INTERVAL_SECONDS` проверяет `report_schedules.next_run_at`.
4. Если расписание наступило, backend выполняет сохраненный SQL.
5. Результат сохраняется в `report_schedules.last_result_preview`, `saved_reports.last_result_preview`, `query_history` и `query_audit_logs`.

### Настройки

```env
REPORT_SCHEDULER_ENABLED=true
REPORT_SCHEDULER_INTERVAL_SECONDS=60
REPORT_SCHEDULER_BATCH_SIZE=10
DEFAULT_REPORT_SCHEDULE_TIMEZONE=UTC
```

Для Railway важно: автоматический запуск работает пока запущен backend-процесс. Если сервис спит/выключен, расписания не выполняются до следующего запуска backend.
