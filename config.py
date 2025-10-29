"""
Configuration module for Homie Flask application
Handles OIDC discovery, app configuration, and environment setup
"""
import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def discover_oidc_endpoints(issuer):
    """Auto-discover OIDC endpoints from issuer's well-known configuration"""
    try:
        well_known_url = f"{issuer}/.well-known/openid-configuration"
        response = requests.get(well_known_url, timeout=10)
        response.raise_for_status()
        config = response.json()
        
        return {
            'authorization_endpoint': config.get('authorization_endpoint'),
            'token_endpoint': config.get('token_endpoint'),
            'userinfo_endpoint': config.get('userinfo_endpoint'),
            'end_session_endpoint': config.get('end_session_endpoint'),
        }
    except Exception as e:
        print(f"Failed to discover OIDC endpoints: {e}")
        # Fallback to manual configuration
        return {
            'authorization_endpoint': os.getenv('OIDC_AUTHORIZATION_ENDPOINT'),
            'token_endpoint': os.getenv('OIDC_TOKEN_ENDPOINT'),
            'userinfo_endpoint': os.getenv('OIDC_USERINFO_ENDPOINT'),
            'end_session_endpoint': os.getenv('OIDC_END_SESSION_ENDPOINT'),
        }

class Config:
    """Application configuration class"""
    
    # Flask Configuration
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY')
    SESSION_COOKIE_SECURE = os.getenv('FLASK_ENV') == 'production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Database Configuration
    DATABASE_PATH = '/app/data/homie.db'
    
    # OIDC Configuration
    OIDC_ISSUER = os.getenv('OIDC_ISSUER')
    OIDC_CLIENT_ID = os.getenv('OIDC_CLIENT_ID')
    OIDC_CLIENT_SECRET = os.getenv('OIDC_CLIENT_SECRET')
    OIDC_REDIRECT_URI = os.getenv('OIDC_REDIRECT_URI')
    
    # Access Control
    ALLOWED_EMAILS = [email.strip() for email in os.getenv('ALLOWED_EMAILS', '').split(',') if email.strip()]
    ALLOWED_GROUPS = [group.strip() for group in os.getenv('ALLOWED_GROUPS', '').split(',') if group.strip()]
    ADMIN_EMAILS = [email.strip() for email in os.getenv('ADMIN_EMAILS', '').split(',') if email.strip()]
    
    # Security Configuration
    ALLOWED_REDIRECT_DOMAINS = [
        'localhost:5000',
        '127.0.0.1:5000',
        os.getenv('ALLOWED_DOMAIN', 'localhost:5000')
    ]
    
    # Rate Limiting
    RATELIMIT_DEFAULTS = ["1000 per hour"]
    
    @property
    def oidc_endpoints(self):
        """Get OIDC endpoints (discovered or manual)"""
        if self.OIDC_ISSUER:
            return discover_oidc_endpoints(self.OIDC_ISSUER)
        return {}
    
    @property
    def oidc_config(self):
        """Complete OIDC configuration"""
        return {
            'client_id': self.OIDC_CLIENT_ID,
            'client_secret': self.OIDC_CLIENT_SECRET,
            'issuer': self.OIDC_ISSUER,
            'redirect_uri': self.OIDC_REDIRECT_URI,
            **self.oidc_endpoints
        }
    
    def configure_app(self, app):
        """Apply configuration to Flask app"""
        app.secret_key = self.SECRET_KEY
        app.config['SESSION_COOKIE_SECURE'] = self.SESSION_COOKIE_SECURE
        app.config['SESSION_COOKIE_HTTPONLY'] = self.SESSION_COOKIE_HTTPONLY
        app.config['SESSION_COOKIE_SAMESITE'] = self.SESSION_COOKIE_SAMESITE
        return app