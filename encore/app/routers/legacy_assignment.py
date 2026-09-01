"""Legacy-compatible wrapper for callboard's /callboard/assignment/offer.

`assignment/accept` is NOT here - it stays on callboard until wave 3 (see
services/assignments.py's docstring and SEAMS.md's wave 2/3 boundary mitigation).
"""
from fastapi import APIRouter, Request
from sqlalchemy.exc import DBAPIError

from .. import legacy
from ..services import assignments as assignment_service

router = APIRouter(prefix="/callboard/assignment", tags=["legacy-assignment"])


def _shape(row: dict) -> dict:
    return {
        "assignment_id": row["assignment_id"],
        "crew_id": row["crew_id"],
        "crew_name": row["crew_name"],
        "pay_estimate": row["pay_estimate"] or "",
        "shift_id": row["shift_id"],
        "shift_title": row["shift_title"],
        "status": row["status"],
    }


@router.post("/offer")
async def offer_assignment(request: Request):
    org = legacy.resolve_org(request.headers.get("x-org-id"))
    if org is None:
        return legacy.render(legacy.fail("missing org"))
    form = await request.form()
    shift_id = form.get("shift_id", "")
    crew_id = form.get("crew_id", "")
    try:
        row = assignment_service.offer_assignment(org, shift_id, crew_id)
    except DBAPIError as exc:
        return legacy.render(legacy.fail(str(exc.orig)))
    if row is None:
        return legacy.render(legacy.fail("not found"))
    return legacy.render(legacy.ok(_shape(row)))
