from typing import Dict, Optional, List, Any, Tuple
from datetime import datetime
from decimal import Decimal
import json
from functools import reduce
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models_sqlalchemy import get_db
from app.utils.logger import logger
from app.services.ebay_event_inbox import log_ebay_event


class PostgresEbayDatabase:
    """
    Postgres-based database for storing eBay data using raw SQL for flexibility
    """
    
    def _get_session(self) -> Session:
        """Get a database session"""
        return next(get_db())
    
    def _safe_get(self, data: Dict, *keys):
        """Safely get nested dict/list values"""
        def accessor(obj, key):
            if obj is None:
                return None
            if isinstance(obj, dict):
                return obj.get(key)
            if isinstance(obj, list) and isinstance(key, int) and 0 <= key < len(obj):
                return obj[key]
            return None
        return reduce(accessor, keys, data)
    
    def _parse_money(self, money_obj: Optional[Dict]) -> Tuple[Optional[Decimal], Optional[str]]:
        """Parse eBay money object to (value, currency)"""
        if not money_obj:
            return (None, None)
        value = money_obj.get('value')
        currency = money_obj.get('currency')
        if value is not None:
            try:
                return (Decimal(str(value)), currency)
            except:
                return (None, currency)
        return (None, currency)
    
    def _parse_datetime(self, dt_string: Optional[str]) -> Optional[datetime]:
        """Parse ISO 8601 datetime to UTC"""
        if not dt_string:
            return None
        try:
            from dateutil import parser
            return parser.isoparse(dt_string)
        except:
            try:
                return datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
            except:
                logger.warning(f"Failed to parse datetime: {dt_string}")
                return None
    
    def normalize_order(self, order_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Normalize eBay order data into DB-ready format
        Returns: (order_dict, line_items_list)
        """
        items = order_data.get('lineItems') or []
        total_val, total_cur = self._parse_money(self._safe_get(order_data, 'pricingSummary', 'total'))
        
        tracking = None
        fulfillments = order_data.get('fulfillments') or []
        for fulfillment in fulfillments:
            shipments = fulfillment.get('shipments') or []
            for shipment in shipments:
                packages = shipment.get('packages') or []
                for package in packages:
                    tracking = package.get('trackingNumber')
                    if tracking:
                        break
                if tracking:
                    break
            if tracking:
                break
        
        ship_to = self._safe_get(order_data, 'fulfillmentStartInstructions', 0, 'shippingStep', 'shipTo') or {}
        contact_addr = ship_to.get('contactAddress') or {}
        
        normalized_order = {
            'order_id': order_data.get('orderId'),
            'creation_date': self._parse_datetime(order_data.get('creationDate')),
            'last_modified': self._parse_datetime(order_data.get('lastModifiedDate')),
            'payment_status': (order_data.get('orderPaymentStatus') or 'UNKNOWN').upper(),
            'fulfillment_status': (order_data.get('orderFulfillmentStatus') or 'UNKNOWN').upper(),
            'buyer_username': self._safe_get(order_data, 'buyer', 'username'),
            'buyer_email': self._safe_get(order_data, 'buyer', 'email'),
            'buyer_registered': self._safe_get(order_data, 'buyer', 'registeredDate'),
            'total_amount': total_val,
            'total_currency': total_cur,
            'order_total_value': total_val,
            'order_total_currency': total_cur,
            'line_items_count': len(items),
            'tracking_number': tracking,
            'ship_to_name': ship_to.get('fullName'),
            'ship_to_city': contact_addr.get('city'),
            'ship_to_state': contact_addr.get('stateOrProvince'),
            'ship_to_postal_code': contact_addr.get('postalCode'),
            'ship_to_country_code': contact_addr.get('countryCode'),
            'order_data': json.dumps(order_data),
            'raw_payload': json.dumps(order_data)
        }
        
        line_items = []
        for li in items:
            line_item_cost = li.get('lineItemCost') or {}
            total_cost = line_item_cost.get('total') or line_item_cost
            item_val, item_cur = self._parse_money(total_cost)
            
            line_items.append({
                'order_id': order_data.get('orderId'),
                'line_item_id': li.get('lineItemId'),
                'sku': li.get('sku'),
                'title': li.get('title'),
                'quantity': li.get('quantity') or 0,
                'total_value': item_val,
                'currency': item_cur,
                'raw_payload': json.dumps(li)
            })
        
        return normalized_order, line_items
    
    def upsert_order(self, user_id: str, order_data: Dict[str, Any]) -> bool:
        """Insert or update an order"""
        session = self._get_session()
        
        try:
            order_id = order_data.get('orderId')
            if not order_id:
                logger.error("Order data missing orderId")
                return False
            
            now = datetime.utcnow()
            
            creation_date = order_data.get('creationDate')
            last_modified = order_data.get('lastModifiedDate')
            payment_status = order_data.get('orderPaymentStatus')
            fulfillment_status = order_data.get('orderFulfillmentStatus')
            
            buyer = order_data.get('buyer', {})
            buyer_username = buyer.get('username')
            buyer_email = buyer.get('email')
            
            pricing = order_data.get('pricingSummary', {})
            total_amount = pricing.get('total', {}).get('value')
            total_currency = pricing.get('total', {}).get('currency')
            
            query = text("""
                INSERT INTO ebay_orders 
                (order_id, user_id, creation_date, last_modified_date, 
                 order_payment_status, order_fulfillment_status, 
                 buyer_username, buyer_email, total_amount, total_currency,
                 order_data, created_at, updated_at)
                VALUES (:order_id, :user_id, :creation_date, :last_modified,
                        :payment_status, :fulfillment_status,
                        :buyer_username, :buyer_email, :total_amount, :total_currency,
                        :order_data, :created_at, :updated_at)
                ON CONFLICT (order_id, user_id) 
                DO UPDATE SET
                    last_modified_date = EXCLUDED.last_modified_date,
                    order_payment_status = EXCLUDED.order_payment_status,
                    order_fulfillment_status = EXCLUDED.order_fulfillment_status,
                    buyer_username = EXCLUDED.buyer_username,
                    buyer_email = EXCLUDED.buyer_email,
                    total_amount = EXCLUDED.total_amount,
                    total_currency = EXCLUDED.total_currency,
                    order_data = EXCLUDED.order_data,
                    updated_at = EXCLUDED.updated_at
            """)
            
            session.execute(query, {
                'order_id': order_id,
                'user_id': user_id,
                'creation_date': creation_date,
                'last_modified': last_modified,
                'payment_status': payment_status,
                'fulfillment_status': fulfillment_status,
                'buyer_username': buyer_username,
                'buyer_email': buyer_email,
                'total_amount': total_amount,
                'total_currency': total_currency,
                'order_data': json.dumps(order_data),
                'created_at': now,
                'updated_at': now
            })
            
            session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error upserting order: {str(e)}")
            session.rollback()
            return False
        finally:
            session.close()
    
    def get_orders(self, user_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get orders for a user"""
        session = self._get_session()
        
        try:
            query = text("""
                SELECT * FROM ebay_orders 
                WHERE user_id = :user_id 
                ORDER BY creation_date DESC 
                LIMIT :limit OFFSET :offset
            """)
            
            result = session.execute(query, {
                'user_id': user_id,
                'limit': limit,
                'offset': offset
            })
            
            orders = []
            for row in result:
                order = dict(row._mapping)
                if order.get('order_data'):
                    order['order_data'] = json.loads(order['order_data'])
                orders.append(order)
            
            return orders
            
        finally:
            session.close()
    
    def get_order_count(self, user_id: str) -> int:
        """Get total order count for a user"""
        session = self._get_session()
        
        try:
            query = text("SELECT COUNT(*) as count FROM ebay_orders WHERE user_id = :user_id")
            result = session.execute(query, {'user_id': user_id})
            count = result.scalar()
            return count or 0
            
        finally:
            session.close()
    
    def batch_upsert_orders(
        self,
        user_id: str,
        orders: List[Dict[str, Any]],
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
    ) -> int:
        """Batch insert or update multiple orders with normalization.

        ebay_account_id / ebay_user_id identify which eBay account (and seller
        user id such as "mil_243") these rows belong to.
        """
        if not orders:
            return 0
        
        session = self._get_session()
        
        try:
            now = datetime.utcnow()
            stored_count = 0
            all_line_items = []
            
            batch_size = 100
            for i in range(0, len(orders), batch_size):
                batch = orders[i:i + batch_size]
                
                values_list = []
                
                for order_data in batch:
                    if not order_data.get('orderId'):
                        logger.warning("Skipping order without orderId")
                        continue
                    
                    try:
                        normalized_order, line_items = self.normalize_order(order_data)
                        # Attach eBay context to both order and its line items
                        normalized_order['user_id'] = user_id
                        normalized_order['ebay_account_id'] = ebay_account_id
                        normalized_order['ebay_user_id'] = ebay_user_id
                        normalized_order['created_at'] = now
                        normalized_order['updated_at'] = now

                        for li in line_items:
                            li['ebay_account_id'] = ebay_account_id
                            li['ebay_user_id'] = ebay_user_id

                        all_line_items.extend(line_items)

                        # Log a unified ebay_events row for this order so that the
                        # Notifications Center has a polling-based view as well.
                        try:
                            event_time_raw = order_data.get('lastModifiedDate') or order_data.get('creationDate')
                            log_ebay_event(
                                source="rest_poll",
                                channel="sell_fulfillment_api",
                                topic="ORDER_UPDATED",
                                entity_type="ORDER",
                                entity_id=order_data.get('orderId'),
                                ebay_account=ebay_user_id or ebay_account_id,
                                event_time=event_time_raw,
                                publish_time=None,
                                headers={
                                    "worker": "orders_worker",
                                    "api_family": "orders",
                                    "user_id": user_id,
                                    "ebay_account_id": ebay_account_id,
                                    "ebay_user_id": ebay_user_id,
                                },
                                payload=order_data,
                                db=session,
                            )
                        except Exception:
                            # Never fail the worker because of event-inbox logging;
                            # emit a warning and continue.
                            logger.warning(
                                "Failed to log ebay_events row for order %s",
                                order_data.get('orderId'),
                                exc_info=True,
                            )

                        values_list.append(normalized_order)
                    except Exception as e:
                        logger.error(f"Error normalizing order {order_data.get('orderId')}: {str(e)}")
                        continue
                if not values_list:
                    continue
                
                params = {}
                value_placeholders = []
                
                for idx, values in enumerate(values_list):
                    placeholders = []
                    for key in [
                        'order_id',
                        'user_id',
                        'ebay_account_id',
                        'ebay_user_id',
                        'creation_date',
                        'last_modified',
                        'payment_status',
                        'fulfillment_status',
                        'buyer_username',
                        'buyer_email',
                        'buyer_registered',
                        'total_amount',
                        'total_currency',
                        'order_total_value',
                        'order_total_currency',
                        'line_items_count',
                        'tracking_number',
                        'ship_to_name',
                        'ship_to_city',
                        'ship_to_state',
                        'ship_to_postal_code',
                        'ship_to_country_code',
                        'order_data',
                        'raw_payload',
                        'created_at',
                        'updated_at',
                    ]:
                        param_name = f"{key}_{idx}"
                        params[param_name] = values.get(key)
                        placeholders.append(f":{param_name}")
                    value_placeholders.append(f"({','.join(placeholders)})")
                
                query = text(f"""
                    INSERT INTO ebay_orders 
                    (order_id, user_id, ebay_account_id, ebay_user_id,
                     creation_date, last_modified_date, 
                     order_payment_status, order_fulfillment_status, 
                     buyer_username, buyer_email, buyer_registered,
                     total_amount, total_currency,
                     order_total_value, order_total_currency, line_items_count,
                     tracking_number, ship_to_name, ship_to_city, ship_to_state,
                     ship_to_postal_code, ship_to_country_code,
                     order_data, raw_payload, created_at, updated_at)
                    VALUES {','.join(value_placeholders)}
                    ON CONFLICT (order_id, user_id) 
                    DO UPDATE SET
                        last_modified_date = EXCLUDED.last_modified_date,
                        order_payment_status = EXCLUDED.order_payment_status,
                        order_fulfillment_status = EXCLUDED.order_fulfillment_status,
                        buyer_username = EXCLUDED.buyer_username,
                        buyer_email = EXCLUDED.buyer_email,
                        buyer_registered = EXCLUDED.buyer_registered,
                        total_amount = EXCLUDED.total_amount,
                        total_currency = EXCLUDED.total_currency,
                        order_total_value = EXCLUDED.order_total_value,
                        order_total_currency = EXCLUDED.order_total_currency,
                        line_items_count = EXCLUDED.line_items_count,
                        tracking_number = EXCLUDED.tracking_number,
                        ship_to_name = EXCLUDED.ship_to_name,
                        ship_to_city = EXCLUDED.ship_to_city,
                        ship_to_state = EXCLUDED.ship_to_state,
                        ship_to_postal_code = EXCLUDED.ship_to_postal_code,
                        ship_to_country_code = EXCLUDED.ship_to_country_code,
                        order_data = EXCLUDED.order_data,
                        raw_payload = EXCLUDED.raw_payload,
                        updated_at = EXCLUDED.updated_at
                """)
                
                session.execute(query, params)
                stored_count += len(values_list)
            
            if all_line_items:
                self.batch_upsert_line_items(session, all_line_items)
            
            session.commit()
            logger.info(f"Batch upserted {stored_count} orders and {len(all_line_items)} line items for user {user_id}")
            return stored_count
            
        except Exception as e:
            logger.error(f"Error in batch upsert orders: {str(e)}")
            session.rollback()
            return 0
        finally:
            session.close()
    
    def batch_upsert_line_items(self, session: Session, line_items: List[Dict[str, Any]]) -> int:
        """Batch upsert line items"""
        if not line_items:
            return 0
        
        try:
            batch_size = 100
            stored_count = 0
            
            for i in range(0, len(line_items), batch_size):
                batch = line_items[i:i + batch_size]
                
                params = {}
                value_placeholders = []
                
                for idx, item in enumerate(batch):
                    if not item.get('order_id') or not item.get('line_item_id'):
                        continue
                    
                    placeholders = []
                    for key in [
                        'order_id',
                        'line_item_id',
                        'sku',
                        'title',
                        'quantity',
                        'total_value',
                        'currency',
                        'raw_payload',
                        'ebay_account_id',
                        'ebay_user_id',
                    ]:
                        param_name = f"{key}_{idx}"
                        params[param_name] = item.get(key)
                        placeholders.append(f":{param_name}")
                    value_placeholders.append(f"({','.join(placeholders)})")
                
                if not value_placeholders:
                    continue
                
                query = text(f"""
                    INSERT INTO order_line_items 
                    (order_id, line_item_id, sku, title, quantity, total_value, currency, raw_payload,
                     ebay_account_id, ebay_user_id)
                    VALUES {','.join(value_placeholders)}
                    ON CONFLICT (order_id, line_item_id) 
                    DO UPDATE SET
                        sku = EXCLUDED.sku,
                        title = EXCLUDED.title,
                        quantity = EXCLUDED.quantity,
                        total_value = EXCLUDED.total_value,
                        currency = EXCLUDED.currency,
                        raw_payload = EXCLUDED.raw_payload,
                        ebay_account_id = EXCLUDED.ebay_account_id,
                        ebay_user_id = EXCLUDED.ebay_user_id
                """)
                
                session.execute(query, params)
                stored_count += len(value_placeholders)
            
            return stored_count
            
        except Exception as e:
            logger.error(f"Error in batch upsert line items: {str(e)}")
            raise
    
    def create_sync_job(self, user_id: str, sync_type: str) -> int:
        """Create a new sync job"""
        session = self._get_session()
        
        try:
            now = datetime.utcnow()
            
            query = text("""
                INSERT INTO ebay_sync_jobs (user_id, sync_type, status, started_at)
                VALUES (:user_id, :sync_type, :status, :started_at)
                RETURNING id
            """)
            
            result = session.execute(query, {
                'user_id': user_id,
                'sync_type': sync_type,
                'status': 'running',
                'started_at': now
            })
            
            job_id = result.scalar()
            session.commit()
            return job_id
            
        except Exception as e:
            logger.error(f"Error creating sync job: {str(e)}")
            session.rollback()
            return 0
        finally:
            session.close()
    
    def update_sync_job(self, job_id: int, status: str, records_fetched: int = 0, 
                        records_stored: int = 0, error_message: str = None):
        """Update sync job status"""
        session = self._get_session()
        
        try:
            now = datetime.utcnow()
            
            query = text("""
                UPDATE ebay_sync_jobs 
                SET status = :status, 
                    records_fetched = :records_fetched, 
                    records_stored = :records_stored, 
                    completed_at = :completed_at, 
                    error_message = :error_message
                WHERE id = :job_id
            """)
            
            session.execute(query, {
                'status': status,
                'records_fetched': records_fetched,
                'records_stored': records_stored,
                'completed_at': now,
                'error_message': error_message,
                'job_id': job_id
            })
            
            session.commit()
            
        except Exception as e:
            logger.error(f"Error updating sync job: {str(e)}")
            session.rollback()
        finally:
            session.close()
    
    def get_sync_jobs(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent sync jobs for a user"""
        session = self._get_session()
        
        try:
            query = text("""
                SELECT * FROM ebay_sync_jobs 
                WHERE user_id = :user_id 
                ORDER BY started_at DESC 
                LIMIT :limit
            """)
            
            result = session.execute(query, {
                'user_id': user_id,
                'limit': limit
            })
            
            return [dict(row._mapping) for row in result]
            
        finally:
            session.close()
    
    def upsert_dispute(
        self,
        user_id: str,
        dispute_data: Dict[str, Any],
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
    ) -> bool:
        """Insert or update a payment dispute with eBay account context."""
        session = self._get_session()

        try:
            dispute_id = dispute_data.get("paymentDisputeId")
            if not dispute_id:
                logger.error("Dispute data missing paymentDisputeId")
                return False

            now = datetime.utcnow()

            order_id = dispute_data.get("orderId")
            dispute_reason = dispute_data.get("reason")
            dispute_status = dispute_data.get("status")
            open_date = dispute_data.get("openDate")
            respond_by_date = dispute_data.get("respondByDate")

            # Log into unified ebay_events inbox (best-effort, never fail on error).
            try:
                log_ebay_event(
                    source="rest_poll",
                    channel="post_order_api",
                    topic="PAYMENT_DISPUTE_UPDATED",
                    entity_type="DISPUTE",
                    entity_id=dispute_id,
                    ebay_account=ebay_user_id or ebay_account_id,
                    event_time=open_date,
                    publish_time=None,
                    headers={
                        "worker": "disputes_worker",
                        "api_family": "disputes",
                        "user_id": user_id,
                        "ebay_account_id": ebay_account_id,
                        "ebay_user_id": ebay_user_id,
                    },
                    payload=dispute_data,
                    db=session,
                )
            except Exception:
                logger.warning("Failed to log ebay_events row for dispute %s", dispute_id, exc_info=True)

            query = text(
                """
                INSERT INTO ebay_disputes
                (dispute_id, user_id, ebay_account_id, ebay_user_id,
                 order_id, dispute_reason,
                 dispute_status, open_date, respond_by_date, dispute_data,
                 created_at, updated_at)
                VALUES (:dispute_id, :user_id, :ebay_account_id, :ebay_user_id,
                        :order_id, :dispute_reason,
                        :dispute_status, :open_date, :respond_by_date, :dispute_data,
                        :created_at, :updated_at)
                ON CONFLICT (dispute_id, user_id)
                DO UPDATE SET
                    order_id = EXCLUDED.order_id,
                    dispute_reason = EXCLUDED.dispute_reason,
                    dispute_status = EXCLUDED.dispute_status,
                    open_date = EXCLUDED.open_date,
                    respond_by_date = EXCLUDED.respond_by_date,
                    dispute_data = EXCLUDED.dispute_data,
                    ebay_account_id = EXCLUDED.ebay_account_id,
                    ebay_user_id = EXCLUDED.ebay_user_id,
                    updated_at = EXCLUDED.updated_at
                """
            )

            session.execute(
                query,
                {
                    "dispute_id": dispute_id,
                    "user_id": user_id,
                    "ebay_account_id": ebay_account_id,
                    "ebay_user_id": ebay_user_id,
                    "order_id": order_id,
                    "dispute_reason": dispute_reason,
                    "dispute_status": dispute_status,
                    "open_date": open_date,
                    "respond_by_date": respond_by_date,
                    "dispute_data": json.dumps(dispute_data),
                    "created_at": now,
                    "updated_at": now,
                },
            )

            session.commit()
            return True

        except Exception as e:
            logger.error(f"Error upserting dispute: {str(e)}")
            session.rollback()
            return False
        finally:
            session.close()

    def upsert_inquiry(
        self,
        user_id: str,
        inquiry_data: Dict[str, Any],
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
    ) -> bool:
        """Insert or update a Post-Order inquiry in ebay_inquiries.

        This stores normalized identifiers and timestamps while preserving the
        full raw JSON payload in raw_json. It mirrors the style of upsert_case
        and upsert_dispute so repeated runs are idempotent.
        """
        session = self._get_session()

        try:
            inquiry_id = inquiry_data.get("inquiryId") or inquiry_data.get("inquiry_id")
            if not inquiry_id:
                logger.error("Inquiry data missing inquiryId")
                return False

            now = datetime.utcnow()

            order_id = inquiry_data.get("orderId") or inquiry_data.get("order_id")
            item_id = inquiry_data.get("itemId") or inquiry_data.get("item_id")
            transaction_id = inquiry_data.get("transactionId") or inquiry_data.get("transaction_id")

            buyer_username = inquiry_data.get("buyer") or inquiry_data.get("buyer_username")
            seller_username = inquiry_data.get("seller") or inquiry_data.get("seller_username")

            status = inquiry_data.get("status") or inquiry_data.get("inquiryStatus")

            # Derive a coarse issue_type (INR/OTHER) from any available reason field.
            raw_reason = (
                inquiry_data.get("reason")
                or inquiry_data.get("inquiryReason")
                or inquiry_data.get("caseType")
                or ""
            )
            issue_type: Optional[str] = None
            if isinstance(raw_reason, str):
                r_upper = raw_reason.upper()
                if "NOT_RECEIVED" in r_upper or "ITEM NOT RECEIVED" in r_upper or "INR" in r_upper:
                    issue_type = "INR"

            # Monetary amount (if present) – shape may mirror claimAmount.value/currency.
            claim_amount_obj = (
                inquiry_data.get("claimAmount")
                or inquiry_data.get("inquiryAmount")
                or inquiry_data.get("disputeAmount")
            )
            if isinstance(claim_amount_obj, dict):
                claim_amount_value, claim_amount_currency = self._parse_money(claim_amount_obj)
            else:
                claim_amount_value = None
                claim_amount_currency = None

            # Timestamps – try both flat and nested value shapes.
            opened_raw = (
                inquiry_data.get("creationDate")
                or inquiry_data.get("openedDate")
                or inquiry_data.get("openDate")
            )
            last_update_raw = inquiry_data.get("lastModifiedDate") or inquiry_data.get("lastUpdateDate")

            # Reuse the same parsing semantics as other ingestion helpers.
            opened_at = self._parse_datetime(opened_raw)
            last_update_at = self._parse_datetime(last_update_raw)

            desired_outcome = (
                inquiry_data.get("preferredOutcome")
                or inquiry_data.get("desiredOutcome")
                or None
            )

            # Log into unified ebay_events inbox (best-effort).
            try:
                log_ebay_event(
                    source="rest_poll",
                    channel="post_order_api",
                    topic="INQUIRY_UPDATED",
                    entity_type="INQUIRY",
                    entity_id=inquiry_id,
                    ebay_account=ebay_user_id or ebay_account_id,
                    event_time=opened_raw,
                    publish_time=None,
                    headers={
                        "worker": "inquiries_worker",
                        "api_family": "inquiries",
                        "user_id": user_id,
                        "ebay_account_id": ebay_account_id,
                        "ebay_user_id": ebay_user_id,
                    },
                    payload=inquiry_data,
                    db=session,
                )
            except Exception:
                logger.warning("Failed to log ebay_events row for inquiry %s", inquiry_id, exc_info=True)

            query = text(
                """
                INSERT INTO ebay_inquiries
                (inquiry_id, user_id, ebay_account_id, ebay_user_id,
                 order_id, item_id, transaction_id,
                 buyer_username, seller_username,
                 status, issue_type,
                 opened_at, last_update_at,
                 claim_amount_value, claim_amount_currency,
                 desired_outcome, raw_json,
                 created_at, updated_at)
                VALUES (:inquiry_id, :user_id, :ebay_account_id, :ebay_user_id,
                        :order_id, :item_id, :transaction_id,
                        :buyer_username, :seller_username,
                        :status, :issue_type,
                        :opened_at, :last_update_at,
                        :claim_amount_value, :claim_amount_currency,
                        :desired_outcome, :raw_json,
                        :created_at, :updated_at)
                ON CONFLICT (inquiry_id, user_id)
                DO UPDATE SET
                    order_id = EXCLUDED.order_id,
                    item_id = EXCLUDED.item_id,
                    transaction_id = EXCLUDED.transaction_id,
                    buyer_username = EXCLUDED.buyer_username,
                    seller_username = EXCLUDED.seller_username,
                    status = EXCLUDED.status,
                    issue_type = EXCLUDED.issue_type,
                    opened_at = EXCLUDED.opened_at,
                    last_update_at = EXCLUDED.last_update_at,
                    claim_amount_value = EXCLUDED.claim_amount_value,
                    claim_amount_currency = EXCLUDED.claim_amount_currency,
                    desired_outcome = EXCLUDED.desired_outcome,
                    raw_json = EXCLUDED.raw_json,
                    ebay_account_id = EXCLUDED.ebay_account_id,
                    ebay_user_id = EXCLUDED.ebay_user_id,
                    updated_at = EXCLUDED.updated_at
                """
            )

            session.execute(
                query,
                {
                    "inquiry_id": inquiry_id,
                    "user_id": user_id,
                    "ebay_account_id": ebay_account_id,
                    "ebay_user_id": ebay_user_id,
                    "order_id": order_id,
                    "item_id": item_id,
                    "transaction_id": transaction_id,
                    "buyer_username": buyer_username,
                    "seller_username": seller_username,
                    "status": status,
                    "issue_type": issue_type,
                    "opened_at": opened_at,
                    "last_update_at": last_update_at,
                    "claim_amount_value": claim_amount_value,
                    "claim_amount_currency": claim_amount_currency,
                    "desired_outcome": desired_outcome,
                    "raw_json": json.dumps(inquiry_data),
                    "created_at": now,
                    "updated_at": now,
                },
            )

            session.commit()
            return True

        except Exception as e:
            logger.error(f"Error upserting inquiry: {str(e)}")
            session.rollback()
            return False
        finally:
            session.close()

    def upsert_return(
        self,
        user_id: str,
        return_data: Dict[str, Any],
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
        *,
        return_id: Optional[str] = None,
    ) -> bool:
        """Insert or update a Post-Order return in ebay_returns.

        There are two supported payload shapes:

        1. A *merged* dict with top-level keys ``summary`` and ``detail`` as
           produced by the Post-Order search + detail API calls.
        2. A flat dict resembling the raw detail response (backwards
           compatibility / defensive path).

        For the merged shape, we apply the explicit mapping rules described in
        EBAY_RETURNS_MAPPING_2025-12-01, including:

        * Identifiers: return_id, order_id, item_id, transaction_id.
        * Actors: buyer_username, seller_username, ebay_user_id.
        * Return state/type and reason.
        * Timestamps: creation_date, last_modified_date, closed_date.
        * Money: sellerTotalRefund → total_amount_value/currency with fallbacks.
        * Raw payload: compact JSON of the full merged summary+detail object.

        ``return_id`` is accepted explicitly so that callers (e.g. workers using
        /post-order/v2/return/search) can pass the ID obtained from the search
        response even if the detailed payload omits or nests the id field.
        """
        session = self._get_session()

        try:
            now = datetime.utcnow()

            # Detect the merged Post-Order payload shape {"summary": {...}, "detail": {...}}.
            summary = None
            detail = None
            if isinstance(return_data.get("summary"), dict) and isinstance(return_data.get("detail"), dict):
                summary = return_data.get("summary") or {}
                detail = return_data.get("detail") or {}

            # Prefer explicit return_id from the worker/search response; for the
            # merged payload we resolve it from summary.returnId; otherwise fall
            # back to any id fields present on the flattened payload.
            if summary is not None:
                effective_return_id = (
                    return_id
                    or summary.get("returnId")
                    or summary.get("return_id")
                )
            else:
                effective_return_id = (
                    return_id
                    or return_data.get("returnId")
                    or return_data.get("return_id")
                )

            if not effective_return_id:
                logger.error(
                    "Return data missing returnId (no explicit return_id passed and "
                    "no returnId/return_id key in payload)",
                )
                return False

            return_id = str(effective_return_id)

            # --- Mapping for merged summary+detail payload (preferred path) ---
            if summary is not None:
                # Identifiers & actors
                order_id = summary.get("orderId") or summary.get("order_id")

                # Item / transaction: prefer summary.creationInfo.item.*, fallback to detail.itemDetail.*
                item_id = (
                    self._safe_get(summary, "creationInfo", "item", "itemId")
                    or self._safe_get(summary, "creationInfo", "item", "item_id")
                    or self._safe_get(detail, "itemDetail", "itemId")
                    or self._safe_get(detail, "itemDetail", "item_id")
                )
                if item_id is not None:
                    item_id = str(item_id)

                transaction_id = (
                    self._safe_get(summary, "creationInfo", "item", "transactionId")
                    or self._safe_get(summary, "creationInfo", "item", "transaction_id")
                    or self._safe_get(detail, "itemDetail", "transactionId")
                    or self._safe_get(detail, "itemDetail", "transaction_id")
                )
                if transaction_id is not None:
                    transaction_id = str(transaction_id)

                buyer_username = (
                    summary.get("buyerLoginName")
                    or detail.get("buyerLoginName")
                    or summary.get("buyer_username")
                    or detail.get("buyer_username")
                )
                seller_username = (
                    summary.get("sellerLoginName")
                    or detail.get("sellerLoginName")
                    or summary.get("seller_username")
                    or detail.get("seller_username")
                )

                # ebay_user_id is the seller login (e.g. "mil_243"); fall back to
                # the worker-provided ebay_user_id if payload is missing it.
                effective_ebay_user_id = seller_username or ebay_user_id

                # Return type & state
                return_type = (
                    summary.get("currentType")
                    or self._safe_get(summary, "creationInfo", "type")
                    or summary.get("returnType")
                )
                return_state = summary.get("state") or summary.get("returnState")

                # Reason string: "{reasonType}:{reason}" | "reasonType" | "reason" | None
                reason_type = self._safe_get(summary, "creationInfo", "reasonType")
                reason_code = self._safe_get(summary, "creationInfo", "reason")
                reason: Optional[str]
                if reason_type and reason_code:
                    reason = f"{reason_type}:{reason_code}"
                elif reason_type:
                    reason = str(reason_type)
                elif reason_code:
                    reason = str(reason_code)
                else:
                    reason = None

                # Money: sellerTotalRefund → buyerTotalRefund → detail.refundInfo...
                amount_obj = (
                    self._safe_get(summary, "sellerTotalRefund", "estimatedRefundAmount")
                    or self._safe_get(summary, "buyerTotalRefund", "estimatedRefundAmount")
                    or self._safe_get(
                        detail,
                        "refundInfo",
                        "estimatedRefundDetail",
                        "itemizedRefundDetails",
                        0,
                        "estimatedAmount",
                    )
                )
                if isinstance(amount_obj, dict):
                    total_amount_value, total_amount_currency = self._parse_money(amount_obj)
                else:
                    total_amount_value, total_amount_currency = (None, None)

                # Dates
                creation_raw = self._safe_get(
                    summary,
                    "creationInfo",
                    "creationDate",
                    "value",
                )

                # last_modified_date ≈ MAX(responseHistory[*].creationDate.value)
                history = detail.get("responseHistory") or []
                history_datetimes: List[datetime] = []
                for entry in history:
                    raw = self._safe_get(entry, "creationDate", "value") or entry.get("creationDate")
                    if isinstance(raw, str):
                        dt = self._parse_datetime(raw)
                        if dt is not None:
                            history_datetimes.append(dt)

                creation_date = self._parse_datetime(creation_raw) if isinstance(creation_raw, str) else None
                if history_datetimes:
                    last_modified_date = max(history_datetimes)
                else:
                    last_modified_date = creation_date

                # closed_date: use any explicit close timestamp on detail if present.
                closed_raw = (
                    self._safe_get(detail, "closeDate", "value")
                    or detail.get("closeDate")
                    or self._safe_get(detail, "closeInfo", "closeDate", "value")
                    or self._safe_get(detail, "closeInfo", "closeDate")
                )
                closed_date = self._parse_datetime(closed_raw) if isinstance(closed_raw, str) else None

                # Raw payload: full merged summary+detail as compact JSON.
                raw_json = json.dumps(return_data, separators=(",", ":"))

            # --- Fallback for legacy / flat payloads (defensive path) ---
            else:
                order_id = return_data.get("orderId") or return_data.get("order_id")
                item_id = return_data.get("itemId") or return_data.get("item_id")
                if item_id is not None:
                    item_id = str(item_id)

                transaction_id = return_data.get("transactionId") or return_data.get("transaction_id")
                if transaction_id is not None:
                    transaction_id = str(transaction_id)

                return_state = (
                    return_data.get("state")
                    or return_data.get("returnState")
                    or return_data.get("return_state")
                )
                return_type = (
                    return_data.get("type")
                    or return_data.get("returnType")
                    or return_data.get("return_type")
                )
                reason = (
                    return_data.get("reason")
                    or return_data.get("reasonCode")
                    or return_data.get("reason_code")
                )

                buyer_username = (
                    self._safe_get(return_data, "buyer", "username")
                    or return_data.get("buyerUsername")
                    or return_data.get("buyer_username")
                )
                seller_username = (
                    self._safe_get(return_data, "seller", "username")
                    or return_data.get("sellerUsername")
                    or return_data.get("seller_username")
                )
                effective_ebay_user_id = seller_username or ebay_user_id

                amount_obj = (
                    self._safe_get(return_data, "totalAmount")
                    or self._safe_get(return_data, "refundAmount")
                    or return_data.get("totalAmount")
                    or return_data.get("refundAmount")
                )
                if isinstance(amount_obj, dict):
                    total_amount_value, total_amount_currency = self._parse_money(amount_obj)
                else:
                    total_amount_value, total_amount_currency = (None, None)

                creation_raw = (
                    self._safe_get(return_data, "creationDate", "value")
                    or return_data.get("creationDate")
                    or return_data.get("creation_date")
                )
                last_modified_raw = (
                    self._safe_get(return_data, "lastModifiedDate", "value")
                    or return_data.get("lastModifiedDate")
                    or return_data.get("last_modified_date")
                )
                closed_raw = (
                    self._safe_get(return_data, "closedDate", "value")
                    or return_data.get("closedDate")
                    or return_data.get("closed_date")
                )

                creation_date = self._parse_datetime(creation_raw if isinstance(creation_raw, str) else None)
                last_modified_date = self._parse_datetime(last_modified_raw if isinstance(last_modified_raw, str) else None)
                closed_date = self._parse_datetime(closed_raw if isinstance(closed_raw, str) else None)

                raw_json = json.dumps(return_data, separators=(",", ":"))

            from sqlalchemy import text as text_query

            query = text_query(
                """
                INSERT INTO ebay_returns
                (return_id, user_id, ebay_account_id, ebay_user_id,
                 order_id, item_id, transaction_id,
                 return_state, return_type, reason,
                 buyer_username, seller_username,
                 total_amount_value, total_amount_currency,
                 creation_date, last_modified_date, closed_date,
                 raw_json, created_at, updated_at)
                VALUES (:return_id, :user_id, :ebay_account_id, :ebay_user_id,
                        :order_id, :item_id, :transaction_id,
                        :return_state, :return_type, :reason,
                        :buyer_username, :seller_username,
                        :total_amount_value, :total_amount_currency,
                        :creation_date, :last_modified_date, :closed_date,
                        :raw_json, :created_at, :updated_at)
                ON CONFLICT (return_id, user_id)
                DO UPDATE SET
                    ebay_account_id = EXCLUDED.ebay_account_id,
                    ebay_user_id = EXCLUDED.ebay_user_id,
                    order_id = EXCLUDED.order_id,
                    item_id = EXCLUDED.item_id,
                    transaction_id = EXCLUDED.transaction_id,
                    return_state = EXCLUDED.return_state,
                    return_type = EXCLUDED.return_type,
                    reason = EXCLUDED.reason,
                    buyer_username = EXCLUDED.buyer_username,
                    seller_username = EXCLUDED.seller_username,
                    total_amount_value = EXCLUDED.total_amount_value,
                    total_amount_currency = EXCLUDED.total_amount_currency,
                    creation_date = EXCLUDED.creation_date,
                    last_modified_date = EXCLUDED.last_modified_date,
                    closed_date = EXCLUDED.closed_date,
                    raw_json = EXCLUDED.raw_json,
                    updated_at = EXCLUDED.updated_at
                """
            )

            session.execute(
                query,
                {
                    "return_id": return_id,
                    "user_id": user_id,
                    "ebay_account_id": ebay_account_id,
                    "ebay_user_id": effective_ebay_user_id,
                    "order_id": order_id,
                    "item_id": item_id,
                    "transaction_id": transaction_id,
                    "return_state": return_state,
                    "return_type": return_type,
                    "reason": reason,
                    "buyer_username": buyer_username,
                    "seller_username": seller_username,
                    "total_amount_value": total_amount_value,
                    "total_amount_currency": total_amount_currency,
                    "creation_date": creation_date,
                    "last_modified_date": last_modified_date,
                    "closed_date": closed_date,
                    "raw_json": raw_json,
                    "created_at": now,
                    "updated_at": now,
                },
            )

            session.commit()
            return True

        except Exception as e:
            logger.error(f"Error upserting return: {str(e)}")
            session.rollback()
            return False
        finally:
            session.close()

    def upsert_case(
        self,
        user_id: str,
        case_data: Dict[str, Any],
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
    ) -> bool:
        """Insert or update a Post-Order case in ebay_cases.

        Pipeline overview (Post-Order cases only): the cases worker calls
        ``EbayService.sync_postorder_cases``, which fetches cases from
        ``GET /post-order/v2/casemanagement/search`` and passes each payload
        here. This helper normalizes identifiers, buyer/seller usernames,
        monetary amounts and key timestamps into explicit ebay_cases columns
        while also storing the full raw JSON payload in ``case_data`` for
        archival/debugging.
        """
        session = self._get_session()

        try:
            case_id = case_data.get("caseId") or case_data.get("case_id")
            if not case_id:
                logger.error("Case data missing caseId")
                return False

            now = datetime.utcnow()

            order_id = case_data.get("orderId") or case_data.get("order_id")
            case_type = case_data.get("caseType") or case_data.get("case_type")
            case_status = case_data.get("status") or case_data.get("caseStatus")
            open_date = case_data.get("openDate") or case_data.get("open_date")
            close_date = case_data.get("closeDate") or case_data.get("close_date")

            # Normalized identifiers and denormalized API fields.
            item_id = case_data.get("itemId") or case_data.get("item_id")
            if item_id is not None:
                item_id = str(item_id)

            transaction_id = case_data.get("transactionId") or case_data.get("transaction_id")
            if transaction_id is not None:
                transaction_id = str(transaction_id)

            buyer_username = case_data.get("buyer") or case_data.get("buyer_username")
            seller_username = case_data.get("seller") or case_data.get("seller_username")

            case_status_enum = case_data.get("caseStatusEnum") or case_data.get("case_status_enum")

            claim_amount_obj = case_data.get("claimAmount") or case_data.get("claim_amount")
            if isinstance(claim_amount_obj, dict):
                claim_amount_value, claim_amount_currency = self._parse_money(claim_amount_obj)
            else:
                claim_amount_value, claim_amount_currency = (None, None)

            respond_by_raw = self._safe_get(case_data, "respondByDate", "value") or case_data.get("respondByDate")
            creation_raw = self._safe_get(case_data, "creationDate", "value") or case_data.get("creationDate")
            last_modified_raw = self._safe_get(case_data, "lastModifiedDate", "value") or case_data.get(
                "lastModifiedDate",
            )

            respond_by = self._parse_datetime(respond_by_raw if isinstance(respond_by_raw, str) else None)
            creation_date_api = self._parse_datetime(creation_raw if isinstance(creation_raw, str) else None)
            last_modified_date_api = self._parse_datetime(
                last_modified_raw if isinstance(last_modified_raw, str) else None,
            )

            if item_id is None or transaction_id is None:
                logger.warning(
                    "Post-Order case %s missing itemId or transactionId (item_id=%r, transaction_id=%r)",
                    case_id,
                    item_id,
                    transaction_id,
                )

            # Log into unified ebay_events inbox (best-effort, never fail on error).
            try:
                log_ebay_event(
                    source="rest_poll",
                    channel="post_order_api",
                    topic="CASE_UPDATED",
                    entity_type="CASE",
                    entity_id=case_id,
                    ebay_account=ebay_user_id or ebay_account_id,
                    event_time=open_date,
                    publish_time=None,
                    headers={
                        "worker": "cases_worker",
                        "api_family": "cases",
                        "user_id": user_id,
                        "ebay_account_id": ebay_account_id,
                        "ebay_user_id": ebay_user_id,
                    },
                    payload=case_data,
                    db=session,
                )
            except Exception:
                logger.warning("Failed to log ebay_events row for case %s", case_id, exc_info=True)

            query = text(
                """
                INSERT INTO ebay_cases
                (case_id, user_id, ebay_account_id, ebay_user_id,
                 order_id, case_type, case_status,
                 open_date, close_date, case_data,
                 item_id, transaction_id,
                 buyer_username, seller_username,
                 case_status_enum,
                 claim_amount_value, claim_amount_currency,
                 respond_by, creation_date_api, last_modified_date_api,
                 created_at, updated_at)
                VALUES (:case_id, :user_id, :ebay_account_id, :ebay_user_id,
                        :order_id, :case_type, :case_status,
                        :open_date, :close_date, :case_data,
                        :item_id, :transaction_id,
                        :buyer_username, :seller_username,
                        :case_status_enum,
                        :claim_amount_value, :claim_amount_currency,
                        :respond_by, :creation_date_api, :last_modified_date_api,
                        :created_at, :updated_at)
                ON CONFLICT (case_id, user_id)
                DO UPDATE SET
                    order_id = EXCLUDED.order_id,
                    case_type = EXCLUDED.case_type,
                    case_status = EXCLUDED.case_status,
                    open_date = EXCLUDED.open_date,
                    close_date = EXCLUDED.close_date,
                    case_data = EXCLUDED.case_data,
                    item_id = EXCLUDED.item_id,
                    transaction_id = EXCLUDED.transaction_id,
                    buyer_username = EXCLUDED.buyer_username,
                    seller_username = EXCLUDED.seller_username,
                    case_status_enum = EXCLUDED.case_status_enum,
                    claim_amount_value = EXCLUDED.claim_amount_value,
                    claim_amount_currency = EXCLUDED.claim_amount_currency,
                    respond_by = EXCLUDED.respond_by,
                    creation_date_api = EXCLUDED.creation_date_api,
                    last_modified_date_api = EXCLUDED.last_modified_date_api,
                    ebay_account_id = EXCLUDED.ebay_account_id,
                    ebay_user_id = EXCLUDED.ebay_user_id,
                    updated_at = EXCLUDED.updated_at
                """
            )

            session.execute(
                query,
                {
                    "case_id": case_id,
                    "user_id": user_id,
                    "ebay_account_id": ebay_account_id,
                    "ebay_user_id": ebay_user_id,
                    "order_id": order_id,
                    "case_type": case_type,
                    "case_status": case_status,
                    "open_date": open_date,
                    "close_date": close_date,
                    "case_data": json.dumps(case_data),
                    "item_id": item_id,
                    "transaction_id": transaction_id,
                    "buyer_username": buyer_username,
                    "seller_username": seller_username,
                    "case_status_enum": case_status_enum,
                    "claim_amount_value": claim_amount_value,
                    "claim_amount_currency": claim_amount_currency,
                    "respond_by": respond_by,
                    "creation_date_api": creation_date_api,
                    "last_modified_date_api": last_modified_date_api,
                    "created_at": now,
                    "updated_at": now,
                },
            )

            session.commit()
            return True

        except Exception as e:
            logger.error(f"Error upserting case: {str(e)}")
            session.rollback()
            return False
        finally:
            session.close()

    def upsert_finances_transaction(
        self,
        user_id: str,
        transaction: Dict[str, Any],
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
    ) -> bool:
        """Insert or update a Finances transaction and its fee lines.

        This writes into ebay_finances_transactions and ebay_finances_fees.
        Existing fee rows for the (account, transaction_id) pair are replaced.
        """
        session = self._get_session()

        try:
            txn_id = transaction.get("transactionId")
            if not txn_id:
                logger.error("Finances transaction missing transactionId")
                return False

            now = datetime.utcnow()

            txn_type = transaction.get("transactionType")
            txn_status = transaction.get("transactionStatus")
            booking_date = transaction.get("transactionDate")

            # Log into unified ebay_events inbox (best-effort).
            try:
                log_ebay_event(
                    source="rest_poll",
                    channel="sell_finances_api",
                    topic="FINANCES_TRANSACTION_UPDATED",
                    entity_type="FINANCES_TRANSACTION",
                    entity_id=txn_id,
                    ebay_account=ebay_user_id or ebay_account_id,
                    event_time=booking_date,
                    publish_time=None,
                    headers={
                        "worker": "finances_worker",
                        "api_family": "finances",
                        "user_id": user_id,
                        "ebay_account_id": ebay_account_id,
                        "ebay_user_id": ebay_user_id,
                    },
                    payload=transaction,
                    db=session,
                )
            except Exception:
                logger.warning("Failed to log ebay_events row for finances transaction %s", txn_id, exc_info=True)

            amount_obj = transaction.get("amount") or {}
            amount_value = amount_obj.get("value")
            amount_currency = amount_obj.get("currency")

            # bookingEntry indicates CREDIT (money to seller) vs DEBIT (money from seller)
            booking_entry = (transaction.get("bookingEntry") or "").upper()
            signed_amount = None
            if amount_value is not None:
                try:
                    from decimal import Decimal

                    val = Decimal(str(amount_value))
                    if booking_entry == "DEBIT":
                        val = -val
                    signed_amount = val
                except Exception:
                    logger.warning(f"Could not parse finances amount '{amount_value}' for txn {txn_id}")

            order_id = transaction.get("orderId")
            # For now, take the first order line item id if present.
            order_line_items = transaction.get("orderLineItems") or []
            order_line_item_id = None
            if order_line_items:
                try:
                    order_line_item_id = (order_line_items[0] or {}).get("lineItemId")
                except Exception:
                    order_line_item_id = None

            payout_id = transaction.get("payoutId")
            seller_reference = transaction.get("salesRecordReference")
            txn_memo = transaction.get("transactionMemo")

            query_txn = text(
                """
                INSERT INTO ebay_finances_transactions
                (ebay_account_id, ebay_user_id,
                 transaction_id, transaction_type, transaction_status,
                 booking_date, transaction_amount_value, transaction_amount_currency,
                 order_id, order_line_item_id, payout_id, seller_reference,
                 transaction_memo, raw_payload,
                 created_at, updated_at)
                VALUES (:ebay_account_id, :ebay_user_id,
                        :transaction_id, :transaction_type, :transaction_status,
                        :booking_date, :transaction_amount_value, :transaction_amount_currency,
                        :order_id, :order_line_item_id, :payout_id, :seller_reference,
                        :transaction_memo, :raw_payload,
                        :created_at, :updated_at)
                ON CONFLICT (ebay_account_id, transaction_id)
                DO UPDATE SET
                    transaction_type = EXCLUDED.transaction_type,
                    transaction_status = EXCLUDED.transaction_status,
                    booking_date = EXCLUDED.booking_date,
                    transaction_amount_value = EXCLUDED.transaction_amount_value,
                    transaction_amount_currency = EXCLUDED.transaction_amount_currency,
                    order_id = EXCLUDED.order_id,
                    order_line_item_id = EXCLUDED.order_line_item_id,
                    payout_id = EXCLUDED.payout_id,
                    seller_reference = EXCLUDED.seller_reference,
                    transaction_memo = EXCLUDED.transaction_memo,
                    raw_payload = EXCLUDED.raw_payload,
                    ebay_user_id = EXCLUDED.ebay_user_id,
                    updated_at = EXCLUDED.updated_at
                """
            )

            session.execute(
                query_txn,
                {
                    "ebay_account_id": ebay_account_id,
                    "ebay_user_id": ebay_user_id,
                    "transaction_id": txn_id,
                    "transaction_type": txn_type,
                    "transaction_status": txn_status,
                    "booking_date": booking_date,
                    "transaction_amount_value": signed_amount,
                    "transaction_amount_currency": amount_currency,
                    "order_id": order_id,
                    "order_line_item_id": order_line_item_id,
                    "payout_id": payout_id,
                    "seller_reference": seller_reference,
                    "transaction_memo": txn_memo,
                    "raw_payload": json.dumps(transaction),
                    "created_at": now,
                    "updated_at": now,
                },
            )

            # Replace fees for this transaction/account
            delete_fees = text(
                "DELETE FROM ebay_finances_fees WHERE ebay_account_id = :ebay_account_id AND transaction_id = :transaction_id"
            )
            session.execute(delete_fees, {"ebay_account_id": ebay_account_id, "transaction_id": txn_id})

            # Collect fee lines from orderLineItems.marketplaceFees and donations
            fee_rows = []

            for oli in order_line_items:
                if not oli:
                    continue
                for fee in (oli.get("marketplaceFees") or []):
                    if not fee:
                        continue
                    fee_rows.append(fee)
                for donation in (oli.get("donations") or []):
                    if not donation:
                        continue
                    fee_rows.append(donation)

            # Some NON_SALE_CHARGE / other fee-only transactions expose feeType at the top level.
            top_fee_type = transaction.get("feeType")
            if top_fee_type:
                top_amount = transaction.get("amount") or {}
                fee_rows.append(
                    {
                        "feeType": top_fee_type,
                        "amount": top_amount,
                    }
                )

            # Internal heuristic: we treat an order as "ready to ship" when we see
            # a successful SALE Finances transaction (credit to the seller) that
            # carries an orderId. This is a first approximation based on the
            # Sell Finances API docs and will be refined once the Shipping
            # module is fully in place (e.g. checking fulfillment status and
            # open disputes).
            try:
                txn_type_upper = (txn_type or "").upper()
                txn_status_upper = (txn_status or "").upper()
                successful_statuses = {"COMPLETED", "SUCCESS", "PAYOUT"}
                is_successful_sale = (
                    txn_type_upper == "SALE"
                    and booking_entry == "CREDIT"
                    and txn_status_upper in successful_statuses
                )
                if is_successful_sale and order_id:
                    from datetime import timedelta, timezone

                    from sqlalchemy import and_ as _and_, exists as _exists

                    from app.models_sqlalchemy.models import EbayEvent  # local import to avoid cycles
                    from app.services.ebay_event_inbox import (  # type: ignore
                        log_ebay_event as _log_evt,
                    )

                    # Deduplicate: only emit one ORDER_READY_TO_SHIP per
                    # (account, orderId) within a 30-day window.
                    lookback = datetime.utcnow() - timedelta(days=30)
                    account_key = ebay_user_id or ebay_account_id
                    dup_query = session.query(_exists().where(
                        _and_(
                            EbayEvent.topic == "ORDER_READY_TO_SHIP",
                            EbayEvent.entity_type == "ORDER",
                            EbayEvent.entity_id == order_id,
                            EbayEvent.created_at >= lookback,
                            *(
                                [EbayEvent.ebay_account == account_key]
                                if account_key
                                else []
                            ),
                        ),
                    ))
                    already_exists = bool(dup_query.scalar())

                    if not already_exists:
                        _log_evt(
                            source="rest_poll",
                            channel="computed",
                            topic="ORDER_READY_TO_SHIP",
                            entity_type="ORDER",
                            entity_id=order_id,
                            ebay_account=account_key,
                            event_time=booking_date,
                            publish_time=None,
                            headers={
                                "worker": "finances_worker",
                                "rule": "successful_sale_implies_ready_to_ship",
                                "user_id": user_id,
                                "ebay_account_id": ebay_account_id,
                                "ebay_user_id": ebay_user_id,
                                "transaction_id": txn_id,
                            },
                            payload={
                                "transactionId": txn_id,
                                "transactionType": txn_type,
                                "transactionStatus": txn_status,
                                "orderId": order_id,
                            },
                            db=session,
                        )
            except Exception:
                logger.warning(
                    "Failed to log ORDER_READY_TO_SHIP event for finances transaction %s",
                    txn_id,
                    exc_info=True,
                )

            if fee_rows:
                insert_fee = text(
                    """
                    INSERT INTO ebay_finances_fees
                    (ebay_account_id, transaction_id, fee_type,
                     amount_value, amount_currency, raw_payload,
                     created_at, updated_at)
                    VALUES (:ebay_account_id, :transaction_id, :fee_type,
                            :amount_value, :amount_currency, :raw_payload,
                            :created_at, :updated_at)
                    """
                )

                from decimal import Decimal

                for fee in fee_rows:
                    fee_type = fee.get("feeType")
                    amount_obj = fee.get("amount") or {}
                    raw_val = amount_obj.get("value")
                    cur = amount_obj.get("currency")
                    amt_val = None
                    if raw_val is not None:
                        try:
                            amt_val = Decimal(str(raw_val))
                        except Exception:
                            logger.warning(
                                f"Could not parse fee amount '{raw_val}' for txn {txn_id} fee_type={fee_type}"
                            )

                    session.execute(
                        insert_fee,
                        {
                            "ebay_account_id": ebay_account_id,
                            "transaction_id": txn_id,
                            "fee_type": fee_type,
                            "amount_value": amt_val,
                            "amount_currency": cur,
                            "raw_payload": json.dumps(fee),
                            "created_at": now,
                            "updated_at": now,
                        },
                    )

            session.commit()
            return True

        except Exception as e:
            logger.error(f"Error upserting finances transaction {transaction.get('transactionId')}: {str(e)}")
            session.rollback()
            return False
        finally:
            session.close()

    def upsert_offer(
        self,
        user_id: str,
        offer_data: Dict[str, Any],
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
    ) -> bool:
        """Insert or update an offer with eBay account context."""
        session = self._get_session()
        
        try:
            offer_id = offer_data.get('offerId')
            if not offer_id:
                logger.error("Offer data missing offerId")
                return False

            now = datetime.utcnow()

            listing_id = offer_data.get('listingId')
            buyer_username = offer_data.get('buyer', {}).get('username')
            
            price = offer_data.get('price', {})
            offer_amount = price.get('value')
            offer_currency = price.get('currency')
            
            offer_status = offer_data.get('status')
            offer_date = offer_data.get('creationDate')
            expiration_date = offer_data.get('expirationDate')

            # Log into unified ebay_events inbox (best-effort).
            try:
                log_ebay_event(
                    source="rest_poll",
                    channel="marketing_offers",
                    topic="OFFER_UPDATED",
                    entity_type="OFFER",
                    entity_id=offer_id,
                    ebay_account=ebay_user_id or ebay_account_id,
                    event_time=offer_date,
                    publish_time=None,
                    headers={
                        "worker": "offers_worker",
                        "api_family": "offers",
                        "user_id": user_id,
                        "ebay_account_id": ebay_account_id,
                        "ebay_user_id": ebay_user_id,
                    },
                    payload=offer_data,
                    db=session,
                )
            except Exception:
                logger.warning("Failed to log ebay_events row for offer %s", offer_id, exc_info=True)
            
            query = text("""
                INSERT INTO ebay_offers 
                (offer_id, user_id, ebay_account_id, ebay_user_id,
                 listing_id, buyer_username, 
                 offer_amount, offer_currency, offer_status, 
                 offer_date, expiration_date, offer_data, 
                 created_at, updated_at)
                VALUES (:offer_id, :user_id, :ebay_account_id, :ebay_user_id,
                        :listing_id, :buyer_username,
                        :offer_amount, :offer_currency, :offer_status,
                        :offer_date, :expiration_date, :offer_data,
                        :created_at, :updated_at)
                ON CONFLICT (offer_id, user_id) 
                DO UPDATE SET
                    listing_id = EXCLUDED.listing_id,
                    buyer_username = EXCLUDED.buyer_username,
                    offer_amount = EXCLUDED.offer_amount,
                    offer_currency = EXCLUDED.offer_currency,
                    offer_status = EXCLUDED.offer_status,
                    offer_date = EXCLUDED.offer_date,
                    expiration_date = EXCLUDED.expiration_date,
                    offer_data = EXCLUDED.offer_data,
                    updated_at = EXCLUDED.updated_at
            """)
            
            session.execute(query, {
                'offer_id': offer_id,
                'user_id': user_id,
                'ebay_account_id': ebay_account_id,
                'ebay_user_id': ebay_user_id,
                'listing_id': listing_id,
                'buyer_username': buyer_username,
                'offer_amount': offer_amount,
                'offer_currency': offer_currency,
                'offer_status': offer_status,
                'offer_date': offer_date,
                'expiration_date': expiration_date,
                'offer_data': json.dumps(offer_data),
                'created_at': now,
                'updated_at': now
            })
            
            session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error upserting offer: {str(e)}")
            session.rollback()
            return False
        finally:
            session.close()
    
    def upsert_transaction(
        self,
        user_id: str,
        transaction_data: Dict[str, Any],
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
    ) -> bool:
        """Insert or update a transaction with eBay account context."""
        session = self._get_session()
        
        try:
            transaction_id = transaction_data.get('transactionId')
            if not transaction_id:
                logger.error("Transaction data missing transactionId")
                return False

            now = datetime.utcnow()

            order_id = transaction_data.get('orderId')
            transaction_date = transaction_data.get('transactionDate')
            transaction_type = transaction_data.get('transactionType')
            transaction_status = transaction_data.get('transactionStatus')

            # Log into unified ebay_events inbox (legacy transactions path).
            try:
                log_ebay_event(
                    source="rest_poll",
                    channel="sell_finances_api",
                    topic="TRANSACTION_UPDATED",
                    entity_type="TRANSACTION",
                    entity_id=transaction_id,
                    ebay_account=ebay_user_id or ebay_account_id,
                    event_time=transaction_date,
                    publish_time=None,
                    headers={
                        "worker": "transactions_worker",
                        "api_family": "transactions",
                        "user_id": user_id,
                        "ebay_account_id": ebay_account_id,
                        "ebay_user_id": ebay_user_id,
                    },
                    payload=transaction_data,
                    db=session,
                )
            except Exception:
                logger.warning("Failed to log ebay_events row for transaction %s", transaction_id, exc_info=True)
            
            amount_data = transaction_data.get('amount', {})
            amount = amount_data.get('value')
            currency = amount_data.get('currency')
            
            query = text("""
                INSERT INTO ebay_transactions 
                (transaction_id, user_id, ebay_account_id, ebay_user_id,
                 order_id, transaction_date, 
                 transaction_type, transaction_status, amount, currency,
                 transaction_data, created_at, updated_at)
                VALUES (:transaction_id, :user_id, :ebay_account_id, :ebay_user_id,
                        :order_id, :transaction_date,
                        :transaction_type, :transaction_status, :amount, :currency,
                        :transaction_data, :created_at, :updated_at)
                ON CONFLICT (transaction_id, user_id) 
                DO UPDATE SET
                    order_id = EXCLUDED.order_id,
                    transaction_date = EXCLUDED.transaction_date,
                    transaction_type = EXCLUDED.transaction_type,
                    transaction_status = EXCLUDED.transaction_status,
                    amount = EXCLUDED.amount,
                    currency = EXCLUDED.currency,
                    transaction_data = EXCLUDED.transaction_data,
                    updated_at = EXCLUDED.updated_at
            """)
            
            session.execute(query, {
                'transaction_id': transaction_id,
                'user_id': user_id,
                'ebay_account_id': ebay_account_id,
                'ebay_user_id': ebay_user_id,
                'order_id': order_id,
                'transaction_date': transaction_date,
                'transaction_type': transaction_type,
                'transaction_status': transaction_status,
                'amount': amount,
                'currency': currency,
                'transaction_data': json.dumps(transaction_data),
                'created_at': now,
                'updated_at': now
            })
            
            session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error upserting transaction: {str(e)}")
            session.rollback()
            return False
        finally:
            session.close()
    
    def get_filtered_orders(self, user_id: str, buyer_username: str = None, 
                           order_status: str = None, start_date: str = None, 
                           end_date: str = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get filtered orders for a user"""
        session = self._get_session()
        
        try:
            query_str = "SELECT * FROM ebay_orders WHERE user_id = :user_id"
            params = {'user_id': user_id}
            
            if buyer_username:
                query_str += " AND buyer_username LIKE :buyer_username"
                params['buyer_username'] = f"%{buyer_username}%"
            
            if order_status:
                query_str += " AND order_payment_status = :order_status"
                params['order_status'] = order_status
            
            if start_date:
                query_str += " AND creation_date >= :start_date"
                params['start_date'] = start_date
            
            if end_date:
                query_str += " AND creation_date <= :end_date"
                params['end_date'] = end_date
            
            query_str += " ORDER BY creation_date DESC LIMIT :limit OFFSET :offset"
            params['limit'] = limit
            params['offset'] = offset
            
            query = text(query_str)
            result = session.execute(query, params)
            
            orders = []
            for row in result:
                order = dict(row._mapping)
                if order.get('order_data'):
                    order['order_data'] = json.loads(order['order_data'])
                orders.append(order)
            
            return orders
            
        finally:
            session.close()
    
    def get_analytics_summary(self, user_id: str) -> Dict[str, Any]:
        """Get analytics summary for a user.

        In some Postgres environments the legacy ``ebay_orders`` table may not
        exist yet. In that case we return an empty summary instead of raising
        an internal error so that the Analytics dashboard and Orders stats
        widgets can still render without crashing the UI.
        """
        session = self._get_session()
        
        try:
            try:
                total_query = text("SELECT COUNT(*) as total FROM ebay_orders WHERE user_id = :user_id")
                total_orders = session.execute(total_query, {'user_id': user_id}).scalar() or 0
                
                sales_query = text("""
                    SELECT SUM(total_amount) as total_sales, total_currency 
                    FROM ebay_orders 
                    WHERE user_id = :user_id AND total_amount IS NOT NULL
                    GROUP BY total_currency
                """)
                sales_data = [dict(row._mapping) for row in session.execute(sales_query, {'user_id': user_id})]
                
                payment_query = text("""
                    SELECT order_payment_status, COUNT(*) as count 
                    FROM ebay_orders 
                    WHERE user_id = :user_id
                    GROUP BY order_payment_status
                """)
                payment_status_counts = {
                    row.order_payment_status: row.count
                    for row in session.execute(payment_query, {'user_id': user_id})
                }
                
                fulfillment_query = text("""
                    SELECT order_fulfillment_status, COUNT(*) as count 
                    FROM ebay_orders 
                    WHERE user_id = :user_id
                    GROUP BY order_fulfillment_status
                """)
                fulfillment_status_counts = {
                    row.order_fulfillment_status: row.count
                    for row in session.execute(fulfillment_query, {'user_id': user_id})
                }
                
                daily_query = text("""
                    SELECT DATE(creation_date) as date, COUNT(*) as count 
                    FROM ebay_orders 
                    WHERE user_id = :user_id AND creation_date IS NOT NULL
                    GROUP BY DATE(creation_date)
                    ORDER BY date DESC
                    LIMIT 30
                """)
                daily_orders = [
                    dict(row._mapping)
                    for row in session.execute(daily_query, {'user_id': user_id})
                ]
                
                return {
                    "total_orders": total_orders,
                    "sales_by_currency": sales_data,
                    "payment_status_breakdown": payment_status_counts,
                    "fulfillment_status_breakdown": fulfillment_status_counts,
                    "daily_orders_last_30_days": daily_orders,
                }
            except Exception as e:  # pragma: no cover - defensive fallback
                logger.warning(
                    "get_analytics_summary failed (likely missing ebay_orders table); "
                    "returning empty analytics summary: %s",
                    e,
                )
                return {
                    "total_orders": 0,
                    "sales_by_currency": [],
                    "payment_status_breakdown": {},
                    "fulfillment_status_breakdown": {},
                    "daily_orders_last_30_days": [],
                }
        finally:
            session.close()
    
    def upsert_inventory_item(
        self,
        user_id: str,
        inventory_item_data: Dict[str, Any],
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
    ) -> bool:
        """
        Insert or update an inventory item from eBay API into the inventory table.
        
        eBay API Response Structure (from getInventoryItems):
        {
            "sku": "string",
            "product": {
                "title": "string",
                "categoryId": "string",
                "aspects": {
                    "Brand": "string",
                    "Model": "string",
                    "Part Number": "string",
                    ...
                },
                "imageUrls": ["string"],
                ...
            },
            "condition": "NEW|USED_GOOD|...",
            "availability": {
                "shipToLocationAvailability": {
                    "quantity": 0
                }
            },
            "pricingSummary": {
                "price": {
                    "value": "string",
                    "currency": "USD"
                }
            },
            "offers": [
                {
                    "offerId": "string",
                    "status": "PUBLISHED|ENDED|..."
                }
            ]
        }
        
        Maps to inventory table:
        - sku -> sku_code (unique key)
        - product.title -> title
        - condition -> condition (enum)
        - availability.shipToLocationAvailability.quantity -> quantity
        - pricingSummary.price -> price_value, price_currency
        - product.categoryId -> category
        - product.aspects -> part_number, model
        - offers[0].offerId -> ebay_listing_id
        - offers status -> ebay_status (ACTIVE/ENDED)
        - product.imageUrls.length -> photo_count
        - Full inventory_item_data -> raw_payload (JSONB)
        
        Args:
            user_id: User ID (currently not stored in inventory table, may need schema update)
            inventory_item_data: Raw inventory item data from eBay API
            
        Returns:
            bool: True if successful, False otherwise
        """
        session = self._get_session()
        
        try:
            sku = inventory_item_data.get('sku')
            if not sku:
                logger.error("Inventory item data missing sku")
                return False
            
            now = datetime.utcnow()
            
            # Extract data from eBay inventory item structure
            product = inventory_item_data.get('product', {})
            title = product.get('title')
            
            # Get condition - map eBay condition to our ConditionType enum
            condition_str = inventory_item_data.get('condition', '')
            condition = None
            if condition_str:
                condition_map = {
                    'NEW': 'NEW',
                    'NEW_OTHER': 'NEW_OTHER',
                    'NEW_WITH_DEFECTS': 'NEW_WITH_DEFECTS',
                    'MANUFACTURER_REFURBISHED': 'MANUFACTURER_REFURBISHED',
                    'SELLER_REFURBISHED': 'SELLER_REFURBISHED',
                    'USED_EXCELLENT': 'USED_EXCELLENT',
                    'USED_VERY_GOOD': 'USED_VERY_GOOD',
                    'USED_GOOD': 'USED_GOOD',
                    'USED_ACCEPTABLE': 'USED_ACCEPTABLE',
                    'FOR_PARTS_OR_NOT_WORKING': 'FOR_PARTS_OR_NOT_WORKING'
                }
                condition = condition_map.get(condition_str.upper())
            
            # Get availability/quantity
            availability = inventory_item_data.get('availability', {})
            quantity = availability.get('shipToLocationAvailability', {}).get('quantity', 0)
            
            # Get pricing if available
            pricing_summary = inventory_item_data.get('pricingSummary', {})
            price_obj = pricing_summary.get('price') or {}
            price_value, price_currency = self._parse_money(price_obj)
            
            # Get category
            category_id = product.get('categoryId')
            category = str(category_id) if category_id else None
            
            # Get listing IDs (offers)
            offers = inventory_item_data.get('offers', [])
            listing_ids = [offer.get('offerId') for offer in offers if offer.get('offerId')]
            ebay_listing_id = listing_ids[0] if listing_ids else None
            
            # Get image URLs count
            image_urls = product.get('imageUrls', [])
            photo_count = len(image_urls) if image_urls else 0
            
            # Get aspects for part_number, model, etc.
            aspects = product.get('aspects', {})
            part_number = aspects.get('Part Number') or aspects.get('MPN') or aspects.get('Brand Part Number')
            model = aspects.get('Model') or aspects.get('Model Number')
            
            # Determine eBay status based on offers
            ebay_status = 'UNKNOWN'
            if offers:
                active_offers = [o for o in offers if o.get('status') in ['PUBLISHED', 'PUBLISHED_IN_PROGRESS']]
                if active_offers:
                    ebay_status = 'ACTIVE'
                else:
                    ebay_status = 'ENDED'
            
            # Upsert using sku_code as unique key
            query = text("""
                INSERT INTO inventory 
                (sku_code, title, condition, part_number, model, category,
                 price_value, price_currency, quantity, ebay_listing_id, ebay_status,
                 photo_count, raw_payload, rec_created, rec_updated,
                 user_id, ebay_account_id, ebay_user_id)
                VALUES (:sku_code, :title, :condition, :part_number, :model, :category,
                        :price_value, :price_currency, :quantity, :ebay_listing_id, :ebay_status,
                        :photo_count, :raw_payload, :rec_created, :rec_updated,
                        :user_id, :ebay_account_id, :ebay_user_id)
                ON CONFLICT (sku_code) 
                DO UPDATE SET
                    title = EXCLUDED.title,
                    condition = EXCLUDED.condition,
                    part_number = EXCLUDED.part_number,
                    model = EXCLUDED.model,
                    category = EXCLUDED.category,
                    price_value = EXCLUDED.price_value,
                    price_currency = EXCLUDED.price_currency,
                    quantity = EXCLUDED.quantity,
                    ebay_listing_id = EXCLUDED.ebay_listing_id,
                    ebay_status = EXCLUDED.ebay_status,
                    photo_count = EXCLUDED.photo_count,
                    raw_payload = EXCLUDED.raw_payload,
                    rec_updated = EXCLUDED.rec_updated,
                    user_id = EXCLUDED.user_id,
                    ebay_account_id = EXCLUDED.ebay_account_id,
                    ebay_user_id = EXCLUDED.ebay_user_id
            """)
            
            session.execute(query, {
                'sku_code': sku,
                'title': title,
                'condition': condition,
                'part_number': part_number,
                'model': model,
                'category': category,
                'price_value': price_value,
                'price_currency': price_currency,
                'quantity': quantity,
                'ebay_listing_id': ebay_listing_id,
                'ebay_status': ebay_status,
                'photo_count': photo_count,
                'raw_payload': json.dumps(inventory_item_data),
                'rec_created': now,
                'rec_updated': now,
                'user_id': user_id,
                'ebay_account_id': ebay_account_id,
                'ebay_user_id': ebay_user_id,
            })
            
            session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error upserting inventory item: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            session.rollback()
            return False
        finally:
            session.close()