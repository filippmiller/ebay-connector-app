from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional, Any, Dict

from openai import AsyncOpenAI
from app.config import settings
from app.utils.logger import logger

@dataclass
class ParsedTransaction:
    """Unified parsed transaction model for ledger imports from PDFs."""
    txn_date: Optional[date]
    posted_date: Optional[date]
    amount: Decimal
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
    bank_name: Optional[str] = None
    account_last4: Optional[str] = None
    currency: Optional[str] = None
    period_start: Optional[str] = None  # YYYY-MM-DD
    period_end: Optional[str] = None    # YYYY-MM-DD
    transactions: List[Dict[str, Any]] = field(default_factory=list)
    raw_text_length: int = 0
    parsing_notes: Optional[str] = None
    raw_json: Optional[Dict[str, Any]] = None


async def parse_pdf_bytes(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """Legacy wrapper."""
    result = await parse_pdf_with_metadata(pdf_bytes)
    return result.transactions


async def parse_pdf_with_metadata(pdf_bytes: bytes) -> ParsedStatementResult:
    """
    Parse a PDF statement using OpenAI Assistants API (v2).
    
    Flow:
    1. Upload file to OpenAI.
    2. Create a temporary Assistant (or use a specialized one) to analyze the file.
    3. Run the thread.
    4. Retrieve and parse JSON output.
    5. Delete the file.
    """
    
    api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    client = AsyncOpenAI(api_key=api_key)
    
    # 1. Upload File
    openai_file = None
    try:
        logger.info("Uploading PDF to OpenAI for analysis...")
        openai_file = await client.files.create(
            file=("bank_statement.pdf", pdf_bytes, "application/pdf"),
            purpose="assistants"
        )
    except Exception as e:
        logger.error(f"Failed to upload file to OpenAI: {e}")
        raise RuntimeError(f"OpenAI File Upload failed: {e}")

    assistant = None
    try:
        # 2. Create Temporary Assistant
        # We create a new one to ensure exact instructions, but in prod you might cache this ID.
        logger.info(f"Creating temporary assistant for analysis (File ID: {openai_file.id})...")
        
        system_instruction = """
You are an expert banking data extraction system. Your job is to extract structured data from the attached bank statement PDF.
You must analyze the document (using OCR/Vision/File Search capabilities) and output the data in a STRICT JSON format.

OUTPUT FORMAT:
Return ONLY a valid JSON object. Do not wrap it in markdown code blocks like ```json ... ```. 
The JSON must adhere to this schema:

{
  "metadata": {
    "bank_name": "Name of the bank (e.g. Chase, TD, Relay, Bank of America)",
    "account_last4": "Last 4 digits of account number (or null if not found)",
    "currency": "Currency code (USD, EUR, etc.)",
    "period_start": "YYYY-MM-DD (Statement Start Date)",
    "period_end": "YYYY-MM-DD (Statement End Date)"
  },
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "description": "Full transaction description",
      "amount": number (Float. Negative for debits/expenses, Positive for credits/deposits),
      "balance": number (Running balance if available, or null)
    }
  ]
}

EXTRACTION RULES:
1. Extract ALL transactions visible in the statement tables. Do not summarize.
2. Ensure the 'amount' sign is correct based on the 'Debit'/'Credit' columns or section headers.
   - Withdrawals/Checks/Fees -> Negative
   - Deposits/Transfers In -> Positive
3. If the date in the row doesn't have a year, use the statement period to determine the correct year.
4. If multiple accounts are present, extract transactions for the MAIN checking/savings account.
"""

        assistant = await client.beta.assistants.create(
            name="Bank Statement Parser Temp",
            instructions=system_instruction,
            tools=[{"type": "file_search"}], # Enable file search to "read" the document
            model=settings.OPENAI_MODEL or "gpt-4o",
        )

        # 3. Create Thread
        thread = await client.beta.threads.create(
            messages=[
                {
                    "role": "user",
                    "content": "Extract the data from the attached bank statement PDF into JSON format.",
                    "attachments": [
                        {
                            "file_id": openai_file.id,
                            "tools": [{"type": "file_search"}]
                        }
                    ]
                }
            ]
        )

        # 4. Run and Poll
        logger.info(f"Running assistant on Thread {thread.id}...")
        run = await client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant.id,
            timeout=180.0  # Allow 3 mins for reading large PDFs
        )

        if run.status != 'completed':
            logger.error(f"Assistant run failed with status: {run.status}")
            if run.last_error:
                logger.error(f"Run error: {run.last_error}")
            raise RuntimeError(f"OpenAI Assistant failed to process document: {run.status}")

        # 5. Get Messages
        messages_page = await client.beta.threads.messages.list(
            thread_id=thread.id,
            order="desc",
            limit=1
        )
        
        if not messages_page.data:
            raise RuntimeError("No response from Assistant")
            
        first_msg = messages_page.data[0]
        if first_msg.role != "assistant":
            raise RuntimeError("Last message was not from assistant")
            
        # Extract text content
        response_text = ""
        for block in first_msg.content:
            if block.type == "text":
                response_text += block.text.value

        # Clean markdown if present
        cleaned_json = response_text.replace("```json", "").replace("```", "").strip()
        
        try:
            data = json.loads(cleaned_json)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON returned by assistant: {cleaned_json[:500]}")
            raise RuntimeError("Assistant returned invalid JSON")

        # 6. Parse Result
        metadata = data.get("metadata", {})
        transactions_raw = data.get("transactions", [])
        
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

        logger.info(f"OpenAI Assistant extraction complete. Found {len(parsed_rows)} transactions.")
        
        return ParsedStatementResult(
            bank_name=metadata.get("bank_name"),
            account_last4=metadata.get("account_last4"),
            currency=metadata.get("currency"),
            period_start=metadata.get("period_start"),
            period_end=metadata.get("period_end"),
            transactions=parsed_rows,
            raw_text_length=0, # Not applicable
            parsing_notes="Processed via OpenAI Assistants API",
            raw_json=data,
        )

    finally:
        # Cleanup Resources
        if openai_file:
            try:
                await client.files.delete(openai_file.id)
                logger.info("Deleted temporary input file.")
            except Exception as e:
                logger.warning(f"Failed to delete temporary file: {e}")
        
        if assistant:
            try:
                await client.beta.assistants.delete(assistant.id)
                logger.info("Deleted temporary assistant.")
            except Exception as e:
                logger.warning(f"Failed to delete temporary assistant: {e}")
