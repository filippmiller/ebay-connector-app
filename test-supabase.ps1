# === 1. Настройка переменных ===
$ref = "nrpfahjygulsfxmbmfzv"
$password = "2ma5C7qZHXFJJGOG"

# Прямое подключение (рекомендуется)
$directUrl = "postgresql://postgres:$password@db.$ref.supabase.co:5432/postgres"

# Pooler (только если нужно — сейчас НЕ используем)
# $poolerUrl = "postgresql://postgres.$ref:$password@aws-1-us-east-1.pooler.supabase.com:5432/postgres"

$env:DATABASE_URL = $directUrl
Write-Host "[✅] Переменная DATABASE_URL установлена:" -ForegroundColor Green
Write-Host "    $env:DATABASE_URL" -ForegroundColor Cyan

# === 2. Проверка: доступен ли psql? ===
Write-Host "`n[🔍] Проверка: установлен ли psql..." -ForegroundColor Yellow
$psqlExists = $null -ne (Get-Command psql -ErrorAction SilentlyContinue)
if ($psqlExists) {
    Write-Host "    ✅ psql найден" -ForegroundColor Green
} else {
    Write-Host "    ❌ psql не найден. Установи через:" -ForegroundColor Red
    Write-Host "       scoop install postgresql" -ForegroundColor Magenta
    Write-Host "       или: winget install PostgreSQL.PostgreSQL"
}

# === 3. Попытка подключения через psql (если есть) ===
if ($psqlExists) {
    Write-Host "`n[🚀] Пробуем подключиться через psql..." -ForegroundColor Yellow
    & psql $env:DATABASE_URL -c "SELECT 'OK' AS status, current_user, current_database(), version();" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n✅ УСПЕХ: psql подключился к Supabase!" -ForegroundColor Green
    } else {
        Write-Host "`n❌ ОШИБКА: psql не смог подключиться." -ForegroundColor Red
        Write-Host "Возможные причины:" -ForegroundColor Yellow
        Write-Host "  • IP не добавлен в Trusted IPs (обязательно!)"
        Write-Host "  • Пароль неверный (но ты его только что сменил)"
        Write-Host "  • Брандмауэр/провайдер блокирует порт 5432"
    }
}

# === 4. Попытка подключения через Python + psycopg2 (в backend) ===
Write-Host "`n[🐍] Пробуем подключиться через Python (poetry -C backend)..." -ForegroundColor Yellow

# Создаём временный скрипт
$tempScript = @"
import os
import sys
try:
    import psycopg2
except ImportError:
    print("❌ psycopg2 не установлен. Выполни: poetry add psycopg2-binary")
    sys.exit(1)

url = os.environ.get("DATABASE_URL")
if not url:
    print("❌ DATABASE_URL не задан")
    sys.exit(1)

print(f"📡 Подключаюсь к: {url}")

try:
    conn = psycopg2.connect(url, connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT 'OK' AS status, current_user, current_database(), now();")
    res = cur.fetchone()
    print(f"✅ УСПЕХ! Подключено как: {res[1]} | БД: {res[2]} | Время: {res[3]}")
    conn.close()
except Exception as e:
    print(f"❌ ОШИБКА подключения:")
    print(f"    {type(e).__name__}: {e}")
"@

# Сохраняем и запускаем
$tempPath = Join-Path $PSScriptRoot "temp_test_db.py"
Set-Content -Path $tempPath -Value $tempScript -Encoding UTF8

try {
    & poetry -C backend run python $tempPath 2>&1
} catch {
    Write-Host "Не удалось запустить poetry. Проверь, что backend/ существует и poetry инициализирован." -ForegroundColor Red
}

# Удаляем временный файл
Remove-Item -Path $tempPath -ErrorAction SilentlyContinue

# === 5. Подсказки ===
Write-Host "`n[💡] Что делать, если всё ещё ошибка?" -ForegroundColor Cyan
Write-Host "1️⃣ Зайди в Supabase Dashboard → Project Settings → Database → Trusted IPs"
Write-Host "   → Добавь свой IP («Detect my IP») → Сохрани"
Write-Host "2️⃣ Подожди 60 секунд после добавления IP"
Write-Host "3️⃣ Убедись, что пароль именно: $password"
Write-Host "4️⃣ Попробуй открыть в браузере: https://$ref.supabase.co — должен быть Supabase Studio"

Write-Host "`nГотово. Удачи! 🚀" -ForegroundColor Green