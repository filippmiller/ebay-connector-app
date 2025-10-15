# eBay API Setup Guide

This guide will walk you through setting up your eBay Developer account and obtaining the necessary credentials to use with the eBay Connector application.

## Step 1: Create an eBay Developer Account

1. Go to https://developer.ebay.com/
2. Click "Register" in the top right corner
3. If you have an eBay account, sign in. Otherwise, create a new eBay account
4. Accept the developer terms and conditions
5. Complete your developer profile

## Step 2: Create a Developer Application

1. Once logged in, go to https://developer.ebay.com/my/keys
2. Click "Create a Keyset" or "Get OAuth Application Credentials"
3. Choose between:
   - **Sandbox**: For development and testing (recommended to start with)
   - **Production**: For live eBay data

### Sandbox Keyset
For testing purposes, create a sandbox keyset first:
1. Select "Sandbox"
2. Fill in the application details:
   - Application Title: "eBay Connector App"
   - Short Description: Brief description of your app
3. Click "Create Keyset"

### Production Keyset
When ready for production:
1. Select "Production"
2. Fill in more detailed application information
3. May require additional verification

## Step 3: Configure OAuth Redirect URI

1. In your application settings, find the "OAuth redirect URI" or "RuName" section
2. Add your redirect URI:
   - **Local Development**: `http://localhost:5173/ebay/callback`
   - **Production**: `https://yourdomain.com/ebay/callback`
3. Save the configuration

**Important**: The redirect URI must exactly match what you configure in your application's `.env` file.

## Step 4: Get Your Credentials

After creating your keyset, you'll see:
1. **App ID (Client ID)**: This is your EBAY_CLIENT_ID
2. **Cert ID (Client Secret)**: This is your EBAY_CLIENT_SECRET
3. **User Token** or **RuName**: This is related to your redirect URI

Copy these credentials - you'll need them for the next step.

## Step 5: Configure the Application

1. Open `/backend/.env` file in your application
2. Add your eBay credentials:

```env
# For Sandbox
EBAY_CLIENT_ID=YourApp-AppName-SBX-xxxxxxx-xxxxxxx
EBAY_CLIENT_SECRET=SBX-xxxxxxxxxxxxxxxxxxxxxxx
EBAY_REDIRECT_URI=http://localhost:5173/ebay/callback
EBAY_ENVIRONMENT=sandbox

# For Production
# EBAY_CLIENT_ID=YourApp-AppName-PRD-xxxxxxx-xxxxxxx
# EBAY_CLIENT_SECRET=PRD-xxxxxxxxxxxxxxxxxxxxxxx
# EBAY_REDIRECT_URI=https://yourdomain.com/ebay/callback
# EBAY_ENVIRONMENT=production
```

3. Restart your backend server if it's already running

## Step 6: Configure OAuth Scopes

The application requests the following default scopes:
- `https://api.ebay.com/oauth/api_scope` - Basic API access
- `https://api.ebay.com/oauth/api_scope/sell.account` - Seller account access

You can modify these in the backend code if you need different permissions. Common scopes include:

- `https://api.ebay.com/oauth/api_scope/sell.inventory` - Inventory management
- `https://api.ebay.com/oauth/api_scope/sell.fulfillment` - Order fulfillment
- `https://api.ebay.com/oauth/api_scope/sell.marketing` - Marketing campaigns
- `https://api.ebay.com/oauth/api_scope/commerce.catalog.readonly` - Catalog read access

See full list at: https://developer.ebay.com/api-docs/static/oauth-scopes.html

## Step 7: Test the Connection

1. Start both backend and frontend servers
2. Register/login to the application
3. Navigate to the Dashboard
4. Click "Connect to eBay" under the eBay Connection tab
5. You'll be redirected to eBay's login page
6. Sign in with your eBay sandbox/production account
7. Grant the requested permissions
8. You'll be redirected back to the application with a success message

## Step 8: Monitor the Connection

1. Go to the "Connection Terminal" tab
2. You'll see detailed logs of the OAuth process including:
   - Authorization URL generation
   - Token exchange requests
   - Token responses (with sanitized credentials)
   - Any errors that occur

## Troubleshooting

### Error: "Invalid client credentials"
- Double-check your Client ID and Client Secret
- Ensure you're using the correct environment (sandbox vs production)
- Verify there are no extra spaces in your credentials

### Error: "Redirect URI mismatch"
- Ensure the redirect URI in your application exactly matches what's configured in eBay Developer Console
- Check for trailing slashes (http://localhost:5173/ebay/callback vs http://localhost:5173/ebay/callback/)
- Protocol must match (http vs https)

### Error: "Invalid scope"
- Check that the scopes you're requesting are available for your application type
- Some scopes require additional approval from eBay

### Token Expires Too Quickly
- eBay user tokens typically expire after 2 hours
- The application stores refresh tokens to get new access tokens
- Implement token refresh logic if you need longer sessions

## eBay API Environments

### Sandbox
- Use for development and testing
- Separate from production data
- Create test users at https://developer.ebay.com/sandbox
- API endpoint: `https://api.sandbox.ebay.com`

### Production
- Use for live eBay data
- Requires verified application
- May need additional business verification
- API endpoint: `https://api.ebay.com`

## Rate Limits

eBay enforces rate limits on API calls:
- Sandbox: More lenient limits for testing
- Production: Stricter limits based on your subscription level

Monitor your usage in the eBay Developer Console.

## Additional Resources

- eBay Developer Documentation: https://developer.ebay.com/docs
- OAuth Guide: https://developer.ebay.com/api-docs/static/oauth-tokens.html
- API Reference: https://developer.ebay.com/api-docs/
- Developer Forums: https://developer.ebay.com/support/forum
- Getting Started Guide: https://developer.ebay.com/api-docs/static/gs_landing.html

## Security Best Practices

1. **Never commit credentials to version control**
   - Keep `.env` file in `.gitignore`
   - Use environment variables in production

2. **Rotate credentials regularly**
   - eBay allows you to regenerate your Client Secret
   - Update your application configuration after rotation

3. **Use minimum required scopes**
   - Only request OAuth scopes your application actually needs
   - Users are more likely to grant limited permissions

4. **Secure token storage**
   - Store tokens securely (encrypted database recommended)
   - Don't expose tokens in logs or client-side code
   - The application sanitizes sensitive data in logs

5. **Use HTTPS in production**
   - Required for production OAuth flows
   - Protects credentials in transit

## Getting Help

If you encounter issues:
1. Check the Connection Terminal in the application for detailed error logs
2. Review eBay's developer documentation
3. Search the eBay developer forums
4. Contact eBay Developer Support

## Next Steps

After successfully connecting:
1. Start building features using eBay APIs
2. Test thoroughly in sandbox before moving to production
3. Monitor your API usage and logs
4. Implement proper error handling and retry logic
5. Consider implementing webhook notifications for real-time updates
