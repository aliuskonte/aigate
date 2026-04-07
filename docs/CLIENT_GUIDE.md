# AIGate API — Инструкция для клиентов

## Доступ

| Параметр | Значение |
|----------|----------|
| **Base URL** | `https://aigates.ru` |
| **API Key** | Получи у администратора |

## Заголовки

```
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

Опционально для `POST /v1/chat/completions`:

| Заголовок | Описание |
|-----------|----------|
| `X-Timeout` | Таймаут запроса к провайдеру в секундах (число, например `60` или `90.5`). **Это header запроса** (Postman → вкладка **Headers**). Значение ограничивается серверным максимумом (`QWEN_TIMEOUT_MAX_SECONDS`); при отсутствии/невалидном значении используется `QWEN_TIMEOUT_DEFAULT_SECONDS`. |

## Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Проверка доступности |
| GET | `/v1/models` | Список доступных моделей |
| POST | `/v1/chat/completions` | Chat completions (OpenAI-совместимый) |

---

## Chat (простой запрос)

```bash
curl -s -X POST https://aigates.ru/v1/chat/completions \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -H "X-Timeout: 300" \
  -d '{"model":"qwen:qwen-flash","messages":[{"role":"user","content":"Привет"}]}' | jq
```

---

## Streaming (потоковый ответ)

Добавь `"stream": true`:

```bash
curl -s -N -X POST https://aigates.ru/v1/chat/completions \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -H "X-Timeout: 300" \
  -d '{"model":"qwen:qwen-flash","messages":[{"role":"user","content":"Привет"}],"stream":true}'
```

---

## Vision (изображения)

### Одно изображение (URL)

```json
{
  "model": "qwen:qwen3-vl-plus",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "Что на изображении?"},
      {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}}
    ]
  }]
}
```

### Два изображения (base64, без внешних ссылок)

```json
{
  "model": "qwen:qwen3-vl-plus",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "Сравни эти два изображения"},
      {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQ..."}},
      {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQ..."}}
    ]
  }]
}
```

Поддерживаются: URL (`https://...`) и base64 (`data:image/jpeg;base64,...`).

---

## Idempotency (опционально)

Для защиты от двойного списания при повторных запросах добавь заголовок:

```
Idempotency-Key: unique-key-123
```

Один и тот же ключ + тот же body → тот же ответ, без повторного биллинга. Не поддерживается при `stream: true`.

---

## Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="<API_KEY>",
    base_url="https://aigates.ru/v1"
)

response = client.chat.completions.create(
    model="qwen:qwen-flash",
    messages=[{"role": "user", "content": "Привет"}]
)
print(response.choices[0].message.content)
```

---

## Модели

| Модель | Описание |
|--------|----------|
| `qwen:qwen-flash` | Быстрая |
| `qwen:qwen-plus` | Баланс |
| `qwen:qwen-max` | Максимальное качество |
| `qwen:qwen3-vl-plus` | Vision (изображения) |

Актуальный список: `GET /v1/models`.

---

## Provider-specific parameters (`extra_body`)

Для передачи нестандартных параметров провайдера (не входящих в OpenAI-спеку) используй поле `extra_body`.
Содержимое мержится в тело запроса к провайдеру as-is.

**Запрещённые ключи** (уже управляются основными полями): `model`, `messages`, `temperature`, `stream`.

### Пример: Deep Thinking (Qwen3+)

```bash
curl -s -X POST https://aigates.ru/v1/chat/completions \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen:qwen-plus",
    "messages": [{"role": "user", "content": "Реши задачу: ..."}],
    "extra_body": {"enable_thinking": true, "thinking_budget": 4096}
  }' | jq
```

В ответе chain-of-thought будет в поле `reasoning_content`:

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "Ответ: 42",
      "reasoning_content": "Рассмотрим задачу поэтапно..."
    }
  }]
}
```

### Python (OpenAI SDK)

```python
response = client.chat.completions.create(
    model="qwen:qwen-plus",
    messages=[{"role": "user", "content": "Реши задачу: ..."}],
    extra_body={"enable_thinking": True, "thinking_budget": 4096},
)
print(response.choices[0].message.reasoning_content)  # chain-of-thought
print(response.choices[0].message.content)             # финальный ответ
```

### Другие параметры

Через `extra_body` можно передать любой параметр DashScope:
`enable_search`, `search_options`, `top_k`, `repetition_penalty`, `response_format` и т.д.
Полный список: [Qwen OpenAI Chat API](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions).

---

## Rate limit

По умолчанию: 60 запросов в минуту на организацию. При превышении: HTTP 429, заголовок `Retry-After`.

---

## Ошибки

| Код | Описание |
|-----|----------|
| 401 | Неверный или отсутствующий API Key |
| 429 | Превышен rate limit |
| 502/504 | Ошибка провайдера |
