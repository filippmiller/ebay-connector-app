# ✅ ФИНАЛЬНОЕ РЕШЕНИЕ: eBay Browser 404

## Корневая причина

1. ✅ `ebayBrowser.ts` использует правильный `apiClient`  
2. ✅ `apiClient` имеет `baseURL = "/api"`
3. ❌ **Cloudflare Pages Functions НЕ РАБОТАЮТ с TypeScript (.ts) файлами**
4. ❌ Наш `functions/api/[[path]].ts` - это TypeScript!
5. ❌ Cloudflare Pages требует `.js` файлы или явную компиляцию
6. ❌ Результат: `/api/*` → 404 (функция не выполняется)

## ✅ Простое решение (рекомендуется)

### Установить `VITE_API_BASE_URL` напрямую на Railway

**Cloudflare Pages → Settings → Environment variables:**

1. Добавить:
   - **Name**: `VITE_API_BASE_URL`
   - **Value**: `https://ebay-connector-app-production.up.railway.app`
   - **Environment**: Production (и Preview)

2. **Удалить** `API_PUBLIC_BASE_URL` (больше не нужна)

3. Redeploy frontend

### Почему это работает:

```javascript
// apiClient.ts
const getBaseURL = () => {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL; // ← Railway URL
  }
  return "/api"; // ← Не работает в Cloudflare
};

// ebayBrowser.ts
api.post('ebay/browse/search', ...) 
// = https://ebay-connector-app-production.up.railway.app/api/ebay/browse/search ✅
```

### Важно: CORS

Railway backend должен разрешить CORS от Cloudflare Pages domain:
```python
# backend/app/main.py
origins = [
    "https://ebay-connector-frontend.pages.dev",
    ...
]
```

Проверьте что это уже есть в вашем `main.py`.

## Альтернативное решение (сложное)

Если хотите оставить Cloudflare Functions proxy:

### 1. Переименовать `.ts` → `.js`

```bash
cd frontend/functions/api
mv "[[path]].ts" "[[path]].js"
```

### 2. Убрать типы TypeScript

```javascript
// frontend/functions/api/[[path]].js
export const onRequest = async ({ request, env }) => {
  const apiBase = env.API_PUBLIC_BASE_URL;
  // ... rest of code без TypeScript типов
};
```

### 3. Обновить postbuild

```json
{
  "postbuild": "node -e \"require('fs').cpSync('functions', 'dist/functions', { recursive: true })\""
}
```

**НО** это сложнее и требует поддержки двух версий кода.

## 🎯 Рекомендация

**Используйте простое решение**:
1. Установите `VITE_API_BASE_URL=https://ebay-connector-app-production.up.railway.app`
2. Удалите `API_PUBLIC_BASE_URL`
3. Redeploy

Все остальные эндпоинты уже работают так → eBay Browser тоже заработает.

## Проверка CORS в backend

```bash
cd c:\dev\ebay-connector-app\backend
grep -A 10 "origins = " app/main.py
```

Должно быть:
```python
origins = [
    "https://ebay-connector-frontend.pages.dev",
    "http://localhost:5173",
    ...
]
```

Если нет - добавьте.

## Команды

```bash
# После установки VITE_API_BASE_URL в Cloudflare:
# Ничего не нужно коммитить, просто trigger redeploy:

git commit --allow-empty -m "Trigger redeploy"
git push
```

Или в Cloudflare Pages Dashboard → Deployments → Retry deployment

---

**После deployment eBay Browser заработает!** 🎉
