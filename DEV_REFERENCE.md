# eBay Connector - Developer Reference & Architecture

**Source:** Master Prompt provided by Phillip Miller
**Date:** October 21, 2025
**Status:** In Active Development

---

## ARCHITECTURE OVERVIEW

### Tech Stack
- **Backend:** FastAPI + SQLAlchemy + Postgres (SQLite for dev)
- **Frontend:** React + Tailwind + shadcn/ui
- **Deployment:** Fly.io (Backend) + Cloudflare Pages (Frontend)
- **Sync:** Background jobs every 5 minutes (APScheduler/Celery)

---

## PHASE 1: DATABASE MODELS

### Core Models (SQLAlchemy)

#### 1. **Buying** (Orders/Transactions)
```python
- id (PK)
- item_id (unique, indexed)
- tracking_number
- buyer_id, seller_id (indexed)
- title
- paid_date (DateTime, indexed)
- amount_paid, sale_price, ebay_fee, shipping_cost, refund
- profit (calculated: sale_price - amount_paid - ebay_fee - shipping_cost)
- status (Enum: unpaid, in_transit, received, cancelled)
- storage, comment, author
- rec_created, rec_updated (timestamps)
```

#### 2. **SKU** (Internal Part Catalog)
```python
- id (PK)
- sku_code (unique, indexed)
- model, category (indexed), condition
- part_number, price, title, description, brand
- image_url
- rec_created, rec_updated
```

#### 3. **Listing** (eBay-Linked Listings)
```python
- id (PK)
- sku_id (FK → sku.id)
- ebay_listing_id (unique, indexed)
- price, ebay_price, shipping_group
- condition, storage
- warehouse_id (FK → warehouses.id)
- rec_created, rec_updated
```

#### 4. **Inventory** (Stock Management)
```python
- id (PK)
- sku_id (FK → sku.id)
- storage, status (available, listed, sold, frozen, reserved)
- category, price
- warehouse_id (FK → warehouses.id)
- rec_created, rec_updated
```

#### 5. **Return** (Returns & Cancellations)
```python
- id (PK)
- return_id (unique, indexed)
- item_id, ebay_order_id (indexed)
- buyer, tracking_number, reason
- sale_price, refund_amount, status, comment
- return_date, resolved_date
- rec_created, rec_updated
```

#### 6. **Warehouse**
```python
- id (PK)
- name (unique), location, capacity, warehouse_type
- rec_created, rec_updated
```

#### 7. **User** (Extended from existing)
```python
- id (PK), email (unique, indexed), username, hashed_password
- role (admin, purchaser, lister, checker, viewer, user)
- ebay_connected, ebay_access_token, ebay_refresh_token
- ebay_token_expires_at, ebay_environment
- created_at, updated_at
```

#### 8. **SyncLog**
```python
- id (PK)
- user_id (FK → users.id)
- endpoint, record_count, duration, status
- error_message
- sync_started_at, sync_completed_at
- rec_created
```

#### 9. **Report**
```python
- id (PK)
- report_type, filters, file_path
- generated_by (FK → users.id)
- generated_at, rec_created
```

---

## PHASE 2: EBAY SYNC ENGINE

### Background Sync (Every 5 Minutes)

**Implementation:**
- Use APScheduler or Celery + Redis
- Authenticate via eBay OAuth (existing credentials)
- Pull from eBay APIs:
  - Orders/Transactions → Buying table
  - Active Listings → Listing table
  - Returns/Cancellations → Returns table

**Sync Flow:**
1. Start sync job → create SyncLog entry
2. Fetch data from eBay API
3. Upsert records (INSERT or UPDATE on conflict)
4. Calculate profit for each order
5. Update SyncLog with results
6. Log errors if any

**Admin API:**
- `POST /admin/resync` → Manual refresh trigger

---

## PHASE 3: PROFIT ENGINE

**Formula:**
```python
profit = sale_price - amount_paid - ebay_fee - shipping_cost
```

**Features:**
- Calculate on each sync
- Store in `Buying.profit` field
- Mark negative profits in RED on UI
- Summary endpoint: `GET /api/stats/profit`

---

## PHASE 4: API ROUTES

| Route | Purpose |
|-------|---------|
| `/api/buying` | GET/POST/PUT/DELETE for orders |
| `/api/sku` | CRUD for SKUs |
| `/api/listing` | CRUD + eBay sync status |
| `/api/inventory` | GET/PUT for storage & status |
| `/api/returns` | GET/PUT for buyer returns |
| `/api/report/export` | CSV export |
| `/api/sync/status` | Last sync summary |

**Requirements:**
- Support filtering, pagination, sorting
- JSON responses
- Authentication required (JWT)
- Admin-only routes for sensitive operations

---

## PHASE 5: FRONTEND MODULES

### Tab Structure
```
TASKS | BUYING | SKU | LISTING | INVENTORY | RETURNS
```

### 1. **BUYING Tab**
- Table view with filters (buyer, seller, status, dates)
- Columns: ID, Image, ItemID, Tracking, Refund, **Profit** (red if negative), Buyer, Seller, PaidDate, Amount, Status, Title, Comment
- Bottom detail pane (seller info, image, payment info)
- Actions: Edit, Delete, Export

### 2. **SKU Tab**
- CRUD interface
- Columns: SKU, Model, Category, Condition, Part #, Price, Title, Description, Brand
- Image preview
- Actions: Add, Edit, Delete, Bulk Import

### 3. **LISTING Tab**
- eBay-linked listings
- Columns: SKU, Model, Price (local vs eBay), Shipping Group, Condition, Storage, Warehouse
- Batch actions: Clone, Commit Selected, Remove Selected
- eBay Listing API integration

