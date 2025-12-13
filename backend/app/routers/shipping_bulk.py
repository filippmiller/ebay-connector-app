from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import (
    ShippingBatch,
    ShippingLabel,
    ShippingLabelProvider,
    ShippingJobStatus,
    Inventory,
)
from app.services.auth import get_current_user
from app.services.shipping_provider import FakeShippingRateProvider, RateRequest, RateSelection
from app.models.user import User as UserModel


router = APIRouter(prefix="/api/shipping/bulk", tags=["shipping-bulk"])


# ----------------------------
# Pydantic models
# ----------------------------


class CandidateResponse(BaseModel):
    order_id: str
    order_line_item_id: str
    order_date: Optional[str]
    buyer_username: Optional[str]
    buyer_name: Optional[str]
    ship_to_city: Optional[str]
    ship_to_state: Optional[str]
    ship_to_postal_code: Optional[str]
    ship_to_country_code: Optional[str]
    item_id: Optional[str]
    sku: Optional[str]
    title: Optional[str]
    quantity: int
    inventory_id: Optional[int]
    storage_id: Optional[str]
    inventory_created_at: Optional[str]
    shipping_status: Optional[str]
    has_shipping_label: bool


class RateLineRequest(BaseModel):
    orderId: str
    orderLineItemId: str
    inventoryId: int
    weightOz: float = Field(..., gt=0)
    lengthIn: Optional[float] = Field(None, gt=0)
    widthIn: Optional[float] = Field(None, gt=0)
    heightIn: Optional[float] = Field(None, gt=0)
    packageType: Optional[str] = None
    carrierPreference: Optional[str] = None
    quantity: Optional[int] = 1

    @validator("quantity")
    def _positive_qty(cls, v: Optional[int]) -> int:
        return max(1, v or 1)


class RateQuote(BaseModel):
    carrier_code: str
    service_code: str
    service_name: str
    amount: float
    currency: str = "USD"
    estimated_days: Optional[int] = None


class RatesResponseItem(BaseModel):
    order_id: str
    order_line_item_id: str
    inventory_id: int
    rates: List[RateQuote]


class RatesRequest(BaseModel):
    items: List[RateLineRequest]


class PurchaseSelection(BaseModel):
    orderId: str
    orderLineItemId: str
    inventoryId: int
    carrierCode: str
    serviceCode: str
    serviceName: str
    amount: float
    currency: str = "USD"
    trackingNumber: Optional[str] = None  # optional override, else provider generates
    weightOz: float
    lengthIn: Optional[float] = None
    widthIn: Optional[float] = None
    heightIn: Optional[float] = None
    quantity: Optional[int] = 1

    @validator("quantity")
    def _qty_positive(cls, v: Optional[int]) -> int:
        return max(1, v or 1)


class PurchaseRequest(BaseModel):
    batchId: Optional[str] = None
    selections: List[PurchaseSelection]


class PurchaseResult(BaseModel):
    batch_id: str
    labels_created: int
    total_cost: float
    currency: str


# ----------------------------
# Helpers
# ----------------------------


def _parse_json_payload(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _default_from_address() -> Dict[str, Any]:
    # Minimal placeholder; production can override via env DEFAULT_SHIP_FROM_JSON
    from_env = None
    try:
        import os

        if os.getenv("DEFAULT_SHIP_FROM_JSON"):
            from_env = json.loads(os.getenv("DEFAULT_SHIP_FROM_JSON"))
    except Exception:
        from_env = None
    return from_env or {
        "name": "Warehouse",
        "addressLine1": "N/A",
        "city": "N/A",
        "stateOrProvince": "NY",
        "postalCode": "00000",
        "countryCode": "US",
    }


def _to_address_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": row.get("ship_to_name") or row.get("buyer_name"),
        "city": row.get("ship_to_city"),
        "stateOrProvince": row.get("ship_to_state"),
        "postalCode": row.get("ship_to_postal_code"),
        "countryCode": row.get("ship_to_country_code"),
    }


