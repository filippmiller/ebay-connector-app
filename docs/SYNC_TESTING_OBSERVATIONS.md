# Наблюдения при тестировании синхронизации

**Дата:** 2025-01-XX  
**Тест после исправлений:** Identity endpoint, filters, scopes

---

## 🔍 Что проверяем

1. **Identity API** - должен вернуть username и userId (не None)
2. **Orders API** - должен работать с правильным фильтром `lastModifiedDate`
3. **Transactions API** - должен работать с RSQL фильтром `filter=transactionDate:[...]`
4. **Кнопка Stop** - должна работать и останавливать синхронизацию
5. **Логирование** - должно показывать правильную информацию

---

## 📝 Наблюдения

### ✅ Что работает:
- ✅ Кнопка **Stop** отображается во время синхронизации
- ✅ Логирование "WHO WE ARE" работает
- ✅ Окно дат правильно формируется
- ✅ Логирование ошибок работает - видим детальную ошибку от eBay API

### ❌ Критические проблемы:

#### 1. Identity API - все еще возвращает None
**Логи:**
```
[21:14:02] Connected as: None (eBay UserID: None)
```

**Проблема:** Identity API endpoint исправлен на `/identity/v1/oauth2/userinfo`, но все еще возвращает None. Возможные причины:
- Токен не имеет нужного scope для Identity API
- Endpoint все еще неправильный
- Токен невалиден

#### 2. Orders API - НЕПРАВИЛЬНОЕ ИМЯ ФИЛЬТРА
**Ошибка от eBay API:**
```
400: Failed to fetch orders: {
  'errors': [{
    'errorId': 30700, 
    'domain': 'API_FULFILLMENT', 
    'category': 'REQUEST', 
    'message': "Invalid filter name: 'lastModifiedDate'",
    'parameters': [{'name': 'filterName', 'value': 'lastModifiedDate'}]
  }]
}
```

**Проблема:** eBay API говорит что `lastModifiedDate` - неправильное имя фильтра! Нужно найти правильное имя.

**Текущий код:**
```python
params["filter"] = f"lastModifiedDate:[{since_date}..{until_date}]"
```

**Вопрос:** Какое правильное имя фильтра для Orders API? Возможно:
- `creationDate`?
- `lastModified`?
- `orderDate`?
- Или фильтр вообще не нужен?

---

## 📋 Результаты всех 5 синхронизаций

### 1. Orders Sync ❌
**Статус:** FAILED (400 Bad Request)  
**Логи:**
```
[21:14:02] Starting Orders sync from eBay (production) - using bulk limit=200
[21:14:02] === WHO WE ARE ===
[21:14:02] Connected as: None (eBay UserID: None)
[21:14:02] Environment: production
[21:14:02] API Configuration: Fulfillment API v1, max batch size: 200 orders per request
[21:14:02] Date window: 2025-08-08T21:09:02.000Z..2025-11-06T21:14:02.000Z
[21:14:02] Safety limit: max 200 pages
[21:14:02] → Requesting page 1: GET /sell/fulfillment/v1/order?limit=200&offset=0
[21:14:02] Orders sync failed: 400: Failed to fetch orders: {'errors': [{'errorId': 30700, 'domain': 'API_FULFILLMENT', 'category': 'REQUEST', 'message': "Invalid filter name: 'lastModifiedDate'", 'parameters': [{'name': 'filterName', 'value': 'lastModifiedDate'}]}]}
[00:14:03] Connection error: Failed to stream events. Check network connection.
```
**Проблема:** `Invalid filter name: 'lastModifiedDate'`

---

### 2. Transactions Sync ❌
**Статус:** FAILED (404 Not Found)  
**Логи:**
```
[21:15:15] Starting Transactions sync from eBay (production) - using bulk limit=200
[21:15:15] === WHO WE ARE ===
[21:15:15] Connected as: None (eBay UserID: None)
[21:15:15] Environment: production
[21:15:15] API Configuration: Finances API v1, max batch size: 200 transactions per request
[21:15:15] Date range: 2025-08-08 to 2025-11-06 (90 days)
[21:15:15] Window: 2025-08-08T21:15:15.000Z..2025-11-06T21:15:15.000Z
[21:15:15] Safety limit: max 200 pages
[21:15:16] → Requesting page 1: GET /sell/finances/v1/transaction?limit=200&offset=0
[21:15:16] Transactions sync failed: 404: Failed to fetch transactions (HTTP 404):
[00:15:16] Connection error: Failed to stream events. Check network connection.
```
**Проблема:** 404 Not Found - возможно неправильный формат фильтра или endpoint

