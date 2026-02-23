# AIGate Assistant (Iteration 1) — Quickstart

Цель: поднять локально `assistant-api` + `assistant-worker` + `qdrant` и получить рабочий RAG-чат по `docs/` (+ опционально приватный `memory-bank/` через volume mount).

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

## Приватный `memory-bank/` (не в репозитории)

`memory-bank/` по умолчанию **не должен быть в git**. Для RAG он подключается как локальная папка через bind mount (volume).

- Если `./memory-bank` существует — worker проиндексирует `docs/` + `memory-bank/`.
- Если `./memory-bank` отсутствует/пустой — проиндексируется только `docs/`.

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

## Eval (оценка retrieval)

Это полезно, если важнее качество ответа: сначала меряем, насколько хорошо retrieval (поиск чанков) находит нужные источники, без затрат на LLM.

1) Убедись, что ingestion уже был запущен и job завершился `succeeded`.

2) Прогон eval-набора (печатает JSON по кейсам + итоговый summary):

```bash
PYTHONPATH=src pipenv run python scripts/assistant_eval.py --eval eval/assistant_eval.jsonl
```

Опционально можно включить `--chat`, чтобы дополнительно проверить валидность ссылок `[N]` в ответе (будет вызывать LLM через AIGate и тратить токены):

```bash
PYTHONPATH=src pipenv run python scripts/assistant_eval.py --eval eval/assistant_eval.jsonl --chat --aigate-api-key <aigate_client_key>
```

## Agent run (Iteration 2: LangGraph + trace + tickets)

Прогон RAG через граф LangGraph (retrieve → generate → format) с сохранением run и trace (шаги), опционально — тикет для аудита.

Запуск прогона:

```bash
curl -s -X POST http://localhost:8010/v1/agent/run \
  -H 'Content-Type: application/json' \
  -H 'X-AIGATE-API-KEY: <aigate_client_key>' \
  -d '{"kb_name":"default","message":"Как запустить ingestion?","create_ticket":true}'
```

Ответ: `{"run_id":"...","ticket_id":"..."}` (ticket_id только при `create_ticket: true`).

Получить run с trace и тикетом:

```bash
curl -s http://localhost:8010/v1/agent/runs/<run_id> \
  -H 'Authorization: Bearer <ASSISTANT_API_KEY>'
```

В ответе: `status`, `query`, `output_payload` (formatted_answer, sources), `trace[]` (шаги retrieve/generate/format с latency_ms, input/output snapshot), `ticket_id` (если есть).

