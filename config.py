"""
Configuration utilities for Homie Flask application
"""
import os
import json
import logging
import requests
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

def is_oidc_enabled():
    """Check if OIDC authentication is enabled"""
    return os.getenv('OIDC_ENABLED', 'true').lower() == 'true'

def get_oidc_configuration():
    """Get OIDC configuration with auto-discovery"""
    # Check if OIDC is enabled
    if not is_oidc_enabled():
        logger.info("OIDC authentication is disabled")
        return None
        
    oidc_base_url = os.getenv('OIDC_BASE_URL')
    if not oidc_base_url:
        logger.error("OIDC_BASE_URL environment variable is required when OIDC is enabled")
        return None
    
    # Build complete OIDC config with client credentials
    config = {
        'client_id': os.getenv('OIDC_CLIENT_ID', ''),
        'client_secret': os.getenv('OIDC_CLIENT_SECRET', ''),
    }
    
    # Try auto-discovery first - try both common endpoint variations
    discovery_endpoints = [
        '/.well-known/openid_configuration',  # Standard endpoint (underscore)
        '/.well-known/openid-configuration'   # Alternative endpoint (hyphen)
    ]
    
    discovery_errors = []  # Collect errors to log only if all attempts fail
    
    for endpoint in discovery_endpoints:
        try:
            discovery_url = urljoin(oidc_base_url, endpoint)
            logger.info(f"Attempting OIDC discovery at: {discovery_url}")
            
            response = requests.get(discovery_url, timeout=10)
            response.raise_for_status()
            
            # Check if response has content
            if not response.text.strip():
                discovery_errors.append(f"Empty response from {discovery_url}")
                continue  # Try next endpoint
            
            try:
                discovered_config = response.json()
            except json.JSONDecodeError as e:
                discovery_errors.append(f"Invalid JSON from {discovery_url}: {e}")
                continue  # Try next endpoint
            
            # Validate required fields
            required_fields = ['issuer', 'authorization_endpoint', 'token_endpoint', 'userinfo_endpoint']
            missing_fields = [field for field in required_fields if field not in discovered_config]
            
            if missing_fields:
                discovery_errors.append(f"Missing required OIDC fields from {discovery_url}: {missing_fields}")
                continue  # Try next endpoint
            
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
            
            logger.info(f"OIDC auto-discovery successful from: {discovery_url}")
            return config
            
        except requests.RequestException as e:
            discovery_errors.append(f"Network error from {discovery_url}: {e}")
            continue  # Try next endpoint
        except Exception as e:
            discovery_errors.append(f"Unexpected error from {discovery_url}: {e}")
            continue  # Try next endpoint
    
    # If we reach here, all discovery attempts failed - now log the errors
    logger.warning("All OIDC auto-discovery endpoints failed")
    for error in discovery_errors:
        logger.warning(f"Discovery error: {error}")
    
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
        'allowed_emails': []
    }
    
    # Load from environment variables
    allowed_emails_str = os.getenv('ALLOWED_EMAILS', '')
    if allowed_emails_str:
        config['allowed_emails'] = [email.strip() for email in allowed_emails_str.split(',')]
    
    # Add allowed domains for redirect validation
    base_url = os.getenv('BASE_URL', 'http://localhost:5000')
    parsed_base = base_url.replace('http://', '').replace('https://', '')
    config['allowed_domains'] = [
        'localhost:5000',
        '127.0.0.1:5000',
        parsed_base
    ]
    
    return config

def load_local_users():
    """Load local users configuration for non-OIDC authentication"""
    users = []
    users_str = os.getenv('USERS', '')
    
    if users_str:
        user_entries = [entry.strip() for entry in users_str.split(',')]
        
        for entry in user_entries:
            entry = entry.strip()
            if not entry:
                continue
                
            if ':' in entry:
                # Full format: "username:email:Full Name" or "username:email"
                parts = entry.split(':', 2)
                if len(parts) >= 2:
                    username = parts[0].strip()
                    email = parts[1].strip()
                    full_name = parts[2].strip() if len(parts) > 2 else username.title()
                    
                    if username and email:
                        users.append({
                            'username': username.lower(),
                            'email': email,
                            'full_name': full_name
                        })
                    else:
                        logger.warning(f"Invalid user entry (missing username or email): {entry}")
                else:
                    logger.warning(f"Invalid user entry format: {entry}")
            else:
                # Simple format: just the name
                name = entry.strip()
                if name:
                    username = name.lower()
                    email = f"{username}@local.homie"  # Generate a local email
                    users.append({
                        'username': username,
                        'email': email,
                        'full_name': name
                    })
    
    logger.info(f"Loaded {len(users)} local users")
    return users

def get_currency_symbol():
    """Get the currency symbol to use in the application"""
    return os.getenv('CURRENCY', '£')

def get_app_config():
    """Get Flask application configuration"""
    return {
        'SECRET_KEY': os.getenv('SECRET_KEY', 'dev-key-change-in-production'),
        'OIDC_ENABLED': is_oidc_enabled(),
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