# План: Полная поддержка Sandbox + Production

## 📋 Как я понял задачу

**Цель:** Сделать возможность работать с sandbox и production одновременно, с понятным переключением между средами.

**Текущая ситуация:**
- В БД есть `ebay_environment` (default="sandbox"), но только один набор токенов
- В config.py уже есть разделение на SANDBOX и PRODUCTION credentials
- Но логика выбора токена основана на глобальном `settings.EBAY_ENVIRONMENT`, а не на `user.ebay_environment`
- Нет отдельных полей для sandbox токенов

**Что нужно сделать:**
1. Добавить поля в БД для sandbox токенов (отдельно от production)
2. Изменить логику выбора токена на основе `user.ebay_environment`
3. Добавить переключатель environment в UI
4. Обновить debugger для отображения текущей среды
5. Изменить `get_authorization_url()` для поддержки sandbox auth URL

---

## 🔧 План изменений

### 1. Миграция БД - Добавить поля для sandbox токенов

**Файл:** Создать новую миграцию Alembic

**Изменения:**
```sql
ALTER TABLE users 
ADD COLUMN ebay_sandbox_access_token TEXT,
ADD COLUMN ebay_sandbox_refresh_token TEXT,
ADD COLUMN ebay_sandbox_token_expires_at TIMESTAMP;

-- Изменить default для ebay_environment на 'production' (или оставить 'sandbox')
ALTER TABLE users 
ALTER COLUMN ebay_environment SET DEFAULT 'sandbox';
```

**Файлы:**
- Создать новую миграцию: `backend/alembic/versions/XXXX_add_sandbox_tokens.py`
- Обновить модель: `backend/app/models_sqlalchemy/models.py`

---

### 2. Обновить модель User

**Файл:** `backend/app/models_sqlalchemy/models.py`

**Добавить поля:**
```python
ebay_sandbox_access_token = Column(Text, nullable=True)
ebay_sandbox_refresh_token = Column(Text, nullable=True)
ebay_sandbox_token_expires_at = Column(DateTime, nullable=True)
```

**Обновить Pydantic модель:** `backend/app/models/user.py`
```python
ebay_sandbox_access_token: Optional[str] = None
ebay_sandbox_refresh_token: Optional[str] = None
ebay_sandbox_token_expires_at: Optional[datetime] = None
```

---

### 3. Создать helper функцию для выбора токена

**Файл:** `backend/app/services/ebay.py` или новый `backend/app/utils/ebay_token_helper.py`

**Функция:**
```python
def get_user_ebay_token(user: User, environment: Optional[str] = None) -> Optional[str]:
    """
    Get eBay access token for user based on environment.
    If environment is None, uses user.ebay_environment.
    """
    env = environment or user.ebay_environment or "sandbox"
    
    if env == "sandbox":
        return user.ebay_sandbox_access_token
    else:
        return user.ebay_access_token

def get_user_ebay_refresh_token(user: User, environment: Optional[str] = None) -> Optional[str]:
    """Get eBay refresh token for user based on environment."""
    env = environment or user.ebay_environment or "sandbox"
    
    if env == "sandbox":
        return user.ebay_sandbox_refresh_token
    else:
        return user.ebay_refresh_token

def save_user_ebay_tokens(user_id: str, access_token: str, refresh_token: str, 
                          expires_at: datetime, environment: str):
    """Save eBay tokens to appropriate fields based on environment."""
    # Implementation in database service
```

---

### 4. Изменить get_authorization_url() для поддержки environment

**Файл:** `backend/app/services/ebay.py`

**Изменения:**
- Добавить параметр `environment: str = "production"` в `get_authorization_url()`
- Использовать правильный auth URL в зависимости от environment:
  ```python
  if environment == "sandbox":
      auth_url = "https://auth.sandbox.ebay.com/oauth2/authorize"
  else:
      auth_url = "https://auth.ebay.com/oauth2/authorize"
  ```
- Использовать правильные credentials из config в зависимости от environment

---

### 5. Обновить все места, где используется токен

**Файлы:**
- `backend/app/routers/ebay.py` - все endpoints
- `backend/app/services/ebay.py` - все методы
- `backend/app/utils/ebay_debugger.py` - debugger

**Изменения:**
- Заменить `current_user.ebay_access_token` на `get_user_ebay_token(current_user, environment)`
- Использовать `user.ebay_environment` вместо `settings.EBAY_ENVIRONMENT` где возможно
- При сохранении токенов - сохранять в правильные поля в зависимости от environment

---

### 6. Обновить OAuth callback для сохранения токенов

**Файл:** `backend/app/routers/ebay.py` - `ebay_auth_callback()`

**Изменения:**
- Получать `environment` из query params или state
- Сохранять токены в правильные поля:
  ```python
  if environment == "sandbox":
      db.update_user(user_id, {
          "ebay_sandbox_access_token": access_token,
          "ebay_sandbox_refresh_token": refresh_token,
          "ebay_sandbox_token_expires_at": expires_at,
          "ebay_environment": "sandbox"
      })
  else:
      db.update_user(user_id, {
          "ebay_access_token": access_token,
          "ebay_refresh_token": refresh_token,
          "ebay_token_expires_at": expires_at,
          "ebay_environment": "production"
      })
  ```

