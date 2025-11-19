from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from bs4 import BeautifulSoup


NEWLINE_RE = re.compile(r"\n{3,}")
DIGITS_RE = re.compile(r"(\d[\d,]*)")
DATE_RE = re.compile(
    r"([A-Z][a-z]+ \d{1,2}, \d{4},? \d{1,2}:\d{2} ?(am|pm|AM|PM))",
)


def _text_from_html_node(node) -> str:
    """Return plain text from a BeautifulSoup node, treating <br> as newlines.

    We do NOT trust arbitrary HTML from buyers; everything is converted to plain
    text and later rendered as escaped text with \n -> <br> on the frontend.
    """

    if node is None:
        return ""

    parts: List[str] = []
    for child in node.descendants:
        # .name is None for NavigableString / text nodes
        if getattr(child, "name", None) is None:
            text = str(child)
            if text:
                parts.append(text)
        elif child.name == "br":
            parts.append("\n")

    text = "".join(parts)
    # Normalise runs of newlines
    text = NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def _clean_whitespace(value: str) -> str:
    return " ".join((value or "").split())


def _parse_feedback_score(text: str) -> Optional[int]:
    if not text:
        return None
    m = DIGITS_RE.search(text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_timestamp_from_text(text: str) -> Optional[str]:
    """Try to find a human-readable timestamp in the text and return ISO string.

    This is best-effort; if parsing fails we simply return None.
    """

    if not text:
        return None
    m = DATE_RE.search(text)
    if not m:
        return None
    candidate = m.group(1)
    for fmt in [
        "%B %d, %Y, %I:%M %p",
        "%B %d, %Y, %I:%M%p",
    ]:
        try:
            dt = datetime.strptime(candidate, fmt)
            return dt.isoformat()
        except ValueError:
            continue
    return None


def parse_ebay_message_body(html: str, *, our_account_username: str) -> Dict[str, Any]:
    """Parse a raw eBay message HTML body into a structured JSON-like dict.

    The parser is intentionally defensive: it only relies on a handful of
    stable ids / patterns (PrimaryMessage, MessageHistory*, UserInputtedText*,
    area7Container, ReferenceId). All user-supplied content is converted to
    plain text with newlines.
    """

    soup = BeautifulSoup(html or "", "html.parser")

    result: Dict[str, Any] = {
        "buyer": {},
        "currentMessage": {},
        "history": [],
        "order": {},
        "meta": {},
    }

    # --- Primary block / buyer info ---
    primary = soup.find(id="PrimaryMessage") or soup

    # Buyer username & feedback
    buyer_username: Optional[str] = None
    buyer_section_h1 = primary.find("h1") if primary else None
    if buyer_section_h1:
        a_tags = buyer_section_h1.find_all("a")
        if a_tags:
            buyer_username = _clean_whitespace(a_tags[0].get_text(strip=True)) or None

        feedback_score: Optional[int] = None
        if len(a_tags) > 1:
            feedback_score = _parse_feedback_score(a_tags[1].get_text(" ", strip=True))

        if buyer_username:
            result["buyer"] = {
                "username": buyer_username,
                "feedbackScore": feedback_score,
                "profileUrl": a_tags[0]["href"] if a_tags[0].has_attr("href") else None,
                "feedbackUrl": a_tags[1]["href"] if len(a_tags) > 1 and a_tags[1].has_attr("href") else None,
            }

    # Latest inbound message is usually in div#UserInputtedText under Primary
    current_div = primary.find("div", id="UserInputtedText") if primary else None
    current_text = _text_from_html_node(current_div)
    if current_text:
        author = buyer_username or "buyer"
        result["currentMessage"] = {
            "author": author,
            "direction": "inbound",
            "role": "buyer",
            "text": current_text,
            "timestamp": _parse_timestamp_from_text(current_text),
        }

    # --- Message history blocks ---
    history_entries: List[Dict[str, Any]] = []
    for tbl in soup.find_all("table", id=re.compile(r"^MessageHistory")):
        header_p = tbl.find("p")
        header_text = header_p.get_text(" ", strip=True) if header_p else ""
        header_text_lower = header_text.lower()

        author = None
        direction = "system"
        role = "system"

        # Our previous message
        if "your previous message" in header_text_lower:
            author = our_account_username
            direction = "outbound"
            role = "seller"
        else:
            a = header_p.find("a") if header_p else None
            if a:
                uname = _clean_whitespace(a.get_text(strip=True))
                if uname:
                    author = uname
                    if buyer_username and uname == buyer_username:
                        direction = "inbound"
                        role = "buyer"
                    else:
                        role = "other"

        body_div = tbl.find("div", id=re.compile(r"^UserInputtedText"))
        body_text = _text_from_html_node(body_div)
        if not body_text:
            continue

        entry: Dict[str, Any] = {
            "author": author or "system",
            "direction": direction,
            "role": role,
            "text": body_text,
        }
        ts = _parse_timestamp_from_text(body_text)
        if ts:
            entry["timestamp"] = ts
        history_entries.append(entry)

    result["history"] = history_entries

    # --- Order / item info ---
    area7 = soup.find(id="area7Container")
    if area7:
        order: Dict[str, Any] = {}

        title_link = area7.find("a")
        if title_link:
            order["title"] = _clean_whitespace(title_link.get_text(" ", strip=True))
            href = title_link.get("href")
            if href:
                order["itemUrl"] = href

        img = area7.find("img")
        if img and img.get("src"):
            order["imageUrl"] = img["src"]

        text_block = area7.get_text("\n", strip=True)
        for line in text_block.splitlines():
            line = line.strip()
            if line.startswith("Order status:"):
                order["status"] = line.split(":", 1)[1].strip()
            elif line.startswith("Item ID:"):
                order["itemId"] = line.split(":", 1)[1].strip()
            elif line.startswith("Transaction ID:"):
                order["transactionId"] = line.split(":", 1)[1].strip()
            elif line.startswith("Order number:"):
                order["orderNumber"] = line.split(":", 1)[1].strip()

        view_link = area7.find("a", string=re.compile("View order details", re.I))
        if view_link and view_link.get("href"):
            order["viewOrderUrl"] = view_link["href"]

        result["order"] = order

    # --- Meta ---
    ref_div = soup.find(id="ReferenceId")
    if ref_div:
        text = ref_div.get_text(" ", strip=True)
        if "Email reference id:" in text:
            ref = text.split("Email reference id:", 1)[1].strip()
            result["meta"]["emailReferenceId"] = ref

    return result
