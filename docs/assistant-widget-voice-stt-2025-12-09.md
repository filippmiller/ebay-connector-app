# AI Chat Widget with Russian Voice Input (STT)

**Created**: 2025-12-09  
**Status**: Implemented & Ready for Deployment  
**Version**: 1.0.0

---

## Overview

The eBay Connector App now features an AI-powered chat assistant with **Russian voice input** (Speech-to-Text). Users can interact with the assistant by typing text or speaking in Russian, and receive intelligent responses powered by OpenAI.

### Key Features

- 🎤 **Russian Voice Input**: Speak naturally in Russian, powered by OpenAI Whisper
- 💬 **Text Chat**: Traditional text-based conversation
- 🌐 **Universal Widget**: Appears on all eBay Connector pages
- 📱 **Responsive Design**: Works on desktop and mobile
- 🔒 **Secure**: API keys stored only in Railway Variables
- 🚀 **Scalable**: Separate Railway service for easy scaling

---

## Architecture

```mermaid
graph LR
    A[User Browser] -->|Voice/Text| B[Chat Widget JS]
    B -->|Audio Blob| C[Railway Backend]
    C -->|Transcribe| D[OpenAI Whisper API]
    D -->|Text| C
    C -->|Text| B
    B -->|Chat Message| C
    C -->|AI Response| E[OpenAI Chat API]
    E -->|Response| C
    C -->|Response| B
    B -->|Display| A
```

### Components

1. **Frontend Widget** (`external/ai-chat-widget/widget/widget.js`)
   - Floating chat button (bottom-right)
   - Chat window with message history
   - Microphone button for voice input
   - MediaRecorder API for audio capture

2. **Backend Service** (`external/ai-chat-widget/backend/`)
   - FastAPI application
   - Endpoints: `/api/chat/message`, `/api/stt/transcribe`, `/widget/widget.js`
   - OpenAI integration (Chat Completions + Audio Transcriptions)
   - JSON file storage (chat history)

3. **eBay Connector Integration** (`frontend/src/main.tsx`)
   - Dynamic script loading
   - Environment-based configuration
   - Appears on all pages

---

## STT (Speech-to-Text) Flow

```mermaid
sequenceDiagram
    participant User
    participant Widget as Widget (JS)
    participant Backend as Railway Backend
    participant OpenAI as OpenAI Whisper

    User->>Widget: Click microphone button
    Widget->>User: Request microphone permission
    User->>Widget: Grant permission
    Widget->>Widget: Start MediaRecorder
    Note over Widget: Recording (red pulsing button)
    User->>Widget: Speak in Russian
    User->>Widget: Click stop recording
    Widget->>Widget: Create audio Blob (webm/ogg)
    Widget->>Backend: POST /api/stt/transcribe (FormData)
    Backend->>OpenAI: POST /v1/audio/transcriptions
    OpenAI->>Backend: {"text": "распознанный текст"}
    Backend->>Widget: {"text": "распознанный текст", "lang": "ru"}
    Widget->>Widget: Insert text into input field
    User->>Widget: Review/Edit text
    User->>Widget: Send message
```

---

## Environment Variables

### Backend (`external/ai-chat-widget/backend/.env`)

```bash
# === AI Provider (OpenAI) ===
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=<your-openai-api-key>  # KEEP SECRET!
AI_MODEL=gpt-4o-mini
AI_TEMPERATURE=0.7
AI_MAX_TOKENS=1000

# === Speech-to-Text ===
STT_ENABLED=true
STT_MODEL=whisper-1
# Alternative: STT_MODEL=gpt-4o-mini-transcribe
STT_LANGUAGE=ru
STT_MAX_FILE_SIZE_MB=25

# === Storage ===
STORAGE_TYPE=json
# For Postgres: STORAGE_TYPE=postgres
# DATABASE_URL=postgresql://user:password@host:5432/dbname

# === Server ===
PORT=8080
DEBUG=false
CORS_ORIGINS=https://ebay-connector-app.pages.dev,https://your-cloudflare-domain.com

# === Optional: Telegram Alerts ===
# TELEGRAM_BOT_TOKEN=123456789:ABCdef...
# TELEGRAM_CHAT_ID=your_chat_id
```

### Frontend (`frontend/.env`)

```bash
VITE_CHAT_WIDGET_BASE_URL=https://assistant-widget.up.railway.app
```

**For Cloudflare Pages**: Set this variable in Cloudflare Pages dashboard under Settings → Environment Variables.

---

## API Endpoints

### 1. Widget JavaScript

```
GET /widget/widget.js
```

**Response**: JavaScript file for the chat widget.

**Usage**:
```html
<script src="https://assistant-widget.up.railway.app/widget/widget.js"></script>
```

---

### 2. Chat Message

```
POST /api/chat/message
```

