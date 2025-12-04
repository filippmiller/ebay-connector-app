# Скрипт для проверки конфигурации Railway Worker
# Использование: .\scripts\check_railway_worker_config.ps1

Write-Host "=== Проверка конфигурации Railway Worker ===" -ForegroundColor Cyan
Write-Host ""

# Проверка наличия Railway CLI
$railwayInstalled = Get-Command railway -ErrorAction SilentlyContinue
if (-not $railwayInstalled) {
    Write-Host "⚠️  Railway CLI не установлен" -ForegroundColor Yellow
    Write-Host "   Установи: npm install -g @railway/cli" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Или проверь вручную в Railway Dashboard:" -ForegroundColor Yellow
    Write-Host "   1. Открой https://railway.app" -ForegroundColor Gray
    Write-Host "   2. Найди сервис 'aebay-workers-loop'" -ForegroundColor Gray
    Write-Host "   3. Settings → Deploy → Start Command" -ForegroundColor Gray
    Write-Host "   4. Должно быть: python -m app.workers.ebay_workers_loop" -ForegroundColor Green
    Write-Host "   5. Settings → Variables → проверь WEB_APP_URL и INTERNAL_API_KEY" -ForegroundColor Gray
    exit 1
}

Write-Host "✅ Railway CLI установлен" -ForegroundColor Green
Write-Host ""

# Проверка статуса
Write-Host "Проверка статуса сервисов..." -ForegroundColor Cyan
railway status

Write-Host ""
Write-Host "Проверка переменных окружения для aebay-workers-loop..." -ForegroundColor Cyan
railway variables --service aebay-workers-loop

Write-Host ""
Write-Host "=== Что проверить ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Start Command должен быть:" -ForegroundColor Yellow
Write-Host "   python -m app.workers.ebay_workers_loop" -ForegroundColor Green
Write-Host ""
Write-Host "2. Обязательные переменные:" -ForegroundColor Yellow
Write-Host "   - WEB_APP_URL (URL основного приложения)" -ForegroundColor Green
Write-Host "   - INTERNAL_API_KEY (должен совпадать с основным приложением)" -ForegroundColor Green
Write-Host ""
Write-Host "3. В логах должно быть:" -ForegroundColor Yellow
Write-Host "   'Starting ALL workers proxy loop...' или" -ForegroundColor Green
Write-Host "   'Starting Transactions-only worker proxy loop...'" -ForegroundColor Green
Write-Host ""