---

### 7. Добавить переключатель Environment в UI

**Файл:** `frontend/src/pages/EbayConnectionPage.tsx`

**Изменения:**
- Добавить Select/Dropdown для выбора environment (sandbox/production)
- При подключении передавать выбранный environment
- Отображать текущий environment в статусе подключения

**Файл:** `frontend/src/components/EbayDebugger.tsx`

**Изменения:**
- В REQUEST CONTEXT показывать текущий environment
- Показывать какой токен используется (sandbox или production)
- Добавить переключатель environment (если нужно)

---

### 8. Обновить debugger для отображения environment

**Файл:** `backend/app/routers/ebay.py` - `debug_ebay_api()`

**Изменения:**
- В `request_context` показывать:
  - `environment`: `user.ebay_environment`
  - `token_source`: "sandbox" или "production"
  - Правильный токен в зависимости от environment

---

### 9. Обновить sync endpoints для использования правильного токена

**Файл:** `backend/app/routers/ebay.py` - все sync endpoints

**Изменения:**
- Использовать `get_user_ebay_token(current_user)` вместо `current_user.ebay_access_token`
- Использовать `user.ebay_environment` для выбора правильного API URL

---

## 📝 Данные, которые нужны для Sandbox

**Вопросы к пользователю:**

1. **RuName (Redirect URI Name):**
   - Где взять: eBay Developer Portal → My Account → Keys → Sandbox Keys
   - Где хранить: `.env` файл как `EBAY_SANDBOX_RUNAME`
   - Формат: строка, например `Filipp_Miller-FilippMil-SBX-xxx-xxx`

2. **Client ID (App ID):**
   - Где взять: eBay Developer Portal → My Account → Keys → Sandbox Keys
   - Где хранить: `.env` файл как `EBAY_SANDBOX_CLIENT_ID`
   - Формат: строка, например `FilippMi-SBX-xxx-xxx`

3. **Client Secret (Cert ID):**
   - Где взять: eBay Developer Portal → My Account → Keys → Sandbox Keys
   - Где хранить: `.env` файл как `EBAY_SANDBOX_CERT_ID`
   - Формат: строка

4. **Dev ID (опционально):**
   - Где взять: eBay Developer Portal → My Account → Keys → Sandbox Keys
   - Где хранить: `.env` файл как `EBAY_SANDBOX_DEV_ID`
   - Формат: строка

5. **Redirect URI:**
   - Обычно совпадает с RuName
   - Где хранить: `.env` файл как `EBAY_SANDBOX_REDIRECT_URI`

**Где хранить:**
- В `.env` файле на сервере (Railway)
- В `.env.local` для локальной разработки (не коммитить в git!)
- Уже есть структура в `config.py` - нужно только заполнить значения

---

## ✅ Чеклист выполнения

- [ ] 1. Создать миграцию БД для sandbox токенов
- [ ] 2. Обновить модель User (SQLAlchemy + Pydantic)
- [ ] 3. Создать helper функции для выбора токена
- [ ] 4. Изменить `get_authorization_url()` для поддержки environment
- [ ] 5. Обновить OAuth callback для сохранения токенов в правильные поля
- [ ] 6. Обновить все места использования токена
- [ ] 7. Добавить переключатель environment в UI
- [ ] 8. Обновить debugger для отображения environment
- [ ] 9. Обновить sync endpoints
- [ ] 10. Протестировать подключение к sandbox
- [ ] 11. Протестировать переключение между sandbox и production

---

## 🎯 Ожидаемый результат

После выполнения:
- ✅ Можно подключиться к sandbox и production одновременно
- ✅ Токены хранятся отдельно для каждой среды
- ✅ Переключение между средами через UI
- ✅ В debugger видно какая среда используется
- ✅ Все API запросы используют правильный токен и URL

---

## ❓ Вопросы к пользователю

1. **Sandbox credentials:**
   - Есть ли у вас уже sandbox credentials в eBay Developer Portal?
   - Если да, можете предоставить:
     - `EBAY_SANDBOX_CLIENT_ID`
     - `EBAY_SANDBOX_CERT_ID`
     - `EBAY_SANDBOX_RUNAME`
     - `EBAY_SANDBOX_DEV_ID` (опционально)

2. **Default environment:**
   - Какой environment должен быть по умолчанию: `sandbox` или `production`?
   - Сейчас в БД default="sandbox", но в задаче указано "production"

3. **UI переключатель:**
   - Где должен быть переключатель environment?
   - В странице "eBay Connection" рядом с кнопкой подключения?
   - Или в отдельном месте?

4. **Миграция:**
   - Нужно ли сохранить существующие production токены при миграции?
   - Или можно их потерять (пользователь переподключится)?

---

## 📌 Важные замечания

- **Безопасность:** Не коммитить credentials в git
- **Миграция:** Сделать backup БД перед миграцией
- **Тестирование:** Сначала протестировать на sandbox, потом на production
- **Обратная совместимость:** Убедиться что существующие production токены продолжают работать

