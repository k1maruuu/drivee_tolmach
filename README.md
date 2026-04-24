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
