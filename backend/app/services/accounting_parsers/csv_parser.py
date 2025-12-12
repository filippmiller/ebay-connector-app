import csv
import io
from typing import List, Dict, Any, Iterable

def _normalize_header(name: str) -> str:
    """Normalize CSV/XLSX header names to improve auto-mapping.

    This makes the CSV/XLSX parser a bit more tolerant to different export
    formats (Google Sheets, various banks, etc.).
    """
    return " ".join(name.strip().split()).lower()

def _iter_dict_rows_from_csv(text: str) -> Iterable[Dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        # Normalize keys to a stable form while keeping the original variants
        normalized: Dict[str, Any] = {}
        if raw:
            for k, v in raw.items():
                if k is None: continue # Skip None keys
                key_norm = _normalize_header(k) if isinstance(k, str) else k
                normalized[key_norm] = v.strip() if isinstance(v, str) else v
            yield normalized

def parse_csv_bytes(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Parse CSV bytes into a list of dictionaries with normalized headers."""
    text = file_bytes.decode("utf-8", errors="ignore")
    rows: List[Dict[str, Any]] = []
    for idx, raw in enumerate(_iter_dict_rows_from_csv(text), start=1):
        rows.append({"__index__": idx, **raw})
    return rows
