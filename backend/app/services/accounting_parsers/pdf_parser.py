from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Any, Dict

import httpx
from app.config import settings
from app.utils.logger import logger

@dataclass
class ParsedTransaction:
    """Unified parsed transaction model for ledger imports from PDFs.

    This mirrors the structure we use for CSV/XLSX parsing so that future PDF
    parsers (TD, Relay, other banks) can plug into the same pipeline.
    """

    txn_date: Optional[date]
    posted_date: Optional[date]
    amount: Decimal  # signed; expense < 0, income > 0
    currency: Optional[str]
    description_raw: str
    counterparty: Optional[str] = None
    external_txn_id: Optional[str] = None
    source_suffix: str = "PDF"
    balance_after: Optional[Decimal] = None
    row_index: Optional[int] = None


async def parse_pdf_bytes(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """Parse a PDF statement into a list of dicts (compatible with CSV/XLSX parser output).
    
    Uses a two-layer approach:
    1. Mechanical text extraction using pdfplumber.
    2. AI-powered structuring using OpenAI to convert raw text into structured JSON.
    """
    
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber not installed")
        raise RuntimeError("PDF parsing requires 'pdfplumber' library.")

    # 1. Extract text from PDF
    full_text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
    except Exception as e:
        logger.error(f"Failed to extract text from PDF: {e}")
        raise RuntimeError(f"Failed to extract text from PDF: {e}")

    if not full_text.strip():
        logger.warning("PDF extraction resulted in empty text")
        return []

    # 2. Send to OpenAI for structuring
    # We process in chunks if the text is too long, but for MVP we'll try to process the first few pages 
    # or a reasonable character limit to avoid context limits. 
    # A typical bank statement page is ~2-3k chars. 10 pages ~30k chars. 
    # GPT-4o context is large enough, but we should be mindful of cost/latency.
    # Let's truncate to ~20k chars for safety/speed for now, or split if needed.
    
    # For this implementation, we will try to parse the whole text if < 30k chars, 
    # otherwise we might need a more sophisticated chunking strategy.
    
    truncated_text = full_text[:30000] 
    if len(full_text) > 30000:
        logger.warning("PDF text truncated to 30000 chars for AI processing")

    api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    model = settings.OPENAI_MODEL or "gpt-4o"
    base_url = (settings.OPENAI_API_BASE_URL or "https://api.openai.com").rstrip("/")

    system_prompt = (
        "You are a specialized banking data extraction assistant. "
        "Your task is to extract financial transactions from the provided bank statement text. "
        "Return a STRICT JSON object with a single key 'transactions' containing a list of objects. "
        "Each object MUST have: "
        "'date' (YYYY-MM-DD), "
        "'description' (string), "
        "'amount' (number, negative for outflow/debit, positive for inflow/credit), "
        "'currency' (string, e.g. USD, EUR), "
        "'balance' (number, optional running balance). "
        "Ignore headers, footers, and summary sections. Only extract line item transactions. "
        "If the year is missing in the date, assume the current year or infer from context if possible. "
        "Do not include markdown formatting."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Bank Statement Text:\n\n{truncated_text}"},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}, 
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"OpenAI API request failed: {e}")
        raise RuntimeError(f"OpenAI API request failed: {e}")

    # 3. Parse JSON response
    try:
        result = json.loads(content)
        transactions = result.get("transactions", [])
    except json.JSONDecodeError:
        logger.error("Failed to parse OpenAI JSON response")
        raise RuntimeError("AI returned invalid JSON")

    # 4. Convert to internal dict format compatible with accounting router
    parsed_rows = []
    for idx, txn in enumerate(transactions, start=1):
        parsed_rows.append({
            "__index__": idx,
            "date": txn.get("date"),
            "description": txn.get("description"),
            "amount": txn.get("amount"),
            "currency": txn.get("currency"),
            "balance": txn.get("balance"),
        })

    return parsed_rows

# Keep stubs for backward compatibility if needed, or remove them.
def parse_td_pdf(pdf_bytes: bytes) -> List[ParsedTransaction]:
    raise NotImplementedError("Use parse_pdf_bytes instead")

def parse_relay_pdf(pdf_bytes: bytes) -> List[ParsedTransaction]:
    raise NotImplementedError("Use parse_pdf_bytes instead")

def parse_generic_pdf(pdf_bytes: bytes) -> List[ParsedTransaction]:
    raise NotImplementedError("Use parse_pdf_bytes instead")
