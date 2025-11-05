# eBay Connector Application

A fullstack application for connecting to eBay API with OAuth authentication, user management, and comprehensive logging.

## Features

- **User Authentication**
  - User registration with role selection (User/Admin)
  - Login with JWT tokens
  - Password reset functionality
  - In-memory database (data persists during runtime)

- **eBay OAuth Integration**
  - OAuth 2.0 authorization code grant flow
  - Token management (access & refresh tokens)
  - Connection status tracking
  - Automatic token expiration handling

- **Comprehensive Logging**
  - Real-time logging of all eBay API interactions
  - Credential exchange monitoring
  - Request/response logging with sensitive data sanitization
  - Connection terminal interface for debugging

- **Admin Features**
  - Admin role for privileged operations
  - Log clearing functionality (admin-only)
  - Full visibility of API interactions

## Tech Stack

### Backend
- FastAPI (Python)
- Argon2 for password hashing
- JWT for authentication
- HTTPX for async HTTP requests
- Comprehensive logging system

### Frontend
- React + TypeScript
- Tailwind CSS for styling
- shadcn/ui component library
- React Router for navigation
- Real-time log updates

## Setup Instructions

### Prerequisites
- Python 3.12+
- Node.js 18+
- Poetry (for Python dependency management)
- eBay Developer Account (for API credentials)

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Install dependencies:
```bash
poetry install
```

3. Configure environment variables in `.env`:
```env
SECRET_KEY=your-secret-key-change-in-production-make-it-long-and-random
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# eBay API Credentials (get these from https://developer.ebay.com/)
EBAY_CLIENT_ID=your_ebay_client_id
EBAY_CLIENT_SECRET=your_ebay_client_secret
EBAY_REDIRECT_URI=http://localhost:5173/ebay/callback
EBAY_ENVIRONMENT=sandbox
```

4. Start the backend server:
```bash
poetry run fastapi dev app/main.py --port 8000
```

The backend will be available at http://localhost:8000

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Configure environment variables in `.env`:
```env
VITE_API_URL=http://localhost:8000
```

4. Start the frontend dev server:
```bash
npm run dev
```

The frontend will be available at http://localhost:5173

## Getting eBay API Credentials

1. Go to https://developer.ebay.com/
2. Sign up or log in to your developer account
3. Create a new application in the developer console
4. Get your Client ID and Client Secret
5. Configure your RuName (Redirect URL): `http://localhost:5173/ebay/callback` (or your deployed URL)
6. Add these credentials to your backend `.env` file

## Usage

### User Registration
1. Navigate to http://localhost:5173/register
2. Fill in email, username, password, and select role (User or Admin)
3. Click "Create Account"

### Login
1. Navigate to http://localhost:5173/login
2. Enter your email and password
3. Click "Sign In"

### Connect to eBay
1. After logging in, you'll be on the Dashboard
2. Go to the "eBay Connection" tab
3. Click "Connect to eBay"
4. You'll be redirected to eBay's authorization page
5. Authorize the application
6. You'll be redirected back with a successful connection

### Monitor Connection Activity
1. Go to the "Connection Terminal" tab on the Dashboard
2. View real-time logs of all eBay API interactions
3. See credential exchanges, request/response data, and errors
4. Admins can clear logs using the "Clear Logs" button

## API Endpoints

### Authentication
- `POST /auth/register` - Register a new user
- `POST /auth/login` - Login and get JWT token
- `GET /auth/me` - Get current user info
- `POST /auth/password-reset/request` - Request password reset token
- `POST /auth/password-reset/confirm` - Confirm password reset

### eBay Integration
- `POST /ebay/auth/start` - Start eBay OAuth flow
- `POST /ebay/auth/callback` - Handle OAuth callback
- `GET /ebay/status` - Get connection status
- `POST /ebay/disconnect` - Disconnect from eBay
- `GET /ebay/logs` - Get eBay connection logs
- `DELETE /ebay/logs` - Clear logs (admin only)

## Authentication Implementation

### Overview

This application uses **custom authentication** with a PostgreSQL/SQLite users table, **not Supabase Auth**. Authentication is handled via JWT tokens with Bearer authentication.

### Auth Flow

1. **User Registration**: POST `/auth/register` with `{email, username, password}`
   - Passwords are hashed using SHA-256 (⚠️ **Security Note**: Migration to bcrypt/argon2 recommended)
   - Admin emails are auto-assigned admin role (see `backend/app/services/auth.py:99-103`)
   - Handler: `backend/app/routers/auth.py:18-30`

