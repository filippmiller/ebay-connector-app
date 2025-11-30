from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models_sqlalchemy import get_db as get_db_sqla
from app.models.user import User
from app.services.auth import get_current_active_user
from app.utils.logger import logger


router = APIRouter(prefix="/api/ai/speech", tags=["ai_speech"])


@router.post("/deepgram", summary="Transcribe short audio snippet via Deepgram STT")
async def transcribe_with_deepgram(
    file: UploadFile = File(..., description="Audio file (e.g. webm/ogg from MediaRecorder)"),
    language: Optional[str] = Form(
        None,
        description=(
            "Optional BCP-47 language code hint for Deepgram, "
            "e.g. 'ru' or 'en'. When omitted, Deepgram will auto-detect."
        ),
    ),
    db: Session = Depends(get_db_sqla),  # noqa: ARG001 – reserved for future per-user config
    current_user: User = Depends(get_current_active_user),  # noqa: ARG001
) -> dict:
    """Proxy a short audio clip to Deepgram and return the transcript.

    Security notes:
    - The Deepgram API key is stored server-side in settings.DEEPGRAM_API_KEY
      and is NEVER exposed to the frontend.
    - The endpoint is authenticated (current_active_user) to avoid becoming
      an open STT proxy.
    - Intended for short admin/productivity snippets (few seconds). We enforce
      a basic size cap to avoid abuse.
    """

    dg_key = settings.DEEPGRAM_API_KEY
    if not dg_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DEEPGRAM_API_KEY is not configured on the backend; contact an administrator.",
        )

    # Basic size guard: reject files larger than ~5 MB.
    # MediaRecorder webm/ogg snippets for short prompts should be << this.
    raw = await file.read()
    max_bytes = 5 * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file is too large; please record a shorter snippet.",
        )

    dg_url = "https://api.deepgram.com/v1/listen"
    params = {}
    if language:
        params["language"] = language

    content_type = file.content_type or "audio/webm"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                dg_url,
                params=params,
                headers={
                    "Authorization": f"Token {dg_key}",
                    "Content-Type": content_type,
                },
                content=raw,
            )
    except httpx.HTTPError as exc:  # pragma: no cover - network failures
        logger.error("Deepgram STT request failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to contact Deepgram for speech-to-text.",
        ) from exc

    if resp.status_code >= 400:
        logger.error("Deepgram HTTP %s: %s", resp.status_code, resp.text[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Deepgram returned HTTP {resp.status_code} while transcribing audio.",
        )

    data = resp.json()

    # Deepgram response shape: results.channels[0].alternatives[0].transcript
    try:
        channels = data.get("results", {}).get("channels", [])
        alt = (channels[0].get("alternatives") or [])[0] if channels else {}
        transcript = (alt.get("transcript") or "").strip()
    except Exception:  # pragma: no cover - defensive
        logger.error("Unexpected Deepgram response structure: %s", resp.text[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Deepgram returned an unexpected response payload.",
        )

    return {"text": transcript}