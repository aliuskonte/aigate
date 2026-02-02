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
docker compose -f docker-compose.dev.yml up -d postgres redis
```

### 3) Переменные окружения

Скопируй шаблон и заполни минимально нужные значения:

```bash
cp .env.example .env
```

Минимально для E2E:
- `POSTGRES_PASSWORD` (обязательно — пароль Postgres, задаётся при первой инициализации тома)
- `DATABASE_URL` (тот же пароль: `postgresql+asyncpg://postgres:<PASSWORD>@localhost:5432/aigate`)
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

Chat completions (streaming SSE):

```bash
curl -s -N \
  -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ${AIGATE_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen:qwen-flash","messages":[{"role":"user","content":"Hi"}],"stream":true}'
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
sudo mkdir -p /opt && sudo chown $USER:$USER /opt
git clone <repo-url> /opt/AIGate && cd /opt/AIGate
cp .env.example .env
# Отредактируй .env: POSTGRES_PASSWORD (обязательно), QWEN_API_KEY (обязательно), QWEN_BASE_URL при необходимости
```

### 2) Запуск

```bash
docker compose up -d --build
```

Миграции выполняются автоматически при старте контейнера. API доступен на порту 8000.

### 3) Сиды (один раз после первого запуска)

```bash
# Создать org + API key (выведет ключ в stdout)
docker compose exec aigate python tools/seed_dev_api_key.py --org-name dev-org

# Заполнить price_rules
docker compose exec aigate python tools/seed_price_rules.py --org-name dev-org
```

Сохрани ключ из `seed_dev_api_key.py` и используй как `AIGATE_API_KEY` для клиентов.

### 4) Проверка

```bash
curl -s http://VPS_IP:8000/health
```

### 5) Nginx + SSL (опционально)

Проксируй запросы на `http://127.0.0.1:8000`, настрой Let's Encrypt через certbot.

### 6) CI/CD (автодеплой при push в main)

Workflow `.github/workflows/deploy.yml`: тесты → SSH на VPS → `cd /opt/AIGate && git pull && docker compose up`.

**GitHub Secrets** (Settings → Secrets → Actions):

| Secret | Описание |
|--------|----------|
| `SSH_HOST` | IP VPS (например 80.93.60.170) |
| `SSH_USER` | Пользователь VPS |
| `SSH_PRIVATE_KEY` | Приватный SSH-ключ для доступа к VPS |

**На VPS:** настроить доступ к репо для `git pull` (HTTPS + токен или SSH deploy key).

**Branch Protection для main** (деплой только при merge PR):

1. GitHub → репо **aigate** → **Settings** → **Branches**
2. **Add branch protection rule**
3. Branch name pattern: `main`
4. Включить: **Require a pull request before merging**
5. Опционально: **Do not allow bypassing the above settings**
6. **Create** / **Save changes**

После этого изменения в `main` возможны только через merge PR, деплой срабатывает при merge.

## Мониторинг (Promtail + Loki + Prometheus + Grafana)

### Запуск

1. Запустить приложение (создаёт сеть `aigate_monitoring`):
   ```bash
   docker compose up -d --build
   ```

2. Запустить стек мониторинга:
   ```bash
   docker compose -f docker-compose.monitoring.yml up -d
   ```

### Доступ

| Сервис | URL | Описание |
|--------|-----|----------|
| Grafana | http://localhost:3000 | Дашборды (admin/admin) |
| Prometheus | http://localhost:9090 | Метрики |
| Loki | http://localhost:3100 | Логи |

### Метрики AIGate

Endpoint `/metrics` (Prometheus format):

- `aigate_requests_total` — всего запросов (provider, model, stream, status)
- `aigate_request_duration_seconds` — длительность запросов
- `aigate_errors_total` — ошибки по статусу
- `aigate_billed_cost_total` — суммарный billed_cost (USD)

### Логи

Promtail читает логи контейнеров из `/var/lib/docker/containers` и отправляет в Loki. AIGate пишет JSON в stdout.

**На Mac (Docker Desktop):** `/var/lib/docker/containers` может быть недоступен (логи в VM). Логи в Loki появятся на Linux/VPS.

### Grafana Cloud

Для визуализации в Grafana Cloud задай в `.env`:

- `LOKI_URL` — полный URL push (например `https://logs-prod-XXX.grafana.net/loki/api/v1/push`)
- `PROMETHEUS_REMOTE_WRITE_URL` — URL remote_write (например `https://prometheus-prod-XX-prod-REGION.grafana.net/api/prom/push`)
- `LOKI_API_TOKEN`, `PROMETHEUS_API_TOKEN` — токены из grafana.com → Stack → Details

Логи и метрики будут отправляться в Grafana Cloud в дополнение к локальному Loki/Prometheus.

## Примечания
- Код в `src/aigate/` (src-layout).

## Troubleshooting

- **500 Internal Server Error, ConnectionRefusedError в auth**: Postgres не запущен. Подними инфраструктуру: `docker compose -f docker-compose.dev.yml up -d postgres redis`. Проверь `DATABASE_URL` в `.env` (например `postgresql+asyncpg://postgres:<PASSWORD>@localhost:5432/aigate`).
- **password authentication failed for user "postgres"**: пароль в БД не совпадает с `POSTGRES_PASSWORD` в `.env`. PostgreSQL задаёт пароль только при первой инициализации тома. **Решение A (данные не нужны):** `docker compose down && docker volume rm aigate_postgres_data && docker compose up -d`, затем сиды. **Решение B (данные нужны):** сменить пароль в контейнере: `docker exec -it aigate-postgres psql -U postgres -d aigate -c "ALTER USER postgres PASSWORD 'postgres';"` (подставь пароль из `.env`).
- **401 Unauthorized на `/v1/*`**: не передан `Authorization: Bearer ...` или не создан ключ (запусти `tools/seed_dev_api_key.py`).
- **502/504 на `/v1/chat/completions`**: проверь `QWEN_API_KEY` и `QWEN_BASE_URL`. `QWEN_BASE_URL` должен соответствовать региону ключа (us/intl/cn). Vision: если `qwen-vl-max` не найден — попробуй `qwen3-vl-plus`.
- **`GET /v1/models` иногда пустой/падает**: есть fallback allowlist на 502/504 (вернёт qwen-flash/plus/max).
- **Логи не появляются в Loki**: на Mac Docker Desktop путь `/var/lib/docker/containers` недоступен из контейнера Promtail. Запускай мониторинг на Linux/VPS.  