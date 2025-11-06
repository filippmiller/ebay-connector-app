# Тестирование синхронизации - Раунд 3

**Дата:** 2025-01-XX  
**Тест:** Orders Sync с исправленным фильтром `lastModifiedDate`

---

## 🔧 Исправления в этом раунде:

1. ✅ **Orders filter:** `createdDate` → `lastModifiedDate` (вернули обратно)

---

## 📋 Результаты тестирования Orders Sync

### Identity API ❌
**Ожидаем:** `Connected as: XXX` (не None)  
**Фактически:**
```
[21:44:26] Connected as: None (eBay UserID: None)
```
**Проблема:** Identity API все еще возвращает None

---

### Orders Sync ❌
**Ожидаем:** 200 OK, хотя бы 1 заказ (или 0 если нет заказов)  
**Логи:**
```
[21:44:26] Starting Orders sync from eBay (production) - using bulk limit=200
[21:44:26] === WHO WE ARE ===
[21:44:26] Connected as: None (eBay UserID: None)
[21:44:26] Environment: production
[21:44:26] API Configuration: Fulfillment API v1, max batch size: 200 orders per request
[21:44:27] Date window: 2025-08-08T21:39:26.000Z..2025-11-06T21:44:26.000Z
[21:44:27] Safety limit: max 200 pages
[21:44:27] → Requesting page 1: GET /sell/fulfillment/v1/order?limit=200&offset=0
[21:44:27] Orders sync failed: 400: Failed to fetch orders: {'errors': [{'errorId': 30700, 'domain': 'API_FULFILLMENT', 'category': 'REQUEST', 'message': "Invalid filter name: 'lastModifiedDate'", 'parameters': [{'name': 'filterName', 'value': 'lastModifiedDate'}]}]}
[00:44:27] Connection error: Failed to stream events. Check network connection.
```

**Network запрос:**
```
POST /api/ebay/sync/orders
→ Backend делает:
GET /sell/fulfillment/v1/order?limit=200&offset=0&filter=lastModifiedDate:[2025-08-08T21:39:26.000Z..2025-11-06T21:44:26.000Z]&fieldGroups=TAX_BREAKDOWN
```

**Результат:**
- [x] FAILED
- [x] HTTP код: 400
- [x] Количество заказов: 0
- [x] Ошибки: `Invalid filter name: 'lastModifiedDate'` - **lastModifiedDate тоже неправильное имя!**

---

## 🐛 Проблемы

### Проблема 1: Orders API - lastModifiedDate тоже неправильное имя фильтра
**Описание:** eBay API говорит что `lastModifiedDate` - неправильное имя фильтра (как и `createdDate`)
**Логи:** `Invalid filter name: 'lastModifiedDate'`
**Ожидаемое поведение:** Фильтр должен работать
**Фактическое поведение:** 400 Bad Request
**Критический вывод:** 
- ❌ `lastModifiedDate` - неправильное имя
- ❌ `createdDate` - неправильное имя
- ❓ Какое правильное имя фильтра? Может быть фильтр вообще не нужен для Orders API?

### Проблема 2: Identity API - все еще None
**Описание:** Identity API возвращает None
**Логи:** `Connected as: None (eBay UserID: None)`
**Ожидаемое поведение:** Должен вернуть username и userId
**Фактическое поведение:** None

---

## ✅ Что работает

- 

---

## ❌ Что не работает

- ❌ **Orders Sync** - `lastModifiedDate` тоже неправильное имя фильтра
- ❌ **Identity API** - все еще возвращает None

---

## 📊 Сводка результатов

| Sync Type | Status | HTTP Code | Количество | Проблемы |
|-----------|--------|-----------|------------|----------|
| **Orders** | ❌ FAILED | 400 | 0 | Invalid filter name: 'lastModifiedDate' |

---

## 💡 Выводы

- **Критическая проблема:** Ни `lastModifiedDate`, ни `createdDate` не работают как имена фильтров для Orders API
- eBay API отклоняет оба варианта с ошибкой `Invalid filter name`
- Нужно проверить документацию eBay API для правильного имени фильтра или убрать фильтр вообще

---

## 📌 Следующие шаги

1. **Проверить документацию eBay API** для Orders API - какое правильное имя фильтра?
2. **Попробовать без фильтра** - может быть фильтр вообще не нужен?
3. **Проверить другие варианты** - может быть `orderDate`, `creationDate`, или другой формат?

