# eBay Data Management - Database Schema

## Overview

This schema is designed to store comprehensive eBay business data including sales, purchases, financials, fees, refunds, communications, and offers.

## Technology Choice: PostgreSQL

**Reasons:**
- JSONB support for flexible eBay data
- Full-text search for messages
- Robust indexing for fast queries
- Excellent for financial data (DECIMAL types)
- Strong ACID compliance
- Scalable for business growth

## Core Tables

### 1. Users (Existing - Enhanced)

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'admin')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- eBay Connection
    ebay_connected BOOLEAN DEFAULT FALSE,
    ebay_user_id VARCHAR(100),  -- eBay's user ID
    ebay_access_token TEXT,
    ebay_refresh_token TEXT,
    ebay_token_expires_at TIMESTAMP,
    ebay_marketplace_id VARCHAR(50) DEFAULT 'EBAY_US',
    ebay_last_sync_at TIMESTAMP,
    
    -- Settings
    notification_preferences JSONB DEFAULT '{}',
    display_preferences JSONB DEFAULT '{}'
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_ebay_user_id ON users(ebay_user_id);
```

### 2. eBay Orders

```sql
CREATE TABLE ebay_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- eBay IDs
    order_id VARCHAR(100) UNIQUE NOT NULL,  -- eBay order ID
    legacy_order_id VARCHAR(100),
    
    -- Order Info
    order_status VARCHAR(50) NOT NULL,  -- NEW, PAID, SHIPPED, COMPLETED, CANCELLED
    order_date TIMESTAMP NOT NULL,
    last_modified_date TIMESTAMP,
    
    -- Buyer Info
    buyer_username VARCHAR(100),
    buyer_email VARCHAR(255),
    buyer_user_id VARCHAR(100),
    buyer_checkout_message TEXT,
    
    -- Shipping
    shipping_address JSONB,  -- Full address object
    shipping_service VARCHAR(100),
    shipping_carrier VARCHAR(50),
    tracking_number VARCHAR(100),
    shipped_date TIMESTAMP,
    delivery_date TIMESTAMP,
    
    -- Financial
    total_amount DECIMAL(10, 2) NOT NULL,
    subtotal DECIMAL(10, 2),
    shipping_cost DECIMAL(10, 2),
    tax_amount DECIMAL(10, 2),
    currency_code VARCHAR(3) DEFAULT 'USD',
    
    -- Payment
    payment_method VARCHAR(50),
    payment_date TIMESTAMP,
    payout_date TIMESTAMP,
    payout_id VARCHAR(100),
    
    -- Metadata
    raw_data JSONB,  -- Full eBay API response
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    synced_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_orders_user ON ebay_orders(user_id);
CREATE INDEX idx_orders_order_id ON ebay_orders(order_id);
CREATE INDEX idx_orders_status ON ebay_orders(order_status);
CREATE INDEX idx_orders_date ON ebay_orders(order_date DESC);
CREATE INDEX idx_orders_buyer ON ebay_orders(buyer_username);
```

### 3. Order Line Items

```sql
CREATE TABLE order_line_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES ebay_orders(id) ON DELETE CASCADE,
    
    -- Item IDs
    line_item_id VARCHAR(100) UNIQUE NOT NULL,
    listing_id VARCHAR(100),
    sku VARCHAR(100),
    
    -- Product Info
    title TEXT NOT NULL,
    item_location VARCHAR(255),
    quantity INTEGER NOT NULL DEFAULT 1,
    
    -- Pricing
    unit_price DECIMAL(10, 2) NOT NULL,
    total_price DECIMAL(10, 2) NOT NULL,
    discount_amount DECIMAL(10, 2) DEFAULT 0,
    
    -- Item Details
    image_url TEXT,
    condition VARCHAR(50),
    category_id VARCHAR(50),
    
    -- Metadata
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_line_items_order ON order_line_items(order_id);
CREATE INDEX idx_line_items_listing ON order_line_items(listing_id);
CREATE INDEX idx_line_items_sku ON order_line_items(sku);
```

### 4. eBay Listings

```sql
CREATE TABLE ebay_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Listing IDs
    listing_id VARCHAR(100) UNIQUE NOT NULL,
    sku VARCHAR(100),
    
    -- Listing Info
    title TEXT NOT NULL,
    description TEXT,
    subtitle TEXT,
    category_id VARCHAR(50),
    category_name VARCHAR(255),
    
    -- Status
    listing_status VARCHAR(50) NOT NULL,  -- ACTIVE, ENDED, SOLD
    quantity_available INTEGER DEFAULT 0,
    quantity_sold INTEGER DEFAULT 0,
    
    -- Pricing
    price DECIMAL(10, 2) NOT NULL,
    currency_code VARCHAR(3) DEFAULT 'USD',
    listing_type VARCHAR(50),  -- FIXED_PRICE, AUCTION
    
    -- Dates
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    
    -- Media
    primary_image_url TEXT,
    image_urls JSONB,  -- Array of image URLs
    
    -- Details
    condition VARCHAR(50),
    condition_description TEXT,
    location VARCHAR(255),
    shipping_options JSONB,
    return_policy JSONB,
    
    -- Metadata
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    synced_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_listings_user ON ebay_listings(user_id);
CREATE INDEX idx_listings_listing_id ON ebay_listings(listing_id);
CREATE INDEX idx_listings_sku ON ebay_listings(sku);
CREATE INDEX idx_listings_status ON ebay_listings(listing_status);
CREATE INDEX idx_listings_title ON ebay_listings USING gin(to_tsvector('english', title));
```

### 5. Offers

```sql
CREATE TABLE ebay_offers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    listing_id UUID REFERENCES ebay_listings(id) ON DELETE SET NULL,
    
    -- Offer IDs
    offer_id VARCHAR(100) UNIQUE NOT NULL,
    ebay_listing_id VARCHAR(100),
    
    -- Buyer Info
    buyer_username VARCHAR(100),
    buyer_user_id VARCHAR(100),
    
    -- Offer Details
    offer_amount DECIMAL(10, 2) NOT NULL,
    quantity INTEGER DEFAULT 1,
    offer_message TEXT,
    
    -- Status
    offer_status VARCHAR(50) NOT NULL,  -- PENDING, ACCEPTED, DECLINED, COUNTERED, EXPIRED
    counter_offer_amount DECIMAL(10, 2),
    
    -- Dates
    offer_date TIMESTAMP NOT NULL,
    expiration_date TIMESTAMP,
    response_date TIMESTAMP,
    
    -- Metadata
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    synced_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_offers_user ON ebay_offers(user_id);
CREATE INDEX idx_offers_listing ON ebay_offers(listing_id);
CREATE INDEX idx_offers_status ON ebay_offers(offer_status);
CREATE INDEX idx_offers_date ON ebay_offers(offer_date DESC);
CREATE INDEX idx_offers_buyer ON ebay_offers(buyer_username);
```

### 6. Messages/Communications

```sql
CREATE TABLE ebay_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    order_id UUID REFERENCES ebay_orders(id) ON DELETE SET NULL,
    listing_id UUID REFERENCES ebay_listings(id) ON DELETE SET NULL,
    
    -- Message IDs
    message_id VARCHAR(100) UNIQUE NOT NULL,
    thread_id VARCHAR(100),  -- Group related messages
    parent_message_id VARCHAR(100),  -- For replies
    
    -- Participants
    sender_username VARCHAR(100),
    sender_user_id VARCHAR(100),
    recipient_username VARCHAR(100),
    recipient_user_id VARCHAR(100),
    
    -- Message Content
    subject TEXT,
    body TEXT NOT NULL,
    message_type VARCHAR(50),  -- QUESTION, ISSUE, SHIPPING, FEEDBACK, etc.
    
    -- Status
    is_read BOOLEAN DEFAULT FALSE,
    is_flagged BOOLEAN DEFAULT FALSE,
    is_archived BOOLEAN DEFAULT FALSE,
    direction VARCHAR(20) NOT NULL,  -- INCOMING, OUTGOING
    
    -- Dates
    message_date TIMESTAMP NOT NULL,
    read_date TIMESTAMP,
    
    -- Metadata
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_messages_user ON ebay_messages(user_id);
CREATE INDEX idx_messages_thread ON ebay_messages(thread_id);
CREATE INDEX idx_messages_order ON ebay_messages(order_id);
CREATE INDEX idx_messages_listing ON ebay_messages(listing_id);
CREATE INDEX idx_messages_date ON ebay_messages(message_date DESC);
CREATE INDEX idx_messages_unread ON ebay_messages(user_id, is_read) WHERE is_read = FALSE;
CREATE INDEX idx_messages_search ON ebay_messages USING gin(to_tsvector('english', subject || ' ' || body));
```

### 7. Transactions/Financials

```sql
CREATE TABLE ebay_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    order_id UUID REFERENCES ebay_orders(id) ON DELETE SET NULL,
    
    -- Transaction IDs
    transaction_id VARCHAR(100) UNIQUE NOT NULL,
    transaction_type VARCHAR(50) NOT NULL,  -- SALE, REFUND, FEE, PAYOUT, ADJUSTMENT
    
    -- Financial Details
    amount DECIMAL(10, 2) NOT NULL,
    currency_code VARCHAR(3) DEFAULT 'USD',
    fee_amount DECIMAL(10, 2) DEFAULT 0,
    net_amount DECIMAL(10, 2) NOT NULL,  -- amount - fee_amount
    
    -- Transaction Info
    transaction_date TIMESTAMP NOT NULL,
    description TEXT,
    reference_id VARCHAR(100),  -- Links to order, listing, etc.
    
    -- Status
    transaction_status VARCHAR(50),  -- COMPLETED, PENDING, FAILED
    payout_id VARCHAR(100),
    payout_date TIMESTAMP,
    
    -- Metadata
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    synced_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_transactions_user ON ebay_transactions(user_id);
CREATE INDEX idx_transactions_order ON ebay_transactions(order_id);
CREATE INDEX idx_transactions_type ON ebay_transactions(transaction_type);
CREATE INDEX idx_transactions_date ON ebay_transactions(transaction_date DESC);
CREATE INDEX idx_transactions_payout ON ebay_transactions(payout_id);
```

### 8. Fees

```sql
CREATE TABLE ebay_fees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    order_id UUID REFERENCES ebay_orders(id) ON DELETE SET NULL,
    listing_id UUID REFERENCES ebay_listings(id) ON DELETE SET NULL,
    
    -- Fee IDs
    fee_id VARCHAR(100) UNIQUE NOT NULL,
    fee_type VARCHAR(50) NOT NULL,  -- LISTING, FINAL_VALUE, SHIPPING, PROMOTION, etc.
    
    -- Financial Details
    fee_amount DECIMAL(10, 2) NOT NULL,
    currency_code VARCHAR(3) DEFAULT 'USD',
    
    -- Fee Info
    fee_date TIMESTAMP NOT NULL,
    description TEXT,
    reference_id VARCHAR(100),
    
    -- Metadata
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    synced_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_fees_user ON ebay_fees(user_id);
CREATE INDEX idx_fees_order ON ebay_fees(order_id);
CREATE INDEX idx_fees_listing ON ebay_fees(listing_id);
CREATE INDEX idx_fees_type ON ebay_fees(fee_type);
CREATE INDEX idx_fees_date ON ebay_fees(fee_date DESC);
```

### 9. Refunds

```sql
CREATE TABLE ebay_refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    order_id UUID REFERENCES ebay_orders(id) ON DELETE SET NULL,
    
    -- Refund IDs
    refund_id VARCHAR(100) UNIQUE NOT NULL,
    return_id VARCHAR(100),
    case_id VARCHAR(100),
    
    -- Refund Details
    refund_amount DECIMAL(10, 2) NOT NULL,
    refund_type VARCHAR(50),  -- FULL, PARTIAL, SHIPPING_ONLY
    refund_reason VARCHAR(100),
    currency_code VARCHAR(3) DEFAULT 'USD',
    
    -- Status
    refund_status VARCHAR(50) NOT NULL,  -- PENDING, COMPLETED, FAILED
    
    -- Dates
    refund_date TIMESTAMP NOT NULL,
    issued_date TIMESTAMP,
    
    -- Details
    buyer_note TEXT,
    seller_note TEXT,
    
    -- Metadata
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    synced_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_refunds_user ON ebay_refunds(user_id);
CREATE INDEX idx_refunds_order ON ebay_refunds(order_id);
CREATE INDEX idx_refunds_status ON ebay_refunds(refund_status);
CREATE INDEX idx_refunds_date ON ebay_refunds(refund_date DESC);
```

### 10. Sync Jobs

```sql
CREATE TABLE sync_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Job Info
    job_type VARCHAR(50) NOT NULL,  -- FULL, INCREMENTAL, ORDERS, MESSAGES, etc.
    job_status VARCHAR(50) NOT NULL,  -- QUEUED, RUNNING, COMPLETED, FAILED
    
    -- Sync Details
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    records_synced INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    
    -- Error Info
    error_message TEXT,
    error_details JSONB,
    
    -- Metadata
    sync_params JSONB,  -- Date ranges, filters, etc.
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_sync_jobs_user ON sync_jobs(user_id);
CREATE INDEX idx_sync_jobs_status ON sync_jobs(job_status);
CREATE INDEX idx_sync_jobs_created ON sync_jobs(created_at DESC);
```

### 11. System Logs

```sql
CREATE TABLE ebay_api_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- Log Details
    timestamp TIMESTAMP DEFAULT NOW(),
    event_type VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    
    -- Request/Response
    request_data JSONB,
    response_data JSONB,
    
    -- Status
    status VARCHAR(20) NOT NULL,  -- success, error, info
    error TEXT,
    
    -- Performance
    duration_ms INTEGER,
    
    -- Metadata
    endpoint VARCHAR(255),
    http_status INTEGER
);

