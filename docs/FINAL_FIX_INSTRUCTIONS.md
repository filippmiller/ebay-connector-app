# Финальные инструкции для исправления синхронизации

**Дата:** 2025-01-XX  
**Статус:** Готов к финальному тесту

---

## ✅ EBAY SYNC — СТАТУС: ГОТОВ К ФИНАЛЬНОМУ ТЕСТУ

### Анализ TOKEN_VALIDATION_GUIDE.md + предыдущих данных:

- ✅ Все нужные scope есть: `sell.fulfillment`, `sell.finances`, `sell.inventory`, `sell.payment.dispute`
- ⚠️ Scope `trading` отсутствует → Messages временно отключить
- ✅ Токен должен быть валиден после удаления `trading` из запроса

---

## 🔧 ФИНАЛЬНАЯ ИНСТРУКЦИЯ:

### 1. ✅ УДАЛЕН scope `trading` из списка scope в `get_authorization_url()`

**Исправлено:**
```python
scopes = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.account",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
    "https://api.ebay.com/oauth/api_scope/sell.finances",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    # "https://api.ebay.com/oauth/api_scope/trading"  # REMOVED - not activated in app
]
```

---

### 2. ⚠️ Messages sync - временно отключить

**Примечание:** Messages sync вызывается отдельно через роутер `/api/messages/sync`, так что просто не запускайте его до тех пор, пока не добавите scope `commerce.message` или не активируете `trading` в eBay Developer Portal.

**Альтернатива:** Можно добавить scope `commerce.message` для нового REST API Messages, но это потребует изменения кода Messages sync.

---

### 3. 🔄 ПЕРЕПОДКЛЮЧИТЕСЬ к eBay → получите новый токен

**Шаги:**
1. Откройте приложение
2. Перейдите в "eBay Connection"
3. Нажмите "Disconnect from eBay"
4. Нажмите "Connect to eBay" снова
5. Пройдите OAuth flow
6. Убедитесь что запрашиваются только активированные scope (без `trading`)

---

### 4. 📝 ПРОВЕРЬТЕ токен:

```bash
curl -H "Authorization: Bearer $NEW_TOKEN" \
     "https://api.ebay.com/identity/v1/oauth2/userinfo"
```

**Ожидаемый результат:**
- ✅ JSON с `user_id` и `username` → токен валиден
- ❌ 401/403/null → токен невалиден, нужно переподключиться

---

### 5. ▶️ ЗАПУСТИТЕ синхронизацию:

**Что должно работать:**
- ✅ **Orders** → должен работать (filter: `lastModifiedDate:[...]`)
- ✅ **Transactions** → должен работать (filter: `transactionDate:[...]`)
- ✅ **Disputes** → должен работать (endpoint: `/sell/fulfillment/v1/payment_dispute`)
- ✅ **Offers** → должен работать (endpoint: `/sell/inventory/v1/inventory_item`)
- ⚠️ **Messages** → временно отключен (нет scope `trading`)

---

## 🎯 ЦЕЛЬ:

**Получить `Connected as: [user_id]` и хотя бы 1 заказ/транзакцию.**

---

## 📋 Чек-лист перед тестом:

- [x] Scope `trading` удален из кода
- [ ] Переподключиться к eBay (получить новый токен)
- [ ] Проверить токен через curl
- [ ] Запустить синхронизацию Orders
- [ ] Проверить логи - должно быть `Connected as: XXXXX`
- [ ] Проверить что Orders/Transactions/Disputes работают

---

## 🔍 Что проверить в логах:

1. **Identity API:**
   ```
   Connected as: [username] (eBay UserID: [user_id])
   ```
   - Должно быть НЕ None!

2. **Orders API:**
   ```
   → Requesting page 1: GET /sell/fulfillment/v1/order?limit=200&offset=0&filter=lastModifiedDate:[...]
   ← Response: 200 OK - Received X orders
   ```
   - Должен быть 200 OK (даже если 0 orders)

3. **Transactions API:**
   ```
   → Requesting page 1: GET /sell/finances/v1/transaction?limit=200&offset=0&filter=transactionDate:[...]
   ← Response: 200 OK - Received X transactions
   ```
   - Должен быть 200 OK (даже если 0 transactions)

---

## 📌 Следующие шаги после успешного теста:

1. Если все работает - добавить scope `commerce.message` для Messages API
2. Или активировать scope `trading` в eBay Developer Portal
3. Протестировать Messages sync с правильным scope

---

**Готов — жду результат!**

