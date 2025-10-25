# Frontend Configuration Guide

## Environment Variables

### Development (Optional)

Create a `.env` file in the frontend directory with the following variables:

```bash
# API Prefix (optional, defaults to /api)
VITE_API_PREFIX=/api
```

### Production (Cloudflare Pages)

Set the following environment variables in Cloudflare Pages dashboard:

**Required:**
- `API_PUBLIC_BASE_URL` - The public URL of your backend API (e.g., `https://api.yourdomain.com`)

**Optional:**
- `VITE_API_PREFIX` - API prefix for frontend requests (defaults to `/api`)

## API Proxy Architecture

### Development (Vite Proxy)

In development, Vite proxies `/api/*` requests to the backend at `http://127.0.0.1:8000`:

```
Frontend (localhost:5173) → /api/auth/login → Vite Proxy → http://127.0.0.1:8000/auth/login
```

The proxy automatically strips the `/api` prefix before forwarding to the backend.

### Production (Cloudflare Pages Functions)

In production, Cloudflare Pages Functions proxy `/api/*` requests to your backend:

```
Frontend (app.yourdomain.com) → /api/auth/login → Pages Function → https://api.yourdomain.com/auth/login
```

The function at `functions/api/[[path]].js` strips the `/api` prefix and forwards to `API_PUBLIC_BASE_URL`.

## Authentication Flow

1. User submits login form with email and password
2. Frontend calls `POST /api/auth/login` (proxied to backend `/auth/login`)
3. Backend returns JWT token in `access_token` field
4. Frontend stores token in `localStorage` as `auth_token`
5. Axios interceptor automatically attaches token to all subsequent requests
6. Frontend calls `GET /api/auth/me` (proxied to backend `/auth/me`) to fetch user data
7. User is authenticated and redirected to dashboard

## Token Storage

- **Storage Key**: `auth_token` (stored in `localStorage`)
- **Legacy Key**: `token` (automatically cleared on logout for clean migration)
- **Token Format**: JWT Bearer token
- **Token Lifecycle**: Automatically attached to requests via Axios interceptor

## Error Handling

- **401 Unauthorized**: Token is automatically cleared from storage
- **Network Errors**: Displayed to user with error message
- **Loading States**: Managed by AuthContext, guaranteed to stop via `finally` blocks

## Testing

### Local Development

1. Start backend: `cd backend && poetry run fastapi dev app/main.py --port 8000`
2. Start frontend: `cd frontend && npm run dev`
3. Navigate to `http://localhost:5173`
4. Test login flow:
   - Submit login form
   - Check Network tab: `POST /api/auth/login` should return 200
   - Check localStorage: `auth_token` should be set
   - Check Network tab: `GET /api/auth/me` should return 200
   - User should be redirected to dashboard

### Production (Cloudflare Pages)

1. Deploy frontend to Cloudflare Pages
2. Set `API_PUBLIC_BASE_URL` environment variable
3. Test login flow via preview URL
4. Verify proxy works: `curl -i https://preview-url.pages.dev/api/healthz`

## Troubleshooting

### Login Form Stuck in "Signing in..." State

**Cause**: AuthContext loading state not completing
**Solution**: Check browser console for errors, verify backend is running, check Network tab for failed requests

### CORS Errors in Development

**Cause**: Vite proxy not configured or backend not running
**Solution**: Verify `vite.config.ts` has proxy configuration, restart Vite dev server

### 401 Errors After Login

**Cause**: Token not being attached to requests or invalid token
**Solution**: Check localStorage for `auth_token`, verify Axios interceptor is working, check backend logs

### Network Errors in Production

**Cause**: Cloudflare Pages Function not configured or `API_PUBLIC_BASE_URL` not set
**Solution**: Verify `functions/api/[[path]].js` exists, check Cloudflare Pages environment variables
