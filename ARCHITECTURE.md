# Architecture Documentation

## System Overview

The eBay Connector is a fullstack web application that enables users to authenticate with eBay's OAuth API and monitor all credential exchanges through a real-time terminal interface.

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                             │
│  (React + TypeScript + Tailwind + shadcn/ui)                │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Auth Pages   │  │  Dashboard   │  │   Terminal   │      │
│  │              │  │              │  │              │      │
│  │ - Login      │  │ - Profile    │  │ - Logs View  │      │
│  │ - Register   │  │ - eBay Conn  │  │ - Real-time  │      │
│  │ - Reset Pwd  │  │ - Status     │  │ - Filtering  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP/REST API
                         │ (JWT Auth)
┌────────────────────────▼─────────────────────────────────────┐
│                        Backend                               │
│              (FastAPI + Python)                              │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Auth Router  │  │ eBay Router  │  │  Middleware  │      │
│  │              │  │              │  │              │      │
│  │ - Register   │  │ - Start Auth │  │ - CORS       │      │
│  │ - Login      │  │ - Callback   │  │ - JWT Auth   │      │
│  │ - Reset      │  │ - Status     │  │ - Logging    │      │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘      │
│         │                  │                                 │
│  ┌──────▼──────────────────▼───────┐  ┌──────────────┐      │
│  │        Services                 │  │   Logger     │      │
│  │                                 │  │              │      │
│  │ - Auth Service (JWT/Argon2)    │  │ - Event Log  │      │
│  │ - eBay Service (OAuth)         │◄─┤ - Sanitizer  │      │
│  │ - Database Service (In-Memory)  │  │ - Storage    │      │
│  └─────────────────────────────────┘  └──────────────┘      │
└────────────────────────┬─────────────────────────────────────┘
                         │ OAuth 2.0
                         │ HTTP Requests
┌────────────────────────▼─────────────────────────────────────┐
│                    eBay API                                  │
│                                                              │
│  - OAuth Authorization                                       │
│  - Token Exchange                                           │
│  - API Endpoints                                            │
└──────────────────────────────────────────────────────────────┘
```

## Component Architecture

### Frontend Structure

```
frontend/
├── src/
│   ├── api/                    # API client layer
│   │   ├── client.ts          # Base HTTP client
│   │   ├── auth.ts            # Auth API calls
│   │   └── ebay.ts            # eBay API calls
│   │
│   ├── components/
│   │   └── ui/                # shadcn/ui components
│   │
│   ├── contexts/              # React contexts
│   │   └── AuthContext.tsx   # Global auth state
│   │
│   ├── pages/                 # Page components
│   │   ├── LoginPage.tsx
│   │   ├── RegisterPage.tsx
│   │   ├── DashboardPage.tsx
│   │   ├── EbayCallbackPage.tsx
│   │   └── PasswordResetPage.tsx
│   │
│   ├── types/                 # TypeScript types
│   │   └── index.ts
│   │
│   ├── App.tsx               # Main app with routing
│   └── main.tsx              # Entry point
│
└── .env                      # Environment config
```

### Backend Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration
│   │
│   ├── models/              # Pydantic models
│   │   ├── user.py         # User models
│   │   └── ebay.py         # eBay models
│   │
│   ├── routers/             # API endpoints
│   │   ├── auth.py         # Auth routes
│   │   └── ebay.py         # eBay routes
│   │
│   ├── services/            # Business logic
│   │   ├── auth.py         # Auth service
│   │   ├── database.py     # DB service
│   │   └── ebay.py         # eBay service
│   │
│   └── utils/               # Utilities
│       └── logger.py        # Logging system
│
├── pyproject.toml           # Dependencies
└── .env                     # Environment config
```

## Data Flow

### 1. User Authentication Flow

```
┌─────────┐                ┌─────────┐                ┌──────────┐
│ Browser │                │ Backend │                │ Database │
└────┬────┘                └────┬────┘                └─────┬────┘
     │                          │                           │
     │ POST /auth/register      │                           │
     ├─────────────────────────►│                           │
     │                          │ hash_password()           │
     │                          ├────────┐                  │
     │                          │◄───────┘                  │
     │                          │                           │
     │                          │ create_user()             │
     │                          ├──────────────────────────►│
     │                          │◄──────────────────────────┤
     │                          │                           │
     │◄─────────────────────────┤                           │
     │    User created          │                           │
     │                          │                           │
     │ POST /auth/login         │                           │
     ├─────────────────────────►│                           │
     │                          │ verify_password()         │
     │                          ├────────┐                  │
     │                          │◄───────┘                  │
     │                          │                           │
     │                          │ create_jwt_token()        │
     │                          ├────────┐                  │
     │                          │◄───────┘                  │
     │                          │                           │
     │◄─────────────────────────┤                           │
     │    JWT Token             │                           │
     │                          │                           │
```

