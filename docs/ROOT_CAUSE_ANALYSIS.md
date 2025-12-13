# ROOT CAUSE ANALYSIS: Encrypted Token Issue

## Проблема
Railway worker отправляет зашифрованные токены (`ENC:v1:...`) в eBay API вместо расшифрованных (`v^1.1#...`), что приводит к 401 ошибкам.

## Анализ логов

### Что видно в логах:
1. ❌ `Token: ENC:v1:uSv***dXe7l34Q==` - токен зашифрован
2. ❌ `Headers: {'Authorization': 'Bearer ENC:v1:...'}` - зашифрованный токен отправляется в eBay
3. ❌ `Identity API error 401: Invalid access token` - eBay отклоняет зашифрованный токен
4. ❌ НЕТ сообщений `[fetch_active_ebay_token]` - функция не вызывается
5. ❌ НЕТ сообщений `[transactions_worker] Calling fetch_active_ebay_token` - BaseWorker.run_for_account() не вызывается или код не задеплоился
6. ❌ НЕТ BUILD_NUMBER в логах - новый код не задеплоился

### Что НЕ видно в логах:
- ✅ `[fetch_active_ebay_token] ✅ Token retrieved successfully` - НЕТ
- ✅ `[transactions_worker] Calling fetch_active_ebay_token` - НЕТ
- ✅ `BUILD=5e52b74` - НЕТ
- ✅ `Running workers cycle (manual code path)...` - НЕТ
- ✅ `[transactions_proxy] Triggering transactions sync via ...` - НЕТ

## Выводы

### 1. Код не задеплоился на Railway worker
В логах НЕТ BUILD_NUMBER и новых диагностических сообщений, которые были добавлены в последних коммитах.

### 2. Railway worker НЕ использует proxy mode
В логах НЕТ сообщений о proxy mode (`[transactions_proxy]`, `Triggering transactions sync via ...`).

### 3. Railway worker использует старый код
В логах НЕТ сообщений `[fetch_active_ebay_token]`, что означает, что `BaseWorker.run_for_account()` либо не вызывается, либо использует старый код без этой функции.

### 4. Токен берется напрямую из `token.access_token` property
В логах видно `Token: ENC:v1:...`, что означает, что токен берется из `token.access_token` property, которое вызывает `crypto.decrypt()`. Если `SECRET_KEY` неправильный в Railway worker, то `crypto.decrypt()` возвращает исходное зашифрованное значение.

## Решение

### КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ

Проблема в том, что `token.access_token` property вызывает `crypto.decrypt()`, который возвращает исходное значение, если расшифровка не удалась (из-за неправильного `SECRET_KEY` в Railway worker).

**Решение:** НЕ полагаться на `token.access_token` property в worker environment. Вместо этого использовать `fetch_active_ebay_token()`, который гарантирует расшифрованный токен.

НО! Проблема в том, что `BaseWorker.run_for_account()` уже использует `fetch_active_ebay_token()`, но в логах НЕТ сообщений об этом - значит код не задеплоился.

### ПЛАН ДЕЙСТВИЙ

1. **Проверить деплой на Railway worker:**
   - Убедиться, что последний коммит задеплоился
   - Проверить, что BUILD_NUMBER появляется в логах

2. **Проверить SECRET_KEY в Railway worker:**
   - Убедиться, что `SECRET_KEY` совпадает с web app
   - Если нет - установить правильный `SECRET_KEY`

3. **Проверить start command в Railway worker:**
   - Должно быть: `python -m app.workers.ebay_workers_loop` (proxy mode)
   - Или: `python -m app.workers.ebay_workers_loop transactions` (только transactions)

4. **Если код задеплоился, но проблема осталась:**
   - Проверить, что `BaseWorker.run_for_account()` действительно вызывается
   - Добавить больше логирования для отслеживания пути выполнения

## Текущий статус

- ❌ Код не задеплоился на Railway worker (нет BUILD_NUMBER в логах)
- ❌ Railway worker использует старый код (нет `[fetch_active_ebay_token]` в логах)
- ❌ Токен берется напрямую из `token.access_token` property (видно `ENC:v1:...` в логах)
- ❌ `SECRET_KEY` может быть неправильным в Railway worker (расшифровка не работает)

## Следующие шаги

1. Проверить деплой на Railway worker
2. Проверить `SECRET_KEY` в Railway worker
3. Проверить start command в Railway worker
4. Если все правильно - добавить больше логирования для диагностики

