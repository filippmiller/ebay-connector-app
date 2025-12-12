# 🚀 CV Module - Быстрый старт

## Вариант 1: RTMP/RTSP (для облачного сервера)

### RTMP URL для DJI Pocket 3:

**YouTube Live:**
```
rtmp://a.rtmp.youtube.com/live2/YOUR_STREAM_KEY
```

**Twitch:**
```
rtmp://live.twitch.tv/app/YOUR_STREAM_KEY
```

**Локальный RTMP сервер:**
```
rtmp://localhost:1935/live/stream
```

**Как использовать:**
1. Настройте DJI Pocket 3 на RTMP стриминг (через DJI Mimo app)
2. Откройте `/admin/camera-vision`
3. Выберите режим **RTMP**
4. Введите RTMP URL
5. Нажмите **Connect**

---

## Вариант 2: Локальный запуск с USB камерой (UVC)

### Шаг 1: Подготовка (5 минут)

```powershell
# 1. Установить зависимости
cd C:\dev\ebay-connector-app\backend
poetry install

# 2. Создать .env файл
# Скопируйте переменные из Railway или создайте новый файл backend/.env:
```

**Минимальный `.env` для CV:**
```env
# Supabase (обязательно)
DATABASE_URL=postgresql://postgres:***@db.***.supabase.co:5432/postgres?sslmode=require
CV_SUPABASE_URL=https://***.supabase.co
CV_SUPABASE_KEY=your-anon-key

# OpenAI (для Brain layer)
OPENAI_API_KEY=sk-...

# JWT (для аутентификации)
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# CORS
ALLOWED_ORIGINS=http://localhost:5173
FRONTEND_URL=http://localhost:5173
```

### Шаг 2: Запуск (2 минуты)

```powershell
# 1. Применить миграции
poetry run alembic upgrade head

# 2. Запустить backend
poetry run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Проверка:** http://localhost:8000/healthz

### Шаг 3: Подключение камеры (3 минуты)

1. **Подключите DJI Pocket 3 через USB**
2. **Включите режим Webcam:**
   - На камере: Settings → USB Mode → Webcam
   - Или через DJI Mimo app
3. **Откройте интерфейс:**
   - Frontend: http://localhost:5173/admin/camera-vision
   - Или если frontend на Railway: https://ebay-connector-frontend.pages.dev/admin/camera-vision
4. **Подключите камеру:**
   - Режим: **UVC**
   - Device ID: **0** (или проверьте через API)
   - Нажмите **Connect**

### Шаг 4: Проверка работы

```powershell
# Список камер
Invoke-RestMethod -Uri "http://localhost:8000/cv/camera/list"

# Статус CV
Invoke-RestMethod -Uri "http://localhost:8000/cv/status"

# Метрики
Invoke-RestMethod -Uri "http://localhost:8000/cv/metrics"
```

---

## ✅ Что работает локально:

- ✅ **Камера (UVC)** — прямое подключение через USB
- ✅ **YOLO детекция** — автоматически загружается при старте
- ✅ **OCR** — автоматический fallback (EasyOCR → Tesseract)
- ✅ **Supabase** — все данные пишутся в облако
- ✅ **Brain Layer** — OpenAI анализ работает
- ✅ **WebSocket** — live streaming в браузер
- ✅ **Логи** — все в Supabase, видно в интерфейсе

---

## 🐛 Частые проблемы

### "No cameras found"
- Проверьте, что камера в режиме Webcam
- Попробуйте другой Device ID (0, 1, 2...)
- Перезапустите камеру

### "EasyOCR not installed"
- **Это нормально!** Система автоматически попробует Tesseract
- Если нужен EasyOCR: `poetry add easyocr`

### "Failed to connect to Supabase"
- Проверьте `CV_SUPABASE_URL` и `CV_SUPABASE_KEY` в `.env`
- Проверьте интернет-соединение

### "YOLO model not found"
- Модель скачивается автоматически при первом запуске
- Нужен интернет для первого скачивания

---

## 📚 Полная документация

См. [CV_LOCAL_SETUP_GUIDE.md](./CV_LOCAL_SETUP_GUIDE.md) для детальной инструкции.

---

**Готово!** Теперь вы можете работать с CV модулем локально. 🎉