### 4. **INVENTORY Tab**
- Stock-level control
- Columns: SKU, Storage, Status, Category, Price, Warehouse
- Actions: Change Listings, Freeze, Relist, Mark As Listed
- Inline status editing

### 5. **RETURNS Tab**
- Columns: ReturnID, ItemID, Buyer, Tracking, Reason, Sale Price, Status, Comment
- Sync via eBay Post-Order API
- Actions: Process Refund, Close, Export

---

## PHASE 6: UTILITIES & FEATURES

- Saved Filters (per user, localStorage or DB)
- CSV / XLS Export
- Column drag + visibility control
- Image zoom
- Status badges with colors
- Role-based access (Admin, Purchaser, Lister, Checker, Viewer)
- Audit logs (edits + timestamps)
- Notification bar for sync failures or profit drops

---

## PHASE 7: BACKGROUND & DEPLOYMENT

### Background Jobs
- APScheduler or Celery for cron (every 5 min)
- Job types:
  - Order sync
  - Listing sync
  - Returns sync
  - Analytics calculation

### Environment Variables
```bash
# eBay API
EBAY_APP_ID=...
EBAY_CERT_ID=...
EBAY_DEV_ID=...
EBAY_REDIRECT_URI=...

# Database
DATABASE_URL=postgresql://...

# JWT
JWT_SECRET_KEY=...
JWT_ALGORITHM=HS256
```

### Deployment
- **Backend:** Fly.io with Postgres
- **Frontend:** Cloudflare Pages
- **Database:** Fly.io Postgres or external (Supabase, etc.)
- Use Alembic for migrations
- Volume mount for persistent storage

---

## PHASE 8: DASHBOARD & REPORTS

### Admin Dashboard (`/admin/dashboard`)

**Widgets:**
- Total purchases
- Total listings
- Returns count
- Profit trend graph (LineChart from recharts)
- Top sellers/buyers
- Recent sync status

**Export:**
- CSV or PDF
- Filtered by date range, category, status

---

## PHASE 9: FUTURE MODULES

1. **Inventory 2.0:** OCR + AI tagging for parts
2. **Messages (AI Draft):** Auto-reply assistant for buyer messages
3. **Extra Module:** Analytics by seller/category/ROI

---

## CURRENT IMPLEMENTATION STATUS

### ✅ Completed
- Registration & Login (admin roles)
- eBay OAuth (sandbox + production)
- Environment switching
- Order sync (1,811 orders)
- Orders display with filters
- Todo list with LOG section
- SQLAlchemy models defined

### 🔄 In Progress
- Fly.io volume creation (waiting for auth)
- Postgres provisioning
- Alembic migrations setup

### ⏳ Pending
- Profit calculation implementation
- Background sync jobs (5-minute interval)
- Frontend modules (BUYING, SKU, LISTING, INVENTORY, RETURNS)
- Role-based access control
- Analytics dashboard
- CSV export functionality

---

## NAMING CONVENTIONS

### Database Tables
- Use lowercase with underscores: `buying`, `sku`, `listings`, `inventory`, `returns`

### Model Fields
- Use snake_case: `item_id`, `buyer_username`, `rec_created`
- Timestamps: `rec_created`, `rec_updated` (or `created_at`, `updated_at`)

### API Endpoints
- RESTful: `/api/buying`, `/api/sku`, `/api/listing`
- Actions: `/api/buying/{id}`, `/api/sync/status`

### Frontend Components
- PascalCase: `BuyingTab`, `SKUTab`, `ListingTab`
- Pages: `BuyingPage`, `DashboardPage`

---

## MIGRATION PLAN (SQLite → Postgres)

### Step 1: Parallel Operation
- Keep SQLite as read-only
- Write to Postgres
- Verify parity

### Step 2: Data Migration
- One-off script to copy all data
- ON CONFLICT upserts on unique keys:
  - orders: `(order_id)`
  - listings: `(ebay_item_id)`
  - sku: `(sku_code)`

### Step 3: Cutover
- Switch DATABASE_URL to Postgres
- Remove SQLite write paths
- Verify sync idempotency

---

## TESTING CHECKLIST

### Backend
- [ ] Order sync (all 1,811 orders)
- [ ] Profit calculation accuracy
- [ ] API endpoints (CRUD operations)
- [ ] Background jobs (5-min sync)
- [ ] Data persistence through redeploy

### Frontend
- [ ] All tabs render correctly
- [ ] Filters work (buyer, seller, date, status)
- [ ] Export to CSV
- [ ] Role-based UI (admin vs user)
- [ ] Real-time updates

### Integration
- [ ] eBay OAuth flow
- [ ] Token refresh mechanism
- [ ] Sync idempotency (no duplicates)
- [ ] Error handling & logging

---

## DEPLOYMENT CHECKLIST

- [ ] Fly.io volume created and mounted
- [ ] Postgres database provisioned
- [ ] Alembic migrations applied
- [ ] Environment variables set
- [ ] Backend deployed (FastAPI)
- [ ] Frontend deployed (React)
- [ ] Health checks passing
- [ ] Data persistence verified

---

## NOTES

- **Admin Emails:** filippmiller@gmail.com, mylifeis0plus1@gmail.com, nikitin.sergei.v@gmail.com
- **OAuth Redirect:** https://ebay-connection-app-k0ge3h93.devinapps.com/ebay/callback
- **Backend URL:** https://app-qngipkhc.fly.dev
- **Frontend URL:** https://ebay-connection-app-k0ge3h93.devinapps.com
- **Todo List:** https://ebay-connection-app-k0ge3h93.devinapps.com/todolist

---

**Last Updated:** October 21, 2025 - 10:50 AM PST
**Maintained By:** Devin AI
**Session:** https://app.devin.ai/sessions/3ef2b75bb4ad437b8274d8223cc18211
