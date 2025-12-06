import sys
import os
from decimal import Decimal
from datetime import datetime

# Mock SQLAlchemy logic to avoid full DB setup
class MockColumn:
    def __init__(self, name):
        self.name = name

# Mock SqItem class based on models.py
class SqItem:
    id = 123
    part = "Test Title"
    sku = Decimal("100500")
    model_id = 999
    price = Decimal("19.99")
    
    # Class attributes
    model = None
    brand = None
    
    @property
    def title(self):
        return self.part
    
    @title.setter
    def title(self, value):
        self.part = value

    def __init__(self):
        self.part = "Test Title"
        self.sku = Decimal("100500")
        self.model_id = 999
        self.price = Decimal("19.99")
        self.category = "InternalCat"
        self.shipping_group = "ShippingGrp"
        self.condition_id = 1

# Import Pydantic model
# We need to import from the app context or redefine minimal model here to test
# Let's try to import first, adding path
sys.path.append(os.getcwd())
try:
    from app.models.sq_item import SqItemRead
    print("Successfully imported SqItemRead")
except ImportError as e:
    print(f"Import failed: {e}")
    # Redefine minimal if import fails
    from pydantic import BaseModel, ConfigDict
    from typing import Optional

    class SqItemBase(BaseModel):
        sku: Optional[str | int | Decimal] = None
        title: Optional[str] = None
        model: Optional[str] = None
        price: Optional[Decimal] = None
        model_config = ConfigDict(from_attributes=True)

    class SqItemRead(SqItemBase):
        id: int


def test_serialization():
    item = SqItem()
    # Simulate the logic in get_sq_item where we manually set model
    item.model = "Test Model Name"
    
    print(f"Item: id={item.id}, title={item.title}, model={item.model}")
    
    try:
        read_model = SqItemRead.model_validate(item)
        print("Serialization SUCCESS:")
        print(read_model.model_dump())
    except Exception as e:
        print(f"Serialization FAILED: {e}")

if __name__ == "__main__":
    test_serialization()
