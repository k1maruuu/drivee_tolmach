# Drivee NL2SQL Backend

Минимальная backend-основа под кейс Drivee: OAuth2-авторизация, Postgres, импорт `train.csv`, подключение локальной Ollama `qwen3:4b`, генерация безопасного SQL и выдача данных из таблицы `train`.

## Быстрый запуск

```bash
cp .env.example .env
# убедись, что локально запущена Ollama и модель скачана:
# ollama pull qwen3:4b
# ollama serve

docker compose up --build
```

Swagger: http://localhost:8000/docs

Демо-аккаунт:

```text
username: admin@example.com
password: admin123
```

При первом старте backend создаст таблицы и импортирует `data/train.csv` в Postgres. CSV большой, поэтому первый запуск может занять время.

## Авторизация OAuth2 в Swagger

1. Открой `http://localhost:8000/docs`.
2. Нажми кнопку **Authorize** справа сверху.
3. Заполни:

```text
username: admin@example.com
password: admin123
```

4. Нажми **Authorize**.
5. После этого защищенные эндпоинты `/api/analytics/*` будут работать из Swagger.

Технически используется OAuth2 Password Bearer flow:

- `POST /api/auth/token` — OAuth2 token endpoint для Swagger.
- `POST /api/auth/login` — alias, тоже принимает OAuth2 form-data.
- `GET /api/auth/me` — текущий пользователь по Bearer token.
- `POST /api/auth/register` — регистрация нового пользователя через JSON.

## Основные эндпоинты

- `POST /api/auth/token` — OAuth2-вход, получить JWT.
- `POST /api/auth/login` — то же самое, совместимый login endpoint.
- `POST /api/auth/register` — регистрация пользователя.
- `GET /api/auth/me` — текущий пользователь.
- `GET /api/analytics/schema` — схема таблицы `train`.
- `POST /api/analytics/ask` — вопрос на русском/английском → SQL через Ollama → проверка → выполнение.
- `POST /api/analytics/sql/validate` — проверить SQL без выполнения.
- `POST /api/analytics/sql/execute` — выполнить SELECT SQL после guardrails.

## Пример через curl

OAuth2 token endpoint принимает `application/x-www-form-urlencoded`, не JSON:

```bash
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=admin123"
```

Запрос к ИИ:

```bash
curl -X POST http://localhost:8000/api/analytics/ask \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"question":"Самая высокая цена поездки за 2025 год", "max_rows": 50}'
```

Проверка текущего пользователя:

```bash
curl http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer <TOKEN>"
```

## Важно про Ollama

В Docker `localhost` внутри backend-контейнера — это сам контейнер, поэтому в `.env` по умолчанию стоит:

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

Если запускаешь backend не в Docker, а напрямую на Windows/Linux/Mac, поставь:

```env
OLLAMA_BASE_URL=http://localhost:11434
```

## SQL guardrails

Backend разрешает только безопасные запросы:

- только `SELECT` или `WITH ... SELECT`;
- только таблица `train`;
- запрещены `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`, `CREATE` и другие изменяющие команды;
- автоматически добавляется `LIMIT`, если его нет;
- используется statement timeout.

## Обновление схемы train

В этой версии таблица `train` создаётся по `data/notes.md` и фактическому порядку колонок в `train.csv`.

Важное изменение:

- колонки `id` больше нет;
- идентификатор заказа — `order_id`;
- идентификатор тендера — `tender_id`;
- `notes.md` передаётся в prompt для Ollama, чтобы модель понимала смысл колонок.

Если у тебя уже был запущен старый volume с неправильной таблицей `train`, проще всего пересоздать базу:

```bash
docker compose down -v
docker compose up --build
```

При старте backend сам проверит список колонок `train`. Если найдёт старую схему с `id/user_hash/order_hash`, он пересоздаст таблицу и импортирует CSV заново.

## Проверка SQL теперь сложнее

`/api/analytics/sql/validate` теперь делает не только статическую проверку опасных команд, но и реальную проверку через PostgreSQL `EXPLAIN`.

Это значит, что запросы с несуществующими колонками будут заблокированы до выполнения, например:

```sql
SELECT id, price_order_local FROM train ORDER BY price_order_local DESC LIMIT 50;
```

Потому что `id` нет в таблице. Правильный вариант:

```sql
SELECT order_id, tender_id, price_order_local
FROM train
ORDER BY price_order_local DESC NULLS LAST
LIMIT 50;
```

Пример вопроса:

```json
{
  "question": "напиши мне 50 самых дорогих заказов",
  "max_rows": 50
}
```

Ожидаемый SQL должен быть похож на:

```sql
SELECT order_id, tender_id, city_id, status_order, order_timestamp, price_order_local
FROM train
ORDER BY price_order_local DESC NULLS LAST
LIMIT 50;
```
