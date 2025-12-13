# Диагностический чеклист для eBay Browser

## Пошаговая диагностика проблемы

### Шаг 1: Проверка environment variables

```bash
# Проверить наличие всех необходимых переменных
echo $EBAY_ENVIRONMENT
echo $EBAY_PRODUCTION_CLIENT_ID
# НЕ печатайте CERT_ID в открытые логи!
```

**Ожидаемый результат**:
- `EBAY_ENVIRONMENT` = "production" или "sandbox"
- `EBAY_PRODUCTION_CLIENT_ID` должен быть заполнен
- `EBAY_PRODUCTION_CERT_ID` должен существовать (НЕ печатайте его значение)
- `EBAY_PRODUCTION_DEV_ID` должен существовать

**Если нет** → Проблема в конфигурации окружения

---

### Шаг 2: Тест OAuth токена напрямую

Запустите debug скрипт:
```bash
cd c:\dev\ebay-connector-app
python debug_ebay_search.py
```

**Ожидаемый результат**:
```
Getting token...
Token obtained (len=2048)

--- Test 1: Sort by Price (Ascending) ---
Found 5 results.
- Lenovo L500 ... | Price: 50.00 | Shipping: 10.00 | Total: 60.00
...

--- Test 2: Pagination (Offset) ---
Page 1:
- v1|123456789|0: Lenovo L500 ...
...
SUCCESS: No overlap between pages.
```

**Если ошибка**:
- "Failed to get token" → Проблема в OAuth аутентификации (неправильные credentials)
- "Search failed" → Проблема в запросе к eBay Browse API
- Network error → Проблема с доступом к api.ebay.com

---

### Шаг 3: Проверка backend logs

Найдите логи вашего backend сервера (Railway, local, etc.)

Ищите:
```bash
grep "app_token" logs.txt
grep "Browse API" logs.txt
grep "ebay_browse" logs.txt
grep "401" logs.txt
grep "error" logs.txt
```

**Что искать**:
- ❌ "eBay credentials not configured" → env vars не установлены
- ❌ "Failed to obtain eBay application access token" → OAuth не работает
- ❌ "Browse API token is invalid or expired" → Токен протух
- ❌ "Browse API request error" → Сетевая ошибка
- ❌ HTTP 429 → Rate limiting
- ✅ "Successfully obtained eBay application access token" → Auth OK
- ✅ HTTP 200 от Browse API → API работает

---

### Шаг 4: Проверка frontend Network tab

Откройте DevTools в браузере → Network tab

1. Откройте страницу eBay Browser
2. Введите поисковый запрос и нажмите "Искать"
3. Найдите запрос к `/api/ebay/browse/search`

**Проверьте**:
- Status Code должен быть 200
- Response должен содержать `items: [...]`
- Если 401 → проблема с аутентификацией backend
- Если 404 → роутинг не настроен
- Если 500 → ошибка в backend логике
- Если CORS error → проблема с CORS настройками

**Request Payload**:
```json
{
  "keywords": "Lenovo L500",
  "max_total_price": 200,
  "category_hint": "laptop",
  ...
}
```

**Expected Response**:
```json
{
  "items": [
    {
      "item_id": "...",
      "title": "...",
      "price": 100.0,
      "shipping": 10.0,
      ...
    }
  ],
  "categories": [...],
  "conditions": [...],
  ...
}
```

---

### Шаг 5: Проверка endpoint доступности

Тест через curl (замените токеном из настроек):
```bash
curl -X POST http://localhost:8000/api/ebay/browse/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "keywords": "Lenovo L500",
    "limit": 5
  }'
```

**Ожидаемый результат**: JSON с items

**Если ошибка**:
- Connection refused → Backend не запущен
- 401 Unauthorized → JWT токен невалиден
- 404 Not Found → Endpoint не зарегистрирован
- 500 Internal Server Error → Проблема в backend коде

---

### Шаг 6: Проверка eBay API напрямую

Тест OAuth flow:
```bash
# Сначала получите access token
CLIENT_ID="ваш_client_id"
CERT_ID="ваш_cert_id"
CREDENTIALS=$(echo -n "$CLIENT_ID:$CERT_ID" | base64)

curl -X POST https://api.ebay.com/identity/v1/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic $CREDENTIALS" \
  -d "grant_type=client_credentials&scope=https://api.ebay.com/oauth/api_scope"
```

**Ожидаемый ответ**:
```json
{
  "access_token": "v^1.1#...",
  "expires_in": 7200,
  "token_type": "Application Access Token"
}
```

Затем проверьте Browse API:
```bash
TOKEN="полученный_access_token"

curl -X GET "https://api.ebay.com/buy/browse/v1/item_summary/search?q=Lenovo%20L500&limit=5" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-EBAY-C-MARKETPLACE-ID: EBAY_US"
```

**Ожидаемый ответ**:
```json
{
  "total": 1234,
  "itemSummaries": [
    {
      "itemId": "...",
      "title": "Lenovo L500...",
      "price": { "value": "100.00", "currency": "USD" },
      ...
    }
  ]
}
```

**Если ошибка**:
- 401 → Credentials неправильные или application не approved в eBay Developer
- 403 → API access запрещен
- 404 → Неправильный endpoint URL
- 500 → Проблема на стороне eBay

---

### Шаг 7: Проверка frontend консоли

Откройте DevTools → Console

**Что искать**:
- ❌ CORS errors → Проблема с backend CORS настройками
- ❌ TypeError → Проблема в JavaScript коде
- ❌ Network errors → Проблема с сетевым подключением
- ❌ "Failed to fetch" → Backend недоступен

---

## Наиболее частые проблемы

### Проблема 1: "Credentials not configured"
**Причина**: Environment variables не установлены или неправильные
**Решение**: 
1. Проверить `.env` файл
2. Убедиться что Railway/deployment platform имеет правильные env vars
3. Перезапустить backend после изменения env vars

### Проблема 2: HTTP 401 от eBay
**Причина**: 
- Неправильные CLIENT_ID или CERT_ID
- Application не approved в eBay Developer
- Scopes неправильные
**Решение**:
1. Проверить credentials в eBay Developer Console
2. Убедиться что application в статусе "Production"
3. Проверить что scopes включают Browse API

### Проблема 3: Empty results
**Причина**:
- Фильтры слишком строгие
- eBay API не возвращает результаты
- Пост-фильтрация удаляет все результаты
**Решение**:
1. Попробовать более общий поисковый запрос
2. Убрать фильтры (max_price, category_hint, exclude_keywords)
3. Проверить raw response от eBay API

### Проблема 4: Frontend не показывает результаты
**Причина**:
- Backend возвращает данные, но frontend не рендерит
- JavaScript ошибки
- State не обновляется
**Решение**:
1. Проверить Console на ошибки
2. Проверить что `items` массив не пустой в response
3. Проверить что `rows` state обновляется в React

### Проблема 5: Timeout errors
**Причина**:
- eBay API медленно отвечает
- Таймауты слишком короткие
**Решение**:
1. Увеличить timeouts в `ebay_api_client.py` (сейчас 20 сек)
2. Проверить сетевую задержку до api.ebay.com
3. Использовать меньше fieldgroups

---

## Следующие шаги

После диагностики запишите:
1. **Какой шаг не прошел?**
2. **Какое сообщение об ошибке вы видите?**
3. **Логи из backend**
4. **Скриншот Network tab из DevTools**

С этой информацией можно определить точную причину и решение.
