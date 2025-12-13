# Railway Setup Instructions

## Start Command

В Railway → Settings → Deploy → Start Command установи:

```bash
bash backend/start.sh
```

**Важно:** Railway запускает команды из корня репозитория, поэтому путь должен быть `backend/start.sh`, а не просто `start.sh`.

## Environment Variables

Добавь в Railway → Variables:

1. `RUN_MIGRATIONS=1` (или `0` для временного отключения миграций при диагностике)
2. `PYTHONUNBUFFERED=1` (уже установлен в start.sh, но можно добавить явно)
3. `NIXPACKS_PREBUILD=bash scripts/install_msodbc18.sh` — установка Microsoft ODBC Driver 18 для MSSQL (msodbcsql18)

## Проверка после деплоя

1. **Health check:**
   ```bash
   curl -i https://<railway-app>.railway.app/healthz
   # Должен вернуть: 200 {"status": "ok"}
   ```

2. **Database health check:**
   ```bash
   curl -i https://<railway-app>.railway.app/healthz/db
   # Должен вернуть: 200 {"status": "ok", "database": "connected"}
   ```

3. **Проверка логов:**
   - Попробуй залогиниться с фронта
   - В Railway Logs должны появиться:
     - `→ POST /auth/login rid=xxxxx`
     - Детальные логи с request ID
     - Если ошибка - полный stacktrace с RID

## Диагностика проблем

### Если контейнер постоянно рестартится:

1. Установи `RUN_MIGRATIONS=0` в Railway Variables
2. Перезапусти сервис
3. Если перестал падать → проблема в миграциях Alembic
4. Если всё равно падает → проблема в старте/конфиге

### Если 500 ошибка при логине:

1. Проверь Railway Logs - должен быть полный stacktrace с RID
2. Проверь `/healthz/db` - работает ли подключение к БД
3. В логах с `echo=True` будут видны все SQL запросы

## Request ID (RID)

Каждый запрос получает уникальный Request ID:
- В логах: `rid=xxxxx`
- В заголовках ответа: `X-Request-ID: xxxxx`
- В UI ошибках: показывается RID для связи с логами