def _select_rates(for_item: Dict[str, Any], weight_oz: float, dims: Tuple[Optional[float], Optional[float], Optional[float]]) -> List[RateQuote]:
    provider = FakeShippingRateProvider()
    rate_req = RateRequest(
        shipping_job_id="bulk",
        from_address=_default_from_address(),
        to_address=_to_address_from_row(for_item),
        weight_oz=weight_oz,
        length_in=dims[0],
        width_in=dims[1],
        height_in=dims[2],
        package_type=for_item.get("package_type"),
        carrier_preference=for_item.get("carrier_preference"),
    )
    rates = provider.get_rates(rate_req)
    return [
        RateQuote(
            carrier_code=r.carrier,
            service_code=r.service_code,
            service_name=r.service_name,
            amount=r.amount,
            currency=r.currency,
            estimated_days=r.estimated_days,
        )
        for r in rates
    ]


# ----------------------------
# Endpoints
# ----------------------------


@router.get("/candidates")
async def list_candidates(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ebay_account_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    search: Optional[str] = Query(None, description="Search in order_id, sku, storage_id"),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return order line items ready for bulk shipping with FIFO inventory match."""

    search_like = f"%{search}%" if search else None

    base_sql = """
        WITH candidate AS (
            SELECT
                oli.order_id,
                oli.line_item_id,
                oli.sku,
                oli.title,
                oli.quantity,
                oli.created_at AS line_created_at,
                COALESCE(
                    NULLIF(oli.raw_payload, '')::jsonb ->> 'legacyItemId',
                    NULLIF(oli.raw_payload, '')::jsonb ->> 'itemId'
                ) AS item_id,
                o.creation_date AS order_date,
                o.buyer_username,
                o.ship_to_city,
                o.ship_to_state,
                o.ship_to_postal_code,
                o.ship_to_country_code,
                o.buyer_username AS buyer_name,
                o.order_payment_status,
                o.order_fulfillment_status
            FROM order_line_items oli
            JOIN ebay_orders o ON o.order_id = oli.order_id
            WHERE (:ebay_account_id IS NULL OR o.ebay_account_id = :ebay_account_id)
              AND (:date_from IS NULL OR o.creation_date >= :date_from)
              AND (:date_to IS NULL OR o.creation_date <= :date_to)
              AND o.order_payment_status IN ('PAID', 'PAID_PENDING', 'PAID_PENDING_RELEASE', 'COMPLETED')
              AND (o.order_fulfillment_status IS NULL OR o.order_fulfillment_status NOT IN ('FULFILLED', 'CANCELLED'))
        ),
        inv_pick AS (
            SELECT
                c.*,
                inv.id AS inventory_id,
                inv.storage_id,
                inv.rec_created AS inventory_created_at
            FROM candidate c
            LEFT JOIN LATERAL (
                SELECT i.*
                FROM inventory i
                WHERE i.item_id = c.item_id
                  AND (i.quantity IS NULL OR i.quantity > 0)
                  AND NOT EXISTS (
                      SELECT 1 FROM shipping_labels sli
                      WHERE sli.inventory_id = i.id
                        AND COALESCE(sli.label_status, 'PENDING') IN ('PENDING','RATED','PURCHASING','PURCHASED')
                  )
                ORDER BY i.rec_created ASC
                LIMIT 1
            ) inv ON TRUE
        ),
        filtered AS (
            SELECT *
            FROM inv_pick p
            WHERE p.inventory_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM shipping_labels sl
                  WHERE sl.order_id = p.order_id
                    AND sl.order_line_item_id = p.line_item_id
                    AND COALESCE(sl.label_status, 'PENDING') <> 'VOIDED'
              )
              AND (
                  :search_like IS NULL
                  OR p.order_id ILIKE :search_like
                  OR p.sku ILIKE :search_like
                  OR p.storage_id ILIKE :search_like
              )
        )
        SELECT * FROM filtered
        ORDER BY order_date DESC NULLS LAST, line_created_at DESC NULLS LAST
        LIMIT :limit OFFSET :offset;
    """

    count_sql = """
        WITH candidate AS (
            SELECT
                oli.order_id,
                oli.line_item_id,
                oli.sku,
                COALESCE(
                    NULLIF(oli.raw_payload, '')::jsonb ->> 'legacyItemId',
                    NULLIF(oli.raw_payload, '')::jsonb ->> 'itemId'
                ) AS item_id,
                o.creation_date,
                o.order_payment_status,
                o.order_fulfillment_status
            FROM order_line_items oli
            JOIN ebay_orders o ON o.order_id = oli.order_id
            WHERE (:ebay_account_id IS NULL OR o.ebay_account_id = :ebay_account_id)
              AND (:date_from IS NULL OR o.creation_date >= :date_from)
              AND (:date_to IS NULL OR o.creation_date <= :date_to)
              AND o.order_payment_status IN ('PAID', 'PAID_PENDING', 'PAID_PENDING_RELEASE', 'COMPLETED')
              AND (o.order_fulfillment_status IS NULL OR o.order_fulfillment_status NOT IN ('FULFILLED', 'CANCELLED'))
        ),
        inv_pick AS (
            SELECT
                c.*,
                inv.storage_id
            FROM candidate c
            LEFT JOIN LATERAL (
                SELECT i.storage_id
                FROM inventory i
                WHERE i.item_id = c.item_id
                  AND (i.quantity IS NULL OR i.quantity > 0)
                  AND NOT EXISTS (
                      SELECT 1 FROM shipping_labels sli
                      WHERE sli.inventory_id = i.id
                        AND COALESCE(sli.label_status, 'PENDING') IN ('PENDING','RATED','PURCHASING','PURCHASED')
                  )
                ORDER BY i.rec_created ASC
                LIMIT 1
            ) inv ON TRUE
        ),
        filtered AS (
            SELECT *
            FROM inv_pick p
            WHERE (
                :search_like IS NULL
                OR p.order_id ILIKE :search_like
                OR p.sku ILIKE :search_like
                OR p.storage_id ILIKE :search_like
            )
              AND NOT EXISTS (
                  SELECT 1 FROM shipping_labels sl
                  WHERE sl.order_id = p.order_id
                    AND sl.order_line_item_id = p.line_item_id
                    AND COALESCE(sl.label_status, 'PENDING') <> 'VOIDED'
              )
              AND p.storage_id IS NOT NULL
        )
        SELECT COUNT(*) FROM filtered;
    """

    params = {
        "ebay_account_id": ebay_account_id,
        "date_from": date_from,
        "date_to": date_to,
        "search_like": search_like,
        "limit": limit,
        "offset": offset,
    }

    rows = db.execute(text(base_sql), params).mappings().all()
    total = db.execute(text(count_sql), params).scalar() or 0

    result: List[CandidateResponse] = []
    for r in rows:
        result.append(
            CandidateResponse(
                order_id=r.get("order_id"),
                order_line_item_id=r.get("line_item_id"),
                order_date=r.get("order_date").isoformat() if r.get("order_date") else None,
                buyer_username=r.get("buyer_username"),
                buyer_name=r.get("buyer_name"),
                ship_to_city=r.get("ship_to_city"),
                ship_to_state=r.get("ship_to_state"),
                ship_to_postal_code=r.get("ship_to_postal_code"),
                ship_to_country_code=r.get("ship_to_country_code"),
                item_id=r.get("item_id"),
                sku=r.get("sku"),
                title=r.get("title"),
                quantity=int(r.get("quantity") or 1),
                inventory_id=r.get("inventory_id"),
                storage_id=r.get("storage_id"),
                inventory_created_at=r.get("inventory_created_at").isoformat() if r.get("inventory_created_at") else None,
                shipping_status=None,
                has_shipping_label=False,
            )
        )

    return {"rows": result, "limit": limit, "offset": offset, "total": total}


@router.post("/rates")
async def get_bulk_rates(
    payload: RatesRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return carrier/service options for each requested line using the provider abstraction."""

    response_items: List[RatesResponseItem] = []

    for item in payload.items:
        # Fetch order + shipping address + sanity checks
        row = db.execute(
            text(
                """
                SELECT
                    o.order_id,
                    o.ship_to_name,
                    o.ship_to_city,
                    o.ship_to_state,
                    o.ship_to_postal_code,
                    o.ship_to_country_code,
                    oli.sku,
                    oli.title,
                    oli.quantity
                FROM order_line_items oli
                JOIN ebay_orders o ON o.order_id = oli.order_id
                WHERE oli.order_id = :order_id AND oli.line_item_id = :line_item_id
                """
            ),
            {"order_id": item.orderId, "line_item_id": item.orderLineItemId},
        ).mappings().one_or_none()

        if not row:
            raise HTTPException(status_code=404, detail=f"order/line not found for {item.orderId}/{item.orderLineItemId}")

        rates = _select_rates(
            row,
            weight_oz=item.weightOz,
            dims=(item.lengthIn, item.widthIn, item.heightIn),
        )

        response_items.append(
            RatesResponseItem(
                order_id=item.orderId,
                order_line_item_id=item.orderLineItemId,
                inventory_id=item.inventoryId,
                rates=rates,
            )
        )

    return {"items": response_items}


