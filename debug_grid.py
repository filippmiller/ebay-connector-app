import sys
import os
import asyncio
from typing import List

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.database import SessionLocal
from app.models.user import User as UserModel
from app.routers.grids_data import _get_accounting_bank_statements_data, _get_accounting_transactions_grid_data
from app.routers.grid_layouts import LAYOUTS

def test_grid_data():
    db = SessionLocal()
    try:
        # Mock user
        params = LAYOUTS['accounting_bank_statements']
        selected_cols = params['visible_columns']
        
        print(f"Selecting columns: {selected_cols}")
        
        data = _get_accounting_bank_statements_data(
            db=db,
            current_user=UserModel(id=1, email="test@example.com"), # Dummy user
            selected_cols=selected_cols,
            limit=10,
            offset=0,
            sort_column=None,
            sort_dir="desc"
        )
        
        print(f"Total rows: {data['total']}")
        if data['rows']:
            print("First row keys:", data['rows'][0].keys())
            print("First row sample:", data['rows'][0])
        else:
            print("No rows returned.")
            
    finally:
        db.close()

if __name__ == "__main__":
    test_grid_data()
