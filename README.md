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

## Security Notes

- JWT tokens are stored in localStorage
- Passwords are hashed using Argon2
- Sensitive credentials in logs are sanitized (showing only first and last 4 characters)
- CORS is configured for local development
- In-memory database (data not persisted to disk)

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
