"""Modern /v3/shifts/{id}/assignments - offer only (see services/assignments.py's docstring
for why `accept` isn't here yet).
"""
from fastapi import APIRouter, HTTPException

from ..schemas.assignment import AssignmentOffer
from ..schemas.shift import Assignment
from ..services import assignments as assignment_service

router = APIRouter(prefix="/v3/shifts/{shift_id}/assignments", tags=["assignments"])


def _to_assignment(row: dict) -> Assignment:
    return Assignment(
        id=row["assignment_id"],
        crew_id=row["crew_id"],
        crew_email=row["crew_name"],
        shift_id=row["shift_id"],
        pay_estimate=row["pay_estimate"],
        status=row["status"],
    )


@router.post("", status_code=201)
def offer_assignment(org: int, shift_id: int, body: AssignmentOffer) -> Assignment:
    row = assignment_service.offer_assignment(org, shift_id, body.crew_id)
    if row is None:
        raise HTTPException(status_code=404, detail="shift or crew not found")
    return _to_assignment(row)
