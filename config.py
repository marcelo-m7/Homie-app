"""
Configuration utilities for Homie Flask application
"""
import os
import json
import logging
import requests
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

def get_oidc_configuration():
    """Get OIDC configuration with auto-discovery"""
    try:
        oidc_base_url = os.getenv('OIDC_BASE_URL')
        if not oidc_base_url:
            logger.error("OIDC_BASE_URL environment variable is required")
            return None
        
        discovery_url = urljoin(oidc_base_url, '/.well-known/openid_configuration')
        response = requests.get(discovery_url, timeout=10)
        response.raise_for_status()
        
        config = response.json()
        
        return {
            'issuer': config['issuer'],
            'authorization_endpoint': config['authorization_endpoint'],
            'token_endpoint': config['token_endpoint'],
            'userinfo_endpoint': config['userinfo_endpoint'],
            'jwks_uri': config['jwks_uri'],
            'end_session_endpoint': config.get('end_session_endpoint', ''),
            'scopes_supported': config.get('scopes_supported', ['openid', 'profile', 'email']),
        }
    except Exception as e:
        logger.error(f"Failed to fetch OIDC configuration: {e}")
        return None

def load_access_control():
    """Load access control configuration"""
    config = {
        'admin_emails': [],
        'allowed_emails': []
    }
    
    # Load from environment variables
    admin_emails_str = os.getenv('ADMIN_EMAILS', '')
    if admin_emails_str:
        config['admin_emails'] = [email.strip() for email in admin_emails_str.split(',')]
    
    allowed_emails_str = os.getenv('ALLOWED_EMAILS', '')
    if allowed_emails_str:
        config['allowed_emails'] = [email.strip() for email in allowed_emails_str.split(',')]
    
    # If no allowed emails specified, use admin emails
    if not config['allowed_emails']:
        config['allowed_emails'] = config['admin_emails']
    
    return config

def get_app_config():
    """Get Flask application configuration"""
    return {
        'SECRET_KEY': os.getenv('SECRET_KEY', 'dev-key-change-in-production'),
        'OIDC_CLIENT_ID': os.getenv('OIDC_CLIENT_ID', ''),
        'OIDC_CLIENT_SECRET': os.getenv('OIDC_CLIENT_SECRET', ''),
        'OIDC_BASE_URL': os.getenv('OIDC_BASE_URL', ''),
        'BASE_URL': os.getenv('BASE_URL', 'http://localhost:5000'),
        'RATELIMIT_STORAGE_URI': 'memory://',  # Use Redis in production
        'SESSION_COOKIE_SECURE': os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true',
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SAMESITE': 'Lax',
        'PERMANENT_SESSION_LIFETIME': 3600,  # 1 hour
        'MAX_CONTENT_LENGTH': 16 * 1024 * 1024,  # 16MB max upload
        'DEBUG': os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
    }

def setup_logging():
    """Setup application logging"""
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format
    )
    
    # Set specific logger levels
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)