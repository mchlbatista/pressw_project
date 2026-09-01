"""Starter test. Replace with the parity/characterization suite the brief asks for.
Run inside the running stack's network or with DATABASE_URL pointed at localhost:5432."""
from fastapi.testclient import TestClient

from app.main import app


def test_healthz():
    assert TestClient(app).get("/healthz").json() == {"ok": True}