@router.post("/purchase")
async def purchase_labels(
    payload: PurchaseRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PurchaseResult:
    """Purchase labels for the provided selections and store tracking/cost data."""

    if not payload.selections:
        raise HTTPException(status_code=400, detail="No selections provided")

    batch: ShippingBatch
    if payload.batchId:
        batch = db.query(ShippingBatch).filter(ShippingBatch.id == payload.batchId).one_or_none()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        batch.status = "PURCHASING"
        batch.updated_at = datetime.utcnow()
    else:
        batch = ShippingBatch(
            id=str(uuid.uuid4()),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            created_by=current_user.id,
            status="PURCHASING",
            currency="USD",
        )
        db.add(batch)
        db.flush()

    provider = FakeShippingRateProvider()
    total_cost = 0.0
    labels_created = 0

    for sel in payload.selections:
        # Validate inventory
        inv: Optional[Inventory] = db.query(Inventory).filter(Inventory.id == sel.inventoryId).one_or_none()
        if not inv:
            raise HTTPException(status_code=404, detail=f"Inventory {sel.inventoryId} not found")

        # Avoid duplicate labels
        existing = (
            db.query(ShippingLabel)
            .filter(
                ShippingLabel.order_id == sel.orderId,
                ShippingLabel.order_line_item_id == sel.orderLineItemId,
                ShippingLabel.inventory_id == sel.inventoryId,
                ShippingLabel.voided.is_(False),
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Label already exists for order {sel.orderId} / line {sel.orderLineItemId} / inventory {sel.inventoryId}",
            )

        fake_rate = RateSelection(
            shipping_job_id="bulk",
            package_id=None,
            rate=provider.get_rates(
                RateRequest(
                    shipping_job_id="bulk",
                    from_address=_default_from_address(),
                    to_address=_default_from_address(),  # placeholder; eBay handles notification/tracking
                    weight_oz=sel.weightOz,
                    length_in=sel.lengthIn,
                    width_in=sel.widthIn,
                    height_in=sel.heightIn,
                )
            )[0],
        )

        label = provider.buy_label(fake_rate, db)

        # Enrich label with bulk metadata
        label.batch_id = batch.id
        label.order_id = sel.orderId
        label.order_line_item_id = sel.orderLineItemId
        label.inventory_id = sel.inventoryId
        label.quantity = sel.quantity or 1
        label.weight_oz = sel.weightOz
        label.length_in = sel.lengthIn
        label.width_in = sel.widthIn
        label.height_in = sel.heightIn
        label.carrier_code = sel.carrierCode
        label.service_code = sel.serviceCode
        label.service_name = sel.serviceName
        label.label_status = "PURCHASED"
        label.label_pdf_url = label.label_url
        label.label_cost_amount = sel.amount
        label.label_cost_currency = sel.currency
        label.tracking_number = sel.trackingNumber or label.tracking_number
        label.updated_at = datetime.utcnow()
        label.updated_by = current_user.id

        # Update inventory quantity (best-effort)
        if inv.quantity is not None:
            inv.quantity = max(0, (inv.quantity or 0) - (sel.quantity or 1))
            db.add(inv)

        db.add(label)
        db.flush()

        total_cost += float(sel.amount)
        labels_created += 1

    batch.labels_count = labels_created
    batch.total_cost = total_cost
    batch.status = "PURCHASED"
    batch.updated_at = datetime.utcnow()
    db.add(batch)
    db.commit()

    return PurchaseResult(batch_id=batch.id, labels_created=labels_created, total_cost=total_cost, currency=batch.currency or "USD")


