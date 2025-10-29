"""
Database models and utilities for Homie Flask application
Handles database connection, initialization, and common queries
"""
import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    """Database connection and utility class"""
    
    def __init__(self, db_path='/app/data/homie.db'):
        self.db_path = db_path
    
    def get_connection(self):
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Initialize the database with required tables"""
        # Ensure the data directory exists
        os.makedirs('/app/data', exist_ok=True)
        conn = self.get_connection()
        
        # Users table (simplified for OIDC-only)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                full_name TEXT,
                is_admin BOOLEAN DEFAULT FALSE,
                oidc_sub TEXT UNIQUE NOT NULL,
                last_login TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP
            )
        ''')
        
        # Shopping list table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS shopping_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                completed BOOLEAN DEFAULT FALSE,
                added_by INTEGER NOT NULL,
                completed_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (added_by) REFERENCES users (id),
                FOREIGN KEY (completed_by) REFERENCES users (id)
            )
        ''')
        
        # Chores table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chore_name TEXT NOT NULL,
                assigned_to INTEGER,
                completed BOOLEAN DEFAULT FALSE,
                added_by INTEGER NOT NULL,
                completed_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (assigned_to) REFERENCES users (id),
                FOREIGN KEY (added_by) REFERENCES users (id),
                FOREIGN KEY (completed_by) REFERENCES users (id)
            )
        ''')
        
        # Expiry items table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS expiry_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                expiry_date DATE NOT NULL,
                added_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (added_by) REFERENCES users (id)
            )
        ''')
        
        # Bills table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_name TEXT NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                due_day INTEGER NOT NULL,
                added_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (added_by) REFERENCES users (id)
            )
        ''')
        
        # Settings table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        
        # Add missing columns to existing tables (migrations)
        self._run_migrations(conn)
        
        conn.commit()
        conn.close()
    
    def _run_migrations(self, conn):
        """Run database migrations for existing installations"""
        migrations = [
            ('ALTER TABLE shopping_items ADD COLUMN completed BOOLEAN DEFAULT FALSE', 'shopping_items completed column'),
            ('ALTER TABLE shopping_items ADD COLUMN completed_by INTEGER', 'shopping_items completed_by column'),
            ('ALTER TABLE shopping_items ADD COLUMN completed_at TIMESTAMP', 'shopping_items completed_at column'),
        ]
        
        for migration, description in migrations:
            try:
                conn.execute(migration)
                logger.info(f"Applied migration: {description}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    logger.debug(f"Migration already applied: {description}")
                else:
                    logger.warning(f"Migration failed: {description} - {e}")

class UserModel:
    """User model with common user operations"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_or_create_user(self, userinfo):
        """Get or create user from OIDC userinfo"""
        conn = self.db.get_connection()
        
        # Try to find existing user by oidc_sub
        user = conn.execute('SELECT * FROM users WHERE oidc_sub = ?', (userinfo['sub'],)).fetchone()
        
        if user:
            # Update last login
            conn.execute('UPDATE users SET last_login = ? WHERE id = ?', 
                        (datetime.now().isoformat(), user['id']))
            conn.commit()
        else:
            # Create new user
            username = userinfo.get('preferred_username', userinfo.get('email', '').split('@')[0])
            full_name = userinfo.get('name', username)
            email = userinfo.get('email', '')
            
            conn.execute('''
                INSERT INTO users (username, email, full_name, oidc_sub, last_login, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (username, email, full_name, userinfo['sub'], 
                  datetime.now().isoformat(), datetime.now().isoformat()))
            
            user_id = conn.lastrowid
            conn.commit()
            
            # Get the created user
            user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        
        conn.close()
        return user
    
    def update_last_activity(self, user_id):
        """Update user's last activity timestamp"""
        conn = self.db.get_connection()
        conn.execute('UPDATE users SET last_activity = ? WHERE id = ?', 
                    (datetime.now().isoformat(), user_id))
        conn.commit()
        conn.close()
    
    def get_user_by_id(self, user_id):
        """Get user by ID"""
        conn = self.db.get_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        return user

class DashboardModel:
    """Dashboard model for stats and counts"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_dashboard_stats(self):
        """Get counts for dashboard stats"""
        conn = self.db.get_connection()
        
        stats = {}
        
        # Get counts for dashboard stats
        stats['shopping_count'] = conn.execute(
            'SELECT COUNT(*) as count FROM shopping_items WHERE completed = 0 OR completed IS NULL'
        ).fetchone()['count']
        
        stats['chores_count'] = conn.execute(
            'SELECT COUNT(*) as count FROM chores WHERE completed = 0 OR completed IS NULL'
        ).fetchone()['count']
        
        stats['expiring_count'] = conn.execute('''
            SELECT COUNT(*) as count FROM expiry_items 
            WHERE expiry_date BETWEEN date('now') AND date('now', '+30 days')
        ''').fetchone()['count']
        
        # Get monthly bills total
        stats['bills_total'] = conn.execute('SELECT SUM(amount) as total FROM bills').fetchone()['total'] or 0
        
        conn.close()
        return stats