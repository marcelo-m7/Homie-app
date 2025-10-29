# Homie - Modular Flask Application

This Flask application has been refactored into a modular architecture for better maintainability and organization.

## Project Structure

```
homie/
├── app.py                  # Main application factory and core routes
├── config.py               # Configuration management and OIDC discovery
├── database.py             # Database utilities and initialization
├── authentication.py       # Authentication decorators and OIDC handling
├── security.py            # Security utilities (CSRF, validation, sanitization)
├── routes/
│   ├── __init__.py        # Routes package
│   ├── shopping.py        # Shopping list routes
│   ├── chores.py          # Chores management routes  
│   ├── bills.py           # Bills tracking routes
│   └── expiry.py          # Expiry tracker routes
├── templates/             # HTML templates
├── static/                # Static assets
├── requirements.txt       # Python dependencies
└── Dockerfile            # Container configuration
```

## Modules Overview

### `app.py` (Main Application)
- Application factory pattern using `create_app()`
- Core authentication routes (`/login`, `/auth/callback`, `/logout`)
- Main routes (`/`, `/dashboard`, `/unauthorized`)
- Error handlers
- Blueprint registration

### `config.py` (Configuration)
- `get_oidc_configuration()` - OIDC auto-discovery
- `load_access_control()` - User authorization settings
- `get_app_config()` - Flask application configuration
- `setup_logging()` - Logging configuration

### `database.py` (Database Layer)
- `init_db()` - Database initialization and migrations
- `get_db_connection()` - Database connection management
- `get_dashboard_stats()` - Dashboard statistics
- `create_or_update_user()` - User management

### `authentication.py` (Authentication)
- Authentication decorators (`@login_required`, `@admin_required`, `@api_auth_required`)
- OIDC flow functions (authorization URL building, token exchange, userinfo)
- Session management utilities
- Authorization validation

### `security.py` (Security)
- CSRF protection (`@csrf_protect` decorator)
- Input sanitization (`sanitize_input()`)
- Ownership validation (`validate_ownership()`)
- HTML sanitization and security logging

### `routes/` (Route Modules)
Each route module follows the same pattern:
- Blueprint creation
- Route definitions with appropriate decorators
- API endpoints for CRUD operations
- Error handling and logging

## Key Features

### Security
- CSRF protection on all state-changing operations
- Input sanitization and validation
- Rate limiting on authentication endpoints
- Secure session management
- Ownership validation for data access

### Authentication
- OIDC integration with auto-discovery
- Session-based authentication
- Role-based access control (admin/user)
- Secure logout with OIDC provider

### Modularity
- Clean separation of concerns
- Reusable components
- Blueprint-based route organization
- Configurable through environment variables

## Environment Variables

Required:
- `SECRET_KEY` - Flask secret key
- `OIDC_BASE_URL` - OIDC provider base URL (used for auto-discovery)
- `OIDC_CLIENT_ID` - OIDC client identifier
- `OIDC_CLIENT_SECRET` - OIDC client secret
- `ALLOWED_EMAILS` - Comma-separated list of allowed user emails

Optional:
- `ADMIN_EMAILS` - Comma-separated list of admin emails
- `BASE_URL` - Application base URL (default: http://localhost:5000)
- `LOG_LEVEL` - Logging level (default: INFO)
- `FLASK_DEBUG` - Enable debug mode (default: False)

## Running the Application

### Development
```bash
python app.py
```

### Production (Docker)
```bash
docker-compose up --build
```

## Security Improvements Included

1. **SQL Injection Prevention** - Parameterized queries throughout
2. **CSRF Protection** - Token-based protection on state changes
3. **XSS Prevention** - HTML input sanitization
4. **Secure Sessions** - HTTPOnly, Secure, SameSite cookies
5. **Rate Limiting** - Protection against brute force attacks
6. **Input Validation** - Comprehensive data validation
7. **Error Handling** - Secure error responses
8. **Access Control** - Ownership validation and authorization
9. **OIDC Security** - Nonce validation and state verification
10. **Database Security** - Proper file permissions and initialization