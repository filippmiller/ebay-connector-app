import sys
import os
import pytest
from sqlalchemy.orm import Session

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models_sqlalchemy import get_db, models
from app.services.database import db as db_service
from app.models.user import UserCreate, UserRole

def test_notification_persistence():
    # Setup: Create a test user
    email = "test_persist_notifications@example.com"
    username = "test_persist"
    password = "password123"
    
    # Clean up existing user if any
    db_gen = get_db()
    db = next(db_gen)
    try:
        existing = db.query(models.User).filter(models.User.email == email).first()
        if existing:
            db.delete(existing)
            db.commit()
            
        # Create user via service (which uses PostgresDatabase.create_user)
        user_data = UserCreate(
            email=email,
            username=username,
            password=password,
            role=UserRole.USER
        )
        # We need to hash password manually if using create_user directly from service?
        # Actually db_service.create_user takes hashed password.
        # But let's use the lower level to be sure or just use what we have.
        # db_service is PostgresDatabase instance.
        
        # Mock hashing
        hashed_pw = "hashed_secret"
        user = db_service.create_user(user_data, hashed_pw)
        
        print(f"User created: {user.email}, worker_notifications_enabled={user.worker_notifications_enabled}")
        assert user.worker_notifications_enabled is True, "Default should be True"
        
        # Test: Update setting to False
        updated_user = db_service.update_user(user.id, {"worker_notifications_enabled": False})
        print(f"User updated: worker_notifications_enabled={updated_user.worker_notifications_enabled}")
        assert updated_user.worker_notifications_enabled is False, "Should be False after update"
        
        # Verify persistence: Fetch again from DB
        # We can use db_service.get_user_by_id
        fetched_user = db_service.get_user_by_id(user.id)
        print(f"User fetched: worker_notifications_enabled={fetched_user.worker_notifications_enabled}")
        assert fetched_user.worker_notifications_enabled is False, "Should persist False"
        
        # Test: Update setting back to True
        updated_user_2 = db_service.update_user(user.id, {"worker_notifications_enabled": True})
        print(f"User updated back: worker_notifications_enabled={updated_user_2.worker_notifications_enabled}")
        assert updated_user_2.worker_notifications_enabled is True, "Should be True after update"
        
        print("Verification SUCCESS!")
        
    finally:
        # Cleanup
        existing = db.query(models.User).filter(models.User.email == email).first()
        if existing:
            db.delete(existing)
            db.commit()
        db.close()

if __name__ == "__main__":
    test_notification_persistence()
