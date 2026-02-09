# AIGate Assistant (Iteration 1) — Quickstart

Цель: поднять локально `assistant-api` + `assistant-worker` + `qdrant` и получить рабочий RAG-чат по `docs/` и `memory-bank/`.

## Предусловия

- В `.env` должны быть заданы:
  - `POSTGRES_PASSWORD`
  - `QWEN_API_KEY` (иначе ассистент не сможет генерировать ответы через AIGate)

## Запуск

```bash
docker compose up -d --build
```

AIGate: `http://localhost:8000`  
Assistant: `http://localhost:8010`

## Сиды (один раз)

Создай API key для вызовов AIGate (ассистент использует его как клиент):

```bash
docker compose exec aigate python tools/seed_dev_api_key.py --org-name dev-org
```

Скопируй ключ и положи его в `.env` как:

- `ASSISTANT_AIGATE_API_KEY=<key>`

Затем перезапусти `assistant-api`:

```bash
docker compose restart assistant-api
```

## Ingestion (индексация документов)

```bash
curl -s -X POST http://localhost:8010/v1/assistant/ingest \
  -H 'Content-Type: application/json' \
  -d '{"kb_name":"default"}'
```

Проверь статус job:

```bash
curl -s http://localhost:8010/v1/assistant/ingest/jobs/<job_id>
```

## Чат

```bash
curl -s -X POST http://localhost:8010/v1/assistant/chat \
  -H 'Content-Type: application/json' \
  -H 'X-AIGATE-API-KEY: <aigate_client_key>' \
  -d '{"kb_name":"default","message":"Как устроен AIGate? Дай кратко и со ссылками."}'
```

Ответ содержит `sources[]` — откуда был взят контекст.

