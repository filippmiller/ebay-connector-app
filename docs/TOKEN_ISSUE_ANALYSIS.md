# Анализ проблемы с токеном eBay API

**Дата:** 2025-01-XX  
**Статус:** Критическая проблема - токен не работает

---

## 🚨 КРИТИЧЕСКАЯ ПРОБЛЕМА: ТОКЕН НЕ РАБОТАЕТ

**Вывод "умного друга":** Проблема не в коде синхронизации, а в авторизации. Все остальное работает идеально — но без валидного токена eBay просто не даст доступ к данным.

---

## ✅ Что я нашел в коде (критические ошибки)

### 1. ❌ Identity API - НЕПРАВИЛЬНЫЙ ENDPOINT

**Текущий код:**
```python
api_url = f"{settings.ebay_api_base_url}/identity/v1/user"
```

**Должно быть (по "умному другу"):**
```python
api_url = f"{settings.ebay_api_base_url}/identity/v1/oauth2/userinfo"
```

**Проблема:** Мы используем `/identity/v1/user`, а правильный endpoint — `/identity/v1/oauth2/userinfo`. Это объясняет почему `Connected as: None`.

---

### 2. ❌ Transactions API - НЕПРАВИЛЬНЫЙ ФОРМАТ ФИЛЬТРА

**Текущий код:**
```python
params['transactionDateRange'] = f"{start_date}..{end_date}"
```

**Должно быть (по "умному другу"):**
```python
params['filter'] = f"transactionDate:[{start_date}..{end_date}]"  # RSQL формат
```

**Проблема:** Мы используем `transactionDateRange=..`, а должен быть `filter=transactionDate:[..]` в RSQL формате. Это объясняет почему Transactions API возвращал 404.

---

### 3. ❌ ОТСУТСТВУЮТ КРИТИЧЕСКИЕ SCOPE

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
- ❌ `https://api.ebay.com/oauth/api_scope/sell.finances` - для Transactions API
- ❌ `https://api.ebay.com/oauth/api_scope/trading` - для Messages API

**Проблема:** Без этих scope токен не может получить доступ к Transactions и Messages API.

---

### 4. ❓ Orders API - НУЖНО ПРОВЕРИТЬ ФОРМАТ ФИЛЬТРА

**Текущий код:**
```python
params["filter"] = f"lastmodifieddate:[{since_date}..{until_date}]"
```

**По "умному другу":** Должен быть RSQL формат с URL-encoding. Нужно проверить правильность.

---

## 📋 План исправлений

### ШАГ 1: Исправить Identity API endpoint

**Файл:** `backend/app/services/ebay.py`  
**Метод:** `get_user_identity()`

**Изменить:**
```python
# БЫЛО:
api_url = f"{settings.ebay_api_base_url}/identity/v1/user"

# ДОЛЖНО БЫТЬ:
api_url = f"{settings.ebay_api_base_url}/identity/v1/oauth2/userinfo"
```

---

### ШАГ 2: Исправить Transactions API формат фильтра

**Файл:** `backend/app/services/ebay.py`  
**Метод:** `fetch_transactions()` и `sync_all_transactions()`

**Изменить:**
```python
# БЫЛО:
params['transactionDateRange'] = f"{start_date}..{end_date}"

# ДОЛЖНО БЫТЬ:
params['filter'] = f"transactionDate:[{start_date}..{end_date}]"  # RSQL формат
```

**Также нужно:** Убедиться что фильтр правильно URL-encoded при отправке запроса.

---

### ШАГ 3: Добавить недостающие scope

**Файл:** `backend/app/services/ebay.py`  
**Метод:** `get_authorization_url()`

**Изменить:**
```python
# БЫЛО:
scopes = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.account",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
    "https://api.ebay.com/oauth/api_scope/sell.inventory"
]

# ДОЛЖНО БЫТЬ:
scopes = [
    "https://api.ebay.com/oauth/api_scope",  # Базовый scope для Identity API
    "https://api.ebay.com/oauth/api_scope/sell.account",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",  # Для Orders
    "https://api.ebay.com/oauth/api_scope/sell.finances",  # ДОБАВИТЬ - для Transactions
    "https://api.ebay.com/oauth/api_scope/sell.inventory",  # Для Inventory/Offers
    "https://api.ebay.com/oauth/api_scope/trading"  # ДОБАВИТЬ - для Messages
]
```

---

### ШАГ 4: Проверить Orders API фильтр

**Файл:** `backend/app/services/ebay.py`  
**Метод:** `sync_all_orders()`

**Текущий код:**
```python
params["filter"] = f"lastmodifieddate:[{since_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{until_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')}]"
```

**По "умному другу":** Формат правильный (RSQL), но нужно убедиться что он правильно URL-encoded. httpx должен делать это автоматически, но стоит проверить.

---