CREATE INDEX idx_api_logs_user ON ebay_api_logs(user_id);
CREATE INDEX idx_api_logs_timestamp ON ebay_api_logs(timestamp DESC);
CREATE INDEX idx_api_logs_event_type ON ebay_api_logs(event_type);
```

## Views for Common Queries

### Sales Summary View

```sql
CREATE VIEW sales_summary AS
SELECT 
    user_id,
    DATE_TRUNC('day', order_date) as sale_date,
    COUNT(*) as order_count,
    SUM(total_amount) as total_sales,
    SUM(shipping_cost) as total_shipping,
    SUM(tax_amount) as total_tax,
    AVG(total_amount) as avg_order_value
FROM ebay_orders
WHERE order_status NOT IN ('CANCELLED')
GROUP BY user_id, DATE_TRUNC('day', order_date);
```

### Unread Messages View

```sql
CREATE VIEW unread_messages AS
SELECT 
    user_id,
    COUNT(*) as unread_count,
    MAX(message_date) as latest_message_date
FROM ebay_messages
WHERE is_read = FALSE AND direction = 'INCOMING'
GROUP BY user_id;
```

### Pending Offers View

```sql
CREATE VIEW pending_offers AS
SELECT 
    o.*,
    l.title as listing_title,
    l.price as listing_price
FROM ebay_offers o
LEFT JOIN ebay_listings l ON o.listing_id = l.id
WHERE o.offer_status = 'PENDING'
ORDER BY o.offer_date DESC;
```

## Migration Strategy

1. **Phase 1**: Set up PostgreSQL database
2. **Phase 2**: Create base tables (users, orders, transactions)
3. **Phase 3**: Add messaging and offers tables
4. **Phase 4**: Add sync jobs and logging
5. **Phase 5**: Create views and optimize indexes

## Data Retention Policy

- **Active Data**: Keep forever
- **Sync Logs**: Keep 90 days
- **API Logs**: Keep 30 days
- **Archived Messages**: Keep 1 year

## Backup Strategy

- Daily automated backups
- Point-in-time recovery enabled
- 30-day backup retention
- Monthly archive to cold storage
