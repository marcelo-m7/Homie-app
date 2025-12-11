"""
Authentication utilities for Homie Flask application
"""
import secrets
import logging
from urllib.parse import urlencode, parse_qs, urlparse
from functools import wraps
from flask import session, request, redirect, url_for, jsonify, flash
import requests
from security import csrf_protect
from config import is_oidc_enabled

logger = logging.getLogger(__name__)

class AuthenticationError(Exception):
    """Custom exception for authentication errors"""
    pass

def generate_state():
    """Generate a random state for OIDC requests"""
    return secrets.token_urlsafe(32)

def generate_nonce():
    """Generate a random nonce for OIDC requests"""
    return secrets.token_urlsafe(32)

def build_authorization_url(oidc_config, state, nonce, base_url):
    """Build the OIDC authorization URL"""
    if not oidc_config:
        raise AuthenticationError("OIDC configuration not available")
    
    auth_params = {
        'response_type': 'code',
        'client_id': oidc_config['client_id'],
        'scope': 'openid profile email groups',  # Request groups scope
        'redirect_uri': f"{base_url}/auth/callback",
        'state': state,
        'nonce': nonce
    }
    
    return f"{oidc_config['authorization_endpoint']}?{urlencode(auth_params)}"

def exchange_code_for_token(oidc_config, code, base_url):
    """Exchange authorization code for access token"""
    if not oidc_config:
        raise AuthenticationError("OIDC configuration not available")
    
    token_data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': f"{base_url}/auth/callback",
        'client_id': oidc_config['client_id'],
        'client_secret': oidc_config['client_secret']
    }
    
    try:
        response = requests.post(
            oidc_config['token_endpoint'],
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Token exchange failed: {e}")
        raise AuthenticationError("Failed to exchange code for token")

def get_userinfo(oidc_config, access_token):
    """Get user information from OIDC provider"""
    if not oidc_config:
        raise AuthenticationError("OIDC configuration not available")
    
    try:
        response = requests.get(
            oidc_config['userinfo_endpoint'],
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Userinfo request failed: {e}")
        raise AuthenticationError("Failed to get user information")

def is_user_authorized(userinfo, access_control):
    """
    Check if user is authorized to access the application.
    Uses group-based authorization if ALLOWED_GROUPS is configured,
    otherwise falls back to email-based authorization.
    """
    # Priority 1: Check group membership if groups are configured
    if access_control.get('allowed_groups'):
        user_groups = userinfo.get('groups', [])
        
        # Normalize groups to a list (some OIDC providers return a string)
        if isinstance(user_groups, str):
            user_groups = [user_groups]
        
        # Check if user is in any of the allowed groups
        for group in user_groups:
            if group in access_control['allowed_groups']:
                logger.info(f"User authorized via group: {group}")
                return True
        
        logger.warning(f"User not in any allowed groups. User groups: {user_groups}")
        return False
    
    # Priority 2: Check email if emails are configured (and groups are not)
    if access_control.get('allowed_emails'):
        email = userinfo.get('email')
        if not email:
            logger.warning("User has no email in userinfo")
            return False
        
        if email in access_control['allowed_emails']:
            logger.info(f"User authorized via email: {email}")
            return True
        
        logger.warning(f"User email not in allowed list: {email}")
        return False
    
    # No access control configured - deny by default for security
    logger.warning("No access control configured (neither groups nor emails)")
    return False

def login_required(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            if is_oidc_enabled():
                return redirect(url_for('login'))
            else:
                # When OIDC is disabled, redirect to local login (to be implemented)
                return redirect(url_for('local_login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin privileges for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        
        user = session['user']
        if not user.get('is_admin', False):
            return redirect(url_for('unauthorized'))
        
        return f(*args, **kwargs)
    return decorated_function

def api_auth_required(f):
    """Decorator for API endpoints that require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

def feature_required(feature_name):
    """Decorator to require a specific feature to be enabled for the user"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                if is_oidc_enabled():
                    return redirect(url_for('login'))
                else:
                    return redirect(url_for('local_login'))
            
            # Import here to avoid circular imports
            from database import get_user_feature_visibility
            
            user_id = session['user']['id']
            
            # Check if user has access to this feature
            if not get_user_feature_visibility(user_id, feature_name):
                logger.warning(f"User {user_id} attempted to access disabled feature: {feature_name}")
                return redirect(url_for('unauthorized'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def validate_redirect_url(url, allowed_domains):
    """Validate that redirect URL is safe"""
    if not url:
        return False
    
    try:
        parsed = urlparse(url)
        
        # Only allow relative URLs or URLs from allowed domains
        if not parsed.netloc:
            return True  # Relative URL
        
        # Check if domain is in allowed list
        return parsed.netloc in allowed_domains
    except Exception:
        return False

def build_logout_url(oidc_config, base_url):
    """Build the OIDC logout URL"""
    if not oidc_config or not oidc_config.get('end_session_endpoint'):
        return None
    
    logout_params = {
        'post_logout_redirect_uri': base_url
    }
    
    return f"{oidc_config['end_session_endpoint']}?{urlencode(logout_params)}"

@csrf_protect
def clear_session():
    """Safely clear the user session"""
    session.pop('user', None)
    session.pop('oidc_state', None) 
    session.pop('oidc_nonce', None)
    session.pop('access_token', None)