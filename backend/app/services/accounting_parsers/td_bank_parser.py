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
    # Account number: Primary Acct#: 123456789 or ****1234
    "account_number": re.compile(r'Primary Acct[#:]\s*[*]*([\d*]+)', re.IGNORECASE),
    # Statement period: January 1, 2025 through January 31, 2025
    "period": re.compile(
        r'(\w+ \d{1,2},?\s*\d{4})\s+(?:through|to|-)\s*(\w+ \d{1,2},?\s*\d{4})',
        re.IGNORECASE
    ),
    # Account owner name (usually all caps after address)
    "owner": re.compile(r'^([A-Z][A-Z\s&.,-]+(?:LLC|INC|CORP|CO)?)\s*$', re.MULTILINE),
    # Beginning/Ending balance
    "beginning_balance": re.compile(r'Beginning Balance\s*[\$]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    "ending_balance": re.compile(r'Ending Balance\s*[\$]?\s*([\d,]+\.\d{2})', re.IGNORECASE),
    # Transaction line: date + description + amount
    # Format: 01/05    CCD DEPOSIT EBAY COM        1,500.00
    "transaction_line": re.compile(
        r'^(\d{1,2}/\d{1,2})\s+(.+?)\s+([\d,]+\.\d{2})$',
        re.MULTILINE
    ),
    # Check number pattern: CHECK          1234        500.00
    "check_line": re.compile(
        r'^(\d{1,2}/\d{1,2})\s+(?:CHECK|CHK)\s+(\d+)\s+([\d,]+\.\d{2})$',
        re.IGNORECASE | re.MULTILINE
    ),
    # Summary section totals
    "electronic_deposits": re.compile(r'Electronic Deposits\s+([\d,]+\.\d{2})', re.IGNORECASE),
    "other_credits": re.compile(r'Other Credits\s+([\d,]+\.\d{2})', re.IGNORECASE),
    "checks_paid": re.compile(r'Checks Paid\s+([\d,]+\.\d{2})', re.IGNORECASE),
    "electronic_payments": re.compile(r'Electronic Payments\s+([\d,]+\.\d{2})', re.IGNORECASE),
    "other_withdrawals": re.compile(r'Other Withdrawals\s+([\d,]+\.\d{2})', re.IGNORECASE),
    "service_charges": re.compile(r'Service Charges/Fees\s+([\d,]+\.\d{2})', re.IGNORECASE),
    "interest_earned": re.compile(r'Interest Earned\s+([\d,]+\.\d{2})', re.IGNORECASE),
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
        """Extract text from all PDF pages using pdfplumber."""
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError(
                "pdfplumber is required for TD Bank PDF parsing. "
                "Install it with: pip install pdfplumber"
            )
        
        with pdfplumber.open(BytesIO(self.pdf_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                self.pages_text.append(text)
                logger.debug(f"TD PDF Parser: Extracted {len(text)} chars from page {page_num}")
        
        self.full_text = "\n\n".join(self.pages_text)
        logger.info(f"TD PDF Parser: Total text length: {len(self.full_text)} chars from {len(self.pages_text)} pages")
    
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
    
    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parse an amount string like '1,500.00' to Decimal."""
        try:
            cleaned = amount_str.replace(',', '').replace('$', '').strip()
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None
    
    def _extract_metadata(self) -> BankStatementMetadataV1:
        """Extract statement metadata from header text."""
        # Account number
        account_match = PATTERNS["account_number"].search(self.full_text)
        account_number = account_match.group(1) if account_match else "UNKNOWN"
        
        # Mask account number if not already masked
        if len(account_number) > 4 and not account_number.startswith('*'):
            account_number = "****" + account_number[-4:]
        
        # Statement period
        period_match = PATTERNS["period"].search(self.full_text)
        if period_match:
            start_str = period_match.group(1)
            end_str = period_match.group(2)
            period_start = self._parse_date(start_str, datetime.now().year)
            period_end = self._parse_date(end_str, datetime.now().year)
        else:
            # Fallback to current month
            today = date.today()
            period_start = date(today.year, today.month, 1)
            period_end = today
            self.parsing_notes.append("Could not extract statement period; using current month")
        
        # Account owner (first capital name block found)
        owner_match = PATTERNS["owner"].search(self.full_text[:2000])  # Search in header
        owner = owner_match.group(1).strip() if owner_match else "Unknown"
        
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
        """Extract ACCOUNT SUMMARY section totals using direct regex patterns.

        TD Bank format (two-column layout):
        Beginning Balance          4,569.84    Average Collected Balance    3,932.76
        Electronic Deposits       56,052.29    Interest Earned This Period      0.00
        ...
        """
        # Use direct regex patterns - more reliable than line parsing
        results: Dict[str, Optional[Decimal]] = {
            "beginning": None,
            "ending": None,
            "electronic_deposits_total": None,
            "other_credits_total": None,
            "checks_paid_total": None,
            "electronic_payments_total": None,
            "other_withdrawals_total": None,
            "service_charges_fees_total": None,
            "interest_earned_total": None,
        }

        # Direct patterns for each field - look for label followed by amount
        patterns = [
            (r'Beginning\s+Balance\s+(-?[\d,]+\.\d{2})', "beginning"),
            (r'Ending\s+Balance\s+(-?[\d,]+\.\d{2})', "ending"),
            (r'Electronic\s+Deposits\s+(-?[\d,]+\.\d{2})', "electronic_deposits_total"),
            (r'Other\s+Credits\s+(-?[\d,]+\.\d{2})', "other_credits_total"),
            (r'Checks\s+Paid\s+(-?[\d,]+\.\d{2})', "checks_paid_total"),
            (r'Electronic\s+Payments\s+(-?[\d,]+\.\d{2})', "electronic_payments_total"),
            (r'Other\s+Withdrawals\s+(-?[\d,]+\.\d{2})', "other_withdrawals_total"),
            (r'Service\s+Charges(?:/Fees)?\s+(-?[\d,]+\.\d{2})', "service_charges_fees_total"),
            (r'Interest\s+Earned\s+(-?[\d,]+\.\d{2})', "interest_earned_total"),
        ]

        for pattern, key in patterns:
            match = re.search(pattern, self.full_text, re.IGNORECASE)
            if match:
                amt = self._parse_amount(match.group(1))
                if amt is not None:
                    results[key] = amt
                    logger.debug(f"TD PDF Parser: Found {key} = {amt}")

        # Log what we found
        found_count = sum(1 for v in results.values() if v is not None)
        logger.info(f"TD PDF Parser: Extracted {found_count}/9 summary fields")
        
        if results["beginning"] is None:
            self.parsing_notes.append("WARNING: Could not extract Beginning Balance from summary")
        if results["ending"] is None:
            self.parsing_notes.append("WARNING: Could not extract Ending Balance from summary")

        return BankStatementSummaryV1(
            beginning_balance=results["beginning"] or Decimal("0.00"),
            ending_balance=results["ending"] or Decimal("0.00"),
            electronic_deposits_total=results["electronic_deposits_total"],
            other_credits_total=results["other_credits_total"],
            checks_paid_total=results["checks_paid_total"],
            electronic_payments_total=results["electronic_payments_total"],
            other_withdrawals_total=results["other_withdrawals_total"],
            service_charges_fees_total=results["service_charges_fees_total"],
            interest_earned_total=results["interest_earned_total"],
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

        # Get transaction block - exclude daily balance summary
        text_upper = self.full_text.upper()
        
        # Find all DAILY ACCOUNT ACTIVITY sections and exclude DAILY BALANCE SUMMARY
        tx_block_parts = []
        remaining = self.full_text
        while True:
            upper = remaining.upper()
            start_idx = upper.find("DAILY ACCOUNT ACTIVITY")
            if start_idx == -1:
                break
            
            # Find end - either next DAILY BALANCE SUMMARY or next DAILY ACCOUNT ACTIVITY
            after_start = upper[start_idx + len("DAILY ACCOUNT ACTIVITY"):]
            
            end_markers = ["DAILY BALANCE SUMMARY", "HOW TO BALANCE", "INTEREST NOTICE"]
            end_idx = len(remaining)
            for marker in end_markers:
                pos = upper.find(marker, start_idx + len("DAILY ACCOUNT ACTIVITY"))
                if pos != -1 and pos < end_idx:
                    end_idx = pos
            
            tx_block_parts.append(remaining[start_idx:end_idx])
            remaining = remaining[end_idx:]
        
        tx_block = "\n".join(tx_block_parts)
        
        if not tx_block:
            logger.warning("TD PDF Parser: No DAILY ACCOUNT ACTIVITY section found")
            return []

        lines = tx_block.split('\n')

        date_re = re.compile(r'^(\d{1,2}/\d{1,2})\s')
        amount_re = re.compile(r'([\d,]+\.\d{2})')
        
        # Pattern for daily balance lines: "DATE BALANCE DATE BALANCE" or just amounts with dates
        daily_balance_re = re.compile(r'^[\d,]+\.\d{2}\s+\d{1,2}/\d{1,2}')

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
            # Pattern: amount followed by date, or multiple amount-date pairs
            if daily_balance_re.search(full_text):
                logger.debug(f"TD PDF Parser: Skipping daily balance line: {full_text[:50]}")
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

            if not description:
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
            
            # Skip known non-transaction lines
            skip_patterns = ["POSTING DATE", "DESCRIPTION", "AMOUNT", "SUBTOTAL", "CALL 1-800", 
                           "BANK DEPOSITS FDIC", "PAGE:", "STATEMENT PERIOD"]
            if any(p in line_upper for p in skip_patterns):
                continue

            # Check for section headers - be more flexible with matching
            section_changed = False
            
            # Exact section header patterns
            section_patterns = [
                (r'^Electronic\s+Deposits', BankSectionCode.ELECTRONIC_DEPOSIT),
                (r'^Other\s+Credits', BankSectionCode.OTHER_CREDIT),
                (r'^Checks\s+Paid', BankSectionCode.CHECKS_PAID),
                (r'^Electronic\s+Payments', BankSectionCode.ELECTRONIC_PAYMENT),
                (r'^Other\s+Withdrawals', BankSectionCode.OTHER_WITHDRAWAL),
                (r'^Service\s+Charges', BankSectionCode.SERVICE_CHARGE),
                (r'^Interest\s+Earned', BankSectionCode.INTEREST_EARNED),
            ]
            
            for pattern, section_code in section_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Make sure it's a header, not a transaction (no leading date)
                    if not date_re.match(line):
                        current_section = section_code
                        section_changed = True
                        logger.debug(f"TD PDF Parser: Entering section {section_code.value}")
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
