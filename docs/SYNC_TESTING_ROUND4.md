# Наблюдения при тестировании синхронизации - Round 4

**Дата:** 2025-01-XX  
**Тест после исправлений:** Добавлен `X-EBAY-C-MARKETPLACE-ID` header во все API вызовы

---

## 🔧 Что было исправлено перед этим тестом

1. ✅ **Добавлен `X-EBAY-C-MARKETPLACE-ID: EBAY_US`** во все API вызовы:
   - Identity API (`/identity/v1/oauth2/userinfo`)
   - Orders API (`/sell/fulfillment/v1/order`)
   - Transactions API (`/sell/finances/v1/transaction`)
   - Disputes API (`/sell/fulfillment/v1/payment_dispute`)
   - Offers API (`/sell/inventory/v1/offer`)
   - Inventory API (`/sell/inventory/v1/inventory_item`)

2. ✅ **Добавлен `Accept: application/json`** где отсутствовал

3. ✅ **Identity endpoint** уже был исправлен на `/identity/v1/oauth2/userinfo`

4. ✅ **Trading scope** уже был удален из списка

---

## 🔍 Что проверяем

1. **Identity API** - должен вернуть `user_id` (не `None`)
   - Endpoint: `GET /identity/v1/oauth2/userinfo`
   - Headers: `Authorization: Bearer <token>`, `X-EBAY-C-MARKETPLACE-ID: EBAY_US`
   - Ожидаемый результат: `{"username": "...", "userId": "..."}`

2. **Orders API** - должен вернуть заказы (не 0 при 200 OK)
   - Endpoint: `GET /sell/fulfillment/v1/order`
   - Filter: `orderStatus:COMPLETED`
   - Headers: `X-EBAY-C-MARKETPLACE-ID: EBAY_US`
   - Ожидаемый результат: `{"orders": [...], "total": N}`

3. **Transactions API** - должен работать без 404
   - Endpoint: `GET /sell/finances/v1/transaction`
   - Filter: `filter=transactionDate:[start..end]` (RSQL format)
   - Headers: `X-EBAY-C-MARKETPLACE-ID: EBAY_US`
   - Ожидаемый результат: `{"transactions": [...], "total": N}`

4. **Environment** - все запросы должны идти на production URL
   - Production: `https://api.ebay.com`
   - НЕ sandbox: `https://api.sandbox.ebay.com`

5. **Token** - должен быть production token (судя по `client_id=filippmi-...PRD...`)

---

## 📝 Наблюдения

### ✅ Что работает:

- ✅ **Offers Sync** - завершился успешно (200 OK)
  - API отвечает корректно
  - Логика работает правильно (0 items - возможно, просто нет инвентаря)
  
- ✅ **User Authentication** - работает
  - User: `filippmiller@gmail.com`
  - Environment: `production`
  
- ✅ **API Configuration** - правильно определяется
  - Production environment
  - Правильные endpoints используются

### ❌ Критические проблемы:

#### 1. Identity API - Access Denied (1100)
**Ошибка:**
```
Identity API error: {
  'errors': [{
    'errorId': 1100, 
    'domain': 'ACCESS', 
    'category': 'REQUEST', 
    'message': 'Access denied', 
    'longMessage': 'Insufficient permissions to fulfill the request.'
  }]
}
```

**Результат:**
- `Connected as: None (eBay UserID: None)`
- Token может быть невалиден или не хватает scope для Identity API

**Проблема:** Несмотря на добавление `X-EBAY-C-MARKETPLACE-ID`, Identity API все еще возвращает Access Denied. Возможные причины:
- Токен не имеет scope `https://api.ebay.com/oauth/api_scope` (базовый scope)
- Токен невалиден или истек
- Неправильный endpoint (хотя мы исправили на `/identity/v1/oauth2/userinfo`)

---

#### 2. Disputes API - 404 Not Found
**Ошибка:**
```
Disputes sync failed: 404: Failed to fetch disputes
Endpoint: GET /sell/fulfillment/v1/payment_dispute
```

**Проблема:** Endpoint возвращает 404, хотя мы исправили его с `/payment_dispute_summary/search` на `/payment_dispute`.

**Возможные причины:**
- Endpoint все еще неправильный
- Нужны дополнительные параметры
- API требует другой путь или метод

