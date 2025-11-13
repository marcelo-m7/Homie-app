"""
Database utilities for Homie Flask application
"""
import sqlite3
import os
import logging
from datetime import datetime
from config import get_currency_symbol

logger = logging.getLogger(__name__)

# Database setup - works for both Docker and local development
# Use environment variable or auto-detect based on platform/container
if 'DATABASE_PATH' in os.environ:
    DATABASE = os.getenv('DATABASE_PATH')
elif os.name == 'nt':  # Windows
    DATABASE = './data/homie.db'
elif os.path.exists('/app'):  # Docker container
    DATABASE = '/app/data/homie.db'
else:  # Linux/Mac local development
    DATABASE = './data/homie.db'

def get_db_connection():
    """Get database connection with row factory"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with required tables"""
    # Ensure the data directory exists
    db_dir = os.path.dirname(DATABASE)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        logger.info(f"Created database directory: {db_dir}")
    
    logger.info(f"Using database: {DATABASE}")
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
        'monthly_total': bills_total
    }

def get_recent_activities(limit=10):
    """Get recent activities across all modules for dashboard display"""
    conn = get_db_connection()
    activities = []
    
    try:
        logger.info(f"Getting recent activities with limit: {limit}")
        # Get recent shopping items added
        shopping_items = conn.execute('''
            SELECT 
                'shopping' as type,
                item_name,
                u.username,
                s.created_at,
                completed,
                completed_at
            FROM shopping_items s
            LEFT JOIN users u ON s.added_by = u.id
            ORDER BY s.created_at DESC
            LIMIT ?
        ''', (limit,)).fetchall()
        
        logger.info(f"Found {len(shopping_items)} shopping items")
        
        for item in shopping_items:
            if item['completed'] and item['completed_at']:
                activities.append({
                    'description': f"{item['username']} completed shopping item: {item['item_name']}",
                    'time': item['completed_at'],
                    'icon': 'fa-check-circle',
                    'type': 'shopping_completed'
                })
            else:
                activities.append({
                    'description': f"{item['username']} added shopping item: {item['item_name']}",
                    'time': item['created_at'],
                    'icon': 'fa-shopping-cart',
                    'type': 'shopping_added'
                })
        
        # Get recent chores
        chores = conn.execute('''
            SELECT 
                'chore' as type,
                chore_name,
                u1.username as added_by_username,
                u2.username as completed_by_username,
                c.created_at,
                completed,
                completed_at
            FROM chores c
            LEFT JOIN users u1 ON c.added_by = u1.id
            LEFT JOIN users u2 ON c.completed_by = u2.id
            ORDER BY COALESCE(completed_at, c.created_at) DESC
            LIMIT ?
        ''', (limit,)).fetchall()
        
        for chore in chores:
            if chore['completed'] and chore['completed_at']:
                activities.append({
                    'description': f"{chore['completed_by_username']} completed chore: {chore['chore_name']}",
                    'time': chore['completed_at'],
                    'icon': 'fa-check-circle',
                    'type': 'chore_completed'
                })
            else:
                activities.append({
                    'description': f"{chore['added_by_username']} added chore: {chore['chore_name']}",
                    'time': chore['created_at'],
                    'icon': 'fa-tasks',
                    'type': 'chore_added'
                })
        
        # Get recent expiry items
        expiry_items = conn.execute('''
            SELECT 
                'expiry' as type,
                item_name,
                expiry_date,
                u.username,
                e.created_at
            FROM expiry_items e
            LEFT JOIN users u ON e.added_by = u.id
            ORDER BY e.created_at DESC
            LIMIT ?
        ''', (limit,)).fetchall()
        
        for item in expiry_items:
            activities.append({
                'description': f"{item['username']} added expiry tracker: {item['item_name']} (expires {item['expiry_date']})",
                'time': item['created_at'],
                'icon': 'fa-calendar-times',
                'type': 'expiry_added'
            })
        
        # Get recent bills
        bills = conn.execute('''
            SELECT 
                'bill' as type,
                bill_name,
                amount,
                u.username,
                b.created_at
            FROM bills b
            LEFT JOIN users u ON b.added_by = u.id
            ORDER BY b.created_at DESC
            LIMIT ?
        ''', (limit,)).fetchall()
        
        for bill in bills:
            activities.append({
                'description': f"{bill['username']} added bill: {bill['bill_name']} ({get_currency_symbol()}{bill['amount']})",
                'time': bill['created_at'],
                'icon': 'fa-receipt',
                'type': 'bill_added'
            })
        
        # Sort all activities by time (most recent first) and limit
        activities.sort(key=lambda x: x['time'], reverse=True)
        activities = activities[:limit]
        
        logger.info(f"Total activities found: {len(activities)}")
        
        # Format timestamps for display
        from datetime import datetime
        for activity in activities:
            try:
                # Parse the timestamp
                dt = datetime.fromisoformat(activity['time'].replace('Z', '+00:00'))
                # Format for display (e.g., "2 hours ago", "Yesterday", etc.)
                now = datetime.now()
                diff = now - dt.replace(tzinfo=None)
                
                if diff.days > 0:
                    if diff.days == 1:
                        activity['time'] = "Yesterday"
                    else:
                        activity['time'] = f"{diff.days} days ago"
                elif diff.seconds > 3600:
                    hours = diff.seconds // 3600
                    activity['time'] = f"{hours} hour{'s' if hours > 1 else ''} ago"
                elif diff.seconds > 60:
                    minutes = diff.seconds // 60
                    activity['time'] = f"{minutes} minute{'s' if minutes > 1 else ''} ago"
                else:
                    activity['time'] = "Just now"
            except Exception as e:
                # Fallback to original timestamp if parsing fails
                logger.warning(f"Error parsing timestamp: {e}")
                activity['time'] = activity['time']
    
    except Exception as e:
        logger.error(f"Error getting recent activities: {e}")
    
    finally:
        conn.close()
    
    return activities

