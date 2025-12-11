# Homie 🏠

> ⚠️ **Note**: This project is in active development and may have breaking changes.

A simple family utility app for managing household tasks with secure authentication.

**Features:** Shopping lists • Chores • Expiry tracking • Bills • Mobile-friendly

## Screenshots

<img width="1281" height="676" alt="image" src="https://github.com/user-attachments/assets/07cf8647-6d5f-420f-ab0e-2c7bf55b7265" />

<img width="1317" height="795" alt="image" src="https://github.com/user-attachments/assets/a14bf3cc-52e5-428c-9a63-4b9be12af3a7" />

<img width="1246" height="634" alt="image" src="https://github.com/user-attachments/assets/4934bbc6-f66b-4d9c-82d7-45d951ec4d82" />

## Quick Start

1. **Get the files:**
   ```bash
   curl -o compose.yml https://raw.githubusercontent.com/Brramble/homie/main/compose.yml
   ```

2. **Configure your OIDC provider:**
   - Set callback URL to: `http://localhost:5000/auth/callback`
   - Note your client ID and secret

3. **Edit the compose.yml file:**

   **For OIDC Authentication:**
   ```yaml
   - SECRET_KEY=your-random-secret-key-here
   - OIDC_ENABLED=true
   - OIDC_BASE_URL=https://your-auth-provider.com
   - OIDC_CLIENT_ID=your-client-id
   - OIDC_CLIENT_SECRET=your-client-secret
   - ALLOWED_EMAILS=your-email@example.com
   ```

   **For Local Authentication (Family Mode):**
   ```yaml
   - SECRET_KEY=your-random-secret-key-here
   - OIDC_ENABLED=false
   - USERS=Dad,Bill,Sarah
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

**For OIDC mode (OIDC_ENABLED=true):**
- `OIDC_BASE_URL` - Your authentication provider URL
- `OIDC_CLIENT_ID` & `OIDC_CLIENT_SECRET` - From your OIDC provider
- **Access Control:** Choose ONE of the following:
  - `ALLOWED_GROUPS` - Comma-separated list of OIDC groups (recommended)
  - `ALLOWED_EMAILS` - Comma-separated list of email addresses
  - **Note:** If both are set, `ALLOWED_GROUPS` takes precedence
- **Admin Control (Optional):**
  - `ADMIN_EMAILS` - Comma-separated list of admin email addresses who can manage feature visibility

**For Local mode (OIDC_ENABLED=false):**
- `USERS` - Local users in format: `username1,username2,username3`

**Important:** Configure `{your-base-url}/auth/callback` as the callback URL in your OIDC provider.

## Authentication Modes

Homie supports two authentication modes:

### OIDC Mode (default)
Use external OIDC provider (Keycloak, Auth0, etc.)
- Set `OIDC_ENABLED=true`
- Configure your OIDC provider details
- Users authenticate through your SSO provider

### Local Mode
Simple user selection without passwords - perfect for family use
- Set `OIDC_ENABLED=false`
- Configure `USERS` environment variable
- Users click their name to login

**Example local users setup:**
```bash
OIDC_ENABLED=false
USERS=Dad,Bill,Sarah
```

## Admin Features

### Feature Visibility Control (OIDC Mode Only)

Admins can control which features are visible to each user. This is useful for:
- Hiding bills and budget from children's accounts
- Customizing the experience for different family members
- Managing access to sensitive financial information

**Setup:**
1. Add admin emails to your `.env` file:
   ```bash
   ADMIN_EMAILS=parent@example.com,spouse@example.com
   ```

2. Admins will see an "Admin" option in the user menu dropdown

3. In the Admin panel, toggle features on/off for each user:
   - Shopping
   - Chores
   - Tracker (Expiry tracking)
   - Bills
   - Budget

**Note:** This feature only works with OIDC authentication. Local mode users can access all features - this is still a WIP.

## Development

```bash
git clone https://github.com/Brramble/homie.git
cd homie
pip install -r requirements.txt
cp .env.sample .env
# Edit .env with your settings
python app.py
```