### 2. eBay OAuth Flow

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌──────────┐
│ Browser │     │ Backend │     │  Logger │     │ eBay API │
└────┬────┘     └────┬────┘     └────┬────┘     └─────┬────┘
     │               │               │                 │
     │ Connect eBay  │               │                 │
     ├──────────────►│               │                 │
     │               │ Log: start    │                 │
     │               ├──────────────►│                 │
     │               │               │                 │
     │               │ Generate auth URL               │
     │               ├────────┐      │                 │
     │               │◄───────┘      │                 │
     │               │               │                 │
     │◄──────────────┤               │                 │
     │ Auth URL      │               │                 │
     │               │               │                 │
     │ Redirect to eBay              │                 │
     ├───────────────────────────────────────────────►│
     │               │               │                 │
     │               │               │  User authorizes│
     │               │               │                 │
     │◄──────────────────────────────────────────────┤
     │ Callback with code            │                 │
     │               │               │                 │
     │ POST /ebay/callback           │                 │
     ├──────────────►│               │                 │
     │               │ Log: exchange │                 │
     │               ├──────────────►│                 │
     │               │               │                 │
     │               │ Exchange code for token         │
     │               ├─────────────────────────────────►│
     │               │               │                 │
     │               │◄────────────────────────────────┤
     │               │ Access token  │                 │
     │               │ Log: success  │                 │
     │               ├──────────────►│                 │
     │               │               │                 │
     │               │ Save tokens   │                 │
     │               ├────────┐      │                 │
     │               │◄───────┘      │                 │
     │               │               │                 │
     │◄──────────────┤               │                 │
     │ Success       │               │                 │
     │               │               │                 │
```

### 3. Real-time Log Updates

```
┌─────────┐                ┌─────────┐                ┌──────────┐
│ Browser │                │ Backend │                │  Logger  │
└────┬────┘                └────┬────┘                └─────┬────┘
     │                          │                           │
     │ GET /ebay/logs           │                           │
     ├─────────────────────────►│                           │
     │                          │ get_logs()                │
     │                          ├──────────────────────────►│
     │                          │◄──────────────────────────┤
     │                          │                           │
     │◄─────────────────────────┤                           │
     │    Log entries           │                           │
     │                          │                           │
     │  (Auto-refresh every 3s) │                           │
     │                          │                           │
     │ GET /ebay/logs           │                           │
     ├─────────────────────────►│                           │
     │                          │ get_logs()                │
     │                          ├──────────────────────────►│
     │                          │◄──────────────────────────┤
     │                          │                           │
     │◄─────────────────────────┤                           │
     │    Updated logs          │                           │
     │                          │                           │
```

## Security Architecture

### Authentication & Authorization

1. **Password Hashing**: Argon2 (memory-hard, resistant to GPU attacks)
2. **JWT Tokens**: HS256 algorithm with configurable expiration
3. **Token Storage**: localStorage on client (consider httpOnly cookies for production)
4. **Role-Based Access**: User and Admin roles with different permissions

### API Security

```
Request → CORS Middleware → JWT Verification → Route Handler
                ↓                   ↓                ↓
           Check origin      Verify signature   Check permissions
                ↓                   ↓                ↓
           Allow/Deny       Get user from DB    Execute/Deny
```

### Sensitive Data Protection

The logger automatically sanitizes sensitive data:
- Client secrets: Shows first and last 4 characters
- Access tokens: Shows first and last 4 characters
- Refresh tokens: Shows first and last 4 characters
- Passwords: Never logged

Example:
```
Original: "abc123xyz456789def"
Logged:   "abc1...9def"
```

## Data Models

### User Model

```typescript
interface User {
  id: string;                    // UUID
  email: string;                 // Unique email
  username: string;              // Display name
  hashed_password: string;       // Argon2 hash
  role: 'user' | 'admin';       // Access level
  is_active: boolean;            // Account status
  created_at: datetime;          // Registration time
  ebay_connected: boolean;       // eBay connection status
  ebay_access_token?: string;    // eBay access token
  ebay_refresh_token?: string;   // eBay refresh token
  ebay_token_expires_at?: datetime; // Token expiry
}
```

### Log Entry Model

```typescript
interface EbayLog {
  timestamp: string;             // ISO 8601 format
  event_type: string;            // Event category
  description: string;           // Human-readable desc
  request_data?: object;         // Sanitized request
  response_data?: object;        // Sanitized response
  status: 'success' | 'error' | 'info';
  error?: string;                // Error message if any
}
```

## API Endpoints

### Authentication Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | /auth/register | Create new user | No |
| POST | /auth/login | Login and get JWT | No |
| GET | /auth/me | Get current user | Yes |
| POST | /auth/password-reset/request | Request reset token | No |
| POST | /auth/password-reset/confirm | Confirm password reset | No |

### eBay Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | /ebay/auth/start | Start OAuth flow | Yes |
| POST | /ebay/auth/callback | Handle OAuth callback | Yes |
| GET | /ebay/status | Get connection status | Yes |
| POST | /ebay/disconnect | Disconnect from eBay | Yes |
| GET | /ebay/logs | Get connection logs | Yes |
| DELETE | /ebay/logs | Clear logs | Yes (Admin) |

## Database Design

### Current: In-Memory Storage

```
InMemoryDatabase
  ├── users: Dict[user_id, User]
  └── password_reset_tokens: Dict[token, email]
