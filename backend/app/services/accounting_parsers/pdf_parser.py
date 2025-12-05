from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass, field
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


@dataclass
class ParsedStatementResult:
    """Result of parsing a bank statement PDF, including metadata and transactions."""
    
    # Extracted metadata
    bank_name: Optional[str] = None
    account_last4: Optional[str] = None
    currency: Optional[str] = None
    period_start: Optional[str] = None  # YYYY-MM-DD
    period_end: Optional[str] = None    # YYYY-MM-DD
    
    # Transactions
    transactions: List[Dict[str, Any]] = field(default_factory=list)
    
    # Raw text for debugging
    raw_text_length: int = 0
    parsing_notes: Optional[str] = None
    raw_json: Optional[Dict[str, Any]] = None


async def parse_pdf_bytes(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """Parse a PDF statement into a list of dicts (compatible with CSV/XLSX parser output).
    
    This is a simplified wrapper that returns just the transactions list for backward compatibility.
    Use parse_pdf_with_metadata() for full metadata extraction.
    """
    result = await parse_pdf_with_metadata(pdf_bytes)
    return result.transactions


async def parse_pdf_with_metadata(pdf_bytes: bytes) -> ParsedStatementResult:
    """Parse a PDF statement into structured data including metadata and transactions.
    
    Uses a two-layer approach:
    1. Mechanical text extraction using pdfplumber.
    2. AI-powered structuring using OpenAI to convert raw text into structured JSON.
    
    Returns:
        ParsedStatementResult with bank metadata and list of transactions.
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
        return ParsedStatementResult(raw_text_length=0, parsing_notes="Empty PDF - no text extracted")

    # 2. Send to OpenAI for structuring
    # A typical bank statement page is ~2-3k chars. 10 pages ~30k chars. 
    # GPT-4o context is large enough, but we should be mindful of cost/latency.
    
    truncated_text = full_text[:50000]  # Increased limit for better extraction
    was_truncated = len(full_text) > 50000
    if was_truncated:
        logger.warning("PDF text truncated to 50000 chars for AI processing")

    api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    model = settings.OPENAI_MODEL or "gpt-4o"
    base_url = (settings.OPENAI_API_BASE_URL or "https://api.openai.com").rstrip("/")

    system_prompt = """You are a specialized banking data extraction assistant. 
Your task is to extract both METADATA and TRANSACTIONS from the provided bank statement text.

Return a STRICT JSON object with these keys:

1. "metadata" - object containing:
   - "bank_name" (string): The name of the bank (e.g., "Chase", "Bank of America", "TD Bank", "Wells Fargo", "Capital One", "Relay")
   - "account_last4" (string or null): Last 4 digits of the account number if visible
   - "currency" (string): Primary currency (e.g., "USD", "EUR", "CAD")
   - "period_start" (string): Statement period start date in YYYY-MM-DD format
   - "period_end" (string): Statement period end date in YYYY-MM-DD format

2. "transactions" - array of objects, each with:
   - "date" (string): Transaction date in YYYY-MM-DD format
   - "description" (string): Full transaction description/memo
   - "amount" (number): Signed amount (negative for debits/expenses, positive for credits/deposits)
   - "currency" (string): Currency code if different from default
   - "balance" (number or null): Running balance after transaction if available

Important rules:
- Extract EVERY individual transaction line item
- DO NOT include summary rows, totals, or header lines
- For debits/withdrawals/payments, amount should be NEGATIVE
- For credits/deposits/refunds, amount should be POSITIVE
- If year is missing, infer from context (statement period dates)
- Do not include markdown formatting in the response"""

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
        async with httpx.AsyncClient(timeout=120.0) as client:  # Increased timeout
            resp = await client.post(
                f"{base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        logger.error("OpenAI API request timed out")
        raise RuntimeError("OpenAI API request timed out - try a smaller document")
    except Exception as e:
        logger.error(f"OpenAI API request failed: {e}")
        raise RuntimeError(f"OpenAI API request failed: {e}")

    # 3. Parse JSON response
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        logger.error("Failed to parse OpenAI JSON response")
        raise RuntimeError("AI returned invalid JSON")

    # 4. Extract metadata
    metadata = result.get("metadata", {})
    transactions_raw = result.get("transactions", [])
    
    # 5. Convert transactions to internal dict format
    parsed_rows = []
    for idx, txn in enumerate(transactions_raw, start=1):
        parsed_rows.append({
            "__index__": idx,
            "date": txn.get("date"),
            "description": txn.get("description"),
            "amount": txn.get("amount"),
            "currency": txn.get("currency") or metadata.get("currency"),
            "balance": txn.get("balance"),
        })

    # 6. Build result
    parsing_notes = None
    if was_truncated:
        parsing_notes = "Document was truncated due to size"
    
    return ParsedStatementResult(
        bank_name=metadata.get("bank_name"),
        account_last4=metadata.get("account_last4"),
        currency=metadata.get("currency"),
        period_start=metadata.get("period_start"),
        period_end=metadata.get("period_end"),
        transactions=parsed_rows,
        raw_text_length=len(full_text),
        parsing_notes=parsing_notes,
        raw_json=result,
    )

# Backward compatibility stubs - use parse_pdf_bytes or parse_pdf_with_metadata instead
def parse_td_pdf(pdf_bytes: bytes) -> List[ParsedTransaction]:
    raise NotImplementedError("Use parse_pdf_with_metadata() instead")

def parse_relay_pdf(pdf_bytes: bytes) -> List[ParsedTransaction]:
    raise NotImplementedError("Use parse_pdf_with_metadata() instead")

def parse_generic_pdf(pdf_bytes: bytes) -> List[ParsedTransaction]:
    raise NotImplementedError("Use parse_pdf_with_metadata() instead")
