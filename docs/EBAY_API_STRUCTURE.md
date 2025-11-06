# 🔍 Структура вызовов eBay API

## 📁 Расположение файлов

### Backend
- **Сервис eBay API**: `backend/app/services/ebay.py`
  - Класс: `EbayService`
  - Методы: `get_user_identity()`, `sync_all_orders()`, и др.

- **API Роутеры**: `backend/app/routers/ebay.py`
  - Endpoint: `POST /ebay/sync/orders`
  - Endpoint: `GET /ebay/debug/templates`

### Frontend
- **Страница подключения**: `frontend/src/pages/EbayConnectionPage.tsx`
- **API клиент**: `frontend/src/lib/apiClient.ts`
- **Компонент Debugger**: `frontend/src/components/EbayDebugger.tsx`

---

## 1️⃣ Функция `get_user_identity()`

### 📍 Расположение
**Файл**: `backend/app/services/ebay.py`  
**Строки**: 413-474  
**Класс**: `EbayService`

### 📝 Полный код функции

```python
async def get_user_identity(self, access_token: str) -> Dict[str, Any]:
    """
    Get eBay user identity (username, userId) from access token using Identity API
    """
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="eBay access token required"
        )
    
    api_url = f"{settings.ebay_api_base_url}/identity/v1/oauth2/userinfo"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            response = await client.get(api_url, headers=headers)
            
            logger.info(f"Identity API response status: {response.status_code}")
            logger.info(f"Identity API response headers: {dict(response.headers)}")
            
            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = str(error_json)
                    logger.error(f"Identity API error {response.status_code}: {error_json}")
                except:
                    logger.error(f"Identity API error {response.status_code}: {error_detail}")
                logger.warning(f"Failed to get user identity: {response.status_code} - {error_detail}")
                return {"username": None, "userId": None, "error": error_detail}
            
            # Log raw response for debugging
            response_text = response.text
            logger.info(f"Identity API raw response: {response_text[:500]}")
            
            try:
                identity_data = response.json()
                logger.info(f"Identity API parsed JSON: {identity_data}")
            except Exception as json_error:
                logger.error(f"Failed to parse Identity API response as JSON: {json_error}, raw: {response_text[:200]}")
                return {"username": None, "userId": None, "error": f"Invalid JSON response: {str(json_error)}"}
            
            # eBay Identity API returns user_id (not userId) and username
            username = identity_data.get("username")
            user_id = identity_data.get("user_id") or identity_data.get("userId")
            
            logger.info(f"Extracted from Identity API - username: {username}, userId: {user_id}")
            
            return {
                "username": username,
                "userId": user_id,
                "accountType": identity_data.get("accountType"),
                "registrationMarketplaceId": identity_data.get("registrationMarketplaceId"),
                "raw_response": identity_data
            }
    except Exception as e:
        logger.error(f"Error getting user identity: {str(e)}", exc_info=True)
        return {"username": None, "userId": None, "error": str(e)}
```

### 🔄 Как вызывается

#### 1. Из `sync_all_orders()` (внутри сервиса)
```python
# backend/app/services/ebay.py, строка 621
identity = await self.get_user_identity(access_token)
username = identity.get("username", "unknown")
ebay_user_id = identity.get("userId", "unknown")
```

#### 2. Из других sync функций
- `sync_all_transactions()` - строка 1203
- `sync_all_disputes()` - аналогично
- `sync_all_offers()` - аналогично

