# Резюме исправлений и анализ запросов к eBay API

**Дата:** 2025-01-XX  
**Статус:** Требуется консультация по запросам к eBay API

---

## ✅ Что удалось исправить

### 1. Transactions API - Исправлен 404
**Проблема:** Transactions sync возвращал 404 ошибку  
**Причина:** Использовался неправильный параметр `filter=transactionDate:[..]` вместо `transactionDateRange=..`  
**Исправление:**
- Заменено `filter=transactionDate:[..]` на `transactionDateRange=..`
- Добавлен заголовок `X-EBAY-C-MARKETPLACE-ID: EBAY_US`
- Улучшены таймауты httpx (20s total, 5s connect)

**Результат:** 404 ошибка устранена, но API все еще возвращает 0 transactions

### 2. Логирование "WHO WE ARE"
**Проблема:** Не было видно, под каким аккаунтом идет синхронизация  
**Исправление:**
- Добавлен метод `get_user_identity()` для получения username и userId
- Перед каждым sync выводится информация о подключенном пользователе

**Результат:** Логирование работает, но Identity API возвращает `None` (проблема с scope или endpoint)

### 3. Orders - Добавлено окно дат
**Проблема:** Orders sync не использовал фильтр по датам  
**Исправление:**
- Добавлен фильтр `lastmodifieddate:[since..until]` с "подушкой" 5 минут
- По умолчанию окно 90 дней назад

**Результат:** Фильтр работает, но API возвращает 0 orders

### 4. Защита от бесконечных циклов
**Проблема:** Синхронизация могла зацикливаться  
**Исправление:**
- Добавлен `max_pages = 200` для Orders и Transactions
- Ранний выход при `total == 0` (после первой страницы)
- Улучшена логика `has_more`

**Результат:** Циклы предотвращены, синхронизация завершается корректно

### 5. Кнопка Stop
**Проблема:** Кнопка Stop не отображалась во время синхронизации  
**Исправление:**
- Исправлена логика отображения: показывается когда `isConnected` или `!isComplete`
- Улучшена видимость (красный фон при наведении)

**Результат:** Кнопка отображается корректно

---

## ❌ Текущие проблемы

### 1. Все API возвращают 0 записей (Orders, Transactions, Offers/Inventory)
**Симптомы:**
- Orders: `200 OK` но `Received 0 orders (Total available: 0)`
- Transactions: `200 OK` но `Received 0 transactions (Total available: 0)`
- Offers/Inventory: `200 OK` но `Received 0 items, 0 SKUs (Total: 0)`

**Возможные причины:**
- Неправильные параметры запросов
- Неправильные scope токена
- Неправильный аккаунт (покупатель вместо продавца)
- Нет данных в указанном окне дат
- Неправильный environment (sandbox vs production)

### 2. Identity API возвращает None
**Симптом:** `Connected as: None (eBay UserID: None)`  
**Возможные причины:**
- Токен не имеет scope для Identity API
- Неправильный endpoint
- Ошибка в запросе

---

## 📋 Полные запросы к eBay API

### 1. Identity API (get_user_identity)

**URL:**
```
GET https://api.ebay.com/identity/v1/user
```

**Headers:**
```http
Authorization: Bearer {access_token}
Accept: application/json
```

**Проблемы:**
- ❓ Возможно нужен другой endpoint или scope
- ❓ Возможно нужны дополнительные заголовки

---

### 2. Orders API (fetch_orders)

**URL:**
```
GET https://api.ebay.com/sell/fulfillment/v1/order
```

