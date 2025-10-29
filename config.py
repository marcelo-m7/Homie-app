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
    oidc_base_url = os.getenv('OIDC_BASE_URL')
    if not oidc_base_url:
        logger.error("OIDC_BASE_URL environment variable is required")
        return None
    
    # Build complete OIDC config with client credentials
    config = {
        'client_id': os.getenv('OIDC_CLIENT_ID', ''),
        'client_secret': os.getenv('OIDC_CLIENT_SECRET', ''),
    }
    
    # Try auto-discovery first
    try:
        discovery_url = urljoin(oidc_base_url, '/.well-known/openid_configuration')
        logger.info(f"Attempting OIDC discovery at: {discovery_url}")
        
        response = requests.get(discovery_url, timeout=10)
        response.raise_for_status()
        
        # Check if response has content
        if not response.text.strip():
            raise ValueError("Empty response from OIDC discovery endpoint")
        
        try:
            discovered_config = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from OIDC discovery endpoint. Response: {response.text[:200]}")
            raise ValueError(f"Invalid JSON response: {e}")
        
        # Validate required fields
        required_fields = ['issuer', 'authorization_endpoint', 'token_endpoint', 'userinfo_endpoint']
        missing_fields = [field for field in required_fields if field not in discovered_config]
        
        if missing_fields:
            raise ValueError(f"Missing required OIDC fields: {missing_fields}")
        
        # Use discovered endpoints
        config.update({
            'issuer': discovered_config['issuer'],
            'authorization_endpoint': discovered_config['authorization_endpoint'],
            'token_endpoint': discovered_config['token_endpoint'],
            'userinfo_endpoint': discovered_config['userinfo_endpoint'],
            'jwks_uri': discovered_config.get('jwks_uri', ''),
            'end_session_endpoint': discovered_config.get('end_session_endpoint', ''),
            'scopes_supported': discovered_config.get('scopes_supported', ['openid', 'profile', 'email']),
        })
        
        logger.info("OIDC auto-discovery successful")
        return config
        
    except requests.RequestException as e:
        logger.warning(f"OIDC auto-discovery failed (network error): {e}")
    except ValueError as e:
        logger.warning(f"OIDC auto-discovery failed (invalid response): {e}")
    except Exception as e:
        logger.warning(f"OIDC auto-discovery failed (unexpected error): {e}")
    
    # Fallback to manual configuration
    logger.info("Falling back to manual OIDC endpoint configuration")
    
    manual_config = {
        'issuer': os.getenv('OIDC_ISSUER', oidc_base_url),
        'authorization_endpoint': os.getenv('OIDC_AUTHORIZATION_ENDPOINT'),
        'token_endpoint': os.getenv('OIDC_TOKEN_ENDPOINT'),
        'userinfo_endpoint': os.getenv('OIDC_USERINFO_ENDPOINT'),
        'jwks_uri': os.getenv('OIDC_JWKS_URI', ''),
        'end_session_endpoint': os.getenv('OIDC_END_SESSION_ENDPOINT', ''),
        'scopes_supported': ['openid', 'profile', 'email'],
    }
    
    config.update(manual_config)
    
    # Validate that we have the minimum required endpoints
    required_endpoints = ['authorization_endpoint', 'token_endpoint', 'userinfo_endpoint']
    missing_endpoints = [ep for ep in required_endpoints if not config.get(ep)]
    
    if missing_endpoints:
        logger.error(f"Missing required OIDC endpoints: {missing_endpoints}")
        logger.error("Please set the following environment variables:")
        for ep in missing_endpoints:
            env_var = f"OIDC_{ep.upper()}"
            logger.error(f"  - {env_var}")
        return None
    
    logger.info("Manual OIDC configuration loaded successfully")
    return config

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