### 📊 Структура вызова

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend: EbayConnectionPage.tsx                            │
│   handleSyncOrders()                                        │
│     ↓ POST /api/ebay/sync/orders                           │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Backend Router: backend/app/routers/ebay.py                 │
│   @router.post("/sync/orders")                              │
│     ↓ Получает current_user из токена                       │
│     ↓ Извлекает access_token из current_user                │
│     ↓ Создает run_id для логирования                        │
│     ↓ Вызывает ebay_service.sync_all_orders()               │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Backend Service: backend/app/services/ebay.py               │
│   EbayService.sync_all_orders()                             │
│     ↓ Вызывает self.get_user_identity(access_token)         │
│     ↓ Формирует URL: /identity/v1/oauth2/userinfo           │
│     ↓ Добавляет headers: Authorization: Bearer {token}      │
│     ↓ Делает GET запрос через httpx                         │
│     ↓ Парсит JSON ответ                                     │
│     ↓ Извлекает username и userId                           │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ eBay Identity API                                           │
│   GET https://api.ebay.com/identity/v1/oauth2/userinfo      │
│   Headers: Authorization: Bearer {access_token}             │
│   Response: { "username": "...", "user_id": "..." }        │
└─────────────────────────────────────────────────────────────┘
```

---

## 2️⃣ Функция `sync_all_orders()`

### 📍 Расположение
**Файл**: `backend/app/services/ebay.py`  
**Строки**: 593-800+  
**Класс**: `EbayService`

### 📝 Полный код функции (ключевые части)

```python
async def sync_all_orders(self, user_id: str, access_token: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Sync all orders from eBay Fulfillment API
    """
    from app.services.ebay_database import ebay_db
    from app.services.sync_event_logger import SyncEventLogger
    import time
    
    # Use provided run_id if available, otherwise create new one
    event_logger = SyncEventLogger(user_id, 'orders', run_id=run_id)
    job_id = ebay_db.create_sync_job(user_id, 'orders')
    start_time = time.time()
    
    try:
        total_fetched = 0
        total_stored = 0
        limit = ORDERS_PAGE_LIMIT  # 200
        offset = 0
        has_more = True
        current_page = 0
        max_pages = 200  # Safety limit
        
        # Get user identity for logging "who we are"
        identity = await self.get_user_identity(access_token)
        username = identity.get("username", "unknown")
        ebay_user_id = identity.get("userId", "unknown")
        
        # Log Identity API errors if any
        if identity.get("error"):
            event_logger.log_error(f"Identity API error: {identity.get('error')}")
            event_logger.log_warning("⚠️ Token may be invalid or missing required scopes.")
        
        # Date window with 5-10 minute cushion
        from datetime import datetime, timedelta
        until_date = datetime.utcnow()
        since_date = until_date - timedelta(days=90)
        since_date = since_date - timedelta(minutes=5)
        
        event_logger.log_start(f"Starting Orders sync from eBay ({settings.EBAY_ENVIRONMENT})")
        event_logger.log_info(f"=== WHO WE ARE ===")
        event_logger.log_info(f"Connected as: {username} (eBay UserID: {ebay_user_id})")
        
        while has_more:
            # Safety check: max pages limit
            if current_page >= max_pages:
                event_logger.log_warning(f"Reached safety limit of {max_pages} pages.")
                break
            
            # Check for cancellation
            if is_cancelled(event_logger.run_id):
                # ... handle cancellation
                return {"status": "cancelled", ...}
            
            current_page += 1
            
            # Prepare filter parameters
            filter_params = {
                "filter": "orderStatus:COMPLETED",  # Filter by order status
                "limit": limit,
                "offset": offset,
                "fieldGroups": "TAX_BREAKDOWN"
            }
            
            # Check cancellation before API request
            if is_cancelled(event_logger.run_id):
                # ... handle cancellation
                return {"status": "cancelled", ...}
            
            # Fetch orders from eBay API
            try:
                orders_data = await self.fetch_orders(access_token, filter_params)
                # ... process orders_data
                # ... store in database
                # ... update pagination
            except Exception as e:
                # ... handle errors
                
        # Return final result
        return {
            "status": "completed",
            "total_fetched": total_fetched,
            "total_stored": total_stored,
            "job_id": job_id,
            "run_id": event_logger.run_id
        }
```

### 🔄 Как вызывается

#### 1. Из API роутера
```python
# backend/app/routers/ebay.py, строки 267-312
@router.post("/sync/orders", status_code=status.HTTP_202_ACCEPTED)
async def sync_all_orders(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user)
):
    # Проверка подключения
    if not current_user.ebay_connected or not current_user.ebay_access_token:
        raise HTTPException(...)
    
    # Получение токена
    access_token = current_user.ebay_access_token
    user_id = current_user.id
    
    # Создание run_id для логирования
    run_id = str(uuid.uuid4())
    
    # Запуск в фоне
    background_tasks.add_task(
        _run_orders_sync,
        user_id=user_id,
        access_token=access_token,
        run_id=run_id
    )
    
    return {"status": "started", "run_id": run_id}

async def _run_orders_sync(user_id: str, access_token: str, run_id: str):
    await ebay_service.sync_all_orders(user_id, access_token, run_id=run_id)
```

#### 2. С фронтенда
```typescript
// frontend/src/pages/EbayConnectionPage.tsx
const handleSyncOrders = async () => {
  setError('');
  setSyncing(true);
  setSyncResult(null);
  setOrdersRunId(null);
  
  try {
    const response = await api.post('/ebay/sync/orders');
    setSyncResult(response.data);
    if (response.data.run_id) {
      setOrdersRunId(response.data.run_id);
    }
  } catch (err) {
    setError(err.message);
    setSyncing(false);
  }
};
```

### 📊 Полная структура вызова

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend: EbayConnectionPage.tsx                            │
│   Пользователь нажимает "Sync Orders"                       │
│   ↓                                                          │
│   handleSyncOrders()                                        │
│     ↓ POST /api/ebay/sync/orders                           │
│     ↓ Через Cloudflare Functions proxy                     │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Cloudflare Functions: functions/api/[[path]].ts             │
│   Проксирует запрос к Railway backend                       │
│   ↓ POST https://{railway-url}/ebay/sync/orders            │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Backend Router: backend/app/routers/ebay.py                 │
│   @router.post("/ebay/sync/orders")                         │
│     ↓ Depends(get_current_active_user)                      │
│     ↓ Извлекает токен из current_user.ebay_access_token     │
│     ↓ Создает run_id = uuid4()                              │
│     ↓ Запускает background task                             │
│     ↓ Возвращает {"status": "started", "run_id": "..."}    │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Background Task: _run_orders_sync()                         │
│   Вызывает ebay_service.sync_all_orders()                   │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Backend Service: backend/app/services/ebay.py               │
│   EbayService.sync_all_orders()                             │
│     ↓ 1. Создает SyncEventLogger для логирования            │
│     ↓ 2. Вызывает get_user_identity(access_token)           │
│     ↓ 3. Логирует "WHO WE ARE"                              │
│     ↓ 4. Цикл пагинации:                                    │
│        - Проверка cancellation                              │
│        - Подготовка filter_params                           │
│        - Вызов fetch_orders(access_token, filter_params)    │
│        - Обработка ответа                                   │
│        - Сохранение в БД                                    │
│        - Обновление offset                                  │
│     ↓ 5. Возвращает результат                               │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ eBay Fulfillment API                                        │
│   GET https://api.ebay.com/sell/fulfillment/v1/order        │
│   Query: ?filter=orderStatus:COMPLETED&limit=200&offset=0   │
│   Headers: Authorization: Bearer {access_token}             │
│   Response: { "orders": [...], "total": 100 }              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔑 Ключевые моменты

### Передача токена
- **Источник**: `current_user.ebay_access_token` (из БД, через `get_current_active_user`)
- **Передача**: Через параметр `access_token` в методы сервиса
- **Использование**: В заголовке `Authorization: Bearer {access_token}`

### Формирование URL
- **Base URL**: `settings.ebay_api_base_url` (из `app/config.py`)
  - Sandbox: `https://api.sandbox.ebay.com`
  - Production: `https://api.ebay.com`
- **Identity API**: `/identity/v1/oauth2/userinfo`
- **Orders API**: `/sell/fulfillment/v1/order`

### Формирование Headers
```python
headers = {
    "Authorization": f"Bearer {access_token}",
    "Accept": "application/json",
    "Content-Type": "application/json"  # для POST/PUT
}
```

### Обработка ответа
- **Identity API**: Извлекает `username` и `user_id` (или `userId`)
- **Orders API**: Парсит JSON, извлекает массив `orders`, обрабатывает пагинацию
- **Ошибки**: Логируются через `SyncEventLogger` и возвращаются в ответе

### Логирование
- **SyncEventLogger**: Логирует все события синхронизации
- **SSE**: События отправляются через Server-Sent Events на фронтенд
- **Frontend**: `SyncTerminal.tsx` отображает логи в реальном времени

---

## 📂 Структура папок

```
backend/
├── app/
│   ├── services/
│   │   ├── ebay.py              ← EbayService с get_user_identity() и sync_all_orders()
│   │   ├── ebay_database.py     ← Работа с БД для хранения заказов
│   │   └── sync_event_logger.py ← Логирование событий синхронизации
│   ├── routers/
│   │   └── ebay.py              ← API endpoints (/ebay/sync/orders)
│   └── config.py                ← Настройки (ebay_api_base_url)
│
frontend/
├── src/
│   ├── pages/
│   │   └── EbayConnectionPage.tsx  ← UI для синхронизации
│   ├── components/
│   │   ├── SyncTerminal.tsx        ← Отображение логов
│   │   └── EbayDebugger.tsx        ← Debugger для тестирования API
│   └── lib/
│       └── apiClient.ts            ← Axios клиент для API запросов
```

---

## 🐛 Где искать ошибки

1. **Identity API возвращает None**:
   - Проверить токен в БД: `current_user.ebay_access_token`
   - Проверить логи: `logger.info("Identity API raw response: ...")`
   - Проверить scopes токена

2. **Orders API возвращает 400/404**:
   - Проверить filter параметры: `filter=orderStatus:COMPLETED`
   - Проверить URL: `/sell/fulfillment/v1/order`
   - Проверить headers: `Authorization: Bearer {token}`

3. **Orders = 0 при 200 OK**:
   - Проверить аккаунт (seller vs buyer)
   - Проверить окно дат
   - Проверить фильтр `orderStatus:COMPLETED`

---

## 🔧 Использование Debugger

Для тестирования API напрямую используйте:
- **UI**: Вкладка "🔧 API Debugger" на странице eBay Connection
- **CLI**: `python -m app.utils.ebay_debugger --user-id <UUID> --template identity`

