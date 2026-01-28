# AIGate (MVP skeleton)

AI gateway/broker: единый API для клиентов, внутри — канонический формат, роутинг на провайдеров, лимиты, идемпотентность, metering/billing.

## Быстрый старт (локально)

### 1) Зависимости (pipenv)

```bash
pip install --upgrade pipenv
pipenv install --dev
```

### 2) Инфраструктура (Postgres + Redis)

Поднять Postgres и Redis:

```bash
docker compose -f docker/docker-compose.yml up -d postgres redis
```

Проверить, что сервисы поднялись:

```bash
docker compose -f docker/docker-compose.yml ps
```

### 3) Переменные окружения

Скопируй шаблон и заполни минимально нужные значения:

```bash
cp .env.example .env
```

Минимально для E2E:
- `DATABASE_URL` (Postgres)
- `REDIS_URL` (Redis)
- `QWEN_API_KEY` (DashScope)

### 4) Миграции + сиды

Применить миграции:

```bash
PYTHONPATH=src pipenv run alembic upgrade head
```

Сгенерировать dev API key (выведет ключ в stdout):

```bash
PYTHONPATH=src pipenv run python tools/seed_dev_api_key.py --org-name dev-org
```

Заполнить price_rules (для billed_cost, когда провайдер не возвращает raw_cost):

```bash
PYTHONPATH=src pipenv run python tools/seed_price_rules.py --org-name dev-org
```

### 5) Запуск API

```bash
PYTHONPATH=src pipenv run uvicorn aigate.main:app --reload
```

API:
- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`

### 6) Проверка (curl)

Health:

```bash
curl -s http://localhost:8000/health
```

Сохрани ключ из `seed_dev_api_key.py` и используй как Bearer:

```bash
export AIGATE_API_KEY="<PASTE_KEY_FROM_seed_dev_api_key>"
```

Список моделей:

```bash
curl -s \
  -H "Authorization: Bearer ${AIGATE_API_KEY}" \
  http://localhost:8000/v1/models
```

Chat completions (non-stream):

```bash
curl -s \
  -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ${AIGATE_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen:qwen-turbo","messages":[{"role":"user","content":"Hi"}]}' | jq
```

Idempotency (тот же `Idempotency-Key` + тот же body → один и тот же ответ):

```bash
IDEM_KEY="demo-123"
curl -s \
  -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ${AIGATE_API_KEY}" \
  -H "Idempotency-Key: ${IDEM_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen:qwen-turbo","messages":[{"role":"user","content":"Hi"}]}' | jq

curl -s \
  -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ${AIGATE_API_KEY}" \
  -H "Idempotency-Key: ${IDEM_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen:qwen-turbo","messages":[{"role":"user","content":"Hi"}]}' | jq
```

## Примечания
- Код в `src/aigate/` (src-layout).

## Troubleshooting

- **401 Unauthorized на `/v1/*`**: не передан `Authorization: Bearer ...` или не создан ключ (запусти `tools/seed_dev_api_key.py`).
- **502/504 на `/v1/chat/completions`**: проверь `QWEN_API_KEY` и `QWEN_BASE_URL`.
- **`GET /v1/models` иногда пустой/падает**: есть fallback allowlist на 502/504 (вернёт qwen-turbo/plus/max).  