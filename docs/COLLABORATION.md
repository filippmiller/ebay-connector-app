# Collaboration Notes - eBay Connector App

**Last Updated:** 2025-11-06  
**Status:** Active debugging session - Railway migrations

---

## Current Problem

Railway backend deployment is experiencing migration issues. The migrations appear to start but logs cut off, making it difficult to diagnose what's happening.

### Symptoms
- Migrations start (`alembic upgrade heads`)
- Logs show "Will assume transactional DDL" then cut off
- **Container restart loop**: Railway keeps stopping and restarting the container
- **No migration logs**: Print statements from `add_core_ops_tables` don't appear (likely because it's already applied and skipped)
- Multiple head revisions: `add_raw_payload_line_items`, `add_core_ops_tables`, `multi_account_001`
- Current revision shows `add_core_ops_tables (head)` - this migration is already applied

### Recent Changes
- Made migrations idempotent (check for existing tables/columns/indexes before creating)
- Fixed indentation issues in migration files
- Added detailed logging with `print()` statements for Railway visibility
- Migration file: `backend/alembic/versions/20251021_171302_add_buying_inventory_transactions_financials.py`

---

## Notes from Smart Friend

<!-- 
FRIEND: Please add your observations, suggestions, or questions here.
Use clear sections and be specific about what you're seeing or thinking.
-->

### [Add your notes here]

---

## Notes from AI Assistant (Auto)

### 2025-11-06 15:15
- Added `print()` statements with `flush=True` to ensure logs appear in Railway
- Wrapped migration in try/except for better error handling
- All table creation now uses `log_print()` function that prints to stdout

### 2025-11-06 15:20 - Analysis of log8.txt
**Critical Observations:**
1. **Container Restart Loop**: Log shows "Stopping Container" multiple times - Railway is killing and restarting the container
2. **No Migration Logs**: Still no `[migration]` print statements appearing, even though migrations are running
3. **Current Revision**: Log shows `add_core_ops_tables (head)` is already applied - this migration might be skipped
4. **Multiple Heads**: Three head revisions exist, but we're not seeing which ones are being applied

**Key Insight**: If `add_core_ops_tables` is already the current revision, Alembic will skip it and only run the other two heads (`add_raw_payload_line_items` and `multi_account_001`). Our print statements are in `add_core_ops_tables`, so they won't execute if that migration is skipped!

**Possible Issues:**
- Railway might have a timeout that kills containers during long migrations
- The other two migrations might be hanging or taking too long
- We need to add logging to ALL migrations, not just one

### 2025-11-06 15:25 - BREAKTHROUGH! log9.txt shows real error
**🎯 ROOT CAUSE IDENTIFIED:**

```
psycopg2.OperationalError: connection to server at "aws-1-us-east-1.pooler.supabase.com" 
(3.227.209.82), port 5432 failed: server closed the connection unexpectedly
This probably means the server terminated abnormally before or while processing the request.
```

**The Problem:**
- **Supabase connection is being closed unexpectedly** during migration attempts
- This is NOT a migration code issue - it's a database connection issue
- The startup script handles it gracefully: `[entry] WARNING: Migrations failed, continuing anyway...`
- Server still starts, but migrations don't run

**Possible Causes:**
1. **Supabase Connection Pool Limits**: Supabase free tier has connection limits (typically 60-100 connections)
2. **Connection Pool Exhaustion**: Multiple migration attempts might be exhausting the pool
3. **Supabase Pooler Issues**: The pooler might be closing idle connections
4. **Network/Timeout Issues**: Connection might be timing out before migration completes

**Solutions to Try:**
1. **Add connection retry logic** with exponential backoff
2. **Use direct connection** instead of pooler (if Supabase allows)
3. **Reduce connection pool size** in SQLAlchemy
4. **Add connection timeout/keepalive settings**
5. **Run migrations separately** (not during startup) - use a one-time migration job

### Next Steps
1. ✅ **ROOT CAUSE FOUND**: Supabase connection issues, not migration code
2. ✅ **IMPLEMENTED**: Connection retry logic with exponential backoff in start.sh
3. ✅ **IMPLEMENTED**: Improved SQLAlchemy connection settings (timeout, keepalive, pool size)
4. ✅ **IMPLEMENTED**: Updated Alembic env.py with same connection settings
5. ⏳ **TODO**: Test the changes on Railway
6. ⏳ **TODO**: Consider using direct connection URL instead of pooler (if issues persist)

### 2025-11-06 15:30 - Solutions Implemented
**✅ Changes Made:**

1. **SQLAlchemy Engine Settings** (`backend/app/models_sqlalchemy/__init__.py`):
   - Increased `connect_timeout` to 10s
   - Added TCP keepalive settings (keepalives, keepalives_idle, keepalives_interval, keepalives_count)
   - Reduced `pool_size` to 5 (Supabase free tier limit)
   - Set `pool_recycle=3600` (1 hour, matches Supabase idle timeout)
   - Added `pool_timeout=30s`

2. **Migration Retry Logic** (`backend/start.sh`):
   - Added `run_migrations_with_retry()` function
   - 3 attempts with exponential backoff (2s, 4s, 8s delays)
   - Clear logging for each attempt

3. **Alembic Connection Settings** (`backend/alembic/env.py`):
   - Added same keepalive and timeout settings as SQLAlchemy engine
   - Ensures consistent connection behavior during migrations

---

## Questions for Discussion

1. **Migration Logging**: Why aren't migration logs appearing in Railway? Is it a buffering issue or something else?

2. **Multiple Heads**: Should we merge the three head revisions into a single migration chain?

3. **Container Restarts**: The logs show "Stopping Container" - is Railway restarting due to timeouts?

---

## Code Changes Made

### Migration File
- `backend/alembic/versions/20251021_171302_add_buying_inventory_transactions_financials.py`
  - Added idempotent checks for all tables
  - Added `log_print()` function for guaranteed stdout output
  - Wrapped in try/except block

### Startup Script
- `backend/start.sh`
  - Uses `alembic upgrade heads` to handle multiple heads
  - Continues even if migrations fail (with warning)

---

## How to Use This Document

1. **Friend**: Add your observations, suggestions, or questions in the "Notes from Smart Friend" section
2. **AI**: Read the friend's notes, implement changes, and document what was done
3. **Both**: Use this as a shared knowledge base to track progress

---

## Git Workflow

1. Friend commits notes: `git commit -m "Notes: [description]"`
2. AI reads notes, makes code changes
3. AI commits code: `git commit -m "Fix: [description]"`
4. Both push/pull as needed

