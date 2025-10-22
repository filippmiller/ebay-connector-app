from typing import Dict, Optional, List, Any, Tuple
from datetime import datetime
from decimal import Decimal
import json
from functools import reduce
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models_sqlalchemy import get_db
from app.utils.logger import logger


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
    
    def batch_upsert_orders(self, user_id: str, orders: List[Dict[str, Any]]) -> int:
        """Batch insert or update multiple orders with normalization"""
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
                        all_line_items.extend(line_items)
                        
                        normalized_order['user_id'] = user_id
                        normalized_order['created_at'] = now
                        normalized_order['updated_at'] = now
                        
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
                    for key in ['order_id', 'user_id', 'creation_date', 'last_modified',
                               'payment_status', 'fulfillment_status', 'buyer_username', 'buyer_email',
                               'buyer_registered', 'total_amount', 'total_currency',
                               'order_total_value', 'order_total_currency', 'line_items_count',
                               'tracking_number', 'ship_to_name', 'ship_to_city', 'ship_to_state',
                               'ship_to_postal_code', 'ship_to_country_code',
                               'order_data', 'raw_payload', 'created_at', 'updated_at']:
                        param_name = f"{key}_{idx}"
                        params[param_name] = values.get(key)
                        placeholders.append(f":{param_name}")
                    value_placeholders.append(f"({','.join(placeholders)})")
                
                query = text(f"""
                    INSERT INTO ebay_orders 
                    (order_id, user_id, creation_date, last_modified_date, 
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
                    for key in ['order_id', 'line_item_id', 'sku', 'title', 'quantity', 
                               'total_value', 'currency', 'raw_payload']:
                        param_name = f"{key}_{idx}"
                        params[param_name] = item.get(key)
                        placeholders.append(f":{param_name}")
                    value_placeholders.append(f"({','.join(placeholders)})")
                
                if not value_placeholders:
                    continue
                
                query = text(f"""
                    INSERT INTO order_line_items 
                    (order_id, line_item_id, sku, title, quantity, total_value, currency, raw_payload)
                    VALUES {','.join(value_placeholders)}
                    ON CONFLICT (order_id, line_item_id) 
                    DO UPDATE SET
                        sku = EXCLUDED.sku,
                        title = EXCLUDED.title,
                        quantity = EXCLUDED.quantity,
                        total_value = EXCLUDED.total_value,
                        currency = EXCLUDED.currency,
                        raw_payload = EXCLUDED.raw_payload
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
    
    def upsert_dispute(self, user_id: str, dispute_data: Dict[str, Any]) -> bool:
        """Insert or update a dispute"""
        session = self._get_session()
        
        try:
            dispute_id = dispute_data.get('paymentDisputeId')
            if not dispute_id:
                logger.error("Dispute data missing paymentDisputeId")
                return False
            
            now = datetime.utcnow()
            
            order_id = dispute_data.get('orderId')
            dispute_reason = dispute_data.get('reason')
            dispute_status = dispute_data.get('status')
            open_date = dispute_data.get('openDate')
            respond_by_date = dispute_data.get('respondByDate')
            
            query = text("""
                INSERT INTO ebay_disputes 
                (dispute_id, user_id, order_id, dispute_reason, 
                 dispute_status, open_date, respond_by_date, dispute_data, 
                 created_at, updated_at)
                VALUES (:dispute_id, :user_id, :order_id, :dispute_reason,
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
                    updated_at = EXCLUDED.updated_at
            """)
            
            session.execute(query, {
                'dispute_id': dispute_id,
                'user_id': user_id,
                'order_id': order_id,
                'dispute_reason': dispute_reason,
                'dispute_status': dispute_status,
                'open_date': open_date,
                'respond_by_date': respond_by_date,
                'dispute_data': json.dumps(dispute_data),
                'created_at': now,
                'updated_at': now
            })
            
            session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error upserting dispute: {str(e)}")
            session.rollback()
            return False
        finally:
            session.close()
    
    def upsert_offer(self, user_id: str, offer_data: Dict[str, Any]) -> bool:
        """Insert or update an offer"""
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
            
            query = text("""
                INSERT INTO ebay_offers 
                (offer_id, user_id, listing_id, buyer_username, 
                 offer_amount, offer_currency, offer_status, 
                 offer_date, expiration_date, offer_data, 
                 created_at, updated_at)
                VALUES (:offer_id, :user_id, :listing_id, :buyer_username,
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
    
    def upsert_transaction(self, user_id: str, transaction_data: Dict[str, Any]) -> bool:
        """Insert or update a transaction"""
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
            
            amount_data = transaction_data.get('amount', {})
            amount = amount_data.get('value')
            currency = amount_data.get('currency')
            
            query = text("""
                INSERT INTO ebay_transactions 
                (transaction_id, user_id, order_id, transaction_date, 
                 transaction_type, transaction_status, amount, currency,
                 transaction_data, created_at, updated_at)
                VALUES (:transaction_id, :user_id, :order_id, :transaction_date,
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
        """Get analytics summary for a user"""
        session = self._get_session()
        
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
            payment_status_counts = {row.order_payment_status: row.count for row in session.execute(payment_query, {'user_id': user_id})}
            
            fulfillment_query = text("""
                SELECT order_fulfillment_status, COUNT(*) as count 
                FROM ebay_orders 
                WHERE user_id = :user_id
                GROUP BY order_fulfillment_status
            """)
            fulfillment_status_counts = {row.order_fulfillment_status: row.count for row in session.execute(fulfillment_query, {'user_id': user_id})}
            
            daily_query = text("""
                SELECT DATE(creation_date) as date, COUNT(*) as count 
                FROM ebay_orders 
                WHERE user_id = :user_id AND creation_date IS NOT NULL
                GROUP BY DATE(creation_date)
                ORDER BY date DESC
                LIMIT 30
            """)
            daily_orders = [dict(row._mapping) for row in session.execute(daily_query, {'user_id': user_id})]
            
            return {
                "total_orders": total_orders,
                "sales_by_currency": sales_data,
                "payment_status_breakdown": payment_status_counts,
                "fulfillment_status_breakdown": fulfillment_status_counts,
                "daily_orders_last_30_days": daily_orders
            }
            
        finally:
            session.close()
