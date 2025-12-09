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
        """Extract ACCOUNT SUMMARY section totals.

        Instead of relying on many independent regexes scattered across the
        whole text, we take the block between 'ACCOUNT SUMMARY' and
        'DAILY ACCOUNT ACTIVITY' and parse each line as

            <label> .... <amount>

        This is more robust against layout changes and matches exactly what is
        shown in the PDF header.
        """
        text_upper = self.full_text.upper()
        start_idx = text_upper.find("ACCOUNT SUMMARY")
        end_idx = text_upper.find("DAILY ACCOUNT ACTIVITY")
        block = ""
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            block = self.full_text[start_idx:end_idx]
        elif start_idx != -1:
            block = self.full_text[start_idx: start_idx + 2000]
        else:
            block = self.full_text

        # Default values
        beginning = Decimal("0.00")
        ending = Decimal("0.00")
        electronic_deposits_total: Optional[Decimal] = None
        other_credits_total: Optional[Decimal] = None
        checks_paid_total: Optional[Decimal] = None
        electronic_payments_total: Optional[Decimal] = None
        other_withdrawals_total: Optional[Decimal] = None
        service_charges_fees_total: Optional[Decimal] = None
        interest_earned_total: Optional[Decimal] = None

        NAME_MAP = {
            "BEGINNING BALANCE": "beginning",
            "ENDING BALANCE": "ending",
            "ELECTRONIC DEPOSITS": "electronic_deposits_total",
            "OTHER CREDITS": "other_credits_total",
            "CHECKS PAID": "checks_paid_total",
            "ELECTRONIC PAYMENTS": "electronic_payments_total",
            "OTHER WITHDRAWALS": "other_withdrawals_total",
            "SERVICE CHARGES": "service_charges_fees_total",
            "SERVICE CHARGES/FEES": "service_charges_fees_total",
            "INTEREST EARNED": "interest_earned_total",
        }

        # Allow optional leading minus and optional leading '$'
        amount_re = re.compile(r"-?[$\d,]+\.\d{2}")

        # В TD суммы могут быть на отдельной строке и/или во второй колонке.
        ordered_keys = [
            "beginning",
            "ending",
            "electronic_deposits_total",
            "other_credits_total",
            "checks_paid_total",
            "electronic_payments_total",
            "other_withdrawals_total",
            "service_charges_fees_total",
            "interest_earned_total",
        ]

        # Используем список-обёртку, чтобы писать из вложенной функции
        mut = {
            "beginning": beginning,
            "ending": ending,
            "electronic_deposits_total": electronic_deposits_total,
            "other_credits_total": other_credits_total,
            "checks_paid_total": checks_paid_total,
            "electronic_payments_total": electronic_payments_total,
            "other_withdrawals_total": other_withdrawals_total,
            "service_charges_fees_total": service_charges_fees_total,
            "interest_earned_total": interest_earned_total,
        }

        def process_fragment(fragment: str, last_label: Optional[str]) -> Optional[str]:
            frag = fragment.strip()
            if not frag:
                return last_label

            amounts = amount_re.findall(frag)

            label_upper = frag.upper().rstrip(":").strip()
            label_key = None
            for name, mapped in NAME_MAP.items():
                if label_upper.startswith(name):
                    label_key = mapped
                    break

            if label_key and not amounts:
                return label_key

            target_key = label_key or last_label
            if not target_key and ordered_keys:
                target_key = ordered_keys.pop(0)

            if amounts and target_key:
                amt_val = self._parse_amount(amounts[-1]) or Decimal("0.00")
                mut[target_key] = amt_val

            return label_key or last_label

        last_label: Optional[str] = None

        for raw_line in block.split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            fragments = re.split(r"\s{2,}", line)
            for frag in fragments:
                last_label = process_fragment(frag, last_label)

        beginning = mut["beginning"]
        ending = mut["ending"]
        electronic_deposits_total = mut["electronic_deposits_total"]
        other_credits_total = mut["other_credits_total"]
        checks_paid_total = mut["checks_paid_total"]
        electronic_payments_total = mut["electronic_payments_total"]
        other_withdrawals_total = mut["other_withdrawals_total"]
        service_charges_fees_total = mut["service_charges_fees_total"]
        interest_earned_total = mut["interest_earned_total"]

        return BankStatementSummaryV1(
            beginning_balance=beginning,
            ending_balance=ending,
            electronic_deposits_total=electronic_deposits_total,
            other_credits_total=other_credits_total,
            checks_paid_total=checks_paid_total,
            electronic_payments_total=electronic_payments_total,
            other_withdrawals_total=other_withdrawals_total,
            service_charges_fees_total=service_charges_fees_total,
            interest_earned_total=interest_earned_total,
        )
    
    def _extract_transactions(self, metadata: BankStatementMetadataV1) -> List[BankStatementTransactionV1]:
        """Extract all transactions from DAILY ACCOUNT ACTIVITY sections.

        Supports both single-line and multi-line TD layouts where description
        spans multiple lines and the amount is on the last line.
        """
        transactions: List[BankStatementTransactionV1] = []
        txn_id = 0

        year = metadata.statement_period_start.year

        current_section = BankSectionCode.UNKNOWN

        # Restrict transaction scanning to the block between DAILY ACCOUNT ACTIVITY
        # and DAILY BALANCE SUMMARY (to avoid picking up daily balance lines like
        # "-1, 816.36 09/18").
        text_upper = self.full_text.upper()
        start_idx = text_upper.find("DAILY ACCOUNT ACTIVITY")
        end_idx = text_upper.find("DAILY BALANCE SUMMARY")
        tx_block = self.full_text
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            tx_block = self.full_text[start_idx:end_idx]
        elif start_idx != -1:
            tx_block = self.full_text[start_idx:]

        lines = tx_block.split('\n')

        date_re = re.compile(r'^(\d{1,2}/\d{1,2})\b')
        amount_re = re.compile(r'-?[\d,]+\.\d{2}')

        buffer: Optional[Dict[str, Any]] = None  # {date, desc_parts, numbers}

        def flush_buffer():
            nonlocal buffer, txn_id, current_section
            if not buffer:
                return
            date_str = buffer["date"]
            desc_parts = buffer["desc_parts"]
            numbers: List[str] = buffer.get("numbers", [])

            posting_date = self._parse_date(date_str, year)
            if not posting_date:
                buffer = None
                return

            amount_val: Optional[Decimal] = None
            balance_after_val: Optional[Decimal] = None
            if numbers:
                # Последнее число — сумма; предпоследнее (если есть) трактуем как balance_after
                amount_val = self._parse_amount(numbers[-1])
                if len(numbers) >= 2:
                    balance_after_val = self._parse_amount(numbers[-2])

            description = re.sub(r"\s+", " ", " ".join(desc_parts)).strip()

            if amount_val is None:
                buffer = None
                return

            txn_id += 1

            # If section headers were not detected correctly, try to infer
            inferred_section = current_section
            desc_upper = description.upper().replace(' ', '')
            if inferred_section == BankSectionCode.UNKNOWN:
                if (
                    "CCDDEPOSIT" in desc_upper
                    or "CCDDEPOSIT" in desc_upper
                    or "ACHDEPOSIT" in desc_upper
                    or "ACHCREDIT" in desc_upper
                    or desc_upper.startswith("DEPOSIT")
                ):
                    inferred_section = BankSectionCode.ELECTRONIC_DEPOSIT
                elif any(key in desc_upper for key in ["SERVICECHARGE", "MAINTENANCEFEE", "OVERDRAFT"]):
                    inferred_section = BankSectionCode.SERVICE_CHARGE

            direction = SECTION_DIRECTION.get(inferred_section, TransactionDirection.DEBIT)
            if direction == TransactionDirection.DEBIT:
                amount_val = -abs(amount_val)
            else:
                amount_val = abs(amount_val)

            bank_subtype = self._extract_subtype(description)

            check_number = None
            check_match = re.match(r'(?:CHECK|CHK)\s+(\d+)', description, re.IGNORECASE)
            if check_match:
                check_number = check_match.group(1)

            txn = BankStatementTransactionV1(
                id=txn_id,
                posting_date=posting_date,
                description=description,
                amount=amount_val,
                bank_section=inferred_section,
                bank_subtype=bank_subtype,
                direction=direction,
                accounting_group=AccountingGroup.OTHER,
                classification=ClassificationCode.UNKNOWN,
                status=TransactionStatus.OK,
                check_number=check_number,
                balance_after=balance_after_val,
                description_raw=description,
            )
            transactions.append(txn)
            buffer = None

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            # Section headers (do not treat as transactions)
            section_switched = False
            for header, section_code in TD_SECTION_HEADERS.items():
                if header.upper() in line.upper() and not amount_re.search(line):
                    current_section = section_code
                    section_switched = True
                    break
            if section_switched:
                continue

            date_match = date_re.match(line)
            if date_match:
                # new transaction starts
                flush_buffer()
                date_str = date_match.group(1)
                rest = line[date_match.end():].strip()
                buffer = {"date": date_str, "desc_parts": [], "numbers": []}
                if rest:
                    buffer["desc_parts"].append(rest)
                    buffer["numbers"].extend(amount_re.findall(rest))
                continue

            # continuation of current transaction
            if buffer is not None:
                buffer["desc_parts"].append(line)
                buffer["numbers"].extend(amount_re.findall(line))

        # flush last
        flush_buffer()

        logger.info(f"TD PDF Parser: Extracted {len(transactions)} transactions")
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