---

### 3. Disputes Sync ❌
**Статус:** FAILED (404 Not Found)  
**Логи:**
```
[21:15:08] Starting Disputes sync from eBay (production)
[21:15:08] API Configuration: Fulfillment API v1 payment_dispute_summary/search
[21:15:08] → Requesting: GET /sell/fulfillment/v1/payment_dispute_summary/search
[21:15:08] Disputes sync failed: 404: Failed to fetch disputes:
[00:15:08] Connection error: Failed to stream events. Check network connection.
```
**Проблема:** 404 Not Found - возможно неправильный endpoint или метод

---

### 4. Messages Sync ✅ (но 0 items)
**Статус:** SUCCESS (200 OK)  
**Логи:**
```
[21:15:02] Starting Messages sync from eBay (production)
[21:15:02] API Configuration: Trading API (XML), message headers limit=200, bodies batch=10
[21:15:02] → Requesting: POST /ws/eBayISAPI.dll (GetMyMessages - ReturnSummary)
[21:15:03] POST /ws/eBayISAPI.dll (GetMyMessages - ReturnSummary) → 200 (419ms) | 0 items
[21:15:03] ← Response: 200 OK (419ms) - Received 0 folders
[21:15:03] No message folders found
[21:15:03] Messages sync completed: no folders found
```
**Результат:** Работает! Но нет данных (0 folders) - это нормально, если нет сообщений

---

### 5. Offers Sync ✅ (но 0 items)
**Статус:** SUCCESS (200 OK)  
**Логи:**
```
[21:14:51] Starting Offers sync from eBay (production)
[21:14:51] API Configuration: Inventory API v1 - getInventoryItems → getOffers per SKU
[21:14:51] Step 1: Fetching all inventory items to get SKU list...
[21:14:52] → Fetching inventory items page 1: GET /sell/inventory/v1/inventory_item?limit=200&offset=0
[21:14:52] ← Response: 200 OK (447ms) - Received 0 items, 0 SKUs (Total: 0)
[21:14:52] ✓ Step 1 complete: Found 0 unique SKUs
[21:14:52] No SKUs found in inventory - no offers to sync
[21:14:52] Offers sync completed: 0 SKUs found, 0 offers fetched, 0 stored
```
**Результат:** Работает! Но нет данных (0 SKUs) - это нормально, если нет inventory items

---

## 🔗 Network запросы

### 1. Orders API
```
POST /api/ebay/sync/orders
→ Backend делает:
GET /sell/fulfillment/v1/order?limit=200&offset=0&filter=lastModifiedDate:[2025-08-08T21:09:02.000Z..2025-11-06T21:14:02.000Z]&fieldGroups=TAX_BREAKDOWN
```
**Ответ:** 400 Bad Request - `Invalid filter name: 'lastModifiedDate'`

### 2. Transactions API
```
POST /api/ebay/sync/transactions
→ Backend делает:
GET /sell/finances/v1/transaction?limit=200&offset=0&filter=transactionDate:[2025-08-08T21:15:15.000Z..2025-11-06T21:15:15.000Z]
```
**Ответ:** 404 Not Found

### 3. Disputes API
```
POST /api/ebay/sync/disputes
→ Backend делает:
GET /sell/fulfillment/v1/payment_dispute_summary/search
```
**Ответ:** 404 Not Found

### 4. Messages API ✅
```
POST /api/messages/sync
→ Backend делает:
POST /ws/eBayISAPI.dll (GetMyMessages - ReturnSummary)
```
**Ответ:** 200 OK - 0 folders (работает!)

### 5. Offers API ✅
```
POST /api/ebay/sync/offers
→ Backend делает:
GET /sell/inventory/v1/inventory_item?limit=200&offset=0
```
**Ответ:** 200 OK - 0 items (работает!)

---

## 💡 Вопросы для "умного друга"

1. **Какое правильное имя фильтра для Orders API?** 
   - eBay API говорит `lastModifiedDate` неправильное. Какое правильное?
   - Может быть `creationDate`, `orderDate`, или фильтр вообще не нужен?

2. **Transactions API - почему 404?**
   - Используем `filter=transactionDate:[...]` в RSQL формате
   - Scope `sell.finances` добавлен
   - Но все еще 404. Что не так?

3. **Disputes API - почему 404?**
   - Endpoint: `/sell/fulfillment/v1/payment_dispute_summary/search`
   - Метод: GET
   - Что неправильно?

