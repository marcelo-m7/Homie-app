"""
Security utilities for Homie Flask application
Handles CSRF protection, input validation, and other security measures
"""
import secrets
import logging
from functools import wraps
from flask import session, request, jsonify, abort, current_app
from urllib.parse import urlparse

# Import bleach with fallback for local development
try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False
    logging.warning("bleach not available - HTML sanitization will use basic escaping")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_csrf_token():
    """Generate a CSRF token for the session"""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return session['_csrf_token']

def validate_csrf_token(token):
    """Validate CSRF token against session token"""
    return token and session.get('_csrf_token') and \
           secrets.compare_digest(session['_csrf_token'], token)

def csrf_protect(f):
    """Decorator to protect routes against CSRF attacks"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            # Try to get token from header first (for AJAX requests)
            token = request.headers.get('X-CSRF-Token')
            
            # If not in header, try form data (for regular form submissions)
            if not token:
                token = request.form.get('csrf_token')
            
            # If still no token, try JSON data
            if not token and request.is_json:
                token = request.get_json().get('csrf_token') if request.get_json() else None
            
            if not validate_csrf_token(token):
                logger.warning(f"CSRF token validation failed for {request.endpoint}")
                abort(403, description="CSRF token validation failed")
        return f(*args, **kwargs)
    return decorated_function

def sanitize_html_input(text):
    """Sanitize HTML input to prevent XSS"""
    if not text:
        return text
    
    if BLEACH_AVAILABLE:
        # Allow minimal safe tags, strip everything else
        allowed_tags = ['b', 'i', 'em', 'strong']
        return bleach.clean(text, tags=allowed_tags, strip=True)
    else:
        # Fallback: escape HTML entities
        import html
        return html.escape(text)

def sanitize_input(text):
    """Sanitize text input by stripping HTML and normalizing"""
    if not text:
        return text
    
    if BLEACH_AVAILABLE:
        # Strip all HTML tags and normalize whitespace
        clean_text = bleach.clean(text, tags=[], strip=True)
        return ' '.join(clean_text.split())
    else:
        # Fallback: basic cleaning without HTML stripping
        import html
        escaped = html.escape(text)
        return ' '.join(escaped.split())

def validate_redirect_url(url, allowed_domains):
    """Validate redirect URL against allowed domains"""
    try:
        parsed = urlparse(url)
        if not parsed.netloc:  # Relative URL is OK
            return True
        return parsed.netloc in allowed_domains
    except Exception:
        return False

def check_ownership(conn, table, item_id, user_id, id_column='id', user_column='added_by'):
    """Check if user owns the specified item"""
    query = f"SELECT 1 FROM {table} WHERE {id_column} = ? AND {user_column} = ?"
    result = conn.execute(query, (item_id, user_id)).fetchone()
    return result is not None

def safe_delete_item(conn, table, item_id, user_id, id_column='id', user_column='added_by'):
    """Safely delete an item with ownership check"""
    if not check_ownership(conn, table, item_id, user_id, id_column, user_column):
        return False
    
    query = f"DELETE FROM {table} WHERE {id_column} = ? AND {user_column} = ?"
    result = conn.execute(query, (item_id, user_id))
    return result.rowcount > 0

def validate_ownership(conn, table, item_id, user):
    """Validate that user owns item or is admin"""
    # Admins can access anything
    if user.get('is_admin', False):
        return True
    
    # Check if user owns the item
    return check_ownership(conn, table, item_id, user['id'])

def log_security_event(event_type, details, user_id=None):
    """Log security-related events"""
    logger.warning(f"Security Event: {event_type} - User: {user_id} - Details: {details}")

class SecurityError(Exception):
    """Custom exception for security-related errors"""
    pass