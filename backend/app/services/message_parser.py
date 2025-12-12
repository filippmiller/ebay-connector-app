from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Literal
import re

from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, HttpUrl


NEWLINE_RE = re.compile(r"\n{3,}")
WHITESPACE_RE = re.compile(r"[ \t]{2,}")
DATE_RE = re.compile(
    r"([A-Z][a-z]+ \d{1,2}, \d{4},? \d{1,2}:\d{2} ?(am|pm|AM|PM))",
)

ALLOWED_TAGS = {
    "p",
    "br",
    "b",
    "strong",
    "i",
    "em",
    "u",
    "a",
    "ul",
    "ol",
    "li",
    "span",
}
ALLOWED_ATTRS = {
    "a": {"href", "title"},
}


class ParsedOrder(BaseModel):
    orderNumber: Optional[str] = None
    itemId: Optional[str] = None
    transactionId: Optional[str] = None
    title: Optional[str] = None
    imageUrl: Optional[HttpUrl] = None
    itemUrl: Optional[HttpUrl] = None
    status: Optional[str] = None
    viewOrderUrl: Optional[HttpUrl] = None


class ParsedMessagePart(BaseModel):
    id: Optional[str] = None
    direction: Literal["inbound", "outbound", "system"]
    text: str
    html: Optional[str] = None
    sentAt: Optional[datetime] = None
    fromName: Optional[str] = None
    toName: Optional[str] = None


class ParsedBody(BaseModel):
    order: Optional[ParsedOrder] = None
    history: List[ParsedMessagePart] = []
    currentMessage: Optional[ParsedMessagePart] = None
    previewText: Optional[str] = None
    richHtml: Optional[str] = None


def _clean_whitespace(value: str) -> str:
    return " ".join((value or "").split())


def _parse_timestamp_from_text(text: str) -> Optional[datetime]:
    """Best-effort parser for eBay's human-readable timestamps.

    Examples: "January 2, 2024, 3:45 pm".
    """

    if not text:
        return None
    m = DATE_RE.search(text)
    if not m:
        return None
    candidate = m.group(1)
    for fmt in ("%B %d, %Y, %I:%M %p", "%B %d, %Y, %I:%M%p"):
        try:
            return datetime.strptime(candidate, fmt)
        except ValueError:
            continue
    return None


