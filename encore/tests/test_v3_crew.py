"""Behavioral tests for /v3/crew.

Unlike the legacy wrapper (diffed byte-for-byte against callboard - see
test_legacy_crew_parity.py once it exists), /v3 has no external oracle: it's
a new shape nothing else defines. So these assert directly on the contract
this API is supposed to have, against known seed data.

Run inside the running stack's network or with DATABASE_URL pointed at
localhost:5432 (same as test_health.py).
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    # Context manager runs the app's lifespan (startup/shutdown) - the
    # documented way to use TestClient.
    with TestClient(app) as c:
        yield c


def test_list_scopes_by_org_and_reports_total(client):
    resp = client.get("/v3/crew", params={"org": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 8
    assert all(item["org"] == 3 for item in body["items"])


def test_list_paginates_and_defaults_to_25_per_page(client):
    resp = client.get("/v3/crew", params={"org": 3})
    body = resp.json()
    assert body["per_page"] == 25
    assert len(body["items"]) == 8  # fewer rows than a page, no truncation

    resp = client.get("/v3/crew", params={"org": 3, "per_page": 3})
    body = resp.json()
    assert len(body["items"]) == 3
    assert body["total"] == 8


def test_list_caps_per_page_at_max(client):
    resp = client.get("/v3/crew", params={"org": 3, "per_page": 1000})
    assert resp.status_code == 422  # over MAX_PER_PAGE, rejected up front


def test_get_returns_typed_fields_and_parsed_prefs(client):
    resp = client.get("/v3/crew/1", params={"org": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_lead"] is True  # not the wire "Y"
    assert isinstance(body["prefs"], dict)  # not a JSON-encoded string
    assert body["prefs"]["ui_rows"] == 25
    assert "password" not in body


def test_get_nonexistent_id_is_a_real_404(client):
    resp = client.get("/v3/crew/999999", params={"org": 3})
    assert resp.status_code == 404


def test_get_cross_org_id_is_a_real_404_not_a_leak(client):
    # crew_id 1 belongs to org 3, not org 7
    resp = client.get("/v3/crew/1", params={"org": 7})
    assert resp.status_code == 404


def test_patch_updates_only_supplied_fields(client):
    resp = client.patch(
        "/v3/crew/25", params={"org": 3}, json={"notes": "v3 patch test"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["notes"] == "v3 patch test"
    assert body["rate"] == 25.00  # untouched, not reset to null/0


def test_patch_nonexistent_id_is_a_real_404(client):
    resp = client.patch(
        "/v3/crew/999999", params={"org": 3}, json={"notes": "x"}
    )
    assert resp.status_code == 404
