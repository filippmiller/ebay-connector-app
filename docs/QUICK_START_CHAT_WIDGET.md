# AI Chat Widget - Quick Reference

## ✅ What's Implemented

1. **Backend STT Endpoint** - `POST /api/stt/transcribe` with OpenAI Whisper integration
2. **Frontend Voice UI** - Microphone button in widget with MediaRecorder
3. **eBay Connector Integration** - Widget loader in `main.tsx`
4. **Comprehensive Documentation** - Architecture, API reference, deployment guide

---

## 🗂️ Repository Structure

```
ebay-connector-app/
├── external/ai-chat-widget/        ← NEW! Widget code
│   ├── backend/
│   │   └── app/
│   │       ├── api/
│   │       │   ├── chat.py         ← Existing
│   │       │   └── stt.py          ← NEW! Voice transcription
│   │       ├── config.py           ← Modified (STT settings)
│   │       └── main.py             ← Modified (registered STT router)
│   └── widget/
│       └── widget.js               ← Modified (voice input UI)
├── frontend/
│   ├── src/
│   │   └── main.tsx                ← Modified (widget loader)
│   └── .env.example                ← Modified (widget URL)
└── docs/
    └── assistant-widget-voice-stt-2025-12-09.md  ← NEW! Full docs
```

---

## 🚀 Quick Start (Local Testing)

### Terminal 1: Widget Backend

```powershell
cd external/ai-chat-widget/backend

# Setup virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env from example
Copy-Item .env.example .env

# Edit .env - ADD YOUR OPENAI_API_KEY!
# Required variables:
#   AI_API_KEY=sk-proj-YOUR_KEY_HERE
#   STT_ENABLED=true

# Start backend
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Visit: http://localhost:8080/docs (FastAPI Swagger UI)

### Terminal 2: eBay Connector Frontend

```powershell
cd frontend

# Add widget URL to .env
Add-Content .env "`nVITE_CHAT_WIDGET_BASE_URL=http://localhost:8080"

# Start frontend
npm run dev
```

Visit: http://localhost:5173

**Expected**: Widget button appears in bottom-right corner 🎯

---

## 🎤 Testing Voice Input

1. Click widget button → Chat opens
2. Click **microphone icon** 🎤
3. Grant microphone permission
4. **Speak in Russian**: "Привет, покажи мои заказы"
5. Click mic again to stop → Text appears in input field
6. Send message → AI responds

---

## ☁️ Railway Deployment Checklist

### 1. Create Service

- [ ] Go to [Railway Dashboard](https://railway.app/dashboard)
- [ ] Click "+ New Service" → "GitHub Repo"
- [ ] Select: `filippmiller/ebay-connector-app`
- [ ] Name: `assistant-widget`

### 2. Configure

**Root Directory**: `external/ai-chat-widget/backend`

**Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### 3. Environment Variables

Copy these to Railway Variables:

```bash
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=<YOUR_OPENAI_KEY>           # SECRET!
AI_MODEL=gpt-4o-mini
AI_TEMPERATURE=0.7
AI_MAX_TOKENS=1000

STT_ENABLED=true
STT_MODEL=whisper-1
STT_LANGUAGE=ru
STT_MAX_FILE_SIZE_MB=25

STORAGE_TYPE=json
PORT=8080
DEBUG=false
CORS_ORIGINS=https://ebay-connector-app.pages.dev
```

### 4. Deploy & Get URL

- [ ] Deploy → Wait for completion
- [ ] Copy public URL (e.g., `https://assistant-widget-production.up.railway.app`)

### 5. Update Cloudflare Pages

- [ ] Cloudflare Pages → Settings → Environment Variables
- [ ] Add: `VITE_CHAT_WIDGET_BASE_URL=<railway-url>`
- [ ] Redeploy frontend

---

## 📝 Environment Variables Summary

