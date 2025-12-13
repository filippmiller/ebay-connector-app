import sqlite3
from typing import Dict, Optional, List, Any
from datetime import datetime
import json
from pathlib import Path
from app.utils.logger import logger


class EbayDatabase:
    """
    Database for storing eBay data: orders, transactions, messages, offers, disputes, cases
    """
    
    def __init__(self, db_path: str = "/data/ebay_connector.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"Initialized eBay data database at {db_path}")
    
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                creation_date TEXT,
                last_modified_date TEXT,
                order_payment_status TEXT,
                order_fulfillment_status TEXT,
                buyer_username TEXT,
                buyer_email TEXT,
                total_amount REAL,
                total_currency TEXT,
                order_data JSON NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(order_id, user_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_creation_date ON orders(creation_date)')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                order_id TEXT,
                transaction_date TEXT,
                transaction_type TEXT,
                transaction_status TEXT,
                amount REAL,
                currency TEXT,
                transaction_data JSON NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(transaction_id, user_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_order_id ON transactions(order_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date)')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                thread_id TEXT,
                order_id TEXT,
                sender TEXT,
                recipient TEXT,
                subject TEXT,
                message_date TEXT,
                is_read INTEGER DEFAULT 0,
                message_data JSON NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(message_id, user_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages(thread_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_order_id ON messages(order_id)')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS offers (
                offer_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                listing_id TEXT,
                buyer_username TEXT,
                offer_amount REAL,
                offer_currency TEXT,
                offer_status TEXT,
                offer_date TEXT,
                expiration_date TEXT,
                offer_data JSON NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(offer_id, user_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_offers_user_id ON offers(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_offers_listing_id ON offers(listing_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_offers_status ON offers(offer_status)')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS disputes (
                dispute_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                order_id TEXT,
                dispute_reason TEXT,
                dispute_status TEXT,
                open_date TEXT,
                respond_by_date TEXT,
                dispute_data JSON NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(dispute_id, user_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_disputes_user_id ON disputes(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_disputes_order_id ON disputes(order_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_disputes_status ON disputes(dispute_status)')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                order_id TEXT,
                case_type TEXT,
                case_status TEXT,
                open_date TEXT,
                close_date TEXT,
                case_data JSON NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(case_id, user_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cases_user_id ON cases(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cases_order_id ON cases(order_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(case_status)')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                sync_type TEXT NOT NULL,
                status TEXT NOT NULL,
                records_fetched INTEGER DEFAULT 0,
                records_stored INTEGER DEFAULT 0,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                error_message TEXT,
                sync_data JSON
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sync_jobs_user_id ON sync_jobs(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sync_jobs_type ON sync_jobs(sync_type)')
        
        conn.commit()
        conn.close()
    
    def upsert_order(self, user_id: str, order_data: Dict[str, Any]) -> bool:
        """Insert or update an order"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        order_id = order_data.get('orderId')
        if not order_id:
            logger.error("Order data missing orderId")
            conn.close()
            return False
        
        now = datetime.utcnow().isoformat()
        
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
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO orders 
                (order_id, user_id, creation_date, last_modified_date, 
                 order_payment_status, order_fulfillment_status, 
                 buyer_username, buyer_email, total_amount, total_currency,
                 order_data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                    COALESCE((SELECT created_at FROM orders WHERE order_id = ?), ?),
                    ?)
            ''', (order_id, user_id, creation_date, last_modified,
                  payment_status, fulfillment_status,
                  buyer_username, buyer_email, total_amount, total_currency,
                  json.dumps(order_data), order_id, now, now))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error upserting order {order_id}: {str(e)}")
            conn.close()
            return False
    
    def get_orders(self, user_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get orders for a user"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM orders 
            WHERE user_id = ? 
            ORDER BY creation_date DESC 
            LIMIT ? OFFSET ?
        ''', (user_id, limit, offset))
        
        rows = cursor.fetchall()
        conn.close()
        
        orders = []
        for row in rows:
            order = dict(row)
            order['order_data'] = json.loads(order['order_data'])
            orders.append(order)
        
        return orders
    
    def get_order_count(self, user_id: str) -> int:
        """Get total order count for a user"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as count FROM orders WHERE user_id = ?', (user_id,))
        count = cursor.fetchone()['count']
        conn.close()
        
        return count
    
    def upsert_transaction(
        self,
        user_id: str,
        transaction_data: Dict[str, Any],
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
    ) -> bool:
        """Insert or update a transaction (SQLite legacy path, ignores eBay context)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        transaction_id = transaction_data.get('transactionId')
        if not transaction_id:
            logger.error("Transaction data missing transactionId")
            conn.close()
            return False
        
        now = datetime.utcnow().isoformat()
        
        order_id = transaction_data.get('orderId')
        transaction_date = transaction_data.get('transactionDate')
        transaction_type = transaction_data.get('transactionType')
        transaction_status = transaction_data.get('transactionStatus')
        
        amount_data = transaction_data.get('amount', {})
        amount = amount_data.get('value')
        currency = amount_data.get('currency')
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO transactions 
                (transaction_id, user_id, order_id, transaction_date, 
                 transaction_type, transaction_status, amount, currency,
                 transaction_data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                    COALESCE((SELECT created_at FROM transactions WHERE transaction_id = ?), ?),
                    ?)
            ''', (transaction_id, user_id, order_id, transaction_date,
                  transaction_type, transaction_status, amount, currency,
                  json.dumps(transaction_data), transaction_id, now, now))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error upserting transaction {transaction_id}: {str(e)}")
            conn.close()
            return False
    
    def create_sync_job(self, user_id: str, sync_type: str) -> int:
        """Create a new sync job"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        now = datetime.utcnow().isoformat()
        
        cursor.execute('''
            INSERT INTO sync_jobs (user_id, sync_type, status, started_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, sync_type, 'running', now))
        
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return job_id
    
    def update_sync_job(self, job_id: int, status: str, records_fetched: int = 0, 
                        records_stored: int = 0, error_message: str = None):
        """Update sync job status"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        now = datetime.utcnow().isoformat()
        
        cursor.execute('''
            UPDATE sync_jobs 
            SET status = ?, records_fetched = ?, records_stored = ?, 
                completed_at = ?, error_message = ?
            WHERE id = ?
        ''', (status, records_fetched, records_stored, now, error_message, job_id))
        
        conn.commit()
        conn.close()
    
    def get_sync_jobs(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent sync jobs for a user"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM sync_jobs 
            WHERE user_id = ? 
            ORDER BY started_at DESC 
            LIMIT ?
        ''', (user_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]


    def upsert_dispute(
        self,
        user_id: str,
        dispute_data: Dict[str, Any],
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
    ) -> bool:
        """Insert or update a dispute (SQLite legacy path, ignores eBay context)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        dispute_id = dispute_data.get('paymentDisputeId')
        if not dispute_id:
            logger.error("Dispute data missing paymentDisputeId")
            conn.close()
            return False
        
        now = datetime.utcnow().isoformat()
        
        order_id = dispute_data.get('orderId')
        dispute_reason = dispute_data.get('reason')
        dispute_status = dispute_data.get('status')
        open_date = dispute_data.get('openDate')
        respond_by_date = dispute_data.get('respondByDate')
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO disputes 
                (dispute_id, user_id, order_id, dispute_reason, 
                 dispute_status, open_date, respond_by_date, dispute_data, 
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                    COALESCE((SELECT created_at FROM disputes WHERE dispute_id = ?), ?),
                    ?)
            ''', (dispute_id, user_id, order_id, dispute_reason,
                  dispute_status, open_date, respond_by_date,
                  json.dumps(dispute_data), dispute_id, now, now))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error upserting dispute {dispute_id}: {str(e)}")
            conn.close()
            return False
    
    def upsert_offer(
        self,
        user_id: str,
        offer_data: Dict[str, Any],
        ebay_account_id: Optional[str] = None,
        ebay_user_id: Optional[str] = None,
    ) -> bool:
        """Insert or update an offer (SQLite legacy path, ignores eBay context)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        offer_id = offer_data.get('offerId')
        if not offer_id:
            logger.error("Offer data missing offerId")
            conn.close()
            return False
        
        now = datetime.utcnow().isoformat()
        
        listing_id = offer_data.get('listingId')
        buyer_username = offer_data.get('buyer', {}).get('username')
        
        price = offer_data.get('price', {})
        offer_amount = price.get('value')
        offer_currency = price.get('currency')
        
        offer_status = offer_data.get('status')
        offer_date = offer_data.get('creationDate')
        expiration_date = offer_data.get('expirationDate')
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO offers 
                (offer_id, user_id, listing_id, buyer_username, 
                 offer_amount, offer_currency, offer_status, 
                 offer_date, expiration_date, offer_data, 
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    COALESCE((SELECT created_at FROM offers WHERE offer_id = ?), ?),
                    ?)
            ''', (offer_id, user_id, listing_id, buyer_username,
                  offer_amount, offer_currency, offer_status,
                  offer_date, expiration_date,
                  json.dumps(offer_data), offer_id, now, now))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error upserting offer {offer_id}: {str(e)}")
            conn.close()
            return False

    
    def get_filtered_orders(self, user_id: str, buyer_username: str = None, 
                           order_status: str = None, start_date: str = None, 
                           end_date: str = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get filtered orders for a user"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM orders WHERE user_id = ?"
        params = [user_id]
        
        if buyer_username:
            query += " AND buyer_username LIKE ?"
            params.append(f"%{buyer_username}%")
        
        if order_status:
            query += " AND order_payment_status = ?"
            params.append(order_status)
        
        if start_date:
            query += " AND creation_date >= ?"
            params.append(start_date)
        
        if end_date:
            query += " AND creation_date <= ?"
            params.append(end_date)
        
        query += " ORDER BY creation_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        orders = []
        for row in rows:
            order = dict(row)
            order['order_data'] = json.loads(order['order_data'])
            orders.append(order)
        
        return orders
    
    def get_analytics_summary(self, user_id: str) -> Dict[str, Any]:
        """Get analytics summary for a user"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as total FROM orders WHERE user_id = ?', (user_id,))
        total_orders = cursor.fetchone()['total']
        
        cursor.execute('''
            SELECT SUM(total_amount) as total_sales, total_currency 
            FROM orders 
            WHERE user_id = ? AND total_amount IS NOT NULL
            GROUP BY total_currency
        ''', (user_id,))
        sales_data = cursor.fetchall()
        
        cursor.execute('''
            SELECT order_payment_status, COUNT(*) as count 
            FROM orders 
            WHERE user_id = ?
            GROUP BY order_payment_status
        ''', (user_id,))
        payment_status_counts = {row['order_payment_status']: row['count'] for row in cursor.fetchall()}
        
        cursor.execute('''
            SELECT order_fulfillment_status, COUNT(*) as count 
            FROM orders 
            WHERE user_id = ?
            GROUP BY order_fulfillment_status
        ''', (user_id,))
        fulfillment_status_counts = {row['order_fulfillment_status']: row['count'] for row in cursor.fetchall()}
        
        cursor.execute('''
            SELECT DATE(creation_date) as date, COUNT(*) as count 
            FROM orders 
            WHERE user_id = ? AND creation_date IS NOT NULL
            GROUP BY DATE(creation_date)
            ORDER BY date DESC
            LIMIT 30
        ''', (user_id,))
        daily_orders = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "total_orders": total_orders,
            "sales_by_currency": [dict(row) for row in sales_data],
            "payment_status_breakdown": payment_status_counts,
            "fulfillment_status_breakdown": fulfillment_status_counts,
            "daily_orders_last_30_days": daily_orders
        }


from app.config import settings

if "postgresql" in settings.DATABASE_URL:
    from app.services.postgres_ebay_database import PostgresEbayDatabase
    ebay_db = PostgresEbayDatabase()
    logger.info("Using PostgresEbayDatabase for eBay data")
else:
    ebay_db = EbayDatabase()
    logger.info("Using SQLiteEbayDatabase for eBay data")
