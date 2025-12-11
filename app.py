"""
Homie - Family Utility App (Refactored)
Main application module using modular architecture
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Import our custom modules
from config import get_app_config, get_oidc_configuration, load_access_control, setup_logging, load_local_users, get_currency_symbol
from database import init_db, get_dashboard_stats, get_recent_activities
from authentication import (
    login_required, admin_required, generate_state, generate_nonce,
    build_authorization_url, exchange_code_for_token, get_userinfo,
    is_user_authorized, validate_redirect_url, build_logout_url, clear_session
)
from security import csrf_protect, generate_csrf_token, sanitize_input

# Import route blueprints  
from routes.shopping import shopping_bp

import logging
import os

logger = logging.getLogger(__name__)

def create_app():
    """Application factory"""
    # Initialize Flask app
    app = Flask(__name__)
    
    # Setup logging first
    setup_logging()
    
    # Load configuration
    app_config = get_app_config()
    app.config.update(app_config)
    
    # Initialize rate limiting
    limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["1000 per hour"])
    
    # Initialize database
    init_db()
    
    # Load runtime configuration
    oidc_config = get_oidc_configuration()
    access_control = load_access_control()
    
    # Template context processor
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf_token)
    
    # Template context processor for currency symbol
    @app.context_processor
    def inject_currency():
        return dict(currency=get_currency_symbol())
    
    # Template context processor for user features
    @app.context_processor
    def inject_user_features():
        """Inject user's feature visibility settings into templates"""
        if 'user' in session:
            from database import get_all_user_features
            try:
                user_features = get_all_user_features(session['user']['id'])
                return dict(user_features=user_features)
            except Exception as e:
                logger.error(f"Error loading user features: {e}")
                # Return all features visible as fallback
                return dict(user_features={
                    'shopping': True,
                    'chores': True,
                    'tracker': True,
                    'bills': True,
                    'budget': True
                })
        return dict(user_features={})
    
    # Add custom Jinja filters
    @app.template_filter('title_case')
    def title_case_filter(text):
        """Convert text to title case"""
        if not text:
            return text
        return ' '.join(word.capitalize() for word in str(text).split())
    
    @app.template_filter('format_date')
    def format_date_filter(date_string, format_str='%B %d, %Y'):
        """Format date string for display"""
        if not date_string:
            return ''
        try:
            from datetime import datetime
            # Handle different input formats
            if isinstance(date_string, str):
                # Try parsing common formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']:
                    try:
                        dt = datetime.strptime(date_string, fmt)
                        return dt.strftime(format_str)
                    except ValueError:
                        continue
            return str(date_string)
        except Exception:
            return str(date_string) if date_string else ''
    
    # ===== ERROR HANDLERS =====
    
    @app.errorhandler(403)
    def forbidden_error(error):
        logger.warning(f"403 Forbidden: {request.remote_addr} - {request.url}")
        return render_template('unauthorized.html'), 403
    
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('base.html', error="Page not found"), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"500 Internal Error: {error}")
        return render_template('base.html', error="Internal server error"), 500
    
    # ===== AUTHENTICATION ROUTES =====
    
    @app.route('/login')
    def login():
        """Initiate authentication (OIDC or local)"""
        if 'user' in session:
            return redirect(url_for('dashboard'))
        
        # Check if OIDC is enabled
        if not app_config['OIDC_ENABLED']:
            # Redirect to local login for user selection
            return redirect(url_for('local_login'))
        
        # OIDC Authentication
        if not oidc_config:
            flash('Authentication service is not configured', 'error')
            return render_template('login.html', oidc_enabled=True)
        
        # Generate state and nonce for security
        state = generate_state()
        nonce = generate_nonce()
        
        # Store in session for validation
        session['oidc_state'] = state
        session['oidc_nonce'] = nonce
        
        # Build authorization URL
        try:
            auth_url = build_authorization_url(
                oidc_config, state, nonce, app_config['BASE_URL']
            )
            return redirect(auth_url)
        except Exception as e:
            logger.error(f"Failed to build authorization URL: {e}")
            flash('Authentication failed', 'error')
            return render_template('login.html', oidc_enabled=True)
    
    @app.route('/auth/callback')
    @limiter.limit("10 per minute")
    def auth_callback():
        """Handle OIDC callback"""
        # Check if OIDC is enabled
        if not app_config['OIDC_ENABLED']:
            flash('OIDC authentication is disabled', 'error')
            return redirect(url_for('login'))
        
        # Validate state parameter
        state = request.args.get('state')
        session_state = session.get('oidc_state')
        
        logger.info(f"Callback received - State: {state[:10] if state else 'None'}..., Session state: {session_state[:10] if session_state else 'None'}...")
        
        if not state or state != session_state:
            if not state:
                logger.warning(f"No state parameter in callback: {request.remote_addr}")
                flash('Missing authentication state parameter', 'error')
            elif not session_state:
                logger.warning(f"No state in session during callback: {request.remote_addr}")
                flash('Session expired during authentication', 'error')
            else:
                logger.warning(f"State mismatch in callback: {request.remote_addr}")
                flash('Authentication state mismatch', 'error')
            return redirect(url_for('login'))
        
        # Get authorization code
        code = request.args.get('code')
        if not code:
            error = request.args.get('error', 'Unknown error')
            logger.warning(f"Authentication error: {error}")
            flash('Authentication failed', 'error')
            return redirect(url_for('login'))
        
        try:
            # Exchange code for token
            token_response = exchange_code_for_token(
                oidc_config, code, app_config['BASE_URL']
            )
            access_token = token_response.get('access_token')
            
            if not access_token:
                flash('Failed to obtain access token', 'error')
                return redirect(url_for('login'))
            
            # Get user information
            userinfo = get_userinfo(oidc_config, access_token)
            
            # Check authorization
            if not is_user_authorized(userinfo, access_control):
                logger.warning(f"Unauthorized access attempt: {userinfo.get('email', 'unknown')}")
                return render_template('unauthorized.html')
            
            # Create/update user and store in session
            from database import create_or_update_user
            user = create_or_update_user(userinfo, access_control)
            
            session['user'] = {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'full_name': user['full_name'],
                'is_admin': user['is_admin']
            }
            session['access_token'] = access_token
            
            # Clean up temporary session data
            session.pop('oidc_state', None)
            session.pop('oidc_nonce', None)
            
            logger.info(f"User logged in: {user['email']}")
            
            # Redirect to originally requested page or dashboard
            next_page = session.get('next_page', url_for('dashboard'))
            session.pop('next_page', None)
            
            if validate_redirect_url(next_page, access_control['allowed_domains']):
                return redirect(next_page)
            else:
                return redirect(url_for('dashboard'))
        
        except Exception as e:
            logger.error(f"Authentication callback failed: {e}")
            flash('Authentication failed', 'error')
            return redirect(url_for('login'))
    
    @app.route('/logout')
    @csrf_protect
    def logout():
        """Handle user logout"""
        # Clear session
        clear_session()
        
        flash('You have been logged out', 'info')
        
        # Build OIDC logout URL if OIDC is enabled and available
        if app_config['OIDC_ENABLED'] and oidc_config:
            logout_url = build_logout_url(oidc_config, app_config['BASE_URL'])
            if logout_url:
                return redirect(logout_url)
        
        # Redirect to login page
        return redirect(url_for('login'))
    
    @app.route('/local_login')
    def local_login():
        """Local authentication login page with user selection"""
        if 'user' in session:
            return redirect(url_for('dashboard'))
        
        local_users = load_local_users()
        # Ensure CSRF token is generated for the session
        generate_csrf_token()
        
        return render_template('login.html', 
                             oidc_enabled=False, 
                             local_mode=True, 
                             local_users=local_users)
    
    @app.route('/local_login_auth', methods=['POST'])
    @csrf_protect
    def local_login_auth():
        """Handle local user authentication"""
        if 'user' in session:
            return redirect(url_for('dashboard'))
        
        username = request.form.get('username')
        if not username:
            flash('Invalid user selection', 'error')
            return redirect(url_for('local_login'))
        
        # Find the user in the local users list
        local_users = load_local_users()
        selected_user = None
        for user in local_users:
            if user['username'] == username:
                selected_user = user
                break
        
        if not selected_user:
            flash('User not found', 'error')
            return redirect(url_for('local_login'))
        
        # Create/update user in database and create session
        from database import create_or_update_local_user
        user = create_or_update_local_user(selected_user)
        
        if not user:
            logger.error(f"Failed to create/update local user: {selected_user}")
            flash('Login failed - user could not be created', 'error')
            return redirect(url_for('local_login'))
        
        session['user'] = {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'full_name': user['full_name'],
            'is_admin': user['is_admin']
        }
        
        logger.info(f"Local user logged in: {user['email']}")
        
        flash(f'Welcome, {user["full_name"]}!', 'success')
        return redirect(url_for('dashboard'))
    
    # ===== MAIN ROUTES =====
    
    @app.route('/')
    def index():
        """Home page - redirect to dashboard or login"""
        if 'user' in session:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))
    
    @app.route('/dashboard')
    @login_required
    def dashboard():
        """Main dashboard page"""
        try:
            stats = get_dashboard_stats()
            recent_activities = get_recent_activities(limit=5)
            return render_template('dashboard.html', recent_activities=recent_activities, **stats)
        except Exception as e:
            logger.error(f"Dashboard error: {e}")
            flash('Error loading dashboard', 'error')
            return render_template('dashboard.html', shopping_count=0, chores_count=0, expiring_count=0, monthly_total=0, recent_activities=[])
    
    @app.route('/unauthorized')
    def unauthorized():
        """Unauthorized access page"""
        return render_template('unauthorized.html')
    
    # ===== STATIC ROUTES =====
    
    @app.route('/manifest.json')
    def manifest():
        """Serve PWA manifest"""
        return send_from_directory('static', 'manifest.json')
    
    # ===== REGISTER BLUEPRINTS =====
    
    # Register route modules
    app.register_blueprint(shopping_bp)
    
    from routes.chores import chores_bp
    from routes.bills import bills_bp 
    from routes.expiry import expiry_bp
    from routes.admin import admin_bp
    app.register_blueprint(chores_bp)
    app.register_blueprint(bills_bp)
    app.register_blueprint(expiry_bp)
    app.register_blueprint(admin_bp)
    
    return app

# Create the application
app = create_app()

if __name__ == '__main__':
    # Development server
    app.run(debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true', 
            host='0.0.0.0', port=int(os.getenv('PORT', '5000')))