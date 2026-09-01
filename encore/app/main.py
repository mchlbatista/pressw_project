"""Encore - the modern ShowCall backend.

This skeleton gives you the app, the DB wiring, and nothing else. Structure the
rest however you think a year-long migration should be structured. Two things to
keep in mind from the brief:

- Modern endpoints live under /v3/... and should look the way you'd want an API
  to look in 2026.
- Legacy-compatible wrappers must answer the ORIGINAL /callboard/... paths (the
  gateway forwards those paths verbatim when routes.yaml points them here) and
  must match Callboard's wire behavior exactly. The legacy frontend cannot tell
  the difference.
"""
from fastapi import FastAPI
from sqlalchemy import text

from . import db
from .routers import legacy_crew, v3_crew

app = FastAPI(title="encore")
app.include_router(v3_crew.router)
app.include_router(legacy_crew.router)


@app.get("/healthz")
def healthz():
    with db.session() as s:
        s.execute(text("SELECT 1"))
    return {"ok": True}
