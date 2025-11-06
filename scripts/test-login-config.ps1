# Test Login Configuration Script
# This script helps verify that the login setup is correct

Write-Host "=== Login Configuration Test ===" -ForegroundColor Cyan
Write-Host ""

# 1. Check Railway backend is accessible
Write-Host "1. Testing Railway backend health..." -ForegroundColor Yellow
$railwayUrl = "https://ebay-connector-app-production.up.railway.app"
try {
    $healthResponse = Invoke-RestMethod -Uri "$railwayUrl/healthz" -Method Get -TimeoutSec 10
    Write-Host "   ✅ Railway backend is accessible" -ForegroundColor Green
    Write-Host "   Response: $($healthResponse | ConvertTo-Json)" -ForegroundColor Gray
} catch {
    Write-Host "   ❌ Railway backend is NOT accessible" -ForegroundColor Red
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# 2. Check if login endpoint exists
Write-Host "2. Testing login endpoint (should return 422 or 401, not 404)..." -ForegroundColor Yellow
try {
    $loginResponse = Invoke-WebRequest -Uri "$railwayUrl/auth/login" -Method Post -Body (@{email="test"; password="test"} | ConvertTo-Json) -ContentType "application/json" -TimeoutSec 10 -ErrorAction Stop
    Write-Host "   ⚠️  Unexpected status: $($loginResponse.StatusCode)" -ForegroundColor Yellow
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    if ($statusCode -eq 422 -or $statusCode -eq 401) {
        Write-Host "   ✅ Login endpoint exists (status: $statusCode - expected for invalid credentials)" -ForegroundColor Green
    } elseif ($statusCode -eq 404) {
        Write-Host "   ❌ Login endpoint NOT found (404)" -ForegroundColor Red
    } else {
        Write-Host "   ⚠️  Login endpoint returned status: $statusCode" -ForegroundColor Yellow
    }
}

Write-Host ""

# 3. Check CORS headers
Write-Host "3. Testing CORS configuration..." -ForegroundColor Yellow
try {
    $corsResponse = Invoke-WebRequest -Uri "$railwayUrl/healthz" -Method Options -Headers @{"Origin"="https://ebay-connector-frontend.pages.dev"} -TimeoutSec 10
    $corsHeaders = $corsResponse.Headers
    
    if ($corsHeaders["Access-Control-Allow-Origin"]) {
        Write-Host "   ✅ CORS headers present" -ForegroundColor Green
        Write-Host "   Access-Control-Allow-Origin: $($corsHeaders['Access-Control-Allow-Origin'])" -ForegroundColor Gray
    } else {
        Write-Host "   ⚠️  No CORS headers found" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ⚠️  Could not test CORS: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""

# 4. Check Cloudflare Pages proxy (if accessible)
Write-Host "4. Testing Cloudflare Pages proxy..." -ForegroundColor Yellow
$cfUrl = "https://ebay-connector-frontend.pages.dev"
try {
    $proxyResponse = Invoke-WebRequest -Uri "$cfUrl/api/healthz" -Method Get -TimeoutSec 10 -ErrorAction Stop
    Write-Host "   ✅ Cloudflare proxy is accessible" -ForegroundColor Green
    Write-Host "   Status: $($proxyResponse.StatusCode)" -ForegroundColor Gray
} catch {
    Write-Host "   ⚠️  Cloudflare proxy test failed (this is OK if frontend is not deployed yet)" -ForegroundColor Yellow
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=== Test Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Check Cloudflare Pages environment variables:" -ForegroundColor White
Write-Host "   - API_PUBLIC_BASE_URL should be: $railwayUrl" -ForegroundColor Gray
Write-Host "   - VITE_API_BASE_URL should NOT exist" -ForegroundColor Gray
Write-Host "   - VITE_API_URL should NOT exist" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Open browser console and check for:" -ForegroundColor White
Write-Host "   - [API] Using /api (Cloudflare proxy -> Railway backend)" -ForegroundColor Gray
Write-Host "   - Requests going to /api/auth/login (NOT fly.dev)" -ForegroundColor Gray
Write-Host ""


