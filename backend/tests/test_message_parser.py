import pytest

from app.services.message_parser import parse_ebay_message_html, ParsedBody


def test_parse_simple_html_single_part():
    raw_html = """
    <html>
      <head>
        <title>Ignored</title>
        <style>td{word-wrap: break-word}</style>
      </head>
      <body>
        <table><tr><td style="word-wrap: break-word">
          <p>Hello buyer,<br/>Thank you for your purchase.</p>
          <p>Best regards,<br/>Seller</p>
        </td></tr></table>
      </body>
    </html>
    """

    parsed: ParsedBody = parse_ebay_message_html(raw_html, our_account_username="our_store")

    assert parsed is not None
    assert parsed.currentMessage is not None
    assert parsed.currentMessage.text
    # No raw HTML tags in text
    assert "<" not in parsed.currentMessage.text
    assert ">" not in parsed.currentMessage.text

    # Fallback path should treat this as a single-part thread
    assert parsed.history == []
    # Preview text should mirror the only part's text
    assert parsed.previewText == parsed.currentMessage.text


def test_parse_structured_primary_and_history():
    # Minimal synthetic example that follows eBay's PrimaryMessage/MessageHistory layout
    raw_html = """
    <html>
      <body>
        <div id="PrimaryMessage">
          <h1>
            <a href="https://example.com/usr/buyer123">buyer123</a>
          </h1>
          <div id="UserInputtedText">
            <p>Hi, I have a question about this item.</p>
          </div>
        </div>

        <table id="MessageHistory1">
          <tr>
            <td>
              <p>Your previous message</p>
              <div id="UserInputtedText1">
                <p>Hello, this item is in great condition.</p>
              </div>
            </td>
          </tr>
        </table>

        <div id="area7Container">
          <a href="https://www.ebay.com/itm/123">Test item title</a>
          <img src="https://i.ebayimg.com/images/123.jpg" />
          <div>
            Order status: Shipped<br/>
            Item ID: 123<br/>
            Transaction ID: 456<br/>
            Order number: 789
          </div>
        </div>
      </body>
    </html>
    """

    parsed: ParsedBody = parse_ebay_message_html(raw_html, our_account_username="our_store")

    assert parsed.order is not None
    assert parsed.order.itemId == "123"
    assert parsed.order.transactionId == "456"
    assert parsed.order.orderNumber == "789"
    assert parsed.order.title == "Test item title"

    # Expect history + currentMessage
    assert parsed.currentMessage is not None
    assert parsed.currentMessage.direction == "inbound"
    assert parsed.currentMessage.fromName in {"buyer123", "Buyer"}

    assert len(parsed.history) == 1
    hist_part = parsed.history[0]
    assert hist_part.direction == "outbound"
    assert hist_part.text

    # HTML for parts should be present but sanitized (no <style>, <script>, <head>)
    assert parsed.currentMessage.html is not None
    assert "<style" not in parsed.currentMessage.html
    assert "<script" not in parsed.currentMessage.html

    # previewText should come from the most recent part (currentMessage)
    assert parsed.previewText == parsed.currentMessage.text
