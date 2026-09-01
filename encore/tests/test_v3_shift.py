"""Behavioral tests for /v3/shifts and /v3/shifts/{id}/assignments.

Like test_v3_crew.py, these assert on the contract /v3 is supposed to have. Shift/assignment
totals aren't hardcoded against the seed the way crew's are - this stack accumulates real
mutations across a long-lived session (background job ticks, prior probing), so tests create
their own shifts/offers where the assertion needs a known-clean starting point, and use
relative checks (org scoping, pagination math, 404s) where an exact seed count would be
brittle.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_list_scopes_by_org(client):
    resp = client.get("/v3/shifts", params={"org": 3, "per_page": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 20
    assert all(item["org"] == 3 for item in body["items"])


def test_list_paginates(client):
    resp = client.get("/v3/shifts", params={"org": 3, "per_page": 3})
    body = resp.json()
    assert len(body["items"]) == 3
    assert body["per_page"] == 3


def test_list_caps_per_page_at_max(client):
    resp = client.get("/v3/shifts", params={"org": 3, "per_page": 1000})
    assert resp.status_code == 422


def test_list_date_filter_is_inclusive_by_start_date(client):
    resp = client.get(
        "/v3/shifts", params={"org": 3, "start": "2026-11-12", "end": "2026-11-12", "per_page": 100}
    )
    body = resp.json()
    assert body["total"] == 2  # two venues' shifts share that start date, per SEAMS.md


def test_get_returns_nested_assignments_and_real_status_words(client):
    resp = client.get("/v3/shifts/3", params={"org": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"open", "full", "cancelled"}
    assert len(body["assignments"]) == 3
    assert all(a["status"] in {"offered", "accepted", "expired", "cancelled"} for a in body["assignments"])


def test_get_nonexistent_id_is_a_real_404(client):
    resp = client.get("/v3/shifts/999999", params={"org": 3})
    assert resp.status_code == 404


def test_get_cross_org_id_is_a_real_404_not_a_leak(client):
    resp = client.get("/v3/shifts/3", params={"org": 7})
    assert resp.status_code == 404


def test_create_then_cancel_round_trip(client):
    created = client.post(
        "/v3/shifts",
        params={"org": 3},
        json={
            "venue_id": 1,
            "title": "wave2 test shift",
            "starts_at": "2026-12-20T08:00:00-06:00",
            "ends_at": "2026-12-20T16:00:00-06:00",
            "slots": 2,
        },
    )
    assert created.status_code == 201
    shift = created.json()
    assert shift["slots"] == 2
    assert shift["open_slots"] == 2
    assert shift["status"] == "open"

    offer = client.post(
        f"/v3/shifts/{shift['id']}/assignments", params={"org": 3}, json={"crew_id": 1}
    )
    assert offer.status_code == 201
    assert offer.json()["status"] == "offered"

    cancelled = client.post(f"/v3/shifts/{shift['id']}/cancel", params={"org": 3})
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["cancelled"] == shift["id"]
    assert body["notified"] == 1

    after = client.get(f"/v3/shifts/{shift['id']}", params={"org": 3})
    assert after.json()["status"] == "cancelled"
    # confirmed live: cancel does NOT recompute open_slots - see services/shifts.py
    assert after.json()["open_slots"] == 2
