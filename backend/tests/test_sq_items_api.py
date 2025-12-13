import pytest

pytestmark = pytest.mark.skip(reason="SQ items API tests require a running DB and app context")


def test_placeholder_sq_items_api():
    """Placeholder test so the SQ catalog module is discoverable in pytest.

    Real API-level tests should be added once a test database / TestClient
    harness is wired for the FastAPI app.
    """

    assert True