| Variable | Example | Used In | Secret? |
|----------|---------|---------|---------|
| `AI_API_KEY` | `sk-proj-...` | Backend | ✅ YES |
| `STT_ENABLED` | `true` | Backend | No |
| `STT_MODEL` | `whisper-1` | Backend | No |
| `STT_LANGUAGE` | `ru` | Backend | No |
| `CORS_ORIGINS` | `https://...` | Backend | No |
| `VITE_CHAT_WIDGET_BASE_URL` | `https://assistant-widget...` | Frontend | No |

---

## 📚 Documentation

**Full Documentation**: [docs/assistant-widget-voice-stt-2025-12-09.md](file:///c:/dev/ebay-connector-app/docs/assistant-widget-voice-stt-2025-12-09.md)

Contents:
- Architecture diagrams
- API endpoint reference (with curl examples)
- Deployment guide
- Troubleshooting
- Browser compatibility
- Cost estimates
- Future enhancements

---

## 🧪 Verification Steps

### Backend

```powershell
# After deploying to Railway
curl https://assistant-widget.up.railway.app/health
# Expected: {"status": "healthy", "storage": "json"}

curl https://assistant-widget.up.railway.app/api/stt/status
# Expected: {"enabled": true, "model": "whisper-1", "default_language": "ru"}
```

### Frontend

1. Visit production eBay Connector App
2. Open browser DevTools (F12) → Console
3. Look for: `AI Chat Widget: Loaded successfully from https://...`
4. Widget button should appear bottom-right

### STT

```powershell
# Create test audio file (5-10 sec of Russian speech)
# Then test:
curl -X POST https://assistant-widget.up.railway.app/api/stt/transcribe \
  -F "file=@test_russian.webm" \
  -F "lang=ru"

# Expected: {"text": "...", "lang": "ru", "provider": "openai"}
```

---

## ⚠️ Important Notes

1. **API Key Security**:
   - NEVER commit `.env` files (already in `.gitignore`)
   - Store `AI_API_KEY` only in Railway Variables
   - Monitor OpenAI usage in dashboard

2. **CORS Configuration**:
   - Set `CORS_ORIGINS` to your actual Cloudflare Pages domain
   - Don't use `*` in production

3. **Browser Requirements**:
   - Voice input requires Chrome 90+, Edge 90+, or Firefox 88+
   - HTTPS required (or localhost for testing)

---

## 📋 Next Steps

### Immediate (Before Deployment)

1. ✅ Code implementation complete
2. ⏳ Get OpenAI API key with Whisper access
3. ⏳ Create Railway service `assistant-widget`
4. ⏳ Configure environment variables
5. ⏳ Deploy and test

### Post-Deployment

1. Test voice input with real Russian phrases
2. Monitor OpenAI costs and usage
3. Collect user feedback
4. Add eBay Connector knowledge base to widget context

### Future Enhancements

- TTS (voice responses)
- Multi-language auto-detection
- Conversation analytics
- Telegram alerts for escalations

---

## 🆘 Troubleshooting

**Widget doesn't appear**:
- Check `VITE_CHAT_WIDGET_BASE_URL` is set
- Rebuild frontend: `npm run build`
- Check browser console for errors

**Microphone button missing**:
- Use supported browser (Chrome/Edge/Firefox)
- Ensure HTTPS (or localhost)

**STT returns empty**:
- Speak clearly and loudly
- Record for at least 2-3 seconds
- Check Railway logs for errors

**Full troubleshooting guide**: See [documentation](file:///c:/dev/ebay-connector-app/docs/assistant-widget-voice-stt-2025-12-09.md#troubleshooting)

---

## 📞 Support

- **Implementation Questions**: Review [walkthrough.md](file:///C:/Users/filip/.gemini/antigravity/brain/37977971-d3fe-4e99-9205-9daf495b8375/walkthrough.md)
- **API Reference**: See [documentation](file:///c:/dev/ebay-connector-app/docs/assistant-widget-voice-stt-2025-12-09.md)
- **Railway Logs**: `railway logs --service assistant-widget`

---

**Status**: ✅ Implementation complete, ready for deployment!
