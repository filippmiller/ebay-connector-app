# Deployment Guide

This guide covers deploying the eBay Connector application to production.

## Pre-Deployment Checklist

### Backend Configuration

1. **Update `.env` file with production settings:**

```env
# Security - CRITICAL: Generate a strong random secret key
SECRET_KEY=<generate-a-long-random-string-at-least-32-characters>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# eBay Production Credentials
EBAY_CLIENT_ID=<your-production-client-id>
EBAY_CLIENT_SECRET=<your-production-client-secret>
EBAY_REDIRECT_URI=<your-deployed-frontend-url>/ebay/callback
EBAY_ENVIRONMENT=production
```

2. **Generate a secure SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

3. **Ensure all dependencies are in `pyproject.toml`:**
```bash
cd backend
poetry install --no-dev
```

### Frontend Configuration

1. **Update `.env` file with production backend URL:**

```env
VITE_API_URL=<your-deployed-backend-url>
```

2. **Build the frontend:**
```bash
cd frontend
npm run build
```

This creates an optimized production build in the `dist` folder.

## Deployment Options

### Option 1: Using Devin's Built-in Deployment (Recommended for Quick Testing)

The backend can be deployed to Fly.io automatically:

```bash
# From the project root
deploy backend --dir=/home/ubuntu/ebay-connector-app/backend
```

The frontend can be deployed as a static site:

```bash
# Build first
cd frontend && npm run build

# Deploy
deploy frontend --dir=/home/ubuntu/ebay-connector-app/frontend/dist
```

### Option 2: Manual Deployment to Fly.io

#### Backend Deployment

1. Install Fly CLI:
```bash
curl -L https://fly.io/install.sh | sh
```

2. Login to Fly:
```bash
fly auth login
```

3. Create `fly.toml` in the backend directory:
```toml
app = "ebay-connector-backend"

[build]
  builder = "paketobuildpacks/builder:base"

[env]
  PORT = "8000"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0

[[http_service.checks]]
  grace_period = "10s"
  interval = "30s"
  method = "GET"
  timeout = "5s"
  path = "/healthz"
```

4. Deploy:
```bash
cd backend
fly launch
fly deploy
```

5. Set environment variables:
```bash
fly secrets set SECRET_KEY="your-secret-key"
fly secrets set EBAY_CLIENT_ID="your-client-id"
fly secrets set EBAY_CLIENT_SECRET="your-client-secret"
fly secrets set EBAY_REDIRECT_URI="your-frontend-url/ebay/callback"
fly secrets set EBAY_ENVIRONMENT="production"
```

#### Frontend Deployment to Vercel

1. Install Vercel CLI:
```bash
npm i -g vercel
```

2. Deploy:
```bash
cd frontend
vercel --prod
```

3. Set environment variable in Vercel dashboard:
   - `VITE_API_URL` = Your backend URL

### Option 3: Deploy to AWS/Azure/GCP

#### Backend (Docker Container)

1. Create `Dockerfile` in backend directory:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install poetry

COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false && poetry install --no-dev

COPY app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

2. Build and push to container registry
3. Deploy to your cloud provider's container service

#### Frontend (Static Hosting)

1. Build the frontend:
```bash
npm run build
```

2. Upload the `dist` folder contents to:
   - AWS S3 + CloudFront
   - Azure Static Web Apps
   - Google Cloud Storage
   - Netlify
   - Any static hosting provider

## Post-Deployment Configuration

### 1. Update eBay Developer Console

1. Go to https://developer.ebay.com/my/keys
2. Update your OAuth Redirect URI to match your deployed frontend URL:
   - Example: `https://your-app.com/ebay/callback`

### 2. Configure CORS (if needed)

Update backend `main.py` if you need to restrict CORS:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-domain.com"],  # Specific domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 3. Set Up SSL/HTTPS

- Most deployment platforms (Fly.io, Vercel, Netlify) provide automatic HTTPS
- If self-hosting, use Let's Encrypt certificates
- eBay OAuth requires HTTPS in production

