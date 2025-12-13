# Архитектура встроенного eBay Browser

## Обзор
Встроенный eBay Browser - это функциональность для поиска активных листингов eBay через eBay Browse API v1.

## Компоненты

### Frontend
- **EbaySearchTab.tsx** - основной UI компонент
- **ebayBrowser.ts** - API client
- Вызывает: `POST /api/ebay/browse/search`

### Cloudflare Pages Proxy
- **functions/api/[[path]].ts** - proxy функция
- Требует: `API_PUBLIC_BASE_URL` env variable
- Пересылает: `/api/*` → Railway backend

### Backend (Railway)
- **ebay_browse.py** - FastAPI router
- **ebay_api_client.py** - eBay API client
- **ebay.py** - OAuth authentication service

## Протоколы

### OAuth 2.0 Client Credentials
```python
# Получение app token
POST https://api.ebay.com/identity/v1/oauth2/token
Authorization: Basic {base64(client_id:cert_id)}
grant_type=client_credentials
scope=https://api.ebay.com/oauth/api_scope
```

### eBay Browse API
```python
GET https://api.ebay.com/buy/browse/v1/item_summary/search
Authorization: Bearer {app_token}
X-EBAY-C-MARKETPLACE-ID: EBAY_US
Parameters: q, limit, offset, sort, category_ids, filter, aspect_filter
```

## Поток данных

1. **User** вводит запрос → **EbaySearchTab**
2. **Frontend** → `POST /api/ebay/browse/search`
3. **Cloudflare Proxy** → читает `API_PUBLIC_BASE_URL`
4. **Cloudflare Proxy** → `POST {railway_url}/ebay/browse/search`
5. **Backend** → `get_browse_app_token()` (OAuth)
6. **Backend** → eBay Browse API
7. **Backend** → пост-фильтрация + refinements
8. **Backend** → response
9. **Frontend** → отображение результатов

## Environment Variables

**Backend (Railway)**:
- `EBAY_ENVIRONMENT`: production/sandbox
- `EBAY_PRODUCTION_CLIENT_ID`
- `EBAY_PRODUCTION_CERT_ID`
- `EBAY_PRODUCTION_DEV_ID`

**Frontend (Cloudflare Pages)**:
- `API_PUBLIC_BASE_URL`: https://ebay-connector-app-production.up.railway.app

## Текущая проблема

❌ `API_PUBLIC_BASE_URL` не установлена в Cloudflare Pages
→ Proxy не знает куда пересылать → 404

Решение: См. `EBAY_BROWSER_FIX.md`
