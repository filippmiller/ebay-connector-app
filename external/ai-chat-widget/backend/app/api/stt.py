"""Speech-to-Text API endpoints."""

import logging
import tempfile
import os
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
import httpx

from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stt", tags=["stt"])


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    lang: str = Form(default=None)
):
    """
    Transcribe audio to text using OpenAI Whisper API.
    
    Args:
        file: Audio file (webm, ogg, mp3, mp4, etc.)
        lang: Language code (default from settings.STT_LANGUAGE)
    
    Returns:
        JSON with transcribed text
    """
    # Check if STT is enabled
    if not settings.STT_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Speech-to-text is not enabled. Set STT_ENABLED=true in .env"
        )
    
    # Validate file size
    file_size = 0
    content = await file.read()
    file_size = len(content)
    
    max_size_bytes = settings.STT_MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {settings.STT_MAX_FILE_SIZE_MB}MB"
        )
    
    # Use language from request or default
    language = lang or settings.STT_LANGUAGE
    
    logger.info(f"Transcribing audio: size={file_size} bytes, lang={language}, model={settings.STT_MODEL}")
    
    try:
        # Prepare file for OpenAI API
        # We need to save to temp file because OpenAI API expects file-like object
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename or "audio.webm")[1]) as tmp_file:
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
        
        try:
            # Call OpenAI Audio Transcriptions API
            async with httpx.AsyncClient(timeout=30.0) as client:
                # OpenAI requires multipart/form-data
                with open(tmp_file_path, "rb") as audio_file:
                    files = {
                        "file": (file.filename or "audio.webm", audio_file, file.content_type or "audio/webm")
                    }
                    data = {
                        "model": settings.STT_MODEL,
                        "language": language,
                        "response_format": "json"
                    }
                    
                    response = await client.post(
                        f"{settings.AI_BASE_URL}/audio/transcriptions",
                        headers={
                            "Authorization": f"Bearer {settings.AI_API_KEY}"
                        },
                        files=files,
                        data=data
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                        raise HTTPException(
                            status_code=response.status_code,
                            detail=f"Transcription failed: {response.text}"
                        )
                    
                    result = response.json()
                    transcribed_text = result.get("text", "")
                    
                    logger.info(f"Transcription successful: {len(transcribed_text)} chars")
                    
                    return JSONResponse(content={
                        "text": transcribed_text,
                        "lang": language,
                        "provider": "openai",
                        "model": settings.STT_MODEL
                    })
        
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_file_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file: {e}")
    
    except httpx.TimeoutException:
        logger.error("OpenAI API timeout")
        raise HTTPException(status_code=504, detail="Transcription request timed out")
    
    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@router.get("/status")
async def stt_status():
    """Get STT service status."""
    return {
        "enabled": settings.STT_ENABLED,
        "model": settings.STT_MODEL if settings.STT_ENABLED else None,
        "default_language": settings.STT_LANGUAGE if settings.STT_ENABLED else None,
        "max_file_size_mb": settings.STT_MAX_FILE_SIZE_MB if settings.STT_ENABLED else None
    }
