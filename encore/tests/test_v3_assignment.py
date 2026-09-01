"""Behavioral tests for POST /v3/shifts/{id}/assignments (offer only - see
services/assignments.py's docstring for why accept isn't here yet).
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_offer_does_not_change_shift_open_slots(client):
    # Confirmed live against callboard: an 'O'-status assignment isn't counted toward
    # open_slots, so offering shouldn't recompute it - see SEAMS.md's corrected finding.
    before = client.get("/v3/shifts/5", params={"org": 3}).json()
    resp = client.post("/v3/shifts/5/assignments", params={"org": 3}, json={"crew_id": 5})
    assert resp.status_code == 201
    after = client.get("/v3/shifts/5", params={"org": 3}).json()
    assert after["open_slots"] == before["open_slots"]


def test_offer_nonexistent_shift_is_a_real_404(client):
    resp = client.post("/v3/shifts/999999/assignments", params={"org": 3}, json={"crew_id": 1})
    assert resp.status_code == 404


def test_offer_nonexistent_crew_is_a_real_404(client):
    resp = client.post("/v3/shifts/5/assignments", params={"org": 3}, json={"crew_id": 999999})
    assert resp.status_code == 404


def test_offer_cross_org_shift_is_a_real_404_not_a_leak(client):
    # shift 5 belongs to org 3, not org 7
    resp = client.post("/v3/shifts/5/assignments", params={"org": 7}, json={"crew_id": 14})
    assert resp.status_code == 404
