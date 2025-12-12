# Проверка Railway Worker Configuration

## 1. Проверка команды запуска в Railway

### Шаги:

1. Открой Railway Dashboard: https://railway.app
2. Выбери проект `pretty-exploration` (или твой проект)
3. Найди сервис **`aebay-workers-loop`**
4. Перейди в **Settings → Deploy**
5. Проверь поле **Start Command**

### Ожидаемая команда:

**Вариант 1 (рекомендуется - proxy mode для всех workers):**
```bash
python -m app.workers.ebay_workers_loop
```

**Вариант 2 (только transactions worker в proxy mode):**
```bash
python -m app.workers.ebay_workers_loop transactions
```

### ❌ НЕ должно быть:

```bash
# Это НЕ proxy mode - может иметь проблемы с токенами
python -m app.workers.ebay_workers_loop --direct
# или любая другая команда, которая вызывает run_ebay_workers_loop() напрямую
```

### Как это работает:

Когда запускается `python -m app.workers.ebay_workers_loop`, выполняется блок:

```python
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    
    if mode == "transactions":
        asyncio.run(run_transactions_worker_proxy_loop())
    else:
        asyncio.run(run_ebay_workers_proxy_loop())  # ← Это proxy mode!
```

Это означает, что worker будет вызывать внутренний endpoint `/api/admin/internal/workers/transactions/run-once` вместо прямых вызовов eBay API.

---

## 2. Проверка переменных окружения

### Шаги:

1. В том же сервисе **`aebay-workers-loop`** перейди в **Variables**
2. Проверь наличие следующих переменных:

### Обязательные переменные:

#### ✅ `WEB_APP_URL`
- **Значение:** URL основного приложения (ebay-connector-app)
- **Пример:** `https://ebay-connector-app-production.up.railway.app`
- **Использование:** Worker использует это для вызова внутренних endpoints

#### ✅ `INTERNAL_API_KEY`
- **Значение:** Секретный ключ для аутентификации внутренних endpoints
- **Должен совпадать** с тем же ключом в основном приложении (`ebay-connector-app`)
- **Использование:** Передаётся в заголовке/теле запроса к внутренним endpoints

### Дополнительные переменные (обычно наследуются):

- `DATABASE_URL` - для подключения к БД (если worker нужен доступ напрямую)
- `EBAY_ENVIRONMENT` - sandbox/production
- Другие переменные из основного приложения

---

## 3. Проверка логов

### Что искать в логах Railway сервиса `aebay-workers-loop`:

#### ✅ Правильные логи (proxy mode):

```
Starting ALL workers proxy loop...
[transactions_proxy] Triggering transactions sync via https://ebay-connector-app-production.up.railway.app/api/admin/internal/workers/transactions/run-once...
[transactions_proxy] SUCCESS: status=ok processed=2 succeeded=2 failed=0
```

Или для transactions-only mode:

```
Starting Transactions-only worker proxy loop...
[transactions_proxy] Triggering transactions sync via ...
```

#### ❌ Неправильные логи (direct mode - может иметь проблемы):

```
Running workers cycle (manual code path)...
Running workers for 2 accounts...
Worker transactions started for Account Name: run_id=...
```

Если видишь такие логи, значит worker НЕ использует proxy mode и может иметь проблемы с токенами.

#### ❌ Ошибки конфигурации:

```
[transactions_proxy] WEB_APP_URL not configured
[transactions_proxy] INTERNAL_API_KEY not configured
[transactions_proxy] FAILED: HTTP 401 - invalid_internal_api_key
```

Это означает, что переменные окружения не установлены или неправильные.

---

## 4. Быстрая проверка через Railway CLI

Если у тебя установлен Railway CLI:

```bash
# Проверить переменные окружения
railway variables --service aebay-workers-loop

# Проверить логи
railway logs --service aebay-workers-loop

# Проверить статус
railway status
```

---

## 5. Проверка через API (если есть доступ)

Можно проверить, что внутренний endpoint работает:

```bash
curl -X POST https://ebay-connector-app-production.up.railway.app/api/admin/internal/workers/transactions/run-once \
  -H "Content-Type: application/json" \
  -d '{"internal_api_key": "YOUR_INTERNAL_API_KEY"}'
```

Если вернётся JSON с `status: "ok"` и `correlation_id`, значит endpoint работает правильно.

---

## 6. Что делать, если что-то не так

### Проблема: Команда запуска неправильная

1. Измени Start Command в Railway Settings → Deploy
2. Установи: `python -m app.workers.ebay_workers_loop`
3. Перезапусти сервис

### Проблема: Отсутствуют переменные окружения

1. Перейди в Variables сервиса `aebay-workers-loop`
2. Добавь `WEB_APP_URL` и `INTERNAL_API_KEY`
3. Убедись, что `INTERNAL_API_KEY` совпадает с основным приложением
4. Перезапусти сервис

### Проблема: 401 ошибки в логах

1. Проверь, что `INTERNAL_API_KEY` совпадает в обоих сервисах
2. Проверь, что `WEB_APP_URL` указывает на правильный URL
3. Проверь логи основного приложения на наличие ошибок

---

## 7. Альтернатива: Использовать основной сервис

Если Railway worker service вызывает проблемы, можно отключить отдельный сервис `aebay-workers-loop` и использовать встроенный loop в основном приложении:

В `backend/app/main.py` уже есть:
```python
asyncio.create_task(run_ebay_workers_loop())
```

Это означает, что workers будут запускаться из основного приложения каждые 5 минут. В этом случае отдельный Railway worker service не нужен.

---

## Резюме чеклиста:

- [ ] Start Command: `python -m app.workers.ebay_workers_loop`
- [ ] Переменная `WEB_APP_URL` установлена и правильная
- [ ] Переменная `INTERNAL_API_KEY` установлена и совпадает с основным приложением
- [ ] В логах видно `[transactions_proxy]` или `Starting ALL workers proxy loop...`
- [ ] Нет ошибок `WEB_APP_URL not configured` или `INTERNAL_API_KEY not configured`
- [ ] Нет 401 ошибок в логах

