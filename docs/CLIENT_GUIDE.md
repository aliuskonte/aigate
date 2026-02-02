# AIGate API — Инструкция для клиентов

## Доступ

| Параметр | Значение |
|----------|----------|
| **Base URL** | `80.93.60.170:8000` |
| **API Key** | Получи у администратора |

## Заголовки

```
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

## Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Проверка доступности |
| GET | `/v1/models` | Список доступных моделей |
| POST | `/v1/chat/completions` | Chat completions (OpenAI-совместимый) |

---

## Chat (простой запрос)

```bash
curl -s -X POST https://api.example.com/v1/chat/completions \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen:qwen-flash","messages":[{"role":"user","content":"Привет"}]}' | jq
```

---

## Streaming (потоковый ответ)

Добавь `"stream": true`:

```bash
curl -s -N -X POST https://api.example.com/v1/chat/completions \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
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
    base_url="https://api.example.com/v1"
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

## Rate limit

По умолчанию: 60 запросов в минуту на организацию. При превышении: HTTP 429, заголовок `Retry-After`.

---

## Ошибки

| Код | Описание |
|-----|----------|
| 401 | Неверный или отсутствующий API Key |
| 429 | Превышен rate limit |
| 502/504 | Ошибка провайдера |