**Headers:**
```http
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Query Parameters (из sync_all_orders):**
```
filter=lastmodifieddate:[2025-08-08T20:36:34.000Z..2025-11-06T20:41:34.000Z]
limit=200
offset=0
fieldGroups=TAX_BREAKDOWN
```

**Полный URL пример:**
```
GET https://api.ebay.com/sell/fulfillment/v1/order?filter=lastmodifieddate%3A%5B2025-08-08T20%3A36%3A34.000Z..2025-11-06T20%3A41%3A34.000Z%5D&limit=200&offset=0&fieldGroups=TAX_BREAKDOWN
```

**Возможные проблемы:**
- ❓ Формат фильтра `lastmodifieddate:[..]` - правильный ли?
- ❓ Нужен ли `fieldGroups=TAX_BREAKDOWN`?
- ❓ Может быть нужен другой фильтр (например, `creationdate`)?
- ❓ Может быть нужен заголовок `X-EBAY-C-MARKETPLACE-ID`?

---

### 3. Transactions API (fetch_transactions)

**URL:**
```
GET https://api.ebay.com/sell/finances/v1/transaction
```

**Headers:**
```http
Authorization: Bearer {access_token}
Accept: application/json
X-EBAY-C-MARKETPLACE-ID: EBAY_US
```

**Query Parameters (из sync_all_transactions):**
```
transactionDateRange=2025-08-08T20:42:53.000Z..2025-11-06T20:42:53.000Z
limit=200
offset=0
```

**Полный URL пример:**
```
GET https://api.ebay.com/sell/finances/v1/transaction?transactionDateRange=2025-08-08T20%3A42%3A53.000Z..2025-11-06T20%3A42%3A53.000Z&limit=200&offset=0
```

**Возможные проблемы:**
- ❓ Формат `transactionDateRange` - правильный ли? (две точки `..` между датами)
- ❓ Может быть нужен `transactionType` параметр?
- ❓ Может быть нужен другой формат дат?
- ❓ Правильный ли `X-EBAY-C-MARKETPLACE-ID: EBAY_US`?

---

### 4. Inventory API (fetch_inventory_items)

**URL:**
```
GET https://api.ebay.com/sell/inventory/v1/inventory_item
```

**Headers:**
```http
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Query Parameters (из sync_all_offers / sync_all_inventory):**
```
limit=200
offset=0
```

**Полный URL пример:**
```
GET https://api.ebay.com/sell/inventory/v1/inventory_item?limit=200&offset=0
```

**Возможные проблемы:**
- ❓ Может быть нужен фильтр по статусу (например, только активные)?
- ❓ Может быть нужен `X-EBAY-C-MARKETPLACE-ID`?
- ❓ Может быть нужны другие параметры для получения всех items?

---

### 5. Offers API (fetch_offers)

**URL:**
```
GET https://api.ebay.com/sell/inventory/v1/offer
```

**Headers:**
```http
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Query Parameters (из sync_all_offers):**
```
sku={SKU}
limit=200
offset=0
```

**Полный URL пример:**
```
GET https://api.ebay.com/sell/inventory/v1/offer?sku=TEST-SKU-123&limit=200&offset=0
```

**Примечание:** Этот запрос вызывается для каждого SKU, полученного из Inventory API. Если Inventory API возвращает 0 items, то Offers API не вызывается.

**Возможные проблемы:**
- ❓ Может быть `sku` должен быть обязательным параметром?
- ❓ Может быть нужны другие параметры?

---

## 🔍 Анализ проблем в запросах

### Проблема 1: Формат фильтров дат

**Orders:**
```
filter=lastmodifieddate:[2025-08-08T20:36:34.000Z..2025-11-06T20:41:34.000Z]
```
- ❓ Правильный ли формат? Может быть нужны квадратные скобки в URL encoding?
- ❓ Может быть нужен другой формат: `lastmodifieddate:2025-08-08T20:36:34.000Z..2025-11-06T20:41:34.000Z` (без скобок)?

**Transactions:**
```
transactionDateRange=2025-08-08T20:42:53.000Z..2025-11-06T20:42:53.000Z
```
- ❓ Правильный ли формат с двумя точками `..`?
- ❓ Может быть нужен другой формат: `2025-08-08T20:42:53.000Z,2025-11-06T20:42:53.000Z` (запятая)?

### Проблема 2: Отсутствие обязательных параметров

**Orders:**
- ❓ Может быть нужен `orderFulfillmentStatus`?
- ❓ Может быть нужен `orderPaymentStatus`?
- ❓ Может быть нужен `marketplaceId`?

**Transactions:**
- ❓ Может быть нужен `transactionType` (SALE, REFUND, etc.)?
- ❓ Может быть нужен `transactionStatus`?

**Inventory:**
- ❓ Может быть нужен `sku` для фильтрации?
- ❓ Может быть нужен `availability` (IN_STOCK, OUT_OF_STOCK)?

### Проблема 3: Заголовки

**Все запросы:**
- ❓ Может быть нужен `X-EBAY-C-MARKETPLACE-ID` для всех запросов, а не только для Transactions?
- ❓ Может быть нужен `X-EBAY-C-ENDUSERCTX`?
- ❓ Может быть нужен `Content-Type: application/json` для GET запросов?

### Проблема 4: Scope токена

**Возможные проблемы:**
- ❓ Токен может не иметь scope `sell.fulfillment.readonly` для Orders
- ❓ Токен может не иметь scope `sell.finances.readonly` для Transactions
- ❓ Токен может не иметь scope `sell.inventory.readonly` для Inventory/Offers
- ❓ Токен может не иметь scope для Identity API

**Текущие scope (из кода):**
```python
scopes = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.account",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
    "https://api.ebay.com/oauth/api_scope/sell.inventory"
]
```

**Отсутствуют:**
- ❓ `https://api.ebay.com/oauth/api_scope/sell.finances.readonly` (для Transactions)
- ❓ `https://api.ebay.com/oauth/api_scope/user.identity.readonly` (для Identity API)

