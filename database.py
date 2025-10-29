"""
Database utilities for Homie Flask application
"""
import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Database setup
DATABASE = '/app/data/homie.db'

def get_db_connection():
    """Get database connection with row factory"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with required tables"""
    # Ensure the data directory exists
    os.makedirs('/app/data', exist_ok=True)
    conn = get_db_connection()
    
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
    try:
        conn.execute('ALTER TABLE shopping_items ADD COLUMN completed BOOLEAN DEFAULT FALSE')
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists
        pass
    
    try:
        conn.execute('ALTER TABLE shopping_items ADD COLUMN completed_by INTEGER')
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists
        pass
    
    try:
        conn.execute('ALTER TABLE shopping_items ADD COLUMN completed_at TIMESTAMP')
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists
        pass
    
    conn.commit()
    conn.close()

def get_dashboard_stats():
    """Get counts for dashboard stats"""
    conn = get_db_connection()
    
    # Get counts for dashboard stats
    shopping_count = conn.execute('SELECT COUNT(*) as count FROM shopping_items WHERE completed = 0 OR completed IS NULL').fetchone()['count']
    chores_count = conn.execute('SELECT COUNT(*) as count FROM chores WHERE completed = 0 OR completed IS NULL').fetchone()['count']
    expiring_count = conn.execute('''
        SELECT COUNT(*) as count FROM expiry_items 
        WHERE expiry_date BETWEEN date('now') AND date('now', '+30 days')
    ''').fetchone()['count']
    
    # Get monthly bills total
    bills_total = conn.execute('SELECT SUM(amount) as total FROM bills').fetchone()['total'] or 0
    
    conn.close()
    
    return {
        'shopping_count': shopping_count,
        'chores_count': chores_count, 
        'expiring_count': expiring_count,
        'bills_total': bills_total
    }

def create_or_update_user(userinfo, access_control):
    """Create or update user from OIDC userinfo"""
    conn = get_db_connection()
    
    # Extract user information
    email = userinfo.get('email')
    username = userinfo.get('preferred_username', email.split('@')[0] if email else 'user')
    full_name = userinfo.get('name', '')
    oidc_sub = userinfo.get('sub')
    is_admin = email in access_control['admin_emails'] if email else False
    
    try:
        # Try to find existing user
        user = conn.execute('''
            SELECT * FROM users WHERE oidc_sub = ?
        ''', (oidc_sub,)).fetchone()
        
        if user:
            # Update existing user
            conn.execute('''
                UPDATE users SET 
                    username = ?, email = ?, full_name = ?, 
                    is_admin = ?, last_login = ?
                WHERE oidc_sub = ?
            ''', (username, email, full_name, is_admin, datetime.now().isoformat(), oidc_sub))
        else:
            # Create new user
            conn.execute('''
                INSERT INTO users (username, email, full_name, is_admin, oidc_sub, last_login, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (username, email, full_name, is_admin, oidc_sub, 
                  datetime.now().isoformat(), datetime.now().isoformat()))
        
        conn.commit()
        
        # Return the user record
        user = conn.execute('''
            SELECT * FROM users WHERE oidc_sub = ?
        ''', (oidc_sub,)).fetchone()
        
        conn.close()
        return user
        
    except Exception as e:
        conn.close()
        logger.error(f"Error creating/updating user: {e}")
        raise