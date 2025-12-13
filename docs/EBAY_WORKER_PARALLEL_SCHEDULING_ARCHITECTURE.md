# eBay Worker Parallel Scheduling Architecture

## Overview
This document describes the parallel execution architecture for eBay background workers, implemented to resolve scheduling bottlenecks where slow workers blocked the entire sync cycle.

## Architecture

### 1. Scheduler (`scheduler.py`)
The scheduler is the entry point for all background sync operations. It has been refactored to support two levels of concurrency:

#### Account-Level Concurrency
-   **Mechanism**: `asyncio.gather` with `asyncio.Semaphore`.
-   **Limit**: Defaults to **5 concurrent accounts**.
-   **Logic**: The `run_cycle_for_all_accounts` function fetches all active eBay accounts, shuffles them (for fairness), and processes them in parallel batches. This ensures that one account with a massive data load does not prevent other accounts from syncing.

#### Worker-Level Concurrency
-   **Mechanism**: `asyncio.gather`.
-   **Limit**: All enabled workers for a single account run simultaneously.
-   **Logic**: Inside `run_cycle_for_account`, the system identifies all enabled worker types (Orders, Offers, Messages, etc.) and launches them as concurrent asyncio tasks.
-   **Isolation**: Each worker uses its own DB session (created within the worker function) to ensure thread/task safety.

### 2. Worker Implementation
Each worker (e.g., `orders_worker.py`, `offers_worker.py`) is designed to be:
-   **Idempotent**: Can be run multiple times without side effects.
-   **Non-Blocking**: Uses `async/await` for all I/O operations (DB and API).
-   **Robust**: Contains top-level `try...except` blocks to ensure that a crash in one worker does not bring down the entire account cycle or the main scheduler loop.

## Benefits
-   **Reduced Latency**: Total cycle time is determined by the slowest single worker, not the sum of all workers.
-   **Fairness**: Small accounts are not blocked by large accounts.
-   **Resilience**: Failures are isolated to the specific worker/account.

## Configuration
-   **Concurrency Limit**: Currently hardcoded to `MAX_CONCURRENT_ACCOUNTS = 5` in `scheduler.py`. This can be exposed as an env var if needed.
-   **Interval**: The main loop interval is controlled by `run_ebay_workers_loop` (default 5 minutes).

## Debugging
-   **Logs**: Check logs for "Running worker cycle for account..." to see start times. Parallel execution will show multiple start logs appearing close together.
-   **Verification**: Use `backend/verify_scheduler.py` (if available) or similar script to simulate concurrent loads.
