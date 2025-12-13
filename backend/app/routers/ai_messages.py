from __future__ import annotations

from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models_sqlalchemy import get_db as get_db_sqla
from app.models_sqlalchemy.models import Message as EbayMessage
from app.services.auth import get_current_user
from app.models.user import User as UserModel

router = APIRouter(prefix="/api/ai/messages", tags=["ai_messages"])


class DraftReplyRequest(BaseModel):
    ebay_account_id: Optional[str] = None
    house_name: Optional[str] = None


class DraftReplyResponse(BaseModel):
    draft: str


def _build_ai_draft(message: EbayMessage, extra: Dict[str, Any]) -> str:
    """Very simple stub that builds a polite reply using message + context.

    This is intentionally provider-agnostic so we can later swap in a real
    LLM call without changing the router contract.
    """

    sender = message.sender_username or "the buyer"
    subject = (message.subject or "this message").strip()
    body_preview = (message.body or "").strip().replace("\n", " ")
    if len(body_preview) > 300:
        body_preview = body_preview[:297] + "..."

    order_id = message.order_id or extra.get("order_id")
    listing_id = message.listing_id or extra.get("listing_id")

    context_lines = []
    if order_id:
        context_lines.append(f"Order ID: {order_id}")
    if listing_id:
        context_lines.append(f"Listing ID: {listing_id}")

    context_block = "\n".join(context_lines)

    reply_lines = [
        f"Hi {sender},",
        "",
        "Thank you for your message.",
    ]

    if subject:
        reply_lines.append(f"Regarding \"{subject}\":")
    if body_preview:
        reply_lines.append(f"You wrote: \"{body_preview}\"")

    if context_block:
        reply_lines.append("")
        reply_lines.append(context_block)

    reply_lines.extend([
        "",
        "Here is a brief update:",
        "- [Fill in specific details or resolution here]",
        "",
        "Best regards,",
        "[Your name]",
    ])

    return "\n".join(reply_lines)


@router.post("/{message_id}/draft", response_model=DraftReplyResponse)
async def draft_reply(
    message_id: str,
    payload: DraftReplyRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db_sqla),
) -> DraftReplyResponse:
    """Generate a draft reply for a given ebay_messages row.

    For now this is a stub implementation that uses simple string templates
    and local context only. It is designed so that we can later plug in a
    real AI provider behind _build_ai_draft without changing the API.
    """

    message: Optional[EbayMessage] = (
        db.query(EbayMessage)
        .filter(EbayMessage.id == message_id, EbayMessage.user_id == current_user.id)
        .first()
    )

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # TODO: optionally load related order / transaction info here.
    extra: Dict[str, Any] = {}
    draft = _build_ai_draft(message, extra)

    return DraftReplyResponse(draft=draft)