2. **User Login**: POST `/auth/login` with `{email, password}`
   - Returns `{access_token, token_type: "bearer"}`
   - Token expires after `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 30)
   - Handler: `backend/app/routers/auth.py:34-61`

3. **Authenticated Requests**: Include `Authorization: Bearer <token>` header
   - Token verification: `backend/app/services/auth.py:46-69`
   - Current user dependency: `backend/app/services/auth.py:72-79`

### Files Handling Auth

**Routes/Controllers:**
- `backend/app/routers/auth.py:34-61` - POST `/auth/login` endpoint
- `backend/app/routers/auth.py:18-30` - POST `/auth/register` endpoint
- `backend/app/routers/auth.py:64-74` - GET `/auth/me` endpoint

**Services/Helpers:**
- `backend/app/services/auth.py:15-16` - `verify_password()` (SHA-256 verification)
- `backend/app/services/auth.py:19-20` - `get_password_hash()` (SHA-256 hashing)
- `backend/app/services/auth.py:23-31` - `create_access_token()` (JWT creation)
- `backend/app/services/auth.py:34-43` - `authenticate_user()` (email/password verification)
- `backend/app/services/auth.py:46-69` - `get_current_user()` (JWT verification)

**Database:**
- `backend/app/services/database.py:3-8` - Database selection (PostgreSQL vs SQLite)
- `backend/app/services/postgres_database.py:53-61` - `get_user_by_email()`
- `backend/app/services/postgres_database.py:63-71` - `get_user_by_id()`
- `backend/app/models_sqlalchemy/models.py` - SQLAlchemy User model

### Required Environment Variables for Auth (Production)

**Backend (`backend/.env`):**
```env
# JWT Configuration
SECRET_KEY=your-long-random-secret-key-here
# OR (alias for ops compatibility):
JWT_SECRET=your-long-random-secret-key-here

# JWT Algorithm (default: HS256)
ALGORITHM=HS256

# Token expiration in minutes (default: 30)
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Database connection (required)
DATABASE_URL=postgresql://user:password@host:5432/dbname

# CORS configuration (required for frontend access)
ALLOWED_ORIGINS=https://your-frontend-domain.com,http://localhost:5173

# Frontend URL (for reference)
FRONTEND_URL=https://your-frontend-domain.com
```

**Not Used by Auth:**
- `COOKIE_DOMAIN`, `COOKIE_SAMESITE`, `COOKIE_SECURE` - We use Bearer tokens, not cookies
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` - No Supabase Auth integration

### Testing Auth Locally

1. **Create a test user:**
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","username":"testuser","password":"TestPassword123!"}'
```

2. **Login:**
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"TestPassword123!"}'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

3. **Access protected endpoints:**
```bash
curl -X GET http://localhost:8000/auth/me \
  -H "Authorization: Bearer <your-token-here>"
```

### Error Handling

**401 Unauthorized:**
- Incorrect email or password
- Invalid or expired JWT token
- Missing Authorization header

**403 Forbidden:**
- Account is inactive
- Insufficient permissions (e.g., non-admin accessing admin endpoint)

**500 Internal Server Error:**
- Database connection failure
- Unexpected server errors

All error responses include proper CORS headers when `ALLOWED_ORIGINS` is configured correctly.

### Security Notes

- JWT tokens are stored in localStorage on the frontend
- Passwords are currently hashed using SHA-256 (⚠️ **Migration to bcrypt/argon2 strongly recommended**)
- Sensitive credentials in logs are sanitized (showing only first and last 4 characters)
- CORS is configured via `ALLOWED_ORIGINS` environment variable
- Database connection errors are caught and return proper 500 responses with JSON body

## Production Deployment

For production deployment:
1. Change `SECRET_KEY` to a strong random value
2. Update `EBAY_REDIRECT_URI` to your production domain
3. Switch `EBAY_ENVIRONMENT` to `production`
4. Configure proper CORS origins in the backend
5. Use a persistent database instead of in-memory
6. Enable HTTPS for both frontend and backend

## Troubleshooting

### eBay Connection Fails
- Check that your eBay API credentials are correctly configured
- Verify your redirect URI matches what's configured in eBay Developer Console
- Check the Connection Terminal for detailed error logs

### Authentication Issues
- Clear localStorage and try logging in again
- Check that the backend is running on port 8000
- Verify the API URL in frontend `.env` is correct

## License

This project is for demonstration purposes.
