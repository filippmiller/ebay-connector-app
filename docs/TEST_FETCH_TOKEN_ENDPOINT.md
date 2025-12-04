# Как протестировать `/api/admin/internal/test-fetch-token`

## Endpoint
```
POST /api/admin/internal/test-fetch-token
```

## Аутентификация
Требуется `INTERNAL_API_KEY` в теле запроса.

## Шаг 1: Получить `ebay_account_id`

### Вариант A: Через API (если есть доступ к Admin UI)
```bash
# Получить список всех активных аккаунтов
GET /api/ebay/accounts?active_only=true
```

### Вариант B: Через базу данных
```sql
SELECT id, house_name, ebay_user_id, is_active 
FROM ebay_accounts 
WHERE is_active = true;
```

### Вариант C: Через Railway CLI
```bash
# Подключиться к базе данных через Railway
railway connect postgres
# Затем выполнить SQL запрос выше
```

## Шаг 2: Получить `INTERNAL_API_KEY`

Проверьте переменные окружения в Railway:
```bash
railway variables --service aebay-api
# Ищите INTERNAL_API_KEY
```

Или в локальном `.env` файле:
```bash
INTERNAL_API_KEY=your-key-here
```

## Шаг 3: Тестирование через curl

### Пример запроса:
```bash
curl -X POST "https://your-api-url.com/api/admin/internal/test-fetch-token" \
  -H "Content-Type: application/json" \
  -d '{
    "internal_api_key": "your-internal-api-key",
    "ebay_account_id": "e524cb1f-87c2-4eda-9518-721fc66bd0c0",
    "triggered_by": "test",
    "api_family": "transactions"
  }'
```

### Минимальный запрос (только обязательные поля):
```bash
curl -X POST "https://your-api-url.com/api/admin/internal/test-fetch-token" \
  -H "Content-Type: application/json" \
  -d '{
    "internal_api_key": "your-internal-api-key",
    "ebay_account_id": "e524cb1f-87c2-4eda-9518-721fc66bd0c0"
  }'
```

## Шаг 4: Ожидаемый ответ

### ✅ Успешный ответ (токен расшифрован):
```json
{
  "success": true,
  "token_received": true,
  "token_prefix": "v^1.1#IAAABk0...",
  "token_is_decrypted": true,
  "token_hash": "a1b2c3d4e5f6",
  "error": null,
  "build_number": "5e52b74"
}
```

### ❌ Ошибка (токен зашифрован):
```json
{
  "success": false,
  "token_received": true,
  "token_prefix": "ENC:v1:PMV***+xjX2wgU1o",
  "token_is_decrypted": false,
  "token_hash": null,
  "error": "fetch_active_ebay_token returned None - check logs for details",
  "build_number": "5e52b74"
}
```

### ❌ Ошибка (токен не найден):
```json
{
  "success": false,
  "token_received": false,
  "token_prefix": null,
  "token_is_decrypted": false,
  "token_hash": null,
  "error": "fetch_active_ebay_token returned None - check logs for details",
  "build_number": "5e52b74"
}
```

## Шаг 5: Проверка логов

После запроса проверьте логи приложения:
```bash
# Railway logs
railway logs --service aebay-api --tail 50 | Select-String -Pattern "fetch_active_ebay_token|test-fetch-token"

# Ищите сообщения:
# [fetch_active_ebay_token] ✅ Token retrieved successfully: ...
# [fetch_active_ebay_token] ⚠️ TOKEN STILL ENCRYPTED! ...
```

## Что проверить:

1. ✅ `token_is_decrypted: true` - токен успешно расшифрован
2. ✅ `token_prefix` начинается с `v^1.1#` (НЕ `ENC:v1:...`)
3. ✅ `build_number` соответствует последнему коммиту
4. ✅ В логах есть сообщение `[fetch_active_ebay_token] ✅ Token retrieved successfully`

## Если токен зашифрован:

1. Проверьте `SECRET_KEY` в Railway worker:
   ```bash
   railway variables --service aebay-workers-loop | grep SECRET_KEY
   ```

2. Убедитесь, что `SECRET_KEY` совпадает с web app:
   ```bash
   railway variables --service aebay-api | grep SECRET_KEY
   ```

3. Проверьте логи на ошибки дешифровки:
   ```bash
   railway logs --service aebay-api --tail 100 | Select-String -Pattern "decrypt|ENC|SECRET_KEY"
   ```

## Тестирование через Python скрипт:

```python
import requests
import os

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")
API_URL = "https://your-api-url.com/api/admin/internal/test-fetch-token"
EBAY_ACCOUNT_ID = "e524cb1f-87c2-4eda-9518-721fc66bd0c0"

response = requests.post(
    API_URL,
    json={
        "internal_api_key": INTERNAL_API_KEY,
        "ebay_account_id": EBAY_ACCOUNT_ID,
        "triggered_by": "test",
        "api_family": "transactions"
    }
)

print(response.json())
```

