from datetime import datetime, timedelta
from decimal import Decimal
from app.database import SessionLocal
from app.db_models import Order, OrderLineItem, Listing, Offer, Message, User
import json

def seed_data():
    db = SessionLocal()
    
    print("Seeding database with mock data...")
    
    user = db.query(User).filter(User.email == "admin@ebay.com").first()
    if not user:
        print("No admin user found. Please create an admin user first.")
        db.close()
        return
    
    user_id = user.id
    
    now = datetime.utcnow()
    
    orders_data = [
        {
            "order_id": "ORD-2024-001",
            "order_status": "SHIPPED",
            "order_date": now - timedelta(days=2),
            "buyer_username": "john_smith_99",
            "buyer_email": "john@example.com",
            "total_amount": Decimal("149.99"),
            "shipping_cost": Decimal("12.99"),
            "tax_amount": Decimal("13.50"),
            "tracking_number": "1Z999AA10123456784",
            "shipped_date": now - timedelta(days=1),
        },
        {
            "order_id": "ORD-2024-002",
            "order_status": "PAID",
            "order_date": now - timedelta(days=1),
            "buyer_username": "sarah_jones",
            "buyer_email": "sarah@example.com",
            "total_amount": Decimal("79.99"),
            "shipping_cost": Decimal("8.99"),
            "tax_amount": Decimal("7.19"),
        },
        {
            "order_id": "ORD-2024-003",
            "order_status": "COMPLETED",
            "order_date": now - timedelta(days=5),
            "buyer_username": "mike_wilson",
            "buyer_email": "mike@example.com",
            "total_amount": Decimal("299.99"),
            "shipping_cost": Decimal("15.99"),
            "tax_amount": Decimal("27.00"),
            "tracking_number": "1Z999AA10123456785",
            "shipped_date": now - timedelta(days=4),
            "delivery_date": now - timedelta(days=1),
        },
    ]
    
    print("Creating orders...")
    for order_data in orders_data:
        order = Order(user_id=user_id, **order_data)
        db.add(order)
        db.flush()
        
        line_item = OrderLineItem(
            order_id=order.id,
            line_item_id=f"{order.order_id}-ITEM-1",
            listing_id=f"LST-{order.order_id}",
            title=f"Vintage Widget - Item for {order.order_id}",
            quantity=1,
            unit_price=order.subtotal if order.subtotal else order.total_amount - order.shipping_cost - order.tax_amount,
            total_price=order.subtotal if order.subtotal else order.total_amount - order.shipping_cost - order.tax_amount,
            image_url="https://via.placeholder.com/150",
            condition="NEW"
        )
        db.add(line_item)
    
    print("Creating listings...")
    listings_data = [
        {
            "listing_id": "LST-2024-001",
            "sku": "WIDGET-001",
            "title": "Professional Camera Lens - Canon EF 50mm f/1.8",
            "description": "High quality camera lens in excellent condition",
            "listing_status": "ACTIVE",
            "quantity_available": 3,
            "quantity_sold": 7,
            "price": Decimal("199.99"),
            "listing_type": "FIXED_PRICE",
            "primary_image_url": "https://via.placeholder.com/300",
            "condition": "USED_EXCELLENT",
        },
        {
            "listing_id": "LST-2024-002",
            "sku": "GADGET-002",
            "title": "Wireless Headphones - Premium Sound Quality",
            "description": "Brand new wireless headphones with noise cancellation",
            "listing_status": "ACTIVE",
            "quantity_available": 10,
            "quantity_sold": 15,
            "price": Decimal("89.99"),
            "listing_type": "FIXED_PRICE",
            "primary_image_url": "https://via.placeholder.com/300",
            "condition": "NEW",
        },
    ]
    
    for listing_data in listings_data:
        listing = Listing(user_id=user_id, **listing_data)
        db.add(listing)
    
    db.flush()
    
    first_listing = db.query(Listing).filter(Listing.user_id == user_id).first()
    
    print("Creating offers...")
    offers_data = [
        {
            "offer_id": "OFFER-2024-001",
            "ebay_listing_id": first_listing.listing_id if first_listing else "LST-2024-001",
            "listing_id": first_listing.id if first_listing else None,
            "buyer_username": "bargain_hunter",
            "offer_amount": Decimal("175.00"),
            "quantity": 1,
            "offer_message": "Can you do $175? I'm a serious buyer.",
            "offer_status": "PENDING",
            "offer_date": now - timedelta(hours=2),
            "expiration_date": now + timedelta(days=2),
        },
        {
            "offer_id": "OFFER-2024-002",
            "ebay_listing_id": first_listing.listing_id if first_listing else "LST-2024-001",
            "listing_id": first_listing.id if first_listing else None,
            "buyer_username": "tech_enthusiast",
            "offer_amount": Decimal("180.00"),
            "quantity": 1,
            "offer_message": "I'll buy it right away if you accept $180.",
            "offer_status": "PENDING",
            "offer_date": now - timedelta(hours=1),
            "expiration_date": now + timedelta(days=2),
        },
    ]
    
    for offer_data in offers_data:
        offer = Offer(user_id=user_id, **offer_data)
        db.add(offer)
    
    print("Creating messages...")
    messages_data = [
        {
            "message_id": "MSG-2024-001",
            "thread_id": "THREAD-001",
            "sender_username": "john_smith_99",
            "recipient_username": "your_store",
            "subject": "Question about shipping",
            "body": "Hi! I just purchased the item. When will it be shipped? Thanks!",
            "message_type": "SHIPPING",
            "is_read": False,
            "direction": "INCOMING",
            "message_date": now - timedelta(hours=3),
        },
        {
            "message_id": "MSG-2024-002",
            "thread_id": "THREAD-002",
            "sender_username": "sarah_jones",
            "recipient_username": "your_store",
            "subject": "Item not as described?",
            "body": "The item looks different from the photos. Can you clarify the condition?",
            "message_type": "ISSUE",
            "is_read": False,
            "direction": "INCOMING",
            "message_date": now - timedelta(hours=5),
        },
        {
            "message_id": "MSG-2024-003",
            "thread_id": "THREAD-003",
            "sender_username": "mike_wilson",
            "recipient_username": "your_store",
            "subject": "Great product!",
            "body": "Just received the item. It's exactly as described. Thank you!",
            "message_type": "FEEDBACK",
            "is_read": True,
            "direction": "INCOMING",
            "message_date": now - timedelta(days=1),
        },
        {
            "message_id": "MSG-2024-004",
            "thread_id": "THREAD-001",
            "parent_message_id": "MSG-2024-001",
            "sender_username": "your_store",
            "recipient_username": "john_smith_99",
            "subject": "Re: Question about shipping",
            "body": "Hi John! Your item will ship today. You'll receive tracking info shortly. Thanks for your purchase!",
            "message_type": "SHIPPING",
            "is_read": True,
            "direction": "OUTGOING",
            "message_date": now - timedelta(hours=2),
        },
    ]
    
    for message_data in messages_data:
        message = Message(user_id=user_id, **message_data)
        db.add(message)
    
    db.commit()
    print("✅ Mock data seeded successfully!")
    print(f"- {len(orders_data)} orders created")
    print(f"- {len(listings_data)} listings created")
    print(f"- {len(offers_data)} offers created")
    print(f"- {len(messages_data)} messages created")
    
    db.close()

if __name__ == "__main__":
    seed_data()