## 🔍 Что нужно проверить вручную

### 1. Проверить токен через curl

**Identity API:**
```bash
curl -H "Authorization: Bearer YOUR_ACTUAL_TOKEN_HERE" \
     "https://api.ebay.com/identity/v1/oauth2/userinfo"
```

**Ожидаемый результат:** JSON с `user_id`, `email`, `username`  
**Если 401/403/null → токен невалиден**

---

**Orders API (без фильтра):**
```bash
curl -H "Authorization: Bearer YOUR_ACTUAL_TOKEN_HERE" \
     "https://api.ebay.com/sell/fulfillment/v1/order?limit=5"
```

**Ожидаемый результат:** `{"orders": [], "total": 0}` или список заказов  
**Если 404/401 → токен невалиден**

---

### 2. Проверить scope в eBay Developer Portal

1. Перейти в [eBay Developer Portal](https://developer.ebay.com/)
2. Найти ваше приложение
3. Проверить раздел "OAuth Scopes"
4. Убедиться что включены:
   - `sell.fulfillment`
   - `sell.finances` ⚠️ **КРИТИЧНО - может отсутствовать**
   - `sell.inventory`
   - `trading` ⚠️ **КРИТИЧНО - может отсутствовать**

---

### 3. Получить новый токен с правильными scope

**Важно:** После добавления scope в код, нужно:
1. Отключиться от eBay в приложении
2. Подключиться заново (чтобы запросить новый токен с новыми scope)
3. Проверить что новый токен работает

---

## 📝 Правильные форматы запросов (по "умному другу")

### Identity API
```
GET https://api.ebay.com/identity/v1/oauth2/userinfo
Headers:
  Authorization: Bearer <token>
  Accept: application/json
```

### Orders API
```
GET https://api.ebay.com/sell/fulfillment/v1/order?limit=200&offset=0
Query params (опционально):
  filter=createdDate:[2025-08-08T00:00:00.000Z..2025-11-06T23:59:59.999Z]  (RSQL, URL-encoded)
Headers:
  Authorization: Bearer <token>
  Accept: application/json
```

### Transactions API
```
GET https://api.ebay.com/sell/finances/v1/transaction?limit=200&offset=0
Query params (обязательно):
  filter=transactionDate:[2025-08-08T00:00:00.000Z..2025-11-06T23:59:59.999Z]  (RSQL, URL-encoded)
Headers:
  Authorization: Bearer <token>
  Accept: application/json
```

### Inventory API
```
GET https://api.ebay.com/sell/inventory/v1/inventory_item?limit=200&offset=0
Headers:
  Authorization: Bearer <token>
  Accept: application/json
```

### Offers API
```
GET https://api.ebay.com/sell/inventory/v1/offer?limit=200&offset=0
Headers:
  Authorization: Bearer <token>
  Accept: application/json
```

---

## ✅ Что делать дальше

1. **Исправить код** (Identity endpoint, Transactions filter, добавить scope)
2. **Получить новый токен** с правильными scope
3. **Проверить токен вручную** через curl
4. **Запустить синхронизацию** и проверить что `Connected as: XXXXX` появляется
5. **Проверить что данные начинают приходить**

---

## Обновление 2025-11-26 – Buy Offer / Sniper

> Историческая заметка: изначальный анализ ниже был сосредоточен на `sell.*` и `trading` scope.
> После внедрения Sniper-модуля и Buy Offer API нам понадобились дополнительные buy-* scope.

- В каталог `ebay_scope_definitions` добавлен scope
  `https://api.ebay.com/oauth/api_scope/buy.offer.auction` с `grant_type = 'user'` и `is_active = true`.
- Теперь **все новые токены**, полученные через стандартный `/ebay/auth/start`, содержат как минимум:
  - базовый scope `https://api.ebay.com/oauth/api_scope`;
  - scope `https://api.ebay.com/oauth/api_scope/buy.offer.auction` для работы Buy Offer Sniper (place_proxy_bid + getBidding).
- Если вы переподключаете аккаунт в продакшене и хотите использовать Sniper, убедитесь, что:
  - миграции Alembic, создающие/обновляющие `ebay_scope_definitions`, применены;
  - вы заново проходите OAuth flow, чтобы аккаунт получил токен с расширенным набором scope.

Остальной текст документа по-прежнему актуален как базовый разбор проблем с токенами и endpoint-ами.

---

## ❓ Вопросы для уточнения

1. **Где хранится текущий токен?** Нужно проверить его формат и scope
2. **Как получить новый токен?** Нужно убедиться что OAuth flow запрашивает все нужные scope
3. **Есть ли доступ к eBay Developer Portal?** Нужно проверить настройки приложения

---

**Вывод:** Проблема точно в токене и неправильных endpoint/форматах. После исправления кода и получения нового токена все должно заработать.
