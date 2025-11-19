from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel


class SqItemBase(BaseModel):
    """Shared fields for SQ catalog items used in create/update/read.

    This schema intentionally exposes only a subset of all columns from
    ``sq_items`` – the database table contains a 1:1 mapping of legacy
    ``tbl_parts_detail`` fields, but most callers need only the core subset.
    """

    sku: Optional[str] = None
    sku2: Optional[str] = None
    model_id: Optional[int] = None
    model: Optional[str] = None
    part: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None

    price: Optional[Decimal] = None
    previous_price: Optional[Decimal] = None
    brutto: Optional[Decimal] = None

    shipping_type: Optional[str] = None
    shipping_group: Optional[str] = None

    condition_id: Optional[int] = None
    condition_description: Optional[str] = None

    part_number: Optional[str] = None
    mpn: Optional[str] = None
    upc: Optional[str] = None

    alert_flag: Optional[bool] = None
    alert_message: Optional[str] = None

    title: Optional[str] = None
    brand: Optional[str] = None

    warehouse_id: Optional[int] = None
    storage_alias: Optional[str] = None

    class Config:
        from_attributes = True


class SqItemCreate(SqItemBase):
    """Payload for creating a new SQ item.

    API-level required fields are kept minimal and aligned with the new UI
    (model, internal category, condition, price, shipping group).
    """

    sku: Optional[str] = None
    model: str
    category: str
    condition_id: int
    price: Decimal
    shipping_group: str


class SqItemUpdate(SqItemBase):
    """Partial update – all fields optional and applied if present."""

    pass


class SqItemListItem(BaseModel):
    """Reduced view used by the grid (``sq_catalog`` DataGridPage)."""

    id: int
    sku: Optional[str] = None
    model: Optional[str] = None
    category: Optional[str] = None
    condition_id: Optional[int] = None
    part_number: Optional[str] = None
    price: Optional[Decimal] = None
    title: Optional[str] = None
    brand: Optional[str] = None
    alert_flag: Optional[bool] = None
    shipping_group: Optional[str] = None
    pic_url1: Optional[str] = None
    record_created: Optional[datetime] = None
    record_updated: Optional[datetime] = None
    record_status: Optional[str] = None

    class Config:
        from_attributes = True


class SqItemRead(SqItemBase):
    """Full detail view for the SKU detail panel and edit form."""

    id: int

    part_id: Optional[int] = None

    market: Optional[str] = None
    use_ebay_id: Optional[bool] = None

    shipping_group_previous: Optional[str] = None
    shipping_group_change_state: Optional[str] = None
    shipping_group_change_state_updated: Optional[datetime] = None
    shipping_group_change_state_updated_by: Optional[str] = None

    pic_url1: Optional[str] = None
    pic_url2: Optional[str] = None
    pic_url3: Optional[str] = None
    pic_url4: Optional[str] = None
    pic_url5: Optional[str] = None
    pic_url6: Optional[str] = None
    pic_url7: Optional[str] = None
    pic_url8: Optional[str] = None
    pic_url9: Optional[str] = None
    pic_url10: Optional[str] = None
    pic_url11: Optional[str] = None
    pic_url12: Optional[str] = None

    weight: Optional[Decimal] = None
    weight_major: Optional[Decimal] = None
    weight_minor: Optional[Decimal] = None
    package_depth: Optional[Decimal] = None
    package_length: Optional[Decimal] = None
    package_width: Optional[Decimal] = None
    size: Optional[str] = None
    unit: Optional[str] = None

    item_grade_id: Optional[int] = None
    basic_package_id: Optional[int] = None

    record_status_flag: Optional[bool] = None
    checked_status: Optional[str] = None
    checked: Optional[bool] = None
    checked_by: Optional[str] = None
    one_time_auction: Optional[bool] = None

    record_created_by: Optional[str] = None
    record_created: Optional[datetime] = None
    record_updated_by: Optional[str] = None
    record_updated: Optional[datetime] = None
    oc_export_date: Optional[datetime] = None
    oc_market_export_date: Optional[datetime] = None

    custom_template_flag: Optional[bool] = None
    custom_template_description: Optional[str] = None
    domestic_only_flag: Optional[bool] = None
    external_category_flag: Optional[bool] = None
    external_category_id: Optional[str] = None
    external_category_name: Optional[str] = None
    listing_type: Optional[str] = None
    listing_duration: Optional[str] = None
    listing_duration_in_days: Optional[int] = None
    clone_sku_flag: Optional[bool] = None
    clone_sku_updated: Optional[datetime] = None
    clone_sku_updated_by: Optional[str] = None
    use_standard_template_for_external_category_flag: Optional[bool] = None
    use_ebay_motors_site_flag: Optional[bool] = None
    site_id: Optional[str] = None

    class Config:
        from_attributes = True


class SqItemListResponse(BaseModel):
    items: List[SqItemListItem]
    total: int
    page: int
    page_size: int
