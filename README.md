# This project is very unstable and may be subject to breaking changes. 
# Homie 🏠

A simple family utility app for managing household tasks with OIDC authentication.

## Features

- 🛒 **Shopping List** - Collaborative family shopping
- 🧹 **Chores** - Track household tasks  
- 📅 **Expiry Tracker** - Monitor food expiration dates (30-day alerts)
- 💳 **Bills** - Manage monthly bills and costs
- 🔐 **OIDC Auth** - Group-based access control
- 📱 **Mobile Friendly** - Responsive design

## Showcase

<img width="1281" height="676" alt="image" src="https://github.com/user-attachments/assets/07cf8647-6d5f-420f-ab0e-2c7bf55b7265" />

<img width="1317" height="795" alt="image" src="https://github.com/user-attachments/assets/a14bf3cc-52e5-428c-9a63-4b9be12af3a7" />

## 🚀 Quick Start with Docker (Recommended)

1. **Download the compose file:**
   ```bash
   curl -o compose.yml https://raw.githubusercontent.com/Brramble/homie/main/compose.yml
   ```

2. **Edit environment variables:**
   Open `compose.yml` and update these required values:
   
   ```yaml
   # Security - REQUIRED: Change this to a secure random string
   - FLASK_SECRET_KEY=your-very-secure-secret-key-here-change-this
   
   # OIDC Authentication - REQUIRED: Replace with your provider details
   - OIDC_BASE_URL=https://your-oidc-provider.com
   - OIDC_CLIENT_ID=your-client-id
   - OIDC_CLIENT_SECRET=your-client-secret
   - OIDC_REDIRECT_URI=http://localhost:5000/auth/callback
   
   # Access Control - REQUIRED: Set allowed users/groups
   - ALLOWED_EMAILS=user1@example.com,user2@example.com
   - ALLOWED_GROUPS=family,admins
   - ADMIN_EMAILS=admin@example.com
   ```

3. **Start the application:**
   ```bash
   docker compose up -d
   ```

4. **Visit:** `http://localhost:5000`

## 🔧 Configuration Details

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `FLASK_SECRET_KEY` | Secure random key for sessions | `super-secret-key-123` |
| `OIDC_BASE_URL` | Your OIDC provider's base URL | `https://auth.provider.com` |
| `OIDC_CLIENT_ID` | OAuth client ID | `homie-app-client` |
| `OIDC_CLIENT_SECRET` | OAuth client secret | `secret123` |
| `OIDC_REDIRECT_URI` | Callback URL | `http://localhost:5000/auth/callback` |

### Access Control Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ALLOWED_EMAILS` | Comma-separated list of allowed emails | `user1@example.com,user2@example.com` |
| `ALLOWED_GROUPS` | Comma-separated list of allowed OIDC groups | `family,household` |
| `ADMIN_EMAILS` | Comma-separated list of admin emails | `admin@example.com` |

### Manual OIDC Endpoints (Fallback)
If auto-discovery fails, you can set these manually:

| Variable | Description | Example |
|----------|-------------|---------|
| `OIDC_ISSUER` | OIDC issuer identifier | `https://auth.provider.com` |
| `OIDC_AUTHORIZATION_ENDPOINT` | Authorization endpoint | `https://auth.provider.com/auth` |
| `OIDC_TOKEN_ENDPOINT` | Token endpoint | `https://auth.provider.com/token` |
| `OIDC_USERINFO_ENDPOINT` | User info endpoint | `https://auth.provider.com/userinfo` |
| `OIDC_END_SESSION_ENDPOINT` | Logout endpoint | `https://auth.provider.com/logout` |

## 🛠️ Development Setup

1. **Clone repository:**
   ```bash
   git clone https://github.com/Brramble/homie.git
   cd homie
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set environment variables** (create a `.env` file or export):
   ```bash
   export FLASK_SECRET_KEY="your-secret-key"
   export OIDC_BASE_URL="https://your-provider.com"
   export OIDC_CLIENT_ID="your-client-id"
   export OIDC_CLIENT_SECRET="your-client-secret"
   export ALLOWED_EMAILS="your-email@example.com"
   # ... etc
   ```

4. **Run:**
   ```bash
   python app.py
   ```

## 🐛 Troubleshooting

### Common Issues

**Error: `OIDC_BASE_URL environment variable is required`**
- Make sure you've set the `OIDC_BASE_URL` environment variable
- This should be your OIDC provider's base URL (e.g., `https://auth.example.com`)
- The app uses this for OIDC auto-discovery

**Error: `Failed to fetch OIDC configuration: Expecting value: line 1 column 1 (char 0)`**
- This means OIDC auto-discovery failed (returning HTML instead of JSON)
- Check that `https://your-provider.com/.well-known/openid_configuration` returns valid JSON
- If auto-discovery isn't supported, set manual endpoints in your `compose.yml`:


**For other providers:**
```yaml
- OIDC_AUTHORIZATION_ENDPOINT=https://your-provider.com/auth
- OIDC_TOKEN_ENDPOINT=https://your-provider.com/token
- OIDC_USERINFO_ENDPOINT=https://your-provider.com/userinfo
```

**Import Errors in Development**
- Run `pip install -r requirements.txt` to install all dependencies
- Make sure you're using Python 3.8 or later

**Authentication Issues**
- Verify your `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` are correct
- Check that your OIDC provider allows the redirect URI: `http://localhost:5000/auth/callback`
- Ensure your email is in the `ALLOWED_EMAILS` list

## Known Issues

- Automatic fetching of OIDC configuration has some issues and will need to be re-worked
- The `BASE_URL` must be set to the URL of your Homie instance for OIDC to function.
- All `OIDC Fallback` environments must be set.