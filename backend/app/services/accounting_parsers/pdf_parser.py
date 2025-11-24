from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional


@dataclass
class ParsedTransaction:
    """Unified parsed transaction model for ledger imports from PDFs.

    This mirrors the structure we use for CSV/XLSX parsing so that future PDF
    parsers (TD, Relay, other banks) can plug into the same pipeline.
    """

    txn_date: date
    posted_date: Optional[date]
    amount: Decimal  # signed; expense < 0, income > 0
    currency: str
    description_raw: str
    counterparty: Optional[str] = None
    external_txn_id: Optional[str] = None
    source_suffix: str = "PDF"


def parse_td_pdf(pdf_bytes: bytes) -> List[ParsedTransaction]:  # pragma: no cover - stub
    """Parse a TD Bank PDF statement into ParsedTransaction rows.

    MVP stub: real TD parsing will be implemented once we have a stable sample
    set of statements. For now this function is intentionally not wired into
    the upload/commit flow and simply signals that PDF parsing is not ready.
    """

    raise NotImplementedError(
        "TD PDF parsing is not implemented yet. "
        "This is a stub; wire it into the Accounting bank-statement workflow "
        "once real TD statement samples and rules are available."
    )


def parse_relay_pdf(pdf_bytes: bytes) -> List[ParsedTransaction]:  # pragma: no cover - stub
    """Parse a Relay PDF statement into ParsedTransaction rows (stub)."""

    raise NotImplementedError(
        "Relay PDF parsing is not implemented yet. "
        "This is a stub; wire it into the Accounting bank-statement workflow "
        "once real Relay statement samples and rules are available."
    )


def parse_generic_pdf(pdf_bytes: bytes) -> List[ParsedTransaction]:  # pragma: no cover - stub
    """Generic PDF parser stub for banks without dedicated logic yet.

    In the future this can use a text/table extraction library such as
    pdfplumber or Camelot to recover transaction tables in a best-effort way.
    For now we keep it as a clear placeholder so that workers can detect the
    lack of PDF support and mark statements with a readable error.
    """

    raise NotImplementedError(
        "Generic PDF parsing for bank statements is not implemented yet. "
        "Use CSV/XLSX exports for now; PDF support will be added in a later "
        "iteration using this module as the integration point."
    )
