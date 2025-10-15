# eBay OAuth Troubleshooting Guide

## Common OAuth Errors and Solutions

### Error: "invalid_request"

This error typically means the OAuth parameters don't match what's configured in your eBay Developer Console.

**Possible Causes:**

1. **Redirect URI Mismatch**
   - The redirect URI in your request must **exactly** match what's configured in eBay Developer Console
   - Check for:
     - Protocol differences (http vs https)
     - Port numbers (http://localhost:5173 vs http://localhost:3000)
     - Trailing slashes (/ebay/callback vs /ebay/callback/)
     - Case sensitivity (usually not an issue but worth checking)

2. **RuName Configuration**
   - Production eBay requires a properly configured RuName
   - The RuName must be accepted/approved by eBay
   - Your RuName: `filipp_miller-filippmi-better-hrorvd`

3. **Client ID/Secret Issues**
   - Wrong environment (Sandbox vs Production)
   - Expired or revoked credentials
   - Incorrect copy/paste with extra spaces

**How to Fix:**

1. Go to https://developer.ebay.com/my/auth
2. Find your RuName: `filipp_miller-filippmi-better-hrorvd`
3. Click "Edit" or view details
4. Check the "OAuth Redirect URL" field
5. It should be exactly: `http://localhost:5173/ebay/callback`
6. If not, update it to match
7. Save changes
8. Wait a few minutes for changes to propagate
9. Try connecting again

### Checking Current Configuration

You can verify your current configuration by looking at the **Connection Terminal** in the application:

1. Go to Dashboard → Connection Terminal tab
2. Click "Connect to eBay"
3. Look at the logged request data:
   ```json
   {
     "redirect_uri": "http://localhost:5173/ebay/callback",
     "scopes": [...],
     "state": "user-id",
     "client_id": "filippmi-betterpl-PRD-0115bff8e-85d4f36a"
   }
   ```

The `redirect_uri` in the logs must match what's in your eBay Developer Console.

### Production vs Sandbox Environment

**Production** (what you're using):
- Environment: `production`
- Client ID starts with: `filippmi-betterpl-PRD-...`
- Client Secret starts with: `PRD-...`
- Uses real eBay accounts
- Authorization URL: `https://auth.ebay.com/oauth2/authorize`

**Sandbox** (for testing):
- Environment: `sandbox`
- Client ID starts with: `...-SBX-...`
- Client Secret starts with: `SBX-...`
- Uses test eBay accounts
- Authorization URL: `https://auth.sandbox.ebay.com/oauth2/authorize`

### Updating Redirect URI in eBay Developer Console

#### Method 1: Via Web Interface

1. Go to https://developer.ebay.com/my/auth
2. Find your application
3. Look for "User Tokens" or "OAuth Redirect URLs"
4. Find your RuName
5. Click "Edit" or "Manage"
6. Update the redirect URL to: `http://localhost:5173/ebay/callback`
7. Save changes

#### Method 2: Contact eBay Support

If you can't change it yourself:
1. Go to https://developer.ebay.com/support
2. Create a support ticket
3. Request to update your RuName's redirect URI
4. Provide your RuName and desired redirect URI

### Alternative: Using a Different RuName

If you have multiple RuNames configured, you might want to:

1. Check all your RuNames in the developer console
2. Find one that matches `http://localhost:5173/ebay/callback`
3. Note that RuName's associated Client ID/Secret
4. Update your `.env` file with that keyset

### Testing the Configuration

Once you've updated the redirect URI:

1. **Clear browser cache** (eBay might cache the old configuration)
2. **Wait 5-10 minutes** for eBay's changes to propagate
3. Try connecting again
4. Watch the Connection Terminal for detailed logs

### Verifying Success

A successful OAuth flow will show these logs in sequence:

1. **authorization_url_generated**
   ```
   Generated eBay authorization URL for redirect_uri: http://localhost:5173/ebay/callback
   ```

2. **token_exchange_request**
   ```
   Exchanging authorization code for access token
   ```

3. **token_exchange_success**
   ```
   Successfully obtained eBay access token
   ```

### For Deployed Application

When you deploy the application to production:

1. Update your `.env` to use the deployed URL:
   ```env
   EBAY_REDIRECT_URI=https://yourdomain.com/ebay/callback
   ```

2. Update the same redirect URI in eBay Developer Console

3. Redeploy both frontend and backend

4. Test the OAuth flow again

### Getting Help

If you're still stuck:

1. **Check the Connection Terminal** - it shows all credential exchanges
2. **Review backend logs** - look for detailed error messages
3. **eBay Developer Forums**: https://developer.ebay.com/support/forum
4. **eBay Developer Support**: https://developer.ebay.com/support

### Common Working Configurations

**Local Development:**
```env
EBAY_REDIRECT_URI=http://localhost:5173/ebay/callback
```
Frontend running on: http://localhost:5173

**Deployed (Example):**
```env
EBAY_REDIRECT_URI=https://ebay-connector.example.com/ebay/callback
```
Frontend deployed at: https://ebay-connector.example.com

### RuName vs Redirect URI

eBay uses "RuName" (Return URL Name) as an identifier for your redirect URI:
- **RuName**: A unique identifier (e.g., `filipp_miller-filippmi-better-hrorvd`)
- **Redirect URI**: The actual URL (e.g., `http://localhost:5173/ebay/callback`)

The RuName is associated with one or more redirect URIs in the eBay Developer Console.

### Advanced: Using eBay's RuName API

If you need to programmatically manage RuNames:

```bash
# Get all RuNames for your application
curl -X GET \
  'https://api.ebay.com/identity/v1/oauth2/token' \
  -H 'Authorization: Basic <base64-encoded-credentials>'
```

See: https://developer.ebay.com/api-docs/static/oauth-runame.html

### Quick Checklist

Before testing OAuth:
- [ ] Backend is running on port 8000
- [ ] Frontend is running on port 5173
- [ ] `.env` has correct Client ID, Secret, and Redirect URI
- [ ] eBay Developer Console has matching Redirect URI
- [ ] Using correct environment (production vs sandbox)
- [ ] RuName is approved/active in eBay Developer Console
- [ ] No typos in any credentials
- [ ] Browser cache cleared

### Connection Terminal Examples

**Successful Connection:**
```
✅ authorization_url_generated - success
✅ token_exchange_request - info
✅ token_exchange_success - success
✅ user_tokens_saved - success
```

**Failed Connection (Redirect URI Mismatch):**
```
✅ authorization_url_generated - success
❌ token_exchange_failed - error
   Error: Failed to exchange code for token: invalid_request
```

The Connection Terminal is your best friend for debugging OAuth issues!
