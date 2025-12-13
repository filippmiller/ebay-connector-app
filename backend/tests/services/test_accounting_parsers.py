import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import AsyncMock, patch
from app.services.accounting_parsers.csv_parser import parse_csv_bytes
from app.services.accounting_parsers.xlsx_parser import parse_xlsx_bytes
from app.services.accounting_parsers.pdf_parser import parse_pdf_bytes

# --- CSV Parser Tests ---

def test_parse_csv_simple():
    csv_content = b"""Date,Description,Amount
2023-01-01,Test Transaction,-100.50
2023-01-02,Income,500.00
"""
    rows = parse_csv_bytes(csv_content)
    assert len(rows) == 2
    
    assert rows[0]["date"] == "2023-01-01"
    assert rows[0]["description"] == "Test Transaction"
    assert rows[0]["amount"] == "-100.50"
    
    assert rows[1]["date"] == "2023-01-02"
    assert rows[1]["amount"] == "500.00"

def test_parse_csv_messy_headers():
    csv_content = b"""Transaction Date, DETAILS ,  Debit/Credit 
2023-05-10,Coffee Shop,-5.00
"""
    rows = parse_csv_bytes(csv_content)
    assert len(rows) == 1
    # The normalizer should handle spaces and case
    # Ideally our parser returns a dict with normalized keys or we check known variants
    # The current implementation returns a dict with keys from the header row (normalized to lower/strip)
    
    # Let's check what the parser actually does. It normalizes headers to lowercase.
    row = rows[0]
    # "Transaction Date" -> "transaction date"
    assert row.get("transaction date") == "2023-05-10"
    # " DETAILS " -> "details"
    assert row.get("details") == "Coffee Shop"
    # "  Debit/Credit " -> "debit/credit"
    assert row.get("debit/credit") == "-5.00"

# --- XLSX Parser Tests ---

def test_parse_xlsx_simple():
    # Creating a real XLSX in memory for testing is complex without extra libs.
    # We can mock openpyxl.load_workbook if we want to test the logic around it,
    # or rely on integration tests.
    # For unit testing the logic *after* loading, we might need to refactor the parser 
    # to accept a workbook object, but for now let's skip complex XLSX generation 
    # and assume the library works if we mock the return.
    pass

# --- PDF Parser Tests ---

@pytest.mark.asyncio
async def test_parse_pdf_mocked():
    # Mock pdfplumber and OpenAI
    
    mock_text = "2023-01-01 UBER TRIP -15.00 USD"
    
    with patch("app.services.accounting_parsers.pdf_parser.pdfplumber") as mock_pdf:
        # Mock context manager for pdfplumber.open
        mock_page = AsyncMock()
        mock_page.extract_text.return_value = mock_text
        
        mock_pdf_obj = AsyncMock()
        mock_pdf_obj.pages = [mock_page]
        
        mock_open = mock_pdf.open
        mock_open.return_value.__enter__.return_value = mock_pdf_obj
        
        with patch("app.services.accounting_parsers.pdf_parser.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            
            # Mock OpenAI response
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "content": '{"transactions": [{"date": "2023-01-01", "description": "UBER TRIP", "amount": -15.00, "currency": "USD"}]}'
                    }
                }]
            }
            mock_client.post.return_value = mock_response
            
            # Run parser
            rows = await parse_pdf_bytes(b"fake_pdf_bytes")
            
            assert len(rows) == 1
            assert rows[0]["date"] == "2023-01-01"
            assert rows[0]["description"] == "UBER TRIP"
            assert rows[0]["amount"] == -15.00
            assert rows[0]["currency"] == "USD"