4. **Identity API все еще возвращает None**
   - Endpoint исправлен на `/identity/v1/oauth2/userinfo`
   - Но все еще None. Что еще может быть не так?
   - Может быть нужен другой endpoint или scope?

5. **Messages и Offers работают - почему?**
   - Messages использует Trading API (XML) - работает!
   - Offers использует Inventory API - работает!
   - Почему эти работают, а Orders/Transactions/Disputes нет?

---

## 📌 Сводка результатов

| Sync Type | Status | HTTP Code | Проблема |
|-----------|--------|-----------|----------|
| **Orders** | ❌ FAILED | 400 | Invalid filter name: 'lastModifiedDate' |
| **Transactions** | ❌ FAILED | 404 | Endpoint или фильтр неправильный |
| **Disputes** | ❌ FAILED | 404 | Endpoint или метод неправильный |
| **Messages** | ✅ SUCCESS | 200 | Работает! (0 items - нормально) |
| **Offers** | ✅ SUCCESS | 200 | Работает! (0 items - нормально) |

**Общая проблема:** Identity API возвращает None для всех синхронизаций

---

## 📌 Следующие шаги

1. **Найти правильное имя фильтра для Orders API** (не `lastModifiedDate`)
2. **Исправить Transactions API** - проверить формат фильтра и scope
3. **Исправить Disputes API** - проверить endpoint и метод
4. **Исправить Identity API** - проверить endpoint, scope, токен
5. **Протестировать снова** после исправлений

### Identity API
- [ ] `Connected as: XXX` (не None)
- [ ] `eBay UserID: XXX` (не None)
- [ ] Ошибки в логах (если есть)

### Orders Sync
- [ ] Статус ответа (200 OK / ошибка)
- [ ] Количество заказов (0 или больше)
- [ ] Время выполнения
- [ ] Ошибки (если есть)
- [ ] Полный URL запроса из логов

### Transactions Sync
- [ ] Статус ответа (200 OK / 404 / другая ошибка)
- [ ] Количество транзакций (0 или больше)
- [ ] Время выполнения
- [ ] Ошибки (если есть)
- [ ] Полный URL запроса из логов

### Кнопка Stop
- [ ] Отображается во время синхронизации
- [ ] Останавливает процесс при нажатии
- [ ] Запросы прекращаются после остановки

### Логирование
- [ ] Показывает правильные endpoint'ы
- [ ] Показывает правильные параметры запросов
- [ ] Показывает ошибки (если есть) с деталями

---

## 🐛 Проблемы (если есть)

### Проблема 1:
**Описание:**
**Логи:**
**Ожидаемое поведение:**
**Фактическое поведение:**

---

## ✅ Что работает

- 

---

## ❌ Что не работает

### 1. Orders Sync - 400 Bad Request
- **Ошибка:** `Invalid filter name: 'lastModifiedDate'`
- **Причина:** Неправильное имя фильтра для Orders API
- **Нужно:** Найти правильное имя фильтра (возможно `creationDate`, `orderDate`, или без фильтра)

### 2. Transactions Sync - 404 Not Found
- **Ошибка:** 404 при запросе к `/sell/finances/v1/transaction`
- **Причина:** Возможно неправильный формат фильтра `filter=transactionDate:[...]` или отсутствие scope
- **Нужно:** Проверить правильность RSQL формата и наличие scope `sell.finances`

### 3. Disputes Sync - 404 Not Found
- **Ошибка:** 404 при запросе к `/sell/fulfillment/v1/payment_dispute_summary/search`
- **Причина:** Возможно неправильный endpoint или метод (GET vs POST)
- **Нужно:** Проверить документацию eBay API для Disputes

### 4. Identity API - все еще None
- **Проблема:** Все синхронизации показывают `Connected as: None (eBay UserID: None)`
- **Причина:** Endpoint исправлен на `/identity/v1/oauth2/userinfo`, но все еще возвращает None
- **Возможные причины:**
  - Токен не имеет нужного scope для Identity API
  - Токен невалиден
  - Endpoint все еще неправильный

---

## 📋 Логи из терминала

```
[ВСТАВИТЬ ЛОГИ ЗДЕСЬ]
```

---

## 🔗 Network запросы

### Identity API
```
[ВСТАВИТЬ ДЕТАЛИ ЗАПРОСА]
```

### Orders API
```
[ВСТАВИТЬ ДЕТАЛИ ЗАПРОСА]
```

### Transactions API
```
[ВСТАВИТЬ ДЕТАЛИ ЗАПРОСА]
```

---

## 💡 Вопросы для "умного друга"

1. 

---

## 📌 Следующие шаги

1. 