---

#### 3. Cancellation - 400 Bad Request
**Ошибка:**
```
POST /api/ebay/sync/cancel/orders_1762497193_09dfab63
Status: 400 Bad Request
Message: "Sync operation is already complete"
```

**Проблема:** При попытке отменить синхронизацию (кнопка Stop) система возвращает 400, говоря что операция уже завершена.

**Наблюдения:**
- Происходит для Orders, Transactions, Disputes
- Возможно race condition: кнопка нажата после завершения
- Или неправильная проверка статуса в backend

---

#### 4. EventSource Errors
**Ошибка:**
```
[SyncTerminal] EventSource error: MessageEvent
Connection error: Failed to stream events. Check network connection.
```

**Проблема:** SSE поток обрывается, логи не доходят до фронтенда в реальном времени.

**Наблюдения:**
- Происходит через ~3 часа после начала (возможно timeout)
- Может быть связано с длительными операциями
- Или проблемы с Cloudflare/Railway проксированием SSE

---

#### 5. Transactions Sync - Identity не работает
**Наблюдение:**
- Transactions sync начался, но `UserID: None`
- Без Identity API мы не знаем, кто мы есть
- Это может влиять на все последующие запросы

---

## 🔍 Детальные логи

### Identity API

**Запрос:**
```
GET https://api.ebay.com/identity/v1/oauth2/userinfo
Headers:
  Authorization: Bearer <token>
  X-EBAY-C-MARKETPLACE-ID: EBAY_US
  Accept: application/json
```

**Ответ:**
```
{
  'errors': [{
    'errorId': 1100, 
    'domain': 'ACCESS', 
    'category': 'REQUEST', 
    'message': 'Access denied', 
    'longMessage': 'Insufficient permissions to fulfill the request.'
  }]
}
```

**Результат:**
- `username`: `None` ❌
- `userId`: `None` ❌
- `accountType`: `None` ❌
- `registrationMarketplaceId`: `None` ❌
- **HTTP Status:** Не указан в логах, но судя по ошибке - 403 Forbidden

---

### Orders API

**Запрос:**
```
GET https://api.ebay.com/sell/fulfillment/v1/order?filter=orderStatus:COMPLETED&limit=200&offset=0
Headers:
  Authorization: Bearer <token>
  X-EBAY-C-MARKETPLACE-ID: EBAY_US
  Accept: application/json
  Content-Type: application/json
```

**Ответ:**
```
*(Заполнить после тестирования)*
```

**Результат:**
- `total`: `?`
- `orders`: `?` (количество)
- `hasMore`: `?`

---

### Transactions API

**Запрос:**
```
GET https://api.ebay.com/sell/finances/v1/transaction?filter=transactionDate:[...]&limit=200&offset=0
Headers:
  Authorization: Bearer <token>
  X-EBAY-C-MARKETPLACE-ID: EBAY_US
  Accept: application/json
```

**Ответ:**
```
*(Заполнить после тестирования)*
```

**Результат:**
- `total`: `?`
- `transactions`: `?` (количество)
- `hasMore`: `?`

---

### Disputes API

**Запрос:**
```
GET https://api.ebay.com/sell/fulfillment/v1/payment_dispute
Headers:
  Authorization: Bearer <token>
  X-EBAY-C-MARKETPLACE-ID: EBAY_US
  Accept: application/json
  Content-Type: application/json
```

**Ответ:**
```
404 Not Found
Failed to fetch disputes
```

**Результат:**
- `total`: `0` ❌
- `disputes`: `0` ❌
- **HTTP Status:** `404 Not Found` ❌
- **Время запроса:** `[06:34:58]`
- **Response Time:** Не указан (запрос не дошел до сервера)

---

### Offers API

**Запрос:**
```
GET https://api.ebay.com/sell/inventory/v1/inventory_item?limit=200&offset=0
Headers:
  Authorization: Bearer <token>
  X-EBAY-C-MARKETPLACE-ID: EBAY_US
  Accept: application/json
```

**Ответ:**
```
200 OK (223ms)
Received 0 items, 0 SKUs (Total: 0)
```