def _html_fragment_to_text(html: str) -> str:
    """Convert minimal HTML to plain text.

    - <br> → "\n"
    - <p> boundaries → blank line
    - collapse multiple blank lines / spaces
    """

    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Convert <br> and <p> to newlines
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for p in soup.find_all("p"):
        # Insert a newline *before* each paragraph (except maybe the first)
        if p is not soup.body and p is not soup.contents[0]:
            p.insert_before("\n\n")

    text = soup.get_text(separator="", strip=False)
    text = NEWLINE_RE.sub("\n\n", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _sanitize_node(node: Tag) -> None:
    """In-place sanitization of a BeautifulSoup node.

    - Drop <script>, <style>, <noscript>, <meta>, <link>, <iframe> entirely.
    - Unwrap layout-ish tags and unknown tags but keep their children.
    - Allow only a minimal set of tags/attrs.
    """

    for tag in list(node.descendants):
        if not isinstance(tag, Tag):
            continue

        if tag.name in {"script", "style", "noscript", "meta", "link", "iframe", "head"}:
            tag.decompose()
            continue

        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
            continue

        # Strip dangerous attributes, keep only whitelisted
        allowed = ALLOWED_ATTRS.get(tag.name, set())
        for attr in list(tag.attrs.keys()):
            if attr not in allowed:
                del tag.attrs[attr]


def _find_primary_container(soup: BeautifulSoup) -> Tag:
    """Best-effort detection of the central message block.

    Heuristics, in order:
    - div#UserInputtedText under #PrimaryMessage
    - #PrimaryMessage itself
    - td with style containing "word-wrap: break-word"
    - the body element
    """

    primary = soup.find(id="PrimaryMessage")
    if primary:
        div = primary.find("div", id="UserInputtedText")
        if div:
            return div
        return primary

    td = soup.find("td", attrs={"style": lambda v: v and "word-wrap" in v})
    if td:
        return td

    body = soup.body or soup
    return body


def _build_part(
    *,
    html_node: Tag,
    direction: Literal["inbound", "outbound", "system"],
    from_name: Optional[str],
    to_name: Optional[str],
    ts_source_text: Optional[str] = None,
    synthetic_id: Optional[str] = None,
) -> ParsedMessagePart:
    node_copy = BeautifulSoup(str(html_node), "html.parser")
    root = node_copy.body or node_copy
    _sanitize_node(root)
    clean_html = "".join(str(child) for child in root.contents) if root.contents else str(root)
    text = _html_fragment_to_text(clean_html)

    ts = _parse_timestamp_from_text(ts_source_text or text)

    return ParsedMessagePart(
        id=synthetic_id,
        direction=direction,
        text=text,
        html=clean_html or None,
        sentAt=ts,
        fromName=from_name,
        toName=to_name,
    )


def parse_ebay_message_html(
    raw_html: str,
    *,
    our_account_username: Optional[str] = None,
) -> ParsedBody:
    """Parse raw eBay Trading GetMyMessages HTML into a structured thread.

    The parser is defensive and heuristic-based. It aims to:
    - keep a minimal, sanitized HTML representation for each message part
    - derive plain text for each part and overall previewText
    - split multi-step conversations using eBay's PrimaryMessage/MessageHistory
      layout when present, otherwise fall back to a single-part thread.
    """

    soup = BeautifulSoup(raw_html or "", "html.parser")

    # --- Order / item info (area7Container) ---
    order: Optional[ParsedOrder] = None
    area7 = soup.find(id="area7Container")
    if area7 is not None:
        title_link = area7.find("a")
        title = _clean_whitespace(title_link.get_text(" ", strip=True)) if title_link else None
        href = title_link.get("href") if title_link else None
        img = area7.find("img")
        img_src = img.get("src") if img and img.get("src") else None

        view_link = area7.find("a", string=re.compile("View order details", re.I))
        view_url = view_link.get("href") if view_link and view_link.get("href") else None

        item_id = None
        transaction_id = None
        order_number = None
        status = None

        text_block = area7.get_text("\n", strip=True)
        for line in text_block.splitlines():
            line = line.strip()
            if line.startswith("Order status:"):
                status = line.split(":", 1)[1].strip()
            elif line.startswith("Item ID:"):
                item_id = line.split(":", 1)[1].strip()
            elif line.startswith("Transaction ID:"):
                transaction_id = line.split(":", 1)[1].strip()
            elif line.startswith("Order number:"):
                order_number = line.split(":", 1)[1].strip()

        order = ParsedOrder(
            orderNumber=order_number or None,
            itemId=item_id or None,
            transactionId=transaction_id or None,
            title=title or None,
            imageUrl=img_src,  # type: ignore[arg-type]
            itemUrl=href,  # type: ignore[arg-type]
            status=status or None,
            viewOrderUrl=view_url,  # type: ignore[arg-type]
        )

    # --- Buyer / author context ---
    primary = soup.find(id="PrimaryMessage") or soup
    buyer_username: Optional[str] = None
    buyer_h1 = primary.find("h1") if primary else None
    if buyer_h1:
        a_tags = buyer_h1.find_all("a")
        if a_tags:
            buyer_username = _clean_whitespace(a_tags[0].get_text(strip=True)) or None

    # --- Current message block ---
    history_parts: List[ParsedMessagePart] = []
    current_part: Optional[ParsedMessagePart] = None

    # Prefer explicit div#UserInputtedText for current message
    current_div = primary.find("div", id="UserInputtedText") if primary else None
    if current_div is not None:
        from_name = buyer_username or "Buyer"
        to_name = our_account_username or None
        current_part = _build_part(
            html_node=current_div,
            direction="inbound",
            from_name=from_name,
            to_name=to_name,
            synthetic_id="current",
        )

    # --- Message history tables ---
    for idx, tbl in enumerate(soup.find_all("table", id=re.compile(r"^MessageHistory"))):
        header_p = tbl.find("p")
        header_text = header_p.get_text(" ", strip=True) if header_p else ""
        header_text_lower = header_text.lower()

        author: Optional[str] = None
        direction: Literal["inbound", "outbound", "system"] = "system"

        if "your previous message" in header_text_lower:
            author = our_account_username or "Seller"
            direction = "outbound"
        else:
            a = header_p.find("a") if header_p else None
            if a:
                uname = _clean_whitespace(a.get_text(strip=True))
                if uname:
                    author = uname
                    if buyer_username and uname == buyer_username:
                        direction = "inbound"
                    elif our_account_username and uname == our_account_username:
                        direction = "outbound"
                    else:
                        direction = "system"

        body_div = tbl.find("div", id=re.compile(r"^UserInputtedText")) or tbl
        part = _build_part(
            html_node=body_div,
            direction=direction,
            from_name=author,
            to_name=(our_account_username if direction == "inbound" else buyer_username),
            ts_source_text=header_text,
            synthetic_id=f"history-{idx}",
        )
        if part.text:
            history_parts.append(part)

    # --- Fallback single-block parsing when no structured layout ---
    if not current_part and not history_parts:
        container = _find_primary_container(soup)
        # Wrap in a <div> for consistent sanitization
        wrapper = BeautifulSoup("<div></div>", "html.parser")
        root = wrapper.div
        for child in list(container.children):
            root.append(child)

        # Infer direction from high-level phrases
        all_text = _html_fragment_to_text(str(root)).lower()
        direction: Literal["inbound", "outbound", "system"] = "inbound"
        if "you sent a message" in all_text or "you sent this message" in all_text:
            direction = "outbound"
        elif "ebay sent this message" in all_text or "this is an automated message" in all_text:
            direction = "system"

        from_name = None
        to_name = None
        if direction == "outbound":
            from_name = our_account_username or "Seller"
            to_name = buyer_username
        elif direction == "inbound":
            from_name = buyer_username or "Buyer"
            to_name = our_account_username

        current_part = _build_part(
            html_node=root,
            direction=direction,
            from_name=from_name,
            to_name=to_name,
            synthetic_id="current",
        )

    # If we have history but no explicit current, treat the last history entry as current
    if history_parts and current_part is None:
        current_part = history_parts[-1]
        history_parts = history_parts[:-1]

    # Ensure at least one part
    parts: List[ParsedMessagePart] = []
    if history_parts:
        parts.extend(history_parts)
    if current_part:
        parts.append(current_part)

    preview_text: Optional[str] = None
    if parts:
        # Use the most recent part's text for preview; frontend will truncate.
        preview_text = parts[-1].text

    # Rich HTML for whole thread: sanitized primary container
    main_container = _find_primary_container(soup)
    main_wrapper = BeautifulSoup("<div></div>", "html.parser")
    main_root = main_wrapper.div
    for child in list(main_container.children):
        main_root.append(child)
    _sanitize_node(main_root)
    rich_html = "".join(str(child) for child in main_root.contents) if main_root.contents else None

    return ParsedBody(
        order=order,
        history=history_parts,
        currentMessage=current_part,
        previewText=preview_text,
        richHtml=rich_html,
    )
