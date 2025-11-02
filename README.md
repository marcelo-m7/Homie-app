# Homie 🏠

> ⚠️ **Note**: This project is in active development and may have breaking changes.

A simple family utility app for managing household tasks with secure authentication.

**Features:** Shopping lists • Chores • Expiry tracking • Bills • Mobile-friendly

## Screenshots

<img width="1281" height="676" alt="image" src="https://github.com/user-attachments/assets/07cf8647-6d5f-420f-ab0e-2c7bf55b7265" />

<img width="1317" height="795" alt="image" src="https://github.com/user-attachments/assets/a14bf3cc-52e5-428c-9a63-4b9be12af3a7" />

## Quick Start

1. **Get the files:**
   ```bash
   curl -o compose.yml https://raw.githubusercontent.com/Brramble/homie/main/compose.yml
   ```

2. **Configure your OIDC provider:**
   - Set callback URL to: `http://localhost:5000/auth/callback`
   - Note your client ID and secret

3. **Edit the compose.yml file:**
   ```yaml
   - SECRET_KEY=your-random-secret-key-here
   - OIDC_ENABLED=true
   - OIDC_BASE_URL=https://your-auth-provider.com
   - OIDC_CLIENT_ID=your-client-id
   - OIDC_CLIENT_SECRET=your-client-secret
   - ALLOWED_EMAILS=your-email@example.com
   ```

4. **Start:**
   ```bash
   docker compose up -d
   ```

5. **Open:** http://localhost:5000

## Configuration

Copy `.env.sample` to `.env` and fill in your values, or edit the environment variables in `compose.yml`.

**Required settings:**
- `SECRET_KEY` - Random string for security
- `OIDC_ENABLED` - Enable/disable OIDC authentication (default: true)
- `OIDC_BASE_URL` - Your authentication provider URL (when OIDC enabled)
- `OIDC_CLIENT_ID` & `OIDC_CLIENT_SECRET` - From your OIDC provider (when OIDC enabled)
- `ALLOWED_EMAILS` - Who can access the app (when OIDC enabled)

**Important:** Configure `{your-base-url}/auth/callback` as the callback URL in your OIDC provider.

## Authentication Modes

Homie supports two authentication modes:

- **OIDC Mode** (default): Use external OIDC provider (Keycloak, Auth0, etc.)
- **Local Mode** (coming soon): Local user accounts with username/password

To disable OIDC and prepare for local accounts, set `OIDC_ENABLED=false` in your environment.

## Development

```bash
git clone https://github.com/Brramble/homie.git
cd homie
pip install -r requirements.txt
cp .env.sample .env
# Edit .env with your settings
python app.py
```

## Need Help?

**Common issues:**
- **Can't login?** Check your OIDC callback URL is set correctly
- **OIDC errors?** Verify your client ID/secret and base URL
- **Access denied?** Add your email to `ALLOWED_EMAILS`

The app uses OIDC auto-discovery but falls back to manual configuration if needed.