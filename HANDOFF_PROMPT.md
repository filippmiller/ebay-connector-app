# eBay Business Management Platform - Session Handoff

## Project Overview

Building a comprehensive eBay business management platform with:
- User authentication (Admin and Regular User roles)
- eBay OAuth integration
- Email-style communication center (Gmail-inspired)
- Orders, offers, and listings management
- Real-time data sync from eBay API
- Admin section for system management

## Current Status

### ✅ Completed

**Database Layer:**
- SQLAlchemy ORM setup with SQLite
- 9 database models created:
  - User (with eBay connection fields)
  - Order & OrderLineItem
  - Listing
  - Offer
  - Message (for email-style interface)
  - Transaction
  - Fee
  - Refund
  - SyncJob
- Database initialized: `/home/ubuntu/ebay-connector-app/backend/ebay_connector.db`
- Models location: `/home/ubuntu/ebay-connector-app/backend/app/db_models/`

**Backend API:**
- FastAPI application running
- CORS configured
- New routers created and registered:
  - `/orders` - Get orders, stats, filtering
  - `/messages` - Get messages by folder, mark read/flagged/archived
  - `/offers` - Get offers, accept/decline/counter actions
- Existing routers:
  - `/auth` - Register, login, password reset (uses old in-memory DB)
  - `/ebay` - OAuth flow, connection status
- Server: http://localhost:8000

**Frontend:**
- React + TypeScript + Tailwind CSS
- Current pages: Login, Register, Dashboard, Password Reset
- Server: http://localhost:5173

**Documentation:**
- DATABASE_SCHEMA.md - Complete schema design
- ROADMAP.md - 9-phase development plan
- EBAY_OAUTH_TROUBLESHOOTING.md - OAuth debugging guide
- ARCHITECTURE.md - System architecture
- PROJECT_STATUS.md - Detailed status

**eBay Integration:**
- OAuth credentials configured (production)
- Client ID: filippmi-betterpl-PRD-0115bff8e-85d4f36a
- Waiting for user to fix redirect URI in eBay Developer Console

### ⚠️ In Progress / Needs Completion

**1. Auth Service Migration (CRITICAL - IN PROGRESS):**
- **Issue**: Auth system still uses in-memory database (`app/services/database.py`)
- **New Service Created**: `app/services/user_service.py` (uses SQLAlchemy)
- **Needs**: Update `app/services/auth.py` to use new UserService instead of old in-memory db
- **Needs**: Update `app/routers/auth.py` to inject database session
- **Files to modify**:
  - `backend/app/services/auth.py` (lines 10, 41, 68, 84, 93)
  - `backend/app/routers/auth.py` (add db: Session = Depends(get_db))

**2. Seed Data Script:**
- Created: `backend/app/seed_data.py`
- Ready to populate database with mock data
- Run after fixing auth migration: `poetry run python -m app.seed_data`

**3. Frontend UI (NOT STARTED):**
- Email-style messages interface (Gmail/Outlook-inspired)
- Orders management view with filtering/search
- Offers management with accept/decline/counter
- Admin dashboard and navigation

### 🎯 Immediate Next Steps

**Step 1: Fix Auth Service (15 minutes)**
```python
# In app/services/auth.py, replace:
from app.services.database import db

# With:
from app.services.user_service import UserService
from app.database import get_db
from fastapi import Depends

# Update all functions to use UserService with db session
# Example:
def authenticate_user(email: str, password: str, db: Session) -> Optional[User]:
    user_service = UserService(db)
    user = user_service.get_user_by_email(email)
    # ... rest of logic
```

**Step 2: Seed Database (2 minutes)**
```bash
cd backend
poetry run python -m app.seed_data
```

**Step 3: Build Frontend UI (2-3 hours)**

**A. Messages Interface (Email-style):**
- Left sidebar with folders: Inbox, Sent, Flagged, Archived
- Unread count badges
- Message list with sender, subject, preview, timestamp
- Thread view for conversations
- Mark read/unread, flag, archive actions
- Search and filter capabilities
- Similar to Gmail/Outlook interface

**B. Orders Management:**
- Filterable table: status, date range, buyer
- Search by order ID, buyer name, email
- Order detail view with line items
- Status badges (PAID, SHIPPED, COMPLETED)
- Export to CSV option

**C. Offers Management:**
- List of pending offers
- Show offer amount vs listing price
- Buyer username and message
- Quick actions: Accept, Decline, Counter
- Offer history/status

**D. Admin vs User Features:**

**Admin Users Can:**
- View system-wide statistics
- Access all sync jobs
- View eBay API logs
- Manage system settings
- See all users' data (future)
- Access admin dashboard

**Regular Users Can:**
- View only their own data (orders, messages, offers)
- Connect their own eBay account
- Manage their listings
- Respond to messages
- Accept/decline offers

### 📂 Key File Locations

**Backend:**
- Main: `backend/app/main.py`
- Config: `backend/app/config.py`
- Database: `backend/app/database.py`
- Models: `backend/app/db_models/`
- Routers: `backend/app/routers/`
- Services: `backend/app/services/`
- .env: `backend/.env`

**Frontend:**
- Main: `frontend/src/App.tsx`
- Pages: `frontend/src/pages/`
- API: `frontend/src/api/`
- Auth Context: `frontend/src/contexts/AuthContext.tsx`
- .env: `frontend/.env`

**Database:**
- Location: `backend/ebay_connector.db` (SQLite)
- Schema: Defined in `backend/app/db_models/`

### 🔧 Technical Details