**Request**:
```json
{
  "session_id": "s_1234567890_abc123",
  "message": "Привет! Покажи мои заказы",
  "page_context": {
    "url": "https://app.example.com/orders",
    "title": "Orders Page",
    "meta_description": "",
    "headings": { "h1": ["Orders"], "h2": [] },
    "selected_text": ""
  }
}
```

**Response**:
```json
{
  "reply": "Здравствуйте! Я могу помочь вам с заказами. Что конкретно вас интересует?",
  "session_id": "s_1234567890_abc123"
}
```

---

### 3. Speech-to-Text (STT)

```
POST /api/stt/transcribe
```

**Request**: `multipart/form-data`
- `file`: Audio file (webm, ogg, mp3, mp4)
- `lang`: Language code (default: `ru`)

**Response**:
```json
{
  "text": "покажи мои заказы за вчера",
  "lang": "ru",
  "provider": "openai",
  "model": "whisper-1"
}
```

**Example (curl)**:
```bash
curl -X POST https://assistant-widget.up.railway.app/api/stt/transcribe \
  -F "file=@audio_test.webm" \
  -F "lang=ru"
```

---

### 4. STT Status

```
GET /api/stt/status
```

**Response**:
```json
{
  "enabled": true,
  "model": "whisper-1",
  "default_language": "ru",
  "max_file_size_mb": 25
}
```

---

### 5. Health Check

```
GET /health
```

**Response**:
```json
{
  "status": "healthy",
  "storage": "json"
}
```

---

## Railway Deployment

### Step 1: Create Railway Service