---

## 📝 Вопросы для "умного друга"

1. **Правильный ли формат фильтров дат?**
   - Orders: `filter=lastmodifieddate:[ISO_DATE..ISO_DATE]` - правильный?
   - Transactions: `transactionDateRange=ISO_DATE..ISO_DATE` - правильный?

2. **Какие обязательные параметры отсутствуют?**
   - Что нужно добавить в запросы для получения данных?

3. **Какие scope нужны?**
   - Нужен ли `sell.finances.readonly` для Transactions?
   - Нужен ли `user.identity.readonly` для Identity API?
   - Какие еще scope могут быть нужны?

4. **Правильные ли заголовки?**
   - Нужен ли `X-EBAY-C-MARKETPLACE-ID` для всех запросов?
   - Какие еще заголовки могут быть нужны?

5. **Правильные ли endpoints?**
   - Все ли endpoints правильные?
   - Может быть нужны другие endpoints?

6. **Почему возвращается 0 записей?**
   - Это проблема с запросами или с данными в аккаунте?
   - Как проверить, что аккаунт имеет данные?

---

## 🔧 Код запросов (для справки)

### Orders (fetch_orders)
```python
api_url = f"{settings.ebay_api_base_url}/sell/fulfillment/v1/order"
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}
params = {
    "filter": f"lastmodifieddate:[{since_date}..{until_date}]",
    "limit": 200,
    "offset": 0,
    "fieldGroups": "TAX_BREAKDOWN"
}
response = await client.get(api_url, headers=headers, params=params, timeout=30.0)
```

### Transactions (fetch_transactions)
```python
api_url = f"{settings.ebay_api_base_url}/sell/finances/v1/transaction"
headers = {
    "Authorization": f"Bearer {access_token}",
    "Accept": "application/json",
    "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
}
params = {
    "transactionDateRange": f"{start_date}..{end_date}",
    "limit": 200,
    "offset": 0
}
response = await client.get(api_url, headers=headers, params=params)
```

### Inventory (fetch_inventory_items)
```python
api_url = f"{settings.ebay_api_base_url}/sell/inventory/v1/inventory_item"
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}
params = {
    "limit": 200,
    "offset": 0
}
response = await client.get(api_url, headers=headers, params=params, timeout=30.0)
```

### Identity (get_user_identity)
```python
api_url = f"{settings.ebay_api_base_url}/identity/v1/user"
headers = {
    "Authorization": f"Bearer {access_token}",
    "Accept": "application/json"
}
response = await client.get(api_url, headers=headers)
```

---

**Примечание:** Все запросы используют `httpx.AsyncClient` с таймаутами (20s total, 5s connect для новых запросов, 30s для старых).