**Database Schema Highlights:**
- `users` table has `role` field ('user' or 'admin')
- All data tables have `user_id` foreign key for multi-tenancy
- Messages have `is_read`, `is_flagged`, `is_archived` for email-style interface
- Offers have `offer_status`: PENDING, ACCEPTED, DECLINED, COUNTERED
- Orders have `order_status`: NEW, PAID, SHIPPED, COMPLETED, CANCELLED

**API Endpoints Available:**
```
GET  /orders/              - List orders (filterable)
GET  /orders/{id}          - Get order details
GET  /orders/stats/summary - Order statistics

GET  /messages/            - List messages (by folder)
GET  /messages/{id}        - Get message details
PATCH /messages/{id}       - Update message (read/flag/archive)
GET  /messages/stats/summary - Message statistics

GET  /offers/              - List offers (filterable)
POST /offers/{id}/action   - Accept/decline/counter offer
GET  /offers/stats/summary - Offer statistics
```

**Frontend Components Needed:**
- `MessagesPage.tsx` - Email-style interface
- `OrdersPage.tsx` - Orders management
- `OffersPage.tsx` - Offers management
- `AdminDashboardPage.tsx` - Admin-only section
- Update `App.tsx` routes for new pages
- Update `DashboardPage.tsx` to show different views for admin vs user

### 🎨 UI Design Guidelines

**Email-Style Messages Interface:**
- 3-column layout: Sidebar (folders) | Message List | Preview Pane
- Use shadcn/ui components: Separator, Badge, Button, ScrollArea
- Color coding: Unread (bold), Flagged (star icon), Archived (gray)
- Keyboard shortcuts (future): j/k for navigation, e for archive

**Orders Management:**
- Table layout with shadcn/ui Table component
- Status badges with color coding
- Filter chips at top
- Click row to expand details

**Offers Management:**
- Card-based layout
- Show % of listing price
- Prominent action buttons
- Countdown timer for expiration

**Role-Based UI:**
```typescript
// In components, check user role:
const { user } = useAuth();
const isAdmin = user?.role === 'admin';

{isAdmin && (
  <AdminOnlySection />
)}
```

### 🔐 OAuth Status

**Current State:**
- eBay production credentials configured in `backend/.env`
- OAuth flow implemented and working
- **Blocker**: Redirect URI needs to be configured in eBay Developer Console
- User will fix tonight: Set redirect URI to `http://localhost:5173/ebay/callback`
- Once fixed, full OAuth flow will work and can sync real eBay data

**Testing OAuth:**
1. User fixes redirect URI
2. Login as admin@ebay.com / testpass123
3. Click "Connect to eBay"
4. Authorize on eBay
5. Should redirect back and save tokens
6. Can then implement data sync

### 📦 Dependencies Already Installed

**Backend:**
- fastapi, uvicorn
- sqlalchemy, psycopg2-binary, alembic
- python-jose (JWT)
- argon2-cffi (password hashing)
- httpx (HTTP client)
- pydantic-settings

**Frontend:**
- react, react-router-dom
- typescript
- tailwindcss
- shadcn/ui components
- lucide-react (icons)

### 🚀 Commands to Remember

**Start Backend:**
```bash
cd backend
poetry run fastapi dev app/main.py --port 8000
```

**Start Frontend:**
```bash
cd frontend
npm run dev
```

**Seed Database:**
```bash
cd backend
poetry run python -m app.seed_data
```

**Create New User:**
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "username": "user", "password": "pass123", "role": "user"}'
```

### 🎯 User Requirements

**From User:**
1. **Admin section** of the site (system management, all data)
2. **Production section** for regular users (their own data)
3. Download and store ALL eBay records (sales, purchases, financials, fees, refunds, communication, offers)
4. Search through records, present to end user
5. **Offers and customer communication should look like a modern email client** (Gmail/Outlook style)
6. **Role-based access**: Admin sees everything, users see only their data

### 💡 Important Notes

- Using SQLite for now (can upgrade to PostgreSQL later)
- Database file persists between restarts
- All timestamps are UTC
- OAuth tokens stored in users table
- Mock data will help build UI before real eBay sync
- User will fix OAuth redirect URI tonight

### 🐛 Known Issues

1. Auth service still uses old in-memory database (needs migration)
2. Seed script won't work until auth is migrated
3. Frontend UI for new features not built yet
4. No role-based UI restrictions implemented yet

### ✅ Success Criteria

**By End of Next Session:**
- [ ] Auth service migrated to SQLAlchemy ✅
- [ ] Database seeded with mock data ✅
- [ ] Email-style messages interface built ✅
- [ ] Orders management view built ✅
- [ ] Offers management interface built ✅
- [ ] Role-based UI restrictions implemented ✅
- [ ] Admin dashboard with navigation ✅
- [ ] All UI tested with mock data ✅

**After OAuth Fixed:**
- [ ] Test full OAuth flow
- [ ] Implement eBay data sync
- [ ] Replace mock data with real eBay data

### 📞 Contact Points

- User email: admin@ebay.com (mock), filippmiller@gmail.com (real)
- User will fix OAuth redirect URI tonight
- Preference: SQLite for now, can upgrade to PostgreSQL later

---

## Quick Start for Next Session

```bash
# 1. Check servers are running
curl http://localhost:8000/healthz
curl http://localhost:5173

# 2. Fix auth service migration
# Edit: backend/app/services/auth.py
# Edit: backend/app/routers/auth.py

# 3. Seed database
cd backend && poetry run python -m app.seed_data

# 4. Build frontend UI
cd frontend/src/pages
# Create: MessagesPage.tsx, OrdersPage.tsx, OffersPage.tsx, AdminDashboardPage.tsx

# 5. Update routing in App.tsx

# 6. Test everything with mock data
```

Good luck! All the foundation is laid, just need to connect the pieces and build the UI! 🚀