1. Go to [Railway Dashboard](https://railway.app/dashboard)
2. Select your project (eBay Connector App)
3. Click "+ New Service" → "GitHub Repo"
4. Select repository: `filippmiller/ebay-connector-app`
5. Name: `assistant-widget`

### Step 2: Configure Service

**Root Directory**: `external/ai-chat-widget/backend`

**Start Command**:
```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**Build Command** (if needed):
```bash
pip install -r requirements.txt
```

### Step 3: Set Environment Variables

In Railway service settings → Variables:

| Variable | Value | Secret? |
|----------|-------|---------|
| `AI_BASE_URL` | `https://api.openai.com/v1` | No |
| `AI_API_KEY` | `sk-proj-...` | ✅ YES |
| `AI_MODEL` | `gpt-4o-mini` | No |
| `AI_TEMPERATURE` | `0.7` | No |
| `AI_MAX_TOKENS` | `1000` | No |
| `STT_ENABLED` | `true` | No |
| `STT_MODEL` | `whisper-1` | No |
| `STT_LANGUAGE` | `ru` | No |
| `STT_MAX_FILE_SIZE_MB` | `25` | No |
| `STORAGE_TYPE` | `json` | No |
| `PORT` | `8080` | No |
| `DEBUG` | `false` | No |
| `CORS_ORIGINS` | `https://ebay-connector-app.pages.dev` | No |

### Step 4: Deploy

Railway will automatically deploy. Wait for deployment to complete.

### Step 5: Get Public URL

Copy the public URL (e.g., `https://assistant-widget-production.up.railway.app`)

### Step 6: Update Cloudflare Pages

In Cloudflare Pages → Settings → Environment Variables:

```bash
VITE_CHAT_WIDGET_BASE_URL=https://assistant-widget-production.up.railway.app
```

Redeploy frontend.

---

## Local Development Testing

### Backend

```bash
cd external/ai-chat-widget/backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Create .env from .env.example
cp .env.example .env
# Edit .env with your OPENAI_API_KEY

# Run server
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Visit: `http://localhost:8080/docs`

### Frontend

```bash
cd frontend

# Add to .env
echo "VITE_CHAT_WIDGET_BASE_URL=http://localhost:8080" >> .env

# Run frontend
npm run dev
```

Visit: `http://localhost:5173`

The widget should appear in bottom-right corner.

---

## Testing Voice Input

### Prerequisites

- Modern browser: Chrome 90+, Edge 90+, or Firefox 88+
- Microphone connected
- HTTPS connection (or localhost)

### Test Steps

1. **Open eBay Connector App** in browser
2. **Click widget button** (bottom-right)
3. **Click microphone icon** in chat input
4. **Grant microphone permission** when prompted
5. **Speak clearly in Russian**: "Привет, покажи мои заказы"
6. **Click microphone again** to stop recording
7. **Verify**: Text appears in input field
8. **Edit if needed**, then send

### Expected Behavior

| Step | Visual Feedback |
|------|-----------------|
| Idle | Gray microphone icon |
| Recording | Red pulsing microphone icon |
| Processing | Typing indicator (3 dots) |
| Success | Text in input field |
| Error | Error message in chat |

---

##Browser Compatibility

### Voice Input (MediaRecorder API)

| Browser | Version | Support |
|---------|---------|---------|
| Chrome | 90+ | ✅ Full |
| Edge | 90+ | ✅ Full |
| Firefox | 88+ | ✅ Full |
| Safari | 14.1+ | ⚠️ Limited (webm not supported) |
| Opera | 76+ | ✅ Full |

### Fallback

- If voice input is not supported, microphone button is hidden
- Text chat continues to work normally

---

## Limitations

| Limitation | Value | Notes |
|------------|-------|-------|
| Max audio file size | 25 MB | OpenAI limit |
| Max recording duration | ~60 seconds | Recommended (no hard limit in widget) |
| Supported formats | webm, ogg, mp3, mp4 | Browser-dependent |
| Language | Russian (primary) | Widget can be configured for other languages |
| Rate limiting | OpenAI account limits | Based on your OpenAI plan |
| Storage | JSON files | Can be upgraded to Postgres if needed |

---

## Troubleshooting

### Widget doesn't appear

**Check**:
1. `VITE_CHAT_WIDGET_BASE_URL` is set in frontend `.env`
2. Frontend was rebuilt after adding environment variable
3. Browser console for errors (F12 → Console)

**Solution**:
```bash
cd frontend
npm run build
```

### Microphone button missing

**Check**:
1. Browser supports MediaRecorder API
2. Page is served over HTTPS (or localhost)

**Solution**: Use supported browser (Chrome/Edge/Firefox)

### "Permission denied" error

**Check**:
1. Microphone is connected
2. Microphone permission granted in browser settings

**Solution**:
- Chrome: Address bar → Lock icon → Site settings → Microphone → Allow
- Firefox: Address bar → Camera icon → Permissions → Microphone → Allow

### STT returns empty text

**Check**:
1. Speak clearly and loudly
2. Recording duration is at least 2-3 seconds
3. Background noise is minimal

**Solution**: Try speaking closer to microphone

### 503 Error "STT not enabled"

**Check**:
1. Backend `.env` has `STT_ENABLED=true`
2. Railway service was redeployed after adding variable

**Solution**:
```bash
# In Railway dashboard
# Variables → Add STT_ENABLED=true
# Deploy → Redeploy
```

---

## Future Enhancements

### Planned Features

- [ ] **TTS (Text-to-Speech)**: Voice responses from AI
- [ ] **Multi-language support**: Auto-detect language, support English/Russian/Ukrainian
- [ ] **Conversation export**: Download chat history as PDF/TXT
- [ ] **Knowledge base integration**: Load eBay Connector docs into widget context
- [ ] **Voice commands**: "Clear history", "Call agent", etc.
- [ ] **Analytics**: Track usage, popular questions, STT accuracy
- [ ] **Persistent storage**: Migrate to Postgres for production
- [ ] **Push notifications**: Telegram alerts for high-value questions
- [ ] **Custom branding**: eBay Connector colors and logo

### Technical Improvements

- [ ] **Optimize audio encoding**: Reduce file size before upload
- [ ] **Streaming STT**: Real-time transcription as you speak
- [ ] **Offline mode**: Cache responses for common questions
- [ ] **A/B testing**: Test different AI models and prompts
- [ ] **RAG integration**: Connect to eBay Connector database for context-aware responses

---

## Security Notes

✅ **DO**:
- Store `AI_API_KEY` only in Railway Variables (never in code)
- Use HTTPS for production
- Set specific `CORS_ORIGINS` (don't use `*` in production)
- Monitor OpenAI usage and set billing limits

❌ **DON'T**:
- Commit `.env` files to git (already in `.gitignore`)
- Log API keys to console or Railway logs
- Expose backend URL publicly without rate limiting
- Store sensitive user data in chat history (if applicable)

---

## Cost Estimates

### OpenAI API Usage

**Chat (gpt-4o-mini)**:
- Input: $0.150 / 1M tokens
- Output: $0.600 / 1M tokens
- ~100 messages/day × 200 tokens/message = ~140K tokens/month = **~$0.02-$0.10/month**

**STT (whisper-1)**:
- $0.006 / minute
- ~50 voice messages/day × 10 seconds/message = ~85 minutes/month = **~$0.50/month**

**Total estimated cost**: **$0.50-$1.00/month** (low usage)

### Railway Costs

- Hobby plan: $5/month (500 execution hours)
- Pro plan: $20/month (unlimited execution hours)

**Widget backend**: Lightweight, ~1-2% CPU usage, **fits in Hobby plan**.

---

## Support

For issues or questions:
1. Check Railway logs: `railway logs --service assistant-widget`
2. Check browser console (F12 → Console)
3. Review this documentation
4. Contact dev team

---

## Changelog

### v1.0.0 (2025-12-09)
- ✅ Initial implementation
- ✅ Russian voice input (OpenAI Whisper)
- ✅ Text chat (OpenAI gpt-4o-mini)
- ✅ Railway deployment ready
- ✅ Frontend integration (eBay Connector)
- ✅ Browser compatibility checks
- ✅ Error handling and user feedback