def create_or_update_user(userinfo, access_control):
    """Create or update user from OIDC userinfo"""
    conn = get_db_connection()
    
    # Extract user information
    email = userinfo.get('email')
    username = userinfo.get('preferred_username', email.split('@')[0] if email else 'user')
    full_name = userinfo.get('name', '')
    oidc_sub = userinfo.get('sub')
    is_admin = False  # Simplified: no admin distinction needed
    
    try:
        # Try to find existing user by oidc_sub (primary identifier)
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
            logger.info(f"Updated existing OIDC user: {email}")
        else:
            # Check if a user with this email or username exists (from local auth or previous setup)
            existing_user = conn.execute('''
                SELECT * FROM users WHERE email = ? OR username = ?
            ''', (email, username)).fetchone()
            
            if existing_user:
                # Update the existing user to link with OIDC
                logger.info(f"Linking existing user {email} to OIDC account")
                conn.execute('''
                    UPDATE users SET 
                        oidc_sub = ?, full_name = ?, 
                        is_admin = ?, last_login = ?
                    WHERE email = ? OR username = ?
                ''', (oidc_sub, full_name, is_admin, datetime.now().isoformat(), email, username))
            else:
                # Create new user
                logger.info(f"Creating new OIDC user: {email}")
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

def create_or_update_local_user(user_info):
    """Create or update a local user (non-OIDC)"""
    conn = get_db_connection()
    
    # Extract user information
    username = user_info['username']
    email = user_info['email']
    full_name = user_info['full_name']
    # Generate a pseudo oidc_sub for local users to maintain database compatibility
    oidc_sub = f"local_{username}"
    is_admin = False  # Simplified: no admin distinction for local users
    
    try:
        # Try to find existing user by username or email
        user = conn.execute('''
            SELECT * FROM users WHERE username = ? OR email = ? OR oidc_sub = ?
        ''', (username, email, oidc_sub)).fetchone()
        
        if user:
            # Update existing user
            conn.execute('''
                UPDATE users SET 
                    username = ?, email = ?, full_name = ?, 
                    is_admin = ?, last_login = ?, last_activity = ?
                WHERE id = ?
            ''', (username, email, full_name, is_admin, 
                  datetime.now().isoformat(), datetime.now().isoformat(), user['id']))
            logger.info(f"Updated local user: {username}")
        else:
            # Create new user
            conn.execute('''
                INSERT INTO users (username, email, full_name, is_admin, oidc_sub, last_login, created_at, last_activity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (username, email, full_name, is_admin, oidc_sub, 
                  datetime.now().isoformat(), datetime.now().isoformat(), datetime.now().isoformat()))
            logger.info(f"Created local user: {username}")
        
        conn.commit()
        
        # Return the user record
        user = conn.execute('''
            SELECT * FROM users WHERE oidc_sub = ?
        ''', (oidc_sub,)).fetchone()
        
        if not user:
            logger.error(f"User not found after creation/update with oidc_sub: {oidc_sub}")
            # Try alternative query as fallback
            user = conn.execute('''
                SELECT * FROM users WHERE username = ? AND email = ?
            ''', (username, email)).fetchone()
        
        conn.close()
        return user
        
    except Exception as e:
        conn.close()
        logger.error(f"Error creating/updating local user: {e}")
        raise