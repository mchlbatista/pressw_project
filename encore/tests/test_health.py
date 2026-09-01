"""Starter test. Replace with the parity/characterization suite the brief asks for.
Run inside the running stack's network or with DATABASE_URL pointed at localhost:5432."""
from fastapi.testclient import TestClient

from app.main import app


def test_healthz():
    # TestClient as a context manager runs the app's lifespan (startup/
    # shutdown), which is the documented way to use it - see test_v3_crew.py.
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"ok": True}
