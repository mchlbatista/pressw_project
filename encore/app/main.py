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
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from . import db
from .routers import (
    legacy_assignment,
    legacy_crew,
    legacy_shift,
    v3_assignment,
    v3_crew,
    v3_shift,
)
from .services import job

JOB_TICK_SECONDS = int(os.environ.get("JOB_TICK_SECONDS", 300))


async def _job_loop():
    while True:
        await asyncio.sleep(JOB_TICK_SECONDS)
        await asyncio.to_thread(job.run_tick)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(job.run_tick)
    task = asyncio.create_task(_job_loop())
    yield
    task.cancel()


app = FastAPI(title="encore", lifespan=lifespan)
app.include_router(v3_crew.router)
app.include_router(v3_shift.router)
app.include_router(v3_assignment.router)
app.include_router(legacy_crew.router)
app.include_router(legacy_shift.router)
app.include_router(legacy_assignment.router)


@app.get("/healthz")
def healthz():
    with db.session() as s:
        s.execute(text("SELECT 1"))
    return {"ok": True}
