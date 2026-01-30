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
docker compose up -d postgres redis
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
  -d '{"model":"qwen:qwen-flash","messages":[{"role":"user","content":"Hi"}]}' | jq
```

Idempotency (тот же `Idempotency-Key` + тот же body → один и тот же ответ):

```bash
IDEM_KEY="demo-123"
curl -s \
  -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ${AIGATE_API_KEY}" \
  -H "Idempotency-Key: ${IDEM_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen:qwen-flash","messages":[{"role":"user","content":"Hi"}]}' | jq

curl -s \
  -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ${AIGATE_API_KEY}" \
  -H "Idempotency-Key: ${IDEM_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen:qwen-flash","messages":[{"role":"user","content":"Hi"}]}' | jq
```

Vision (изображения): `content` может быть массивом частей (OpenAI-совместимый формат). Для vision используй модель `qwen:qwen3-vl-plus` (или `qwen:qwen-vl-plus`, `qwen:qwen-vl-max` — доступность зависит от региона DashScope):

```bash
curl -s \
  -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ${AIGATE_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen:qwen3-vl-plus","messages":[{"role":"user","content":[{"type":"text","text":"What is in the image?"},{"type":"image_url","image_url":{"url":"https://example.com/img.png"}}]}]}' | jq
```

Поддерживаются URL (`https://...`) и base64 (`data:image/jpeg;base64,...`).

Локальные файлы (base64):

```bash
# Одно изображение
PYTHONPATH=src pipenv run python tools/test_vision_local.py tests/img/adorable-cat-lifestyle_23-2151593310.jpg.jpeg -p "Опиши кота"

# Несколько изображений
PYTHONPATH=src pipenv run python tools/test_vision_local.py tests/img/*.jpeg -p "Сравни эти изображения"
```

Требуется `AIGATE_API_KEY` или `QWEN_API_KEY` в env.

## Deploy на VPS (Docker Compose)

### 1) На VPS: клонировать и настроить

```bash
git clone <repo-url> AIGate && cd AIGate
cp .env.example .env
# Отредактируй .env: QWEN_API_KEY (обязательно), QWEN_BASE_URL при необходимости
```

### 2) Запуск

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Миграции выполняются автоматически при старте контейнера. API доступен на порту 8000.

### 3) Сиды (один раз после первого запуска)

```bash
# Создать org + API key (выведет ключ в stdout)
docker compose -f docker-compose.prod.yml exec aigate python tools/seed_dev_api_key.py --org-name dev-org

# Заполнить price_rules
docker compose -f docker-compose.prod.yml exec aigate python tools/seed_price_rules.py --org-name dev-org
```

Сохрани ключ из `seed_dev_api_key.py` и используй как `AIGATE_API_KEY` для клиентов.

### 4) Проверка

```bash
curl -s http://VPS_IP:8000/health
```

### 5) Nginx + SSL (опционально)

Проксируй запросы на `http://127.0.0.1:8000`, настрой Let's Encrypt через certbot.

### 6) CI/CD (автодеплой при push в main)

Workflow `.github/workflows/deploy.yml`: тесты → SSH на VPS → `git pull` + `docker compose up`.

**GitHub Secrets** (Settings → Secrets → Actions):

| Secret | Описание |
|--------|----------|
| `SSH_HOST` | IP VPS (например 80.93.60.170) |
| `SSH_USER` | Пользователь VPS |
| `SSH_PRIVATE_KEY` | Приватный SSH-ключ для доступа к VPS |

**На VPS:** настроить доступ к репо для `git pull` (HTTPS + токен или SSH deploy key).

## Примечания
- Код в `src/aigate/` (src-layout).

## Troubleshooting

- **500 Internal Server Error, ConnectionRefusedError в auth**: Postgres не запущен. Подними инфраструктуру: `docker compose up -d postgres redis`. Проверь `DATABASE_URL` в `.env` (например `postgresql+asyncpg://postgres:postgres@localhost:5432/aigate`).
- **401 Unauthorized на `/v1/*`**: не передан `Authorization: Bearer ...` или не создан ключ (запусти `tools/seed_dev_api_key.py`).
- **502/504 на `/v1/chat/completions`**: проверь `QWEN_API_KEY` и `QWEN_BASE_URL`. `QWEN_BASE_URL` должен соответствовать региону ключа (us/intl/cn). Vision: если `qwen-vl-max` не найден — попробуй `qwen3-vl-plus`.
- **`GET /v1/models` иногда пустой/падает**: есть fallback allowlist на 502/504 (вернёт qwen-flash/plus/max).  