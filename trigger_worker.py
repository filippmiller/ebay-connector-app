#!/usr/bin/env python3
"""Quick script to trigger a single worker run for debugging."""
import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.workers.token_refresh_worker import refresh_expiring_tokens

async def main():
    print("=== Triggering single token refresh cycle ===")
    result = await refresh_expiring_tokens()
    print(f"=== Result: {result} ===")

if __name__ == "__main__":
    asyncio.run(main())
