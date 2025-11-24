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

    The returned dict keeps existing top-level keys (buyer, currentMessage,
    history, order, meta) and adds a "normalized" block that surfaces fields
    useful for matching against orders / cases / disputes and for driving
    the Messages grid:

        {
          "normalized": {
            "source": "EBAY_EMAIL",
            "topic": "CASE" | "RETURN" | ...,
            "subtype": "INR" | "SNAD" | ...,
            "caseId": str | None,
            "inquiryId": str | None,
            "returnId": str | None,
            "paymentDisputeId": str | None,
            "caseType": str | None,
            "caseStatus": str | None,
            "orderId": str | None,
            "orderLineItemId": str | None,
            "itemId": str | None,
            "transactionId": str | None,
            "buyerUsername": str | None,
            "sellerUsername": str | None,
            "respondBy": str | None,
            "amount": float | None,
            "currency": str | None,
            "summaryHtml": str | None,
            "summaryText": str | None,
            "attachments": [...]
          }
        }
    """

    soup = BeautifulSoup(html or "", "html.parser")

    result: Dict[str, Any] = {
        "buyer": {},
        "currentMessage": {},
        "history": [],
        "order": {},
        "meta": {},
        # New normalized block is optional and populated best-effort.
        "normalized": {},
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

    normalized: Dict[str, Any] = {
        "source": "EBAY_EMAIL",
    }

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

        # Feed key identifiers into normalized view as well.
        normalized["orderId"] = order.get("orderNumber")
        normalized["itemId"] = order.get("itemId")
        normalized["transactionId"] = order.get("transactionId")

    # --- Meta ---
    ref_div = soup.find(id="ReferenceId")
    if ref_div:
        text = ref_div.get_text(" ", strip=True)
        if "Email reference id:" in text:
            ref = text.split("Email reference id:", 1)[1].strip()
            result["meta"]["emailReferenceId"] = ref

    # --- Heuristic topic / subtype classification ---
    subject = (result.get("currentMessage", {}).get("text") or "").lower()
    body_text = subject
    if result.get("history"):
        try:
            body_text = "\n".join(
                [entry.get("text", "") or "" for entry in result["history"]]
            ).lower()
        except Exception:
            body_text = subject

    topic = "OTHER"
    subtype = None

    if any(k in body_text for k in ["payment dispute", "chargeback"]):
        topic = "PAYMENT_DISPUTE"
    elif any(k in body_text for k in ["item not received", "inr inquiry", "non-received item"]):
        topic = "INQUIRY"
        subtype = "INR"
    elif any(k in body_text for k in ["return request", "return case"]):
        topic = "RETURN"
    elif "case" in body_text or "dispute" in body_text:
        topic = "CASE"
    elif any(k in body_text for k in ["offer", "best offer"]):
        topic = "OFFER"
    elif any(k in body_text for k in ["order", "shipped", "tracking number"]):
        topic = "ORDER"

    normalized["topic"] = topic
    if subtype:
        normalized["subtype"] = subtype

    # Buyer/seller usernames
    if result.get("buyer") and result["buyer"].get("username"):
        normalized["buyerUsername"] = result["buyer"]["username"]
    normalized.setdefault("sellerUsername", our_account_username)

    # Summary text: use current message text as lightweight preview
    if result.get("currentMessage") and result["currentMessage"].get("text"):
        normalized["summaryText"] = result["currentMessage"]["text"]

    result["normalized"] = normalized
    return result