### 4. Database Migration (Future Enhancement)

Currently using in-memory database. For production, consider:
- PostgreSQL (recommended)
- MySQL
- MongoDB

Update the backend to use a persistent database:
1. Add database driver to `pyproject.toml`
2. Update database connection in backend code
3. Implement migrations

## Environment Variables Summary

### Backend (.env or deployment platform)
```
SECRET_KEY=<strong-random-string>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
EBAY_CLIENT_ID=<your-ebay-client-id>
EBAY_CLIENT_SECRET=<your-ebay-client-secret>
EBAY_REDIRECT_URI=<frontend-url>/ebay/callback
EBAY_ENVIRONMENT=production
```

### Frontend (.env or deployment platform)
```
VITE_API_URL=<backend-url>
```

## Monitoring and Maintenance

### Health Checks

Backend provides a health endpoint:
```
GET /healthz
```

Set up monitoring to check this endpoint regularly.

### Logs

- Backend logs are available through your deployment platform
- Frontend errors can be monitored with tools like Sentry
- eBay API logs are viewable in the Connection Terminal

### Backup Strategy

Since using in-memory database:
- User data is lost on restart
- Consider implementing database backup if switching to persistent storage

### Scaling Considerations

Current architecture supports:
- Horizontal scaling of backend instances
- CDN distribution of frontend
- Add Redis for session management if needed
- Implement rate limiting for API endpoints

## Security Hardening

### Production Checklist

- [ ] Use strong SECRET_KEY (32+ characters)
- [ ] Enable HTTPS everywhere
- [ ] Restrict CORS to specific domains
- [ ] Implement rate limiting
- [ ] Add request logging
- [ ] Set up security headers
- [ ] Use environment variables (never hardcode secrets)
- [ ] Implement proper error handling (don't expose stack traces)
- [ ] Regular dependency updates
- [ ] Monitor for security vulnerabilities

### Security Headers (Backend)

Add to `main.py`:
```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["your-domain.com"])

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response
```

## Troubleshooting Deployment Issues

### Backend Won't Start
- Check logs for Python errors
- Verify all dependencies are installed
- Ensure PORT environment variable is set
- Check that FastAPI can import all modules

### Frontend Build Fails
- Run `npm install` to ensure dependencies are installed
- Check for TypeScript errors: `npm run build`
- Verify all imports are correct

### eBay OAuth Fails in Production
- Verify redirect URI matches exactly (including protocol https://)
- Check eBay credentials are for production environment
- Ensure frontend URL is correct in backend config
- Check CORS settings allow your frontend domain

### 502/504 Gateway Errors
- Backend may be taking too long to start
- Increase health check grace period
- Check backend logs for startup errors

## Rolling Back

If deployment fails:
1. Keep previous version tagged in git
2. Most platforms support instant rollback
3. Verify environment variables are correct
4. Check logs for specific errors

## Cost Considerations

### Free Tier Options
- **Backend**: Fly.io free tier (limited resources)
- **Frontend**: Vercel/Netlify free tier (personal projects)
- **Domain**: Freenom or use platform subdomain

### Paid Recommendations
- **Backend**: Fly.io ($5-10/month), Railway, Render
- **Frontend**: Vercel Pro, Netlify Pro
- **Database**: Fly.io Postgres, Supabase, PlanetScale

## Support and Updates

After deployment:
1. Monitor application logs
2. Set up uptime monitoring (UptimeRobot, StatusCake)
3. Keep dependencies updated
4. Respond to eBay API changes
5. Monitor eBay rate limits

## Quick Deploy Commands Summary

```bash
# Backend (using Devin deployment)
deploy backend --dir=/home/ubuntu/ebay-connector-app/backend

# Frontend (using Devin deployment)
cd /home/ubuntu/ebay-connector-app/frontend
npm run build
deploy frontend --dir=/home/ubuntu/ebay-connector-app/frontend/dist

# Manual with Fly.io
cd backend && fly launch && fly deploy

# Manual with Vercel
cd frontend && vercel --prod
```
