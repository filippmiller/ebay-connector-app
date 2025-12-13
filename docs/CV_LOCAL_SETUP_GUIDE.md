# Гайд: Локальный запуск CV модуля с DJI Osmo Pocket 3

## 📋 Содержание
1. [RTMP/RTSP URL для DJI Pocket 3](#1-rtmprtsp-url-для-dji-pocket-3)
2. [Локальный запуск Backend](#2-локальный-запуск-backend)
3. [Подключение камеры в режиме UVC](#3-подключение-камеры-в-режиме-uvc)
4. [Работа с Supabase и YOLO](#4-работа-с-supabase-и-yolo)

---

## 1. RTMP/RTSP URL для DJI Pocket 3

### Вариант A: RTMP стриминг (рекомендуется для облака)

DJI Pocket 3 может стримить напрямую на RTMP сервер. Примеры URL:

**YouTube Live:**
```
rtmp://a.rtmp.youtube.com/live2/YOUR_STREAM_KEY
```

**Twitch:**
```
rtmp://live.twitch.tv/app/YOUR_STREAM_KEY
```

**Локальный RTMP сервер (OBS/Nginx):**
```
rtmp://localhost:1935/live/stream
```

**Настройка в интерфейсе:**
1. Откройте `/admin/camera-vision`
2. В разделе "DJI Osmo Pocket 3" выберите режим **RTMP**
3. Введите RTMP URL (например, `rtmp://localhost:1935/live/stream`)
4. Нажмите **Connect**

### Вариант B: RTSP стриминг

Если у вас есть RTSP сервер или медиа-сервер:

```
rtsp://username:password@your-server.com:554/stream
```

**Для локального тестирования можно использовать:**
- **VLC Media Player** (создать RTSP сервер)
- **FFmpeg** (ретрансляция)
- **MediaMTX** (легковесный медиа-сервер)

---

## 2. Локальный запуск Backend

### Шаг 1: Установка зависимостей

```powershell
# Перейти в директорию backend
cd C:\dev\ebay-connector-app\backend

# Установить зависимости через Poetry
poetry install

# Или если Poetry не установлен:
pip install -r requirements.txt
```

### Шаг 2: Настройка переменных окружения

Создайте файл `backend/.env`:

```env
# Database (Supabase)
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT.supabase.co:5432/postgres?sslmode=require

# Supabase для CV модуля
CV_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
CV_SUPABASE_KEY=YOUR_SUPABASE_ANON_KEY

# OpenAI для Brain layer
OPENAI_API_KEY=sk-...

# JWT для аутентификации
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# CORS
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
FRONTEND_URL=http://localhost:5173

# CV настройки (опционально)
CV_CAMERA_MODE=uvc
CV_CAMERA_DEVICE_ID=0
CV_YOLO_MODEL=yolov8n.pt
CV_YOLO_DEVICE=cpu
CV_OCR_ENGINE=easyocr
CV_OCR_LANGUAGES=en,ru
```

**Где взять значения:**
- `DATABASE_URL`: Railway Variables или Supabase Dashboard → Settings → Database → Connection string
- `CV_SUPABASE_URL` и `CV_SUPABASE_KEY`: Supabase Dashboard → Settings → API
- `OPENAI_API_KEY`: https://platform.openai.com/api-keys

### Шаг 3: Запуск миграций

```powershell
cd backend
poetry run alembic upgrade head
```

### Шаг 4: Запуск сервера

```powershell
# С авто-перезагрузкой (для разработки)
poetry run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Или без перезагрузки
poetry run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Проверка:**
- API: http://localhost:8000/healthz
- CV Health: http://localhost:8000/cv/health
- CV Status: http://localhost:8000/cv/status

---

## 3. Подключение камеры в режиме UVC

### Шаг 1: Подготовка DJI Osmo Pocket 3

1. **Включите камеру** и подключите к компьютеру через USB-C
2. **Выберите режим "Webcam"** или "UVC" в настройках камеры
   - На экране камеры: Settings → Connection → USB Mode → Webcam
   - Или через DJI Mimo app: Settings → USB Connection → Webcam Mode

3. **Проверьте, что Windows видит камеру:**
   ```powershell
   # Список всех камер
   Get-PnpDevice -Class Camera
   ```

### Шаг 2: Определение Device ID

```powershell
# Python скрипт для проверки камер
cd backend
poetry run python -c "import cv2; [print(f'Camera {i}: {cv2.VideoCapture(i).isOpened()}') for i in range(5)]"
```

Обычно:
- **Device ID 0** = первая подключенная камера
- **Device ID 1** = вторая камера (если есть встроенная веб-камера)

### Шаг 3: Подключение через интерфейс

1. Откройте фронтенд: http://localhost:5173/admin/camera-vision
2. В разделе "DJI Osmo Pocket 3":
   - Выберите режим **UVC**
   - Device ID: **0** (или другой, если камера на другом индексе)
   - Нажмите **Connect**

### Шаг 4: Проверка подключения

После подключения вы должны увидеть:
- ✅ Статус: **CONNECTED**
- ✅ Live Video Stream показывает видео
- ✅ System Metrics показывает FPS > 0

---

## 4. Работа с Supabase и YOLO

### ✅ Да, локальный backend полностью работает с:

#### **Supabase:**
- ✅ Все логи пишутся в `camera_logs`, `camera_ocr_logs`
- ✅ Детекции сохраняются в `vision_detections`
- ✅ OCR результаты в `vision_ocr_results`
- ✅ Brain решения в `vision_brain_decisions`
- ✅ Операторские события в `vision_operator_events`

**Проверка:**
```sql
-- В Supabase SQL Editor
SELECT * FROM camera_logs ORDER BY timestamp DESC LIMIT 10;
SELECT * FROM vision_detections ORDER BY timestamp DESC LIMIT 10;
```

#### **YOLO:**
- ✅ Модель загружается автоматически при старте
- ✅ Обрабатывает каждый N-й кадр (по умолчанию каждый 5-й)
- ✅ Детекции отправляются в Supabase
- ✅ Работает на CPU (или GPU, если установлен CUDA)

**Настройка YOLO:**
```env
CV_YOLO_MODEL=yolov8n.pt  # nano (быстро), s/m/l/x (точнее, но медленнее)
CV_YOLO_DEVICE=cpu        # или cuda для GPU
CV_YOLO_CONFIDENCE=0.5    # порог уверенности
```

#### **OCR:**
- ✅ Автоматический fallback: EasyOCR → Tesseract → PaddleOCR
- ✅ Если EasyOCR не установлен, попробует Tesseract
- ✅ Результаты сохраняются в Supabase

#### **Brain Layer (OpenAI):**
- ✅ Анализирует YOLO + OCR результаты
- ✅ Принимает решения и отправляет инструкции оператору
- ✅ Все запросы логируются в `vision_brain_decisions`

### Архитектура работы:

```
[Локальный Backend] 
    ↓
[USB Camera (UVC)] → [OpenCV] → [YOLO Detection] → [OCR (если нужно)]
    ↓
[Supabase (облако)] ← [Все данные: логи, детекции, OCR, решения]
    ↓
[Frontend (localhost:5173)] ← [WebSocket] ← [Backend]
```

**Важно:**
- Backend работает локально, но **данные идут в облачный Supabase**
- Frontend может быть локальным или на Railway — не важно
- WebSocket соединение работает между локальным frontend и локальным backend

---

## 🐛 Troubleshooting

### Камера не найдена
```powershell
# Проверка доступных камер
poetry run python -c "import cv2; cap = cv2.VideoCapture(0); print('Opened:', cap.isOpened()); cap.release()"
```

### Ошибка "OpenCV not found"
```powershell
poetry add opencv-python-headless
poetry install
```

### Ошибка "EasyOCR not installed"
Это нормально! Система автоматически попробует Tesseract. Если нужен EasyOCR:
```powershell
poetry add easyocr
poetry install
```

### Ошибка подключения к Supabase
Проверьте:
1. `CV_SUPABASE_URL` и `CV_SUPABASE_KEY` в `.env`
2. Интернет-соединение
3. Supabase проект активен

### YOLO модель не загружается
Модель скачивается автоматически при первом запуске. Если проблема:
```powershell
# Проверка интернета для скачивания модели
poetry run python -c "from ultralytics import YOLO; model = YOLO('yolov8n.pt')"
```

---

## 📝 Примеры использования

### Тест камеры через API:
```powershell
# Список камер
Invoke-RestMethod -Uri "http://localhost:8000/cv/camera/list"

# Подключение
$body = @{
    mode = "uvc"
    device_id = 0
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/cv/camera/connect" -Method POST -Body $body -ContentType "application/json"

# Статус
Invoke-RestMethod -Uri "http://localhost:8000/cv/status"
```

### Запуск CV Pipeline:
```powershell
# Старт
Invoke-RestMethod -Uri "http://localhost:8000/cv/pipeline/start" -Method POST

# Метрики
Invoke-RestMethod -Uri "http://localhost:8000/cv/metrics"
```

---

## ✅ Чеклист перед запуском

- [ ] Poetry установлен и зависимости установлены
- [ ] `.env` файл создан с правильными ключами Supabase
- [ ] Миграции применены (`alembic upgrade head`)
- [ ] Backend запущен на `localhost:8000`
- [ ] DJI Pocket 3 подключен через USB в режиме Webcam
- [ ] Камера видна в системе (Device ID определен)
- [ ] Frontend запущен и открыт `/admin/camera-vision`
- [ ] Интернет работает (для Supabase и скачивания YOLO модели)

---

**Готово!** Теперь вы можете работать с CV модулем локально, при этом все данные будут сохраняться в облачный Supabase. 🎉

