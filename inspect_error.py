import sys
import os
import asyncio
from datetime import datetime

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.database import SessionLocal
from app.models_sqlalchemy.models import AccountingBankStatement

def inspect_failed_statement():
    db = SessionLocal()
    try:
        # Get the latest statement (or ID 7 as mentioned by user)
        # Sort by id desc to get the most recent one
        stmt = db.query(AccountingBankStatement).order_by(AccountingBankStatement.id.desc()).first()
        
        if not stmt:
            print("No statements found in DB.")
            return

        print(f"Statement ID: {stmt.id}")
        print(f"Status: {stmt.status}")
        print(f"Error Message: {stmt.error_message}")
        print(f"Created At: {stmt.created_at}")
        
        if stmt.raw_openai_response:
            print("\n--- Raw OpenAI Response (First 500 chars) ---")
            print(str(stmt.raw_openai_response)[:500])
        else:
            print("\nNo raw OpenAI response stored.")

    finally:
        db.close()

if __name__ == "__main__":
    inspect_failed_statement()
