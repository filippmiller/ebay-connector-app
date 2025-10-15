from app.database import Base, engine
from app.db_models import (
    User, Order, OrderLineItem, Listing, Offer,
    Message, Transaction, Fee, Refund, SyncJob
)

def init_db():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

if __name__ == "__main__":
    init_db()
