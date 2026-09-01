"""Legacy-compatible wrappers for callboard's /callboard/crew/* endpoints.

Must match callboard's wire behavior exactly - the legacy frontend can't
tell the difference. That means the envelope, field names/types, the
per_page=0 "no pagination" convention, the trailing newline on every body
(see legacy.render()), and even callboard's raw DB-error passthrough on a
malformed crew_id (see services/crew.py's docstring and SEAMS.md's probe
log). Every quirk reproduced here that /v3 deliberately does not carry
forward is called out in TRADEOFFS.md.
"""
from fastapi import APIRouter, Request
from sqlalchemy.exc import DBAPIError

from .. import legacy
from ..services import crew as crew_service

router = APIRouter(prefix="/callboard/crew", tags=["legacy-crew"])


def _shape(row: dict) -> dict:
    return {
        "crew_id": row["crew_id"],
        "crew_name": row["crew_name"],
        "display_name": row["display_name"],
        "is_lead": row["is_lead"],
        "notes": row["notes"],
        "org": row["org"],
        "rate": row["rate"],
    }


def _shape_detail(row: dict) -> dict:
    return {
        "crew_id": row["crew_id"],
        "crew_name": row["crew_name"],
        "display_name": row["display_name"],
        "is_lead": row["is_lead"],
        "notes": row["notes"],
        "org": row["org"],
        "prefs": row["prefs_blob"],
        "rate": row["rate"],
    }


@router.get("/list")
def list_crew(request: Request, page: int = 1, per_page: int = 0):
    org = legacy.resolve_org(request.headers.get("x-org-id"))
    if org is None:
        return legacy.render(legacy.fail("missing org"))
    rows, total = crew_service.list_crew(org, page, per_page)
    payload = legacy.ok(
        {"crew": [_shape(r) for r in rows], "page": page, "total": total}
    )
    return legacy.render(payload)


@router.get("/show")
def show_crew(request: Request, crew_id: str = ""):
    org = legacy.resolve_org(request.headers.get("x-org-id"))
    if org is None:
        return legacy.render(legacy.fail("missing org"))
    try:
        row = crew_service.get_crew(org, crew_id)
    except DBAPIError as exc:
        return legacy.render(legacy.fail(str(exc.orig)))
    if row is None:
        return legacy.render(legacy.fail("not found"))
    return legacy.render(legacy.ok(_shape_detail(row)))


@router.post("/update")
async def update_crew(request: Request):
    org = legacy.resolve_org(request.headers.get("x-org-id"))
    if org is None:
        return legacy.render(legacy.fail("missing org"))
    form = await request.form()
    crew_id = form.get("crew_id", "")
    fields = {k: v for k, v in form.items() if k != "crew_id"}
    try:
        row = crew_service.update_crew(org, crew_id, fields)
    except DBAPIError as exc:
        return legacy.render(legacy.fail(str(exc.orig)))
    if row is None:
        return legacy.render(legacy.fail("not found"))
    return legacy.render(legacy.ok(_shape(row)))
