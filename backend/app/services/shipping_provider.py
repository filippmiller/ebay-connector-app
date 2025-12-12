from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from app.models_sqlalchemy.models import ShippingLabel, ShippingLabelProvider


@dataclass
class RateRequest:
    """Logical request for shipping rates for a single package/job.

    This is intentionally generic so we can plug in eBay Logistics, Shippo, or
    other providers later without changing the rest of the code.
    """

    shipping_job_id: str
    from_address: Dict[str, Any]
    to_address: Dict[str, Any]
    weight_oz: Optional[float] = None
    length_in: Optional[float] = None
    width_in: Optional[float] = None
    height_in: Optional[float] = None
    package_type: Optional[str] = None
    carrier_preference: Optional[str] = None


@dataclass
class Rate:
    service_code: str
    service_name: str
    carrier: str
    amount: float
    currency: str = "USD"
    estimated_days: Optional[int] = None


@dataclass
class RateSelection:
    shipping_job_id: str
    package_id: Optional[str]
    rate: Rate


@dataclass
class LabelDetails:
    tracking_number: str
    carrier: str
    service_name: str
    label_url: str
    label_cost_amount: float
    label_cost_currency: str = "USD"
    label_file_type: str = "pdf"


class ShippingRateProvider:
    """Abstract interface for shipping rate/label providers.

    Concrete implementations (e.g. eBay Logistics, Shippo, EasyPost) should
    subclass this and implement the two methods below.
    """

    def get_rates(self, request: RateRequest) -> List[Rate]:  # pragma: no cover - interface
        raise NotImplementedError

    def buy_label(self, selection: RateSelection, db: Session) -> ShippingLabel:  # pragma: no cover - interface
        raise NotImplementedError


class FakeShippingRateProvider(ShippingRateProvider):
    """Phase 1 stub provider returning fake rates and labels.

    This implementation is intentionally simple and is only used for local
    testing and wiring. It does **not** talk to any external service.
    """

    def get_rates(self, request: RateRequest) -> List[Rate]:
        base_amount = 8.50
        weight_factor = (request.weight_oz or 16.0) / 16.0
        amount_priority = round(base_amount * weight_factor, 2)
        amount_ground = round(max(5.0, amount_priority - 2.0), 2)

        return [
            Rate(
                service_code="USPS_PRIORITY",
                service_name="USPS Priority Mail",
                carrier="USPS",
                amount=amount_priority,
                currency="USD",
                estimated_days=2,
            ),
            Rate(
                service_code="USPS_GROUND",
                service_name="USPS Ground Advantage",
                carrier="USPS",
                amount=amount_ground,
                currency="USD",
                estimated_days=5,
            ),
        ]

    def buy_label(self, selection: RateSelection, db: Session) -> ShippingLabel:
        """Create a fake ShippingLabel row for the given selection.

        Caller is responsible for updating the corresponding ShippingJob status
        and linking job.label_id, if desired.
        """

        tracking = f"FAKE{uuid.uuid4().hex[:12].upper()}"
        now = datetime.utcnow()

        label = ShippingLabel(
            id=str(uuid.uuid4()),
            shipping_job_id=selection.shipping_job_id,
            provider=ShippingLabelProvider.EXTERNAL,
            provider_shipment_id=None,
            tracking_number=tracking,
            carrier=selection.rate.carrier,
            service_name=selection.rate.service_name,
            label_url="about:blank",
            label_file_type="pdf",
            label_cost_amount=selection.rate.amount,
            label_cost_currency=selection.rate.currency,
            purchased_at=now,
            voided=False,
            created_at=now,
            updated_at=now,
        )

        db.add(label)
        db.commit()
        db.refresh(label)
        return label