**Результат:**
- `total`: `0` ✅ (может быть нормально, если нет инвентаря)
- `inventoryItems`: `0` ✅
- `SKUs`: `0` ✅
- **HTTP Status:** `200 OK` ✅
- **Response Time:** `223ms` ✅
- **Время запроса:** `[06:35:27]`
- **Вывод:** API работает корректно, просто нет данных для синхронизации

---

## 🎯 Выводы и следующие шаги

### Критические проблемы, требующие немедленного решения:

1. **Identity API - Access Denied (1100)**
   - **Приоритет:** 🔴 КРИТИЧЕСКИЙ
   - **Проблема:** Токен не имеет доступа к Identity API
   - **Возможные причины:**
     - Токен не содержит базовый scope `https://api.ebay.com/oauth/api_scope`
     - Токен истек или невалиден
     - Неправильный endpoint (хотя мы исправили)
   - **Следующие шаги:**
     - Проверить токен через debugger - какие scope он содержит?
     - Проверить, что базовый scope запрашивается при OAuth
     - Возможно, нужно переподключиться к eBay с правильными scope

2. **Disputes API - 404 Not Found**
   - **Приоритет:** 🟡 ВЫСОКИЙ
   - **Проблема:** Endpoint `/sell/fulfillment/v1/payment_dispute` не найден
   - **Следующие шаги:**
     - Проверить документацию eBay API для Disputes
     - Возможно, нужен другой путь или метод
     - Или нужны обязательные query параметры

3. **Cancellation - 400 Bad Request**
   - **Приоритет:** 🟡 СРЕДНИЙ
   - **Проблема:** Кнопка Stop не работает - говорит что операция уже завершена
   - **Следующие шаги:**
     - Проверить логику проверки статуса в backend
     - Возможно race condition - нужно улучшить проверку
     - Или кнопка нажимается после завершения (UX проблема)

4. **EventSource Errors**
   - **Приоритет:** 🟢 НИЗКИЙ
   - **Проблема:** SSE поток обрывается через ~3 часа
   - **Следующие шаги:**
     - Проверить timeout настройки на Cloudflare/Railway
     - Добавить reconnection logic на фронтенде
     - Или это нормально для длительных операций

### Что работает хорошо:

- ✅ Offers API - работает корректно
- ✅ User Authentication - работает
- ✅ Environment detection - правильно определяется production
- ✅ Headers - `X-EBAY-C-MARKETPLACE-ID` добавлен везде

### Рекомендации:

1. **СРОЧНО:** Проверить токен через debugger - какие scope он содержит?
2. **СРОЧНО:** Проверить, что базовый scope `https://api.ebay.com/oauth/api_scope` запрашивается при OAuth
3. Проверить документацию eBay API для Disputes endpoint
4. Улучшить логику cancellation в backend
5. Добавить reconnection для SSE на фронтенде

---

## 📌 Важные заметки

- **Токен:** Production token (новый, добавлен через интерфейс)
- **Environment:** `production` ✅
- **Marketplace ID:** `EBAY_US` (добавлен во все запросы) ✅
- **User:** `filippmiller@gmail.com` ✅
- **Следующая задача:** Добавить кнопку "Show Token" с pop-up для визуализации токена (production/sandbox)

### Детали из консоли:

**Environment Variables:**
- `VITE_API_BASE_URL`: (not set)
- `VITE_API_URL`: (not set)
- `VITE_API_PREFIX`: (not set)
- `MODE`: `production` ✅
- `PROD`: `true` ✅

**API Proxy:**
- Using `/api` (Cloudflare proxy -> Railway backend) ✅

**Cancellation Errors (для всех sync типов):**
- Orders: `POST /api/ebay/sync/cancel/orders_1762497193_09dfab63` → 400
- Transactions: `POST /api/ebay/sync/cancel/transactions_1762497261_9f151312` → 400
- Disputes: `POST /api/ebay/sync/cancel/disputes_...` → 400
- Все с сообщением: `"Sync operation is already complete"`

---

## 🔗 Связанные документы

- `SYNC_TESTING_ROUND3.md` - предыдущий раунд тестирования
- `TOKEN_VALIDATION_GUIDE.md` - руководство по валидации токенов
- `EBAY_API_STRUCTURE.md` - структура вызовов eBay API

