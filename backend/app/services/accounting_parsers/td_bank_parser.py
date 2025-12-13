"""
TD Bank PDF Parser — Deterministic PDF-to-JSON parser (no OpenAI).

This parser extracts transactions from TD Bank PDF statements and converts them
to the canonical Bank Statement v1.0 JSON format.

Architecture note:
- This is one of potentially many bank-specific parsers
- All parsers must produce BankStatementV1 output
- The parser registry (see bottom of file) allows dynamic selection by bank_code
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple, Dict, Any
from io import BytesIO

from app.utils.logger import logger
from .bank_statement_schema import (
    BankStatementV1,
    BankStatementSourceV1,
    BankStatementMetadataV1,
    BankStatementSummaryV1,
    BankStatementTransactionV1,
    BankSectionCode,
    TransactionDirection,
    AccountingGroup,
    ClassificationCode,
    TransactionStatus,
)


# ============================================================================
# TD Bank PDF Structure Constants
# NOTE: local deterministic parser, no OpenAI/LLM involved.
# ============================================================================

# Section headers in TD Bank statements (DAILY ACCOUNT ACTIVITY)
TD_SECTION_HEADERS = {
    # Some statements use generic "Deposits" before the detailed Electronic Deposits
    "Deposits": BankSectionCode.ELECTRONIC_DEPOSIT,
    "Electronic Deposits": BankSectionCode.ELECTRONIC_DEPOSIT,
    "Other Credits": BankSectionCode.OTHER_CREDIT,
    "Checks Paid": BankSectionCode.CHECKS_PAID,
    "Electronic Payments": BankSectionCode.ELECTRONIC_PAYMENT,
    "Other Withdrawals": BankSectionCode.OTHER_WITHDRAWAL,
    "Service Charges/Fees": BankSectionCode.SERVICE_CHARGE,
    "Interest Earned": BankSectionCode.INTEREST_EARNED,
}

# Section direction mapping
SECTION_DIRECTION = {
    BankSectionCode.ELECTRONIC_DEPOSIT: TransactionDirection.CREDIT,
    BankSectionCode.OTHER_CREDIT: TransactionDirection.CREDIT,
    BankSectionCode.INTEREST_EARNED: TransactionDirection.CREDIT,
    BankSectionCode.CHECKS_PAID: TransactionDirection.DEBIT,
    BankSectionCode.ELECTRONIC_PAYMENT: TransactionDirection.DEBIT,
    BankSectionCode.OTHER_WITHDRAWAL: TransactionDirection.DEBIT,
    BankSectionCode.SERVICE_CHARGE: TransactionDirection.DEBIT,
    BankSectionCode.UNKNOWN: TransactionDirection.DEBIT,
}

# Regex patterns for TD Bank statement parsing
PATTERNS = {
    # Account number: Primary Acct#: 123456789 or ****1234 or 625-2192140
    "account_number": re.compile(r'Primary\s*Account\s*[#:]?\s*[*]*([\d*-]+)', re.IGNORECASE),
    
    # Statement period: Flexible pattern for TD Bank quirks
    # Handles: "Aug 01 2025", "Aug 012025" (no space), "Jan 31,2025", "Aug 01 2025 through Aug 31 2025"
    # Key fix: (?:\s*,?\s*|\s*) allows NO space between day and year (e.g., "Jan 012025")
    "period_dates": re.compile(
        r'(\w{3,9})\s+(\d{1,2})(?:\s*,?\s*|\s*)(\d{4})?\s*(?:[-–]|to|through)\s*(\w{3,9})\s+(\d{1,2})(?:\s*,?\s*|\s*)(\d{4})?',
        re.IGNORECASE
    ),
    
    # Debug pattern: capture raw Statement Period line for diagnostics
    "period_any": re.compile(r'Statement\s*Period[:\s]+(.{0,100})', re.IGNORECASE),
    
    # Account owner name (usually all caps after address)
    "owner": re.compile(r'^([A-Z][A-Z\s&.,-]+(?:LLC|INC|CORP|CO)?)\s*$', re.MULTILINE),
    
    # Beginning/Ending balance - flexible spacing, handles $ sign and various formats
    "beginning_balance": re.compile(r'Beginning\s+Balance\s*[\$]?\s*(-?[\d,]+\.\d{2})', re.IGNORECASE),
    "ending_balance": re.compile(r'Ending\s+Balance\s*[\$]?\s*(-?[\d,]+\.\d{2})', re.IGNORECASE),
    
    # Transaction line: date + description + amount
    "transaction_line": re.compile(
        r'^(\d{1,2}/\d{1,2})\s+(.+?)\s+([\d,]+\.\d{2})$',
        re.MULTILINE
    ),
    # Check number pattern: CHECK 1234, Check No. 1234, Check 1234
    "check_line": re.compile(
        r'^(\d{1,2}/\d{1,2})\s+(?:CHECK|CHK)(?:\s+(?:NO\.?|#)?)?\s*(\d+)\s+([\d,]+\.\d{2})$',
        re.IGNORECASE | re.MULTILINE
    ),
    # Summary section totals - handle plural/singular forms
    "electronic_deposits": re.compile(r'Electronic\s+Deposits?\s+([\d,]+\.\d{2})', re.IGNORECASE),
    "other_credits": re.compile(r'Other\s+Credits?\s+([\d,]+\.\d{2})', re.IGNORECASE),
    "checks_paid": re.compile(r'Checks?\s+Paid\s+([\d,]+\.\d{2})', re.IGNORECASE),
    "electronic_payments": re.compile(r'Electronic\s+Payments?\s+([\d,]+\.\d{2})', re.IGNORECASE),
    "other_withdrawals": re.compile(r'Other\s+Withdrawals?\s+([\d,]+\.\d{2})', re.IGNORECASE),
    "service_charges": re.compile(r'Service\s+Charges?(?:/Fees?)?\s+([\d,]+\.\d{2})', re.IGNORECASE),
    "interest_earned": re.compile(r'Interest\s+Earned\s+([\d,]+\.\d{2})', re.IGNORECASE),
}


# ============================================================================
# PARSER CLASS
# ============================================================================

class TDBankPDFParser:
    """
    TD Bank statement PDF parser.
    
    Uses pdfplumber for text extraction and regex-based parsing.
    No AI/LLM dependencies.
    """
    
    def __init__(self, pdf_bytes: bytes, source_filename: Optional[str] = None):
        self.pdf_bytes = pdf_bytes
        self.source_filename = source_filename or "td_statement.pdf"
        self.pages_text: List[str] = []
        self.full_text: str = ""
        self.parsing_notes: List[str] = []
        
    def _extract_text(self) -> None:
        """Extract text from all PDF pages using pdfplumber.
        
        Uses layout=True and tolerance settings to preserve proper column order
        (left-to-right, top-to-bottom) which is critical for TD Bank's two-column format.
        """
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError(
                "pdfplumber is required for TD Bank PDF parsing. "
                "Install it with: pip install pdfplumber"
            )
        
        with pdfplumber.open(BytesIO(self.pdf_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                # Use layout=True to preserve proper reading order (left-to-right)
                # x_tolerance and y_tolerance help group characters correctly
                text = page.extract_text(x_tolerance=2, y_tolerance=3, layout=True) or ""
                self.pages_text.append(text)
                logger.debug(f"TD PDF Parser: Extracted {len(text)} chars from page {page_num}")
        
        self.full_text = "\n\n".join(self.pages_text)
        logger.info(f"TD PDF Parser: Total text length: {len(self.full_text)} chars from {len(self.pages_text)} pages")
        
        # Log first 3 pages text for debugging header parsing issues
        for i, page_text in enumerate(self.pages_text[:3], start=1):
            preview = page_text[:2000]
            logger.info(f"TD PDF Parser: Page {i} preview (2000 chars):\n{preview}")
    
    def _parse_date(self, date_str: str, year: int) -> Optional[date]:
        """Parse a date string like '01/05' with inferred year."""
        try:
            # Format: MM/DD
            parts = date_str.split('/')
            if len(parts) == 2:
                month = int(parts[0])
                day = int(parts[1])
                return date(year, month, day)
        except (ValueError, IndexError):
            pass
        
        # Try full date formats
        for fmt in ['%B %d, %Y', '%B %d %Y', '%m/%d/%Y', '%m/%d/%y']:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        
        return None
    
    def _parse_date_flexible(self, date_str: str) -> Optional[date]:
        """Parse date string flexibly, handling TD Bank quirks like 'Apr 302025' (no space)."""
        if not date_str:
            return None
            
        date_str = date_str.strip()
        
        # Month name mapping
        month_map = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
            'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6,
            'jul': 7, 'july': 7, 'aug': 8, 'august': 8, 'sep': 9, 'september': 9,
            'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12,
        }
        
        # Try standard formats first
        for fmt in ['%B %d, %Y', '%B %d %Y', '%b %d, %Y', '%b %d %Y', '%m/%d/%Y']:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        # Handle TD Bank format: "Apr 302025" (month day_merged_with_year)
        # Pattern: Month DayYear where day is 1-2 digits and year is 4 digits
        match = re.match(r'(\w+)\s+(\d{1,2})(\d{4})', date_str, re.IGNORECASE)
        if match:
            month_str = match.group(1).lower()
            day = int(match.group(2))
            year = int(match.group(3))
            month = month_map.get(month_str)
            if month and 1 <= day <= 31 and 2000 <= year <= 2100:
                try:
                    return date(year, month, day)
                except ValueError:
                    pass
        
        # Handle format with space: "Apr 30 2025"
        match = re.match(r'(\w+)\s+(\d{1,2})\s*,?\s*(\d{4})', date_str, re.IGNORECASE)
        if match:
            month_str = match.group(1).lower()
            day = int(match.group(2))
            year = int(match.group(3))
            month = month_map.get(month_str)
            if month and 1 <= day <= 31 and 2000 <= year <= 2100:
                try:
                    return date(year, month, day)
                except ValueError:
                    pass
        
        logger.warning(f"TD PDF Parser: Could not parse date: '{date_str}'")
        return None
    
    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parse an amount string like '1,500.00' to Decimal."""
        try:
            cleaned = amount_str.replace(',', '').replace('$', '').strip()
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None
    
    def _extract_metadata(self) -> BankStatementMetadataV1:
        """Extract statement metadata from header text.
        
        Searches first 3 pages (not just 3000 chars) to handle varying PDF layouts.
        """
        # Month name mapping
        month_map = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
            'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6,
            'jul': 7, 'july': 7, 'aug': 8, 'august': 8, 'sep': 9, 'september': 9,
            'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12,
        }
        
        # Search in first 3 pages (handles pdfplumber extraction order issues)
        header_text = "\n".join(self.pages_text[:3]) if self.pages_text else self.full_text[:10000]
        logger.info(f"TD PDF Parser: Header search area: {len(header_text)} chars from first 3 pages")
        
        # Account number
        account_match = PATTERNS["account_number"].search(header_text)
        account_number = account_match.group(1) if account_match else "UNKNOWN"
        logger.info(f"TD PDF Parser: Account number match: {account_number}")
        
        # Mask account number if not already masked
        if len(account_number) > 4 and not account_number.startswith('*'):
            account_number = "****" + account_number[-4:]
        
        # Statement period - find date range pattern
        period_start = None
        period_end = None
        
        # Try main period_dates pattern first
        period_match = PATTERNS["period_dates"].search(header_text)
        logger.info(f"TD PDF Parser: period_dates match: {period_match}")
        
        if period_match:
            # Groups: (start_month, start_day, start_year_opt, end_month, end_day, end_year_opt)
            start_month_str = period_match.group(1).lower()
            start_day = int(period_match.group(2))
            start_year_str = period_match.group(3)  # May be None
            end_month_str = period_match.group(4).lower()
            end_day = int(period_match.group(5))
            end_year_str = period_match.group(6)  # May be None
            
            # Parse years - start year may be missing, infer from end year
            end_year = int(end_year_str) if end_year_str else date.today().year
            start_year = int(start_year_str) if start_year_str else end_year
            
            start_month = month_map.get(start_month_str)
            end_month = month_map.get(end_month_str)
            
            logger.info(f"TD PDF Parser: Parsed period components: {start_month_str}/{start_day}/{start_year} - {end_month_str}/{end_day}/{end_year}")
            
            if start_month and end_month:
                try:
                    period_start = date(start_year, start_month, start_day)
                    period_end = date(end_year, end_month, end_day)
                    logger.info(f"TD PDF Parser: Found period {period_start} to {period_end}")
                except ValueError as e:
                    logger.warning(f"TD PDF Parser: Invalid date values: {e}")
        
        # Fallback: try period_any debug pattern to see raw period string
        if not period_start or not period_end:
            any_match = PATTERNS["period_any"].search(header_text)
            if any_match:
                raw_period = any_match.group(1).strip()
                logger.warning(f"TD PDF Parser: period_dates failed, but found raw period string: '{raw_period}'")
                self.parsing_notes.append(f"DEBUG: Raw period string found: '{raw_period}'")
        
        if not period_start or not period_end:
            self.parsing_notes.append("WARNING: Could not extract statement period from header")
            logger.warning("TD PDF Parser: Could not extract statement period - using fallback dates")
            today = date.today()
            period_start = period_start or date(today.year, today.month, 1)
            period_end = period_end or today
        
        # Account owner (first capital name block found)
        owner_match = PATTERNS["owner"].search(header_text)
        owner = owner_match.group(1).strip() if owner_match else "Unknown"
        
        logger.info(f"TD PDF Parser: Metadata - period {period_start} to {period_end}, account {account_number}, owner {owner}")
        
        return BankStatementMetadataV1(
            bank_name="TD Bank",
            product_name="TD Business Checking Account",
            account_owner=owner,
            primary_account_number=account_number,
            statement_period_start=period_start,
            statement_period_end=period_end,
            currency="USD",
        )
    
    def _extract_summary(self) -> BankStatementSummaryV1:
        """Extract ACCOUNT SUMMARY section totals.

        TD Bank format: Beginning/Ending Balance are inline in ACCOUNT SUMMARY.
        Category totals appear as "Subtotal:" at end of each transaction section.
        
        Example:
            Beginning Balance -1,258.02
            ...
            Ending Balance    -966.22
            
            Electronic Deposits
            POSTING DATE DESCRIPTION        AMOUNT
            08/01 RTP RCVD...              2,948.26
            ...
                                 Subtotal: 15,138.33
        """
        results: Dict[str, Optional[Decimal]] = {}
        
        # Find ACCOUNT SUMMARY section
        summary_match = re.search(r'ACCOUNT\s+SUMMARY', self.full_text, re.IGNORECASE)
        summary_text = ""
        if summary_match:
            summary_start = summary_match.start()
            activity_match = re.search(r'DAILY\s+ACCOUNT\s+ACTIVITY', self.full_text, re.IGNORECASE)
            summary_end = activity_match.start() if activity_match else summary_start + 2000
            summary_text = self.full_text[summary_start:summary_end]
            logger.info(f"TD PDF Parser: Found ACCOUNT SUMMARY section ({len(summary_text)} chars)")
        else:
            logger.warning(f"TD PDF Parser: ACCOUNT SUMMARY section not found!")
            summary_text = self.full_text[:3000]  # Use first part as fallback
        
        # ---- 1. Beginning & Ending Balance ----
        # Format in ACCOUNT SUMMARY: "Beginning Balance    4,569.84"
        # Try summary section first, then full text as fallback
        for search_text in [summary_text, self.full_text]:
            if results.get("beginning") is None:
                beg_match = re.search(r'Beginning\s+Balance\s+(-?[\d,]+\.\d{2})', search_text, re.IGNORECASE)
                if beg_match:
                    results["beginning"] = self._parse_amount(beg_match.group(1))
                    logger.info(f"TD PDF Parser: Beginning Balance = {results['beginning']}")
            
            if results.get("ending") is None:
                end_match = re.search(r'Ending\s+Balance\s+(-?[\d,]+\.\d{2})', search_text, re.IGNORECASE)
                if end_match:
                    results["ending"] = self._parse_amount(end_match.group(1))
                    logger.info(f"TD PDF Parser: Ending Balance = {results['ending']}")
        
        # ---- 2. Section Totals from ACCOUNT SUMMARY header ----
        # TD Bank format: "Electronic Deposits    56,052.29" (direct value after label)
        # These appear in the ACCOUNT SUMMARY block, NOT as "Subtotal:" lines
        summary_patterns = {
            "electronic_deposits": r'Electronic\s+Deposits?\s+([\d,]+\.\d{2})',
            "other_credits": r'Other\s+Credits?\s+([\d,]+\.\d{2})',
            "checks_paid": r'Checks?\s+Paid\s+([\d,]+\.\d{2})',
            "electronic_payments": r'Electronic\s+Payments?\s+([\d,]+\.\d{2})',
            "other_withdrawals": r'Other\s+Withdrawals?\s+([\d,]+\.\d{2})',
            "service_charges": r'Service\s+Charges?\s+([\d,]+\.\d{2})',
            "interest_earned": r'Interest\s+Earned\s+([\d,]+\.\d{2})',
        }
        
        # Search ONLY in the ACCOUNT SUMMARY section (NOT with DOTALL across whole document!)
        for key, pattern in summary_patterns.items():
            match = re.search(pattern, summary_text, re.IGNORECASE)
            if match:
                amt = self._parse_amount(match.group(1))
                if amt is not None:
                    results[key] = amt
                    logger.info(f"TD PDF Parser: {key} = {amt}")
        
        # ---- 3. Log findings ----
        found_count = sum(1 for v in results.values() if v is not None)
        logger.info(f"TD PDF Parser: Extracted {found_count} summary fields from ACCOUNT SUMMARY")
        
        if results.get("beginning") is None:
            self.parsing_notes.append("WARNING: Could not extract Beginning Balance")
        if results.get("ending") is None:
            self.parsing_notes.append("WARNING: Could not extract Ending Balance")

        return BankStatementSummaryV1(
            beginning_balance=results.get("beginning") or Decimal("0.00"),
            ending_balance=results.get("ending") or Decimal("0.00"),
            electronic_deposits_total=results.get("electronic_deposits"),
            other_credits_total=results.get("other_credits"),
            checks_paid_total=results.get("checks_paid"),
            electronic_payments_total=results.get("electronic_payments"),
            other_withdrawals_total=results.get("other_withdrawals"),
            service_charges_fees_total=results.get("service_charges"),
            interest_earned_total=results.get("interest_earned"),
        )
    
    def _extract_transactions(self, metadata: BankStatementMetadataV1) -> List[BankStatementTransactionV1]:
        """Extract all transactions from DAILY ACCOUNT ACTIVITY sections.

        TD Bank transactions can span 1-3 lines:
        - Line 1: MM/DD + start of description (+ maybe amount)
        - Lines 2-3: continuation of description
        - Last line may have amount at the end

        Sections: Electronic Deposits (+), Other Credits (+), Checks Paid (-),
                  Electronic Payments (-), Other Withdrawals (-), Service Charges (-)
        """
        transactions: List[BankStatementTransactionV1] = []
        txn_id = 0

        year = metadata.statement_period_start.year

        current_section = BankSectionCode.UNKNOWN

        # Get transaction block - everything from first DAILY ACCOUNT ACTIVITY
        # Need to handle multi-page documents where this header repeats
        text_upper = self.full_text.upper()
        
        # Remove known non-transaction sections before parsing
        # These sections appear on various pages and pollute transaction extraction
        cleanup_patterns = [
            r'HOW\s+TO\s+BALANCE\s+YOUR\s+ACCOUNT.*?(?=DAILY\s+ACCOUNT\s+ACTIVITY|DAILY\s+BALANCE\s+SUMMARY|$)',
            r'FOR\s+CONSUMER\s+ACCOUNTS\s+ONLY.*?(?=DAILY\s+ACCOUNT\s+ACTIVITY|DAILY\s+BALANCE\s+SUMMARY|Page:|$)',
            r'INTEREST\s+NOTICE.*?(?=DAILY\s+ACCOUNT\s+ACTIVITY|DAILY\s+BALANCE\s+SUMMARY|Page:|$)',
            r'DAILY\s+BALANCE\s+SUMMARY.*?(?=Page:|DAILY\s+ACCOUNT\s+ACTIVITY|$)',
        ]
        
        cleaned_text = self.full_text
        for pattern in cleanup_patterns:
            cleaned_text = re.sub(pattern, ' ', cleaned_text, flags=re.IGNORECASE | re.DOTALL)
        
        # Find ALL DAILY ACCOUNT ACTIVITY sections (they repeat on each page)
        # and merge all blocks between them and the next DAILY BALANCE SUMMARY
        activity_pattern = re.compile(r'DAILY\s+ACCOUNT\s+ACTIVITY', re.IGNORECASE)
        balance_pattern = re.compile(r'DAILY\s+BALANCE\s+SUMMARY', re.IGNORECASE)
        
        activity_matches = list(activity_pattern.finditer(cleaned_text))
        balance_matches = list(balance_pattern.finditer(cleaned_text))
        
        logger.info(f"TD PDF Parser: Found {len(activity_matches)} DAILY ACCOUNT ACTIVITY sections and {len(balance_matches)} DAILY BALANCE SUMMARY sections")
        
        tx_blocks = []
        for i, activity_match in enumerate(activity_matches):
            start_idx = activity_match.start()
            
            # Find the nearest DAILY BALANCE SUMMARY after this activity section
            end_idx = len(cleaned_text)
            for balance_match in balance_matches:
                if balance_match.start() > start_idx:
                    end_idx = balance_match.start()
                    break
            
            # Also check if there's another DAILY ACCOUNT ACTIVITY before the balance summary
            # (i.e., the balance summary is on a different page)
            if i + 1 < len(activity_matches):
                next_activity = activity_matches[i + 1].start()
                if next_activity < end_idx:
                    end_idx = next_activity
            
            block = cleaned_text[start_idx:end_idx]
            tx_blocks.append(block)
            logger.debug(f"TD PDF Parser: Activity block {i+1}: {len(block)} chars")
        
        # Combine all blocks
        if tx_blocks:
            tx_block = "\n".join(tx_blocks)
        else:
            logger.warning("TD PDF Parser: No DAILY ACCOUNT ACTIVITY section found, using full text")
            tx_block = cleaned_text
        
        logger.info(f"TD PDF Parser: Combined transaction block is {len(tx_block)} chars from {len(tx_blocks)} sections")

        lines = tx_block.split('\n')

        # Date pattern - more flexible, just needs digit/digit at start
        date_re = re.compile(r'^(\d{1,2}/\d{1,2})\b')
        amount_re = re.compile(r'([\d,]+\.\d{2})')
        
        # Check line pattern - multiple formats, may contain several checks on one line:
        # - #331 03/31 $4,000.00
        # - #1234 03/31   $4,000.00   #1235 03/31   $2,000.00
        # We capture ALL occurrences (#num date amount) in a single line.
        check_re = re.compile(r'#\s*(\d+)\s+(\d{1,2}/\d{1,2})\s+[\$\s]*([\d,]+\.\d{2})')
        
        # Pattern for daily balance lines: amount followed by date
        daily_balance_re = re.compile(r'^\d[\d,]*\.\d{2}\s+\d{1,2}/\d{1,2}')

        # Buffer for current transaction being built
        current_txn: Optional[Dict[str, Any]] = None

        def flush_transaction():
            """Process buffered transaction and add to list."""
            nonlocal current_txn, txn_id

            if not current_txn:
                return

            date_str = current_txn["date_str"]
            txn_lines = current_txn["lines"]
            section_at_start = current_txn["section"]

            if not txn_lines:
                current_txn = None
                return

            # Join all lines
            full_text = " ".join(txn_lines)
            
            # Skip if this looks like a daily balance entry
            if daily_balance_re.search(full_text):
                logger.debug(f"TD PDF Parser: Skipping daily balance line: {full_text[:50]}")
                current_txn = None
                return
            
            # Skip page headers and other non-transaction content
            skip_keywords = [
                "STATEMENTOFACCOUNT", "STATEMENT OF ACCOUNT",
                "PAGE:", "PAGE :", "OF 28", "OF 31", "OF 27",
                "MILLER SELLS IT LLC",
                "HOW TO BALANCE", "BALANCE YOUR ACCOUNT",
                "FOR CONSUMER ACCOUNTS", "ELECTRONIC FUND TRANSFER",
                "INTEREST NOTICE", "TOTAL INTEREST",
                "PRIMARY ACCOUNT", "CUST REF",
                "CALL 1-800", "BANK DEPOSITS FDIC",
                "TD BANK", "AMERICA'S MOST CONVENIENT",
                "DAILY BALANCE SUMMARY", "DATE BALANCE DATE",
                "BEGINNING BALANCE", "ENDING BALANCE",
                "SUBTOTAL:", "TOTAL FOR THIS CYCLE",
            ]
            full_text_upper = full_text.upper().replace(' ', '')
            if any(kw.replace(' ', '') in full_text_upper for kw in skip_keywords):
                logger.debug(f"TD PDF Parser: Skipping non-transaction line: {full_text[:80]}")
                current_txn = None
                return
            
            # Skip if text is too long (likely garbage from page merging)
            # Increased from 500 to 800 to handle long vendor names
            if len(full_text) > 800:
                logger.debug(f"TD PDF Parser: Skipping overly long line ({len(full_text)} chars)")
                current_txn = None
                return
            
            amounts = amount_re.findall(full_text)

            if not amounts:
                current_txn = None
                return

            # Last amount is the transaction amount
            amount_str = amounts[-1]
            amount = self._parse_amount(amount_str)

            if amount is None:
                current_txn = None
                return

            # Remove amount from description (last occurrence)
            description = full_text
            last_amount_idx = description.rfind(amount_str)
            if last_amount_idx != -1:
                description = description[:last_amount_idx] + description[last_amount_idx + len(amount_str):]

            # Clean up description
            description = re.sub(r'\s+', ' ', description).strip()
            description = description.rstrip(',').strip()
            
            # Skip if description is just numbers/dates (daily balance line leaked through)
            if re.match(r'^[\d,\s./]+$', description):
                current_txn = None
                return

            if not description or len(description) < 5:
                current_txn = None
                return

            posting_date = self._parse_date(date_str, year)
            if not posting_date:
                current_txn = None
                return

            txn_id += 1

            # Determine section and direction
            inferred_section = section_at_start
            desc_upper = description.upper().replace(' ', '')

            # Fallback inference if section unknown
            if inferred_section == BankSectionCode.UNKNOWN:
                if any(kw in desc_upper for kw in ["CCDDEPOSIT", "ACHDEPOSIT", "ACHCREDIT", "POSCREDIT", "DEBITCARDCREDIT", "PAYPAL"]):
                    inferred_section = BankSectionCode.ELECTRONIC_DEPOSIT
                elif "RETURNEDITEM" in desc_upper or "ODGRACEFEEREFUND" in desc_upper:
                    inferred_section = BankSectionCode.OTHER_CREDIT
                elif any(kw in desc_upper for kw in ["DBCRDPUR", "DEBITPOS", "DEBITCARD", "ELECTRONICPMT"]):
                    inferred_section = BankSectionCode.ELECTRONIC_PAYMENT
                elif any(kw in desc_upper for kw in ["SERVICECHARGE", "MAINTENANCEFEE", "OVERDRAFTPD"]):
                    inferred_section = BankSectionCode.SERVICE_CHARGE
                elif "CHECK" in desc_upper or "CHK" in desc_upper:
                    inferred_section = BankSectionCode.CHECKS_PAID

            direction = SECTION_DIRECTION.get(inferred_section, TransactionDirection.DEBIT)

            # Apply sign based on direction
            if direction == TransactionDirection.DEBIT:
                amount = -abs(amount)
            else:
                amount = abs(amount)

            bank_subtype = self._extract_subtype(description)

            check_number = None
            check_match = re.search(r'(?:CHECK|CHK)\s*#?\s*(\d+)', description, re.IGNORECASE)
            if check_match:
                check_number = check_match.group(1)

            txn = BankStatementTransactionV1(
                id=txn_id,
                posting_date=posting_date,
                description=description,
                amount=amount,
                bank_section=inferred_section,
                bank_subtype=bank_subtype,
                direction=direction,
                accounting_group=AccountingGroup.OTHER,
                classification=ClassificationCode.UNKNOWN,
                status=TransactionStatus.OK,
                check_number=check_number,
                description_raw=description,
            )
            transactions.append(txn)
            current_txn = None

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            line_upper = line.upper()
            
            # Skip known non-transaction header/footer lines
            skip_line_patterns = [
                "POSTING DATE", "CALL 1-800", "BANK DEPOSITS FDIC",
                "STATEMENT OF ACCOUNT", "STATEMENTOFACCOUNT",
                "PRIMARY ACCOUNT", "CUST REF", "PAGE:",
                "TD BANK", "AMERICA'S MOST",
                "HOW TO BALANCE", "FOR CONSUMER",
                "DAILY BALANCE SUMMARY", "DATE BALANCE",
                "MILLER SELLS IT", "VERDUN NY",
                "ACCOUNT SUMMARY", "TOTAL FOR THIS",
                "GRACE PERIOD", "INTEREST NOTICE",
            ]
            if any(p in line_upper for p in skip_line_patterns):
                continue
            # Skip subtotal lines
            if "SUBTOTAL:" in line_upper or line_upper.startswith("SUBTOTAL"):
                continue
            # Skip lines that are just page numbers or dates
            if re.match(r'^(\d+\s+of\s+\d+|\d{1,2}/\d{1,2}/\d{2,4})$', line, re.IGNORECASE):
                continue

            # Check for section headers - look for key phrases anywhere in line
            # IMPORTANT: Order matters - check longer keywords first to avoid partial matches
            section_changed = False
            
            # Section header keywords - LONGEST FIRST to avoid "Deposits" matching "Electronic Deposits"
            section_keywords = [
                ("ELECTRONIC DEPOSITS", BankSectionCode.ELECTRONIC_DEPOSIT),
                ("ELECTRONIC PAYMENTS", BankSectionCode.ELECTRONIC_PAYMENT),
                ("OTHER WITHDRAWALS", BankSectionCode.OTHER_WITHDRAWAL),
                ("SERVICE CHARGES", BankSectionCode.SERVICE_CHARGE),
                ("INTEREST EARNED", BankSectionCode.INTEREST_EARNED),
                ("OTHER CREDITS", BankSectionCode.OTHER_CREDIT),
                ("CHECKS PAID", BankSectionCode.CHECKS_PAID),
                # Plain "DEPOSITS" last (after Electronic Deposits checked)
                ("DEPOSITS", BankSectionCode.ELECTRONIC_DEPOSIT),
            ]
            
            # Normalize line for matching (remove spaces between words)
            line_upper_nospace = line_upper.replace(' ', '')
            
            for keyword, section_code in section_keywords:
                keyword_nospace = keyword.replace(' ', '')
                # Check both with and without spaces
                if keyword in line_upper or keyword_nospace in line_upper_nospace:
                    # Make sure it's a header, not a transaction (no leading date)
                    # Allow headers that might have "POSTING DATE" or "AMOUNT" merged
                    if not date_re.match(line):
                        current_section = section_code
                        section_changed = True
                        logger.info(f"TD PDF Parser: --> Entering section {section_code.value} (matched: {keyword})")
                        break
            
            if section_changed:
                continue

            # Check if line starts with date (new transaction)
            date_match = date_re.match(line)
            if date_match:
                # Flush previous transaction
                flush_transaction()

                # Start new transaction
                date_str = date_match.group(1)
                rest_of_line = line[date_match.end():].strip()
                current_txn = {
                    "date_str": date_str,
                    "lines": [rest_of_line] if rest_of_line else [],
                    "section": current_section,
                }
            else:
                # Check for check line(s): can include multiple checks in one line
                check_matches = list(check_re.finditer(line))
                if check_matches:
                    # Flush previous transaction
                    flush_transaction()

                    for cm in check_matches:
                        check_num = cm.group(1)
                        check_date = cm.group(2)
                        check_amount = cm.group(3)

                        posting_date = self._parse_date(check_date, year)
                        if not posting_date:
                            continue

                        amount = self._parse_amount(check_amount)
                        if amount is None:
                            continue

                        # Checks are debits
                        amount = -abs(amount)
                        txn_id += 1

                        txn = BankStatementTransactionV1(
                            id=txn_id,
                            posting_date=posting_date,
                            description=f"CHECK #{check_num}",
                            amount=amount,
                            bank_section=BankSectionCode.CHECKS_PAID,
                            bank_subtype="CHECK",
                            direction=TransactionDirection.DEBIT,
                            accounting_group=AccountingGroup.OTHER,
                            classification=ClassificationCode.UNKNOWN,
                            status=TransactionStatus.OK,
                            check_number=check_num,
                            description_raw=line,
                        )
                        transactions.append(txn)
                elif current_txn is not None:
                    # Continuation line
                    current_txn["lines"].append(line)

        # Flush last transaction
        flush_transaction()

        # Log section distribution
        from collections import Counter
        section_counts = Counter(t.bank_section for t in transactions)
        logger.info(f"TD PDF Parser: Extracted {len(transactions)} transactions. Sections: {dict(section_counts)}")
        
        return transactions
    
    def _extract_subtype(self, description: str) -> Optional[str]:
        """Extract subtype from description (e.g., 'CCD DEPOSIT', 'ACH DEBIT')."""
        subtypes = [
            "CCD DEPOSIT", "CCD CREDIT", "CCD DEBIT",
            "ACH DEPOSIT", "ACH DEBIT", "ACH CREDIT", "ACH PAYMENT",
            "WIRE TRANSFER", "WIRE IN", "WIRE OUT",
            "MOBILE DEPOSIT", "REMOTE DEPOSIT",
            "ONLINE TRANSFER", "FUNDS TRANSFER",
            "CHECK", "CHK", "COUNTER CHECK",
            "DEBIT CARD", "POS PURCHASE",
            "ATM WITHDRAWAL", "ATM DEPOSIT",
            "SERVICE CHARGE", "MAINTENANCE FEE",
            "INTEREST PAYMENT",
        ]
        
        desc_upper = description.upper()
        for subtype in subtypes:
            if subtype in desc_upper:
                return subtype
        
        return None
    
    def _verify_totals(
        self,
        summary: BankStatementSummaryV1,
        transactions: List[BankStatementTransactionV1]
    ) -> Tuple[bool, str]:
        """Verify transaction totals match summary."""
        credits = sum(t.amount for t in transactions if t.amount > 0)
        debits = sum(t.amount for t in transactions if t.amount < 0)
        
        expected_net = summary.ending_balance - summary.beginning_balance
        actual_net = credits + debits  # debits are negative
        
        diff = abs(expected_net - actual_net)
        
        if diff < Decimal("0.01"):
            return True, "Totals match exactly"
        elif diff < Decimal("1.00"):
            return True, f"Totals match within $1.00 (diff: ${diff})"
        else:
            return False, f"Balance mismatch: expected net ${expected_net}, actual ${actual_net}, diff ${diff}"
    
    def parse(self) -> BankStatementV1:
        """
        Parse the PDF and return a BankStatementV1 object.
        
        Raises:
            RuntimeError: If PDF cannot be parsed
        """
        try:
            # Extract text
            self._extract_text()
            
            if not self.full_text.strip():
                raise RuntimeError("PDF appears to be empty or unreadable")
            
            # Extract components
            metadata = self._extract_metadata()
            summary = self._extract_summary()
            transactions = self._extract_transactions(metadata)
            
            # Verify totals
            verified, verify_msg = self._verify_totals(summary, transactions)
            
            if not verified:
                self.parsing_notes.append(f"WARNING: {verify_msg}")
                logger.warning(f"TD PDF Parser: {verify_msg}")
            
            # Build source info
            source = BankStatementSourceV1(
                statement_type="BANK_ACCOUNT",
                bank_name="TD Bank",
                bank_code="TD",
                generated_by="td_pdf_parser_v1",
                generated_from_pdf=self.source_filename,
                parsing_timestamp=datetime.utcnow().isoformat() + "Z",
            )
            
            result = BankStatementV1(
                schema_version="1.0",
                source=source,
                statement_metadata=metadata,
                statement_summary=summary,
                transactions=transactions,
                parsing_notes="; ".join(self.parsing_notes) if self.parsing_notes else None,
                verification_passed=verified,
                verification_message=verify_msg,
            )
            
            logger.info(
                f"TD PDF Parser: Successfully parsed statement for "
                f"{metadata.primary_account_number} "
                f"({metadata.statement_period_start} to {metadata.statement_period_end}), "
                f"{len(transactions)} transactions"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"TD PDF Parser: Failed to parse PDF: {e}")
            raise RuntimeError(f"Failed to parse TD Bank PDF: {e}")


