import pytest

pytestmark = pytest.mark.skip(
    reason="Grid/analytics API tests require DATABASE_URL and a running FastAPI app; enable in CI with proper env."
)


def test_orders_grid_preferences_has_columns_placeholder():
    """Placeholder: ensure /api/grid/preferences for orders returns columns.

    Once a test DB + TestClient harness is wired, this test should:
    - create a test user
    - call GET /api/grid/preferences?grid_key=orders
    - assert status 200 and that available_columns / columns.visible are non-empty
    """

    assert True


def test_analytics_summary_missing_ebay_orders_placeholder():
    """Placeholder: ensure /ebay/analytics/summary does not 500 when ebay_orders is absent.

    In a real test environment, you would:
    - provision a Postgres DB *without* ebay_orders table
    - create a test user and auth token
    - call GET /ebay/analytics/summary
    - assert 200 and that the JSON payload has zero/empty fields, not an error
    """

    assert True
