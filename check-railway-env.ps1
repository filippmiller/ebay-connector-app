# Railway Environment Variables Diagnostic Script
# This script helps diagnose OAuth issues by checking what variables are needed

Write-Host "=== eBay OAuth Environment Variables Checklist ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "Required for PRODUCTION OAuth:" -ForegroundColor Yellow
Write-Host "1. EBAY_ENVIRONMENT = 'production'" -ForegroundColor White
Write-Host "2. EBAY_PRODUCTION_CLIENT_ID = (your eBay App ID)" -ForegroundColor White
Write-Host "3. EBAY_PRODUCTION_CERT_ID = (your eBay Cert ID / Client Secret)" -ForegroundColor White
Write-Host "4. EBAY_PRODUCTION_RUNAME = 'filipp_miller-filippmi-better-iamftmmqf'" -ForegroundColor White
Write-Host ""

Write-Host "Current Error: 'invalid_client' - client authentication failed" -ForegroundColor Red
Write-Host "This means:" -ForegroundColor Yellow
Write-Host "  - EBAY_PRODUCTION_CLIENT_ID is missing/incorrect, OR" -ForegroundColor White
Write-Host "  - EBAY_PRODUCTION_CERT_ID is missing/incorrect, OR" -ForegroundColor White
Write-Host "  - The Client ID and Cert ID don't match each other" -ForegroundColor White
Write-Host ""

Write-Host "=== How to Check Railway Variables ===" -ForegroundColor Cyan
Write-Host "1. Go to: https://railway.app" -ForegroundColor White
Write-Host "2. Select your backend service" -ForegroundColor White
Write-Host "3. Go to 'Variables' tab" -ForegroundColor White
Write-Host "4. Check these variables exist and are correct:" -ForegroundColor White
Write-Host "   - EBAY_ENVIRONMENT" -ForegroundColor Green
Write-Host "   - EBAY_PRODUCTION_CLIENT_ID" -ForegroundColor Green
Write-Host "   - EBAY_PRODUCTION_CERT_ID" -ForegroundColor Green
Write-Host "   - EBAY_PRODUCTION_RUNAME" -ForegroundColor Green
Write-Host ""

Write-Host "=== How to Get eBay Credentials ===" -ForegroundColor Cyan
Write-Host "1. Go to: https://developer.ebay.com/my/keys" -ForegroundColor White
Write-Host "2. Find your Production Application Keyset" -ForegroundColor White
Write-Host "3. Copy:" -ForegroundColor White
Write-Host "   - App ID (Client ID) - starts with 'filippmi-betterpl-PRD-...'" -ForegroundColor Green
Write-Host "   - Cert ID (Client Secret) - starts with 'PRD-...'" -ForegroundColor Green
Write-Host "4. Verify RuName: 'filipp_miller-filippmi-better-iamftmmqf'" -ForegroundColor Green
Write-Host "   - Callback URL should be: https://ebay-connector-frontend.pages.dev/ebay/callback" -ForegroundColor Green
Write-Host ""

Write-Host "=== Quick Fix Steps ===" -ForegroundColor Cyan
Write-Host "1. Verify eBay credentials in Railway match eBay Developer Portal" -ForegroundColor White
Write-Host "2. Make sure EBAY_ENVIRONMENT = 'production' (not 'sandbox')" -ForegroundColor White
Write-Host "3. Redeploy backend after updating variables" -ForegroundColor White
Write-Host "4. Test OAuth flow again" -ForegroundColor White
Write-Host ""

Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")