# ============================================================================
# PUBLIC API
# ============================================================================

def parse_td_pdf_to_bank_statement_v1(pdf_bytes: bytes, source_filename: Optional[str] = None) -> BankStatementV1:
    """
    Parse a TD Bank PDF statement and return BankStatementV1.
    
    This is the main entry point for TD Bank PDF parsing.
    Does NOT use OpenAI or any AI/LLM.
    
    Args:
        pdf_bytes: Raw PDF file content
        source_filename: Optional original filename for tracking
        
    Returns:
        BankStatementV1: Parsed statement in canonical format
        
    Raises:
        RuntimeError: If parsing fails
    """
    parser = TDBankPDFParser(pdf_bytes, source_filename)
    return parser.parse()


# ============================================================================
# PARSER REGISTRY — Multi-bank support
# ============================================================================

# Registry of parsers by bank code
# Future banks can be added here without modifying existing code
PDF_PARSER_REGISTRY: Dict[str, Any] = {
    "TD": parse_td_pdf_to_bank_statement_v1,
    # Future parsers:
    # "BOA": parse_boa_pdf_to_bank_statement_v1,
    # "CITI": parse_citi_pdf_to_bank_statement_v1,
    # "CHASE": parse_chase_pdf_to_bank_statement_v1,
}


def get_available_bank_parsers() -> List[str]:
    """Return list of supported bank codes for PDF parsing."""
    return list(PDF_PARSER_REGISTRY.keys())


def parse_pdf_by_bank_code(bank_code: str, pdf_bytes: bytes, source_filename: Optional[str] = None) -> BankStatementV1:
    """
    Parse a PDF statement using the appropriate bank parser.
    
    Args:
        bank_code: Bank code (e.g., 'TD', 'BOA')
        pdf_bytes: Raw PDF content
        source_filename: Optional original filename
        
    Returns:
        BankStatementV1: Parsed statement
        
    Raises:
        ValueError: If bank_code is not supported
        RuntimeError: If parsing fails
    """
    parser_func = PDF_PARSER_REGISTRY.get(bank_code.upper())
    if not parser_func:
        available = ", ".join(get_available_bank_parsers())
        raise ValueError(f"No PDF parser available for bank code '{bank_code}'. Available: {available}")
    
    return parser_func(pdf_bytes, source_filename)