```

**Pros:**
- Fast access
- Simple implementation
- No setup required

**Cons:**
- Data lost on restart
- No persistence
- Can't scale horizontally

### Future: PostgreSQL Schema

```sql
CREATE TABLE users (
  id UUID PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  username VARCHAR(100) NOT NULL,
  hashed_password VARCHAR(255) NOT NULL,
  role VARCHAR(20) NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT NOW(),
  ebay_connected BOOLEAN DEFAULT FALSE,
  ebay_access_token TEXT,
  ebay_refresh_token TEXT,
  ebay_token_expires_at TIMESTAMP
);

CREATE TABLE password_resets (
  token UUID PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  expires_at TIMESTAMP NOT NULL
);

CREATE TABLE ebay_logs (
  id SERIAL PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  timestamp TIMESTAMP DEFAULT NOW(),
  event_type VARCHAR(100) NOT NULL,
  description TEXT NOT NULL,
  request_data JSONB,
  response_data JSONB,
  status VARCHAR(20) NOT NULL,
  error TEXT
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_logs_timestamp ON ebay_logs(timestamp DESC);
CREATE INDEX idx_logs_user ON ebay_logs(user_id);
```

## Performance Considerations

### Current Performance

- **Backend**: FastAPI async handlers (non-blocking I/O)
- **Frontend**: React with optimized re-renders
- **Logs**: In-memory storage (max 1000 entries)
- **Auto-refresh**: 3-second polling interval

### Optimization Opportunities

1. **WebSocket for Logs**: Replace polling with real-time updates
2. **Caching**: Redis for session data
3. **Pagination**: For large log lists
4. **Database**: Switch to PostgreSQL
5. **CDN**: For static frontend assets
6. **Rate Limiting**: Prevent abuse

## Error Handling

### Frontend

```typescript
try {
  await apiCall();
} catch (error) {
  // Display user-friendly error
  setError(error.message);
}
```

### Backend

```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
```

## Monitoring & Observability

### Current Logging

- **Console logs**: All events logged to stdout
- **Structured logging**: JSON-formatted log entries
- **User-visible logs**: Via Connection Terminal

### Production Recommendations

1. **Application Monitoring**: Use Sentry or similar
2. **Performance Monitoring**: New Relic, DataDog
3. **Log Aggregation**: ELK stack, Papertrail
4. **Uptime Monitoring**: UptimeRobot, Pingdom
5. **User Analytics**: PostHog, Mixpanel

## Scalability Path

### Phase 1 (Current): MVP
- Single server
- In-memory database
- No caching

### Phase 2: Production-Ready
- Persistent database
- Redis caching
- SSL/HTTPS
- Error tracking

### Phase 3: Scale
- Multiple backend instances
- Load balancer
- Database read replicas
- CDN for frontend

### Phase 4: Enterprise
- Microservices architecture
- Message queue (RabbitMQ/Kafka)
- Separate logging service
- Auto-scaling

## Technology Choices Rationale

### Why FastAPI?
- High performance (async)
- Automatic API documentation
- Type safety with Pydantic
- Modern Python features

### Why React?
- Component reusability
- Large ecosystem
- Good TypeScript support
- Fast development

### Why Argon2?
- Most secure password hashing
- Resistant to GPU attacks
- Memory-hard algorithm
- Recommended by security experts

### Why JWT?
- Stateless authentication
- Scales horizontally
- Works across domains
- Industry standard

## Future Enhancements

1. **WebSocket Integration**: Real-time log streaming
2. **Database Migration**: PostgreSQL support
3. **Email Service**: Password reset via email
4. **2FA**: Two-factor authentication
5. **API Rate Limiting**: Prevent abuse
6. **Audit Logs**: Track all user actions
7. **Session Management**: Active session tracking
8. **eBay API Integration**: Full eBay API features
9. **Bulk Operations**: Process multiple eBay items
10. **Webhooks**: eBay event notifications
