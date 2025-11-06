# Sync Terminal & Messages Sync Fixes

## Issues Identified

### Issue 1: Offers Sync Terminal Disappearing
**Problem:** When offers sync completed, the terminal would disappear immediately, preventing users from viewing the logs.

**Root Cause:** In `EbayConnectionPage.tsx`, the `offersRunId` was being cleared on completion (line 501), which caused the terminal component to unmount since it's conditionally rendered based on `offersRunId`.

**Fix Applied:**
- Removed the `setOffersRunId(null)` call from the `onComplete` handler for offers sync
- Added comment explaining that runId should NOT be cleared to keep terminal visible
- Applied same fix to messages sync terminal

**Files Modified:**
- `frontend/src/pages/EbayConnectionPage.tsx`

### Issue 2: Messages Sync Infinite Loop
**Problem:** Messages sync would loop continuously, trying to fetch the same pages over and over without stopping. The stop button didn't work.

**Root Cause:** 
1. The `while True:` loop in `messages.py` could loop forever if `total_pages` wasn't set correctly or if the response didn't include proper pagination info
2. Cancellation checks weren't frequent enough
3. No safety limits to prevent infinite loops

**Fix Applied:**
1. Changed `while True:` to `while page_number <= max_pages:` with a safety limit of 1000 pages
2. Added check for consecutive empty pages (stop after 3 empty pages)
3. Added validation for `total_pages` (if 0 or None, set to 1)
4. Added cancellation check BEFORE each request (not just at the start of the loop)
5. Added try-catch around the request to handle errors gracefully without breaking the loop
6. Added logging when safety limits are reached

**Files Modified:**
- `backend/app/routers/messages.py`

## Testing Recommendations

1. **Offers Sync:**
   - Start offers sync
   - Wait for completion
   - Verify terminal stays visible with all logs
   - Verify you can scroll through all log entries
   - Verify "Fetched:" and "Stored:" counts are displayed

2. **Messages Sync:**
   - Start messages sync
   - Verify it doesn't loop infinitely
   - Test stop button - it should stop the sync within a few seconds
   - After stopping, verify terminal stays visible with logs
   - Verify cancellation is logged in the terminal

3. **Log Persistence:**
   - Start any sync
   - Refresh the page
   - Verify terminal reloads with historical logs from database
   - Verify all events are displayed correctly

## Log Retrieval

All sync logs are stored persistently in the database (`sync_event_logs` table). You can retrieve them via:

- **API Endpoint:** `GET /api/ebay/sync/logs/{run_id}`
- **Export:** `GET /api/ebay/sync/logs/{run_id}/export` (downloads as NDJSON)

The terminal component automatically loads historical logs on mount via `/api/ebay/sync/logs/${runId}`.

## Notes

- Terminal will now stay visible after sync completes or is stopped
- All sync types (orders, transactions, disputes, messages, offers) now keep terminals visible
- Messages sync has multiple safety mechanisms to prevent infinite loops
- Cancellation checks are more frequent and should respond faster


