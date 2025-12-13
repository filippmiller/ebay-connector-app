import json
import hashlib
import httpx
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models_sqlalchemy.models import EbayAccount, EbayToken
from app.db_models.inventory_offer import EbayInventoryOffer, EbayInventoryOfferEvent
from app.services.ebay_account_service import ebay_account_service
from app.utils.logger import logger
from app.config import settings

class EbayOffersService:
    def __init__(self):
        self.base_url = settings.ebay_api_base_url.rstrip("/")

    def _get_interesting_fields(self, offer: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields relevant for history tracking."""
        pricing = offer.get("pricingSummary", {})
        price = pricing.get("price", {})
        listing = offer.get("listing", {})
        listing_policies = offer.get("listingPolicies", {})
        tax = offer.get("tax", {})

        return {
            "pricingSummary.price.currency": price.get("currency"),
            "pricingSummary.price.value": price.get("value"),
            "availableQuantity": offer.get("availableQuantity"),
            "quantityLimitPerBuyer": offer.get("quantityLimitPerBuyer"),
            "status": offer.get("status"),
            "listing.listingStatus": listing.get("listingStatus"),
            "listing.listingOnHold": listing.get("listingOnHold"),
            "listing.soldQuantity": listing.get("soldQuantity"),
            "listing.startDate": listing.get("startDate"),
            "listing.endDate": listing.get("endDate"),
            "listingPolicies.fulfillmentPolicyId": listing_policies.get("fulfillmentPolicyId"),
            "listingPolicies.paymentPolicyId": listing_policies.get("paymentPolicyId"),
            "listingPolicies.returnPolicyId": listing_policies.get("returnPolicyId"),
            "marketplaceId": offer.get("marketplaceId"),
            "merchantLocationKey": offer.get("merchantLocationKey"),
            "tax.vatPercentage": tax.get("vatPercentage"),
        }

    def _compute_snapshot_signature(self, interesting_fields: Dict[str, Any]) -> str:
        """Compute SHA-256 hash of interesting fields."""
        # Sort keys to ensure determinism
        serialized = json.dumps(interesting_fields, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

    def _compute_changed_fields(self, old_fields: Dict[str, Any], new_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Compute diff between old and new fields."""
        diff = {}
        all_keys = set(old_fields.keys()) | set(new_fields.keys())
        
        for key in all_keys:
            old_val = old_fields.get(key)
            new_val = new_fields.get(key)
            if old_val != new_val:
                diff[key] = {"old": old_val, "new": new_val}
        
        return diff if diff else None

    def _determine_event_type(self, changed_fields: Dict[str, Any], is_new: bool) -> str:
        """Determine event type based on changes."""
        if is_new:
            return "created"
        
        if any(k.startswith("pricingSummary.price") for k in changed_fields):
            return "price_change"
        if "availableQuantity" in changed_fields:
            return "qty_change"
        if "status" in changed_fields or "listing.listingStatus" in changed_fields:
            return "status_change"
        if any(k.startswith("listingPolicies") or k.startswith("tax") for k in changed_fields):
            return "policy_change"
        
        return "snapshot"

    async def fetch_offers(self, access_token: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Fetch offers from eBay Inventory API."""
        url = f"{self.base_url}/sell/inventory/v1/offer"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Content-Language": "en-US" # Ensure consistent locale if needed
        }
        params = {
            "limit": limit,
            "offset": offset
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            return resp.json()

    async def sync_offers_for_account(self, db: Session, account: EbayAccount, access_token: Optional[str] = None) -> Dict[str, int]:
        """Sync offers for a single account.
        
        Args:
            db: Database session
            account: EbayAccount to sync
            access_token: Optional decrypted access token. If not provided, will try to fetch from DB (legacy).
        """
        stats = {"fetched": 0, "created": 0, "updated": 0, "events": 0, "errors": 0}
        
        if not access_token:
            logger.warning(
                f"[offers_service] No access_token provided for account {account.id}. "
                f"Falling back to legacy token fetching (deprecated)."
            )
            token = ebay_account_service.get_token(db, account.id)
            if not token or not token.access_token:
                logger.error(f"No access token for account {account.id}")
                stats["errors"] += 1
                return stats
            access_token = token.access_token

        # CRITICAL: Validate token is decrypted (not ENC:v1:...)
        if access_token.startswith("ENC:"):
            logger.error(
                f"[offers_service] ⚠️ TOKEN STILL ENCRYPTED! account={account.id} "
                f"token_prefix={access_token[:20]}. Check SECRET_KEY/JWT_SECRET."
            )
            stats["errors"] += 1
            return stats

        try:
            # Pagination loop
            offset = 0
            limit = 100
            while True:
                response = await self.fetch_offers(access_token, limit=limit, offset=offset)
                offers = response.get("offers", [])
                if not offers:
                    break
                
                stats["fetched"] += len(offers)
                
                for offer_data in offers:
                    await self._process_offer(db, account.id, offer_data, stats)
                
                offset += limit
                total = response.get("total", 0)
                if offset >= total:
                    break
                    
        except Exception as e:
            logger.error(f"Error syncing offers for account {account.id}: {str(e)}", exc_info=True)
            stats["errors"] += 1
            
        return stats

    async def _process_offer(self, db: Session, account_id: str, offer_data: Dict[str, Any], stats: Dict[str, int]):
        offer_id = offer_data.get("offerId")
        if not offer_id:
            return

        sku = offer_data.get("sku")
        interesting_fields = self._get_interesting_fields(offer_data)
        snapshot_signature = self._compute_snapshot_signature(interesting_fields)
        
        # Check existing offer
        existing_offer = db.query(EbayInventoryOffer).filter_by(
            ebay_account_id=account_id, 
            offer_id=offer_id
        ).first()
        
        is_new = existing_offer is None
        changed_fields = None
        
        if not is_new:
            if existing_offer.raw_payload:
                old_interesting = self._get_interesting_fields(existing_offer.raw_payload)
                changed_fields = self._compute_changed_fields(old_interesting, interesting_fields)
            else:
                changed_fields = {"_meta": {"old": "unknown", "new": "known"}}

        if is_new or (changed_fields and len(changed_fields) > 0):
            event_type = self._determine_event_type(changed_fields or {}, is_new)
            
            # Upsert current state
            offer_dict = {
                "ebay_account_id": account_id,
                "offer_id": offer_id,
                "sku": sku,
                "marketplace_id": offer_data.get("marketplaceId"),
                "listing_id": offer_data.get("listing", {}).get("listingId"),
                "status": offer_data.get("status"),
                "listing_status": offer_data.get("listing", {}).get("listingStatus"),
                "price_currency": offer_data.get("pricingSummary", {}).get("price", {}).get("currency"),
                "price_value": offer_data.get("pricingSummary", {}).get("price", {}).get("value"),
                "available_quantity": offer_data.get("availableQuantity"),
                "sold_quantity": offer_data.get("listing", {}).get("soldQuantity"),
                "quantity_limit_per_buyer": offer_data.get("quantityLimitPerBuyer"),
                "vat_percentage": offer_data.get("tax", {}).get("vatPercentage"),
                "merchant_location_key": offer_data.get("merchantLocationKey"),
                "raw_payload": offer_data,
                "updated_at": datetime.now(timezone.utc)
            }
            
            if is_new:
                offer_dict["id"] = str(uuid.uuid4())
                offer_dict["created_at"] = datetime.now(timezone.utc)
                db.add(EbayInventoryOffer(**offer_dict))
                stats["created"] += 1
            else:
                for k, v in offer_dict.items():
                    if k not in ["id", "created_at"]:
                        setattr(existing_offer, k, v)
                stats["updated"] += 1

            # Create history event
            event = EbayInventoryOfferEvent(
                id=str(uuid.uuid4()),
                ebay_account_id=account_id,
                offer_id=offer_id,
                sku=sku,
                event_type=event_type,
                snapshot_signature=snapshot_signature,
                changed_fields=changed_fields,
                snapshot_payload=offer_data,
                price_currency=offer_dict["price_currency"],
                price_value=offer_dict["price_value"],
                available_quantity=offer_dict["available_quantity"],
                sold_quantity=offer_dict["sold_quantity"],
                status=offer_dict["status"],
                listing_status=offer_dict["listing_status"],
                source="inventory.getOffers",
                fetched_at=datetime.now(timezone.utc)
            )
            
            try:
                db.add(event)
                db.commit()
                stats["events"] += 1
            except IntegrityError as e:
                db.rollback()
                # If unique constraint violation, it means we already have this snapshot.
                # That's fine, just ignore.
                if "uq_ebay_inventory_offer_event_dedupe" in str(e):
                    pass
                else:
                    logger.error(f"Error saving offer event: {e}")
                    # Don't raise, just log and continue
            except Exception as e:
                db.rollback()
                logger.error(f"Error saving offer event: {e}")
        else:
            # No changes, maybe just update updated_at?
            existing_offer.updated_at = datetime.now(timezone.utc)
            db.commit()

ebay_offers_service = EbayOffersService()
