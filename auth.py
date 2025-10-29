"""
Authentication module for Homie Flask application
Handles OIDC authentication, login/logout, and authorization
"""
import secrets
import requests
import base64
import json
import logging
from functools import wraps
from flask import session, request, redirect, url_for, flash, Blueprint, render_template
from urllib.parse import urlencode

from security import validate_redirect_url, log_security_event
from models import UserModel

logger = logging.getLogger(__name__)

# Create auth blueprint
auth_bp = Blueprint('auth', __name__)

def is_user_authorized(userinfo, config):
    """Check if user is authorized based on email or groups"""
    email = userinfo.get('email', '').lower()
    groups = userinfo.get('groups', [])
    
    # Convert groups to list if it's a string (some OIDC providers)
    if isinstance(groups, str):
        groups = [groups]
    
    # Check allowed emails
    if config.ALLOWED_EMAILS and email in [e.lower() for e in config.ALLOWED_EMAILS]:
        return True
    
    # Check allowed groups
    if config.ALLOWED_GROUPS and any(group in config.ALLOWED_GROUPS for group in groups):
        return True
    
    return False

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        
        # Update last activity
        user_model = UserModel(current_app.db)
        user_model.update_last_activity(session['user_id'])
        
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/login')
def login():
    """Initiate OIDC login"""
    from flask import current_app
    
    # Generate state and nonce for CSRF and replay protection
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    session['oauth_nonce'] = nonce
    
    # Build authorization URL - request groups if available
    params = {
        'client_id': current_app.config['OIDC_CONFIG']['client_id'],
        'response_type': 'code',
        'scope': 'openid profile email groups',  # Add groups scope
        'redirect_uri': current_app.config['OIDC_CONFIG']['redirect_uri'],
        'state': state,
        'nonce': nonce
    }
    
    auth_url = f"{current_app.config['OIDC_CONFIG']['authorization_endpoint']}?{urlencode(params)}"
    return redirect(auth_url)

@auth_bp.route('/auth/callback')
def oidc_callback():
    """Handle OIDC callback"""
    from flask import current_app
    
    # Verify state parameter
    if request.args.get('state') != session.get('oauth_state'):
        flash('Invalid authentication state. Please try again.', 'error')
        return redirect(url_for('auth.login'))
    
    # Check for error
    if 'error' in request.args:
        error_description = request.args.get('error_description', 'Authentication failed')
        flash(f'Authentication error: {error_description}', 'error')
        return redirect(url_for('auth.login'))
    
    # Get authorization code
    code = request.args.get('code')
    if not code:
        flash('No authorization code received', 'error')
        return redirect(url_for('auth.login'))
    
    try:
        # Exchange code for tokens
        token_data = {
            'grant_type': 'authorization_code',
            'client_id': current_app.config['OIDC_CONFIG']['client_id'],
            'client_secret': current_app.config['OIDC_CONFIG']['client_secret'],
            'code': code,
            'redirect_uri': current_app.config['OIDC_CONFIG']['redirect_uri']
        }
        
        token_response = requests.post(
            current_app.config['OIDC_CONFIG']['token_endpoint'],
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=10
        )
        token_response.raise_for_status()
        tokens = token_response.json()
        
        # Verify nonce in ID token (basic verification without full JWT validation)
        id_token = tokens.get('id_token')
        if id_token:
            try:
                # Simple base64 decode of JWT payload (not cryptographically verified)
                payload_part = id_token.split('.')[1]
                # Add padding if needed
                payload_part += '=' * (4 - len(payload_part) % 4)
                payload = json.loads(base64.b64decode(payload_part))
                
                # Verify nonce
                if payload.get('nonce') != session.get('oauth_nonce'):
                    log_security_event("invalid_nonce", "OIDC callback nonce mismatch")
                    flash('Authentication failed. Please try again.', 'error')
                    return redirect(url_for('auth.login'))
                    
            except Exception as e:
                logger.warning(f"Failed to verify nonce: {e}")
                # Continue anyway for compatibility, but log the issue
        
        # Get user info
        userinfo_response = requests.get(
            current_app.config['OIDC_CONFIG']['userinfo_endpoint'],
            headers={'Authorization': f'Bearer {tokens["access_token"]}'},
            timeout=10
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()
        
        # Debug: Print user info to see what groups are available
        logger.info(f"User info for {userinfo.get('email', 'unknown')}: {userinfo}")
        logger.info(f"Groups: {userinfo.get('groups', 'No groups key found')}")
        
        # Check if user is authorized
        if not is_user_authorized(userinfo, current_app.config['APP_CONFIG']):
            flash('You are not authorized to access this application', 'error')
            return redirect(url_for('auth.unauthorized'))
        
        # Get or create user
        user_model = UserModel(current_app.db)
        user = user_model.get_or_create_user(userinfo)
        
        # Set up session
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['email'] = user['email']
        session['is_admin'] = user['is_admin'] or user['email'].lower() in [e.lower() for e in current_app.config['APP_CONFIG'].ADMIN_EMAILS]
        
        # Clean up OAuth state
        session.pop('oauth_state', None)
        session.pop('oauth_nonce', None)
        
        flash('Welcome!', 'success')
        return redirect(url_for('main.index'))
        
    except requests.exceptions.RequestException as e:
        logger.error(f"OIDC callback error: {e}")
        flash('Authentication failed. Please try again.', 'error')
        return redirect(url_for('auth.login'))
    except Exception as e:
        logger.error(f"Unexpected error in OIDC callback: {e}")
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('auth.login'))

@auth_bp.route('/logout')
def logout():
    """Logout and redirect to OIDC logout if available"""
    from flask import current_app
    
    # Clear local session
    session.clear()
    flash('You have been logged out', 'info')
    
    # Redirect to OIDC logout if available
    oidc_config = current_app.config['OIDC_CONFIG']
    if oidc_config.get('end_session_endpoint'):
        # Validate redirect URL against allowed domains
        redirect_uri = request.url_root.rstrip('/') + url_for('auth.login')
        if validate_redirect_url(redirect_uri, current_app.config['APP_CONFIG'].ALLOWED_REDIRECT_DOMAINS):
            logout_params = {
                'post_logout_redirect_uri': redirect_uri
            }
            logout_url = f"{oidc_config['end_session_endpoint']}?{urlencode(logout_params)}"
            return redirect(logout_url)
        else:
            log_security_event("invalid_redirect_attempt", f"URL: {redirect_uri}")
            # Fall back to safe redirect
    
    return redirect(url_for('auth.login'))

@auth_bp.route('/unauthorized')
def unauthorized():
    """Unauthorized access page"""
    return render_template('unauthorized.html'), 403