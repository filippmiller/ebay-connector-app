# Критическое исправление: Дешифровка токенов в автоматических workers

## Проблема

Автоматические workers (Railway worker loop) получали зашифрованные токены (`ENC:v1:...`) вместо расшифрованных (`v^1.1...`), что приводило к 401 ошибкам от eBay API.

### Симптомы

- **Manual Run Now:** ✅ Работает идеально, токен расшифрован
- **Auto Worker:** ❌ 401 Unauthorized, токен в логах показывает `ENC:v1:...`

### Корневая причина

В `BaseWorker.run_for_account()`:

1. ✅ Вызывается `get_valid_access_token()` → возвращает правильно расшифрованный токен в `token_result.access_token`
2. ❌ Затем вызывается `ebay_account_service.get_token()` → возвращает объект `EbayToken` из БД
3. ❌ Используется `token.access_token` property → может вернуть `ENC:v1:...` если расшифровка не удалась в worker environment

**Проблема:** `token.access_token` property вызывает `crypto.decrypt()`, который может вернуть исходное зашифрованное значение, если:
- `SECRET_KEY` / `JWT_SECRET` отличается в worker environment
- Расшифровка не удалась по какой-то причине

## Решение

В `backend/app/services/ebay_workers/base_worker.py`:

**До исправления:**
```python
token_result = await get_valid_access_token(...)
token = ebay_account_service.get_token(db, ebay_account_id)
# token.access_token может вернуть ENC:v1:... ❌
```

**После исправления:**
```python
token_result = await get_valid_access_token(...)
token = ebay_account_service.get_token(db, ebay_account_id)

# Используем расшифрованный токен из token_result
decrypted_access_token = token_result.access_token

# Валидация: токен должен быть расшифрован
if decrypted_access_token.startswith("ENC:"):
    logger.error("Token still encrypted!")
    return None

# КРИТИЧЕСКИ ВАЖНО: Устанавливаем расшифрованный токен в объект
token._access_token = decrypted_access_token

# Теперь token.access_token вернет правильное значение ✅
```

### Как это работает

1. `get_valid_access_token()` гарантированно возвращает расшифрованный токен (использует правильный `SECRET_KEY`)
2. Мы устанавливаем `token._access_token = decrypted_access_token` (bypass property setter)
3. Когда `token.access_token` property вызывается, он делает `crypto.decrypt(_access_token)`
4. Так как `_access_token` теперь содержит расшифрованное значение (не начинается с `ENC:`), `crypto.decrypt()` вернет его как есть (backwards compatible behavior)

## Проверка

### Логи должны показывать:

**Правильно (после исправления):**
```
[transactions_worker] Token retrieved: account=... token_decrypted=yes token_prefix=v^1.1#...
```

**Неправильно (до исправления):**
```
[transactions_worker] Token retrieved: account=... token_decrypted=NO - STILL ENCRYPTED! token_prefix=ENC:v1:...
```

### Диагностика

Если видишь в логах:
```
⚠️ TOKEN STILL ENCRYPTED! account_id=... token_prefix=ENC:v1:...
```

Это означает:
1. `get_valid_access_token()` не смог расшифровать токен
2. Проверь `SECRET_KEY` / `JWT_SECRET` в worker environment
3. Убедись, что они совпадают с основным приложением

## Файлы изменены

- `backend/app/services/ebay_workers/base_worker.py` - основное исправление
- `backend/app/services/ebay_workers/transactions_worker.py` - дополнительное логирование

## Важно

Это исправление применяется ко **всем** workers, которые наследуются от `BaseWorker`:
- TransactionsWorker
- OrdersWorker
- OffersWorker
- MessagesWorker
- CasesWorker
- FinancesWorker
- ActiveInventoryWorker
- ReturnsWorker
- и т.д.

Все они теперь используют правильно расшифрованный токен из `get_valid_access_token()`.

