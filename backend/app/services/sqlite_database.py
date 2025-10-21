import sqlite3
from typing import Dict, Optional
from datetime import datetime
import uuid
import json
from pathlib import Path
from app.models.user import User, UserCreate, UserRole
from app.utils.logger import logger


class SQLiteDatabase:
    
    def __init__(self, db_path: str = "/data/ebay_connector.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"Initialized SQLite database at {db_path}")
    
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                hashed_password TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                ebay_connected INTEGER DEFAULT 0,
                ebay_access_token TEXT,
                ebay_refresh_token TEXT,
                ebay_token_expires_at TEXT,
                ebay_environment TEXT DEFAULT 'sandbox'
            )
        ''')
        
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN ebay_environment TEXT DEFAULT "sandbox"')
            conn.commit()
            logger.info("Added ebay_environment column to users table")
        except sqlite3.OperationalError:
            pass
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def create_user(self, user_data: UserCreate, hashed_password: str) -> User:
        user_id = str(uuid.uuid4())
        created_at = datetime.utcnow()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO users (id, email, username, hashed_password, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, user_data.email, user_data.username, hashed_password, 
              user_data.role.value, created_at.isoformat()))
        
        conn.commit()
        conn.close()
        
        user = User(
            id=user_id,
            email=user_data.email,
            username=user_data.username,
            hashed_password=hashed_password,
            role=user_data.role,
            created_at=created_at
        )
        
        logger.info(f"Created user: {user.email} with role: {user.role}")
        return user
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_user(row)
        return None
    
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_user(row)
        return None
    
    def update_user(self, user_id: str, updates: dict) -> Optional[User]:
        if not updates:
            return self.get_user_by_id(user_id)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        set_clauses = []
        values = []
        
        for key, value in updates.items():
            if key == 'ebay_connected':
                set_clauses.append(f"{key} = ?")
                values.append(1 if value else 0)
            elif key == 'ebay_token_expires_at' and isinstance(value, datetime):
                set_clauses.append(f"{key} = ?")
                values.append(value.isoformat())
            else:
                set_clauses.append(f"{key} = ?")
                values.append(value)
        
        values.append(user_id)
        
        query = f"UPDATE users SET {', '.join(set_clauses)} WHERE id = ?"
        cursor.execute(query, values)
        conn.commit()
        conn.close()
        
        user = self.get_user_by_id(user_id)
        if user:
            logger.info(f"Updated user: {user.email}")
        return user
    
    def create_password_reset_token(self, email: str) -> str:
        reset_token = str(uuid.uuid4())
        created_at = datetime.utcnow()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO password_reset_tokens (token, email, created_at)
            VALUES (?, ?, ?)
        ''', (reset_token, email, created_at.isoformat()))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Created password reset token for: {email}")
        return reset_token
    
    def verify_password_reset_token(self, token: str) -> Optional[str]:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT email FROM password_reset_tokens WHERE token = ?', (token,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return row['email']
        return None
    
    def delete_password_reset_token(self, token: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM password_reset_tokens WHERE token = ?', (token,))
        conn.commit()
        conn.close()
    
    def _row_to_user(self, row) -> User:
        expires_at = None
        if row['ebay_token_expires_at']:
            try:
                expires_at = datetime.fromisoformat(row['ebay_token_expires_at'])
            except:
                pass
        
        try:
            ebay_env = row['ebay_environment'] if row['ebay_environment'] else 'sandbox'
        except (KeyError, IndexError):
            ebay_env = 'sandbox'
        
        return User(
            id=row['id'],
            email=row['email'],
            username=row['username'],
            hashed_password=row['hashed_password'],
            role=UserRole(row['role']),
            created_at=datetime.fromisoformat(row['created_at']),
            ebay_connected=bool(row['ebay_connected']),
            ebay_access_token=row['ebay_access_token'],
            ebay_refresh_token=row['ebay_refresh_token'],
            ebay_token_expires_at=expires_at,
            ebay_environment=ebay_env
        )


db = SQLiteDatabase()
