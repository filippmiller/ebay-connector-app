import json
from typing import Any, Dict

from fastapi.testclient import TestClient

from app.main import app
from app.routers import ebay_browse
from app.services import ebay as ebay_service_module
from app.services import ebay_api_client


class _DummyUser:
    id = "test-user-id"


def _override_current_user() -> _DummyUser:
    # The route does not actually use current_user, it just enforces auth.
    return _DummyUser()


def _setup_dependency_overrides() -> None:
    # Override auth dependency so we do not need a real JWT.
    app.dependency_overrides[ebay_browse.get_current_active_user] = _override_current_user


def _clear_dependency_overrides() -> None:
    app.dependency_overrides.pop(ebay_browse.get_current_active_user, None)


def test_ebay_browse_search_route_exists(monkeypatch) -> None:
    """Smoke test that /api/ebay/browse/search is wired and returns 200.

    We stub out all external eBay calls so this test is fast and deterministic.
    """

    _setup_dependency_overrides()

    # Stub Browse token + search so we do not hit the real eBay API.
    async def fake_get_browse_app_token(*args: Any, **kwargs: Any) -> str:  # type: ignore[override]
        return "dummy-token"

    async def fake_search_active_listings(
        access_token: str,
        keywords: str,
        *,
        limit: int = 20,
        offset: int = 0,
        sort: str = "newlyListed",
        category_id: str | None = None,
        filter_expr: str | None = None,
        fieldgroups: list[str] | None = None,
        aspect_filter: str | None = None,
        return_raw: bool = False,
    ) -> Any:
        from app.services.ebay_api_client import EbayListingSummary

        listings = [
            EbayListingSummary(
                item_id="123",
                title="Dummy listing",
                price=100.0,
                shipping=10.0,
                condition="Used",
                description="Test description",
            )
        ]
        raw: Dict[str, Any] = {
            "total": 1,
            "refinement": {
                "categoryDistributions": [],
                "aspectDistributions": [],
                "conditionDistributions": [],
            },
        }
        return (listings, raw) if return_raw else listings

    monkeypatch.setattr(
        ebay_service_module.ebay_service,
        "get_browse_app_token",
        fake_get_browse_app_token,
    )
    monkeypatch.setattr(ebay_api_client, "search_active_listings", fake_search_active_listings)

    client = TestClient(app)

    payload = {
        "keywords": "lenovo l500",
        "max_total_price": 200,
        "category_hint": "laptop",
        "limit": 10,
        "offset": 0,
        "sort": "newlyListed",
    }

    resp = client.post("/api/ebay/browse/search", json=payload)

    _clear_dependency_overrides()

    assert resp.status_code == 200, resp.text

    data = resp.json()
    # Basic shape checks so we notice if the response model changes.
    assert "items" in data
    assert isinstance(data["items"], list)
    assert data["items"]
    first = data["items"][0]
    assert first["item_id"] == "123"
    assert first["total_price"] == 110.0
