"""Modern /v3/shifts endpoints - see schemas/shift.py for the wire-shape deviations from
legacy this deliberately makes (ISO datetimes, lowercase status words, no roster_rows).
"""
from datetime import date, timezone

from fastapi import APIRouter, HTTPException, Query

from ..schemas.shift import CancelResult, Shift, ShiftCreate, ShiftDetail, ShiftList
from ..services import shifts as shift_service
from .v3_assignment import _to_assignment

router = APIRouter(prefix="/v3/shifts", tags=["shifts"])

MAX_PER_PAGE = 100


def _to_shift(row: dict) -> Shift:
    return Shift(
        id=row["shift_id"],
        org=row["org_id"],
        venue=row["venue"],
        title=row["title"],
        starts_at=row["start_ts"],
        ends_at=row["end_ts"],
        slots=row["slots"],
        open_slots=row["open_slots"],
        status=row["staffing_status"],
    )


@router.get("")
def list_shifts(
    org: int,
    page: int = 1,
    per_page: int = Query(default=25, le=MAX_PER_PAGE),
    start: date | None = None,
    end: date | None = None,
) -> ShiftList:
    rows, total = shift_service.list_shifts(org, page, per_page, start, end)
    return ShiftList(
        items=[_to_shift(r) for r in rows], page=page, per_page=per_page, total=total
    )


@router.get("/{shift_id}")
def get_shift(org: int, shift_id: int) -> ShiftDetail:
    row = shift_service.get_shift(org, shift_id)
    if row is None:
        raise HTTPException(status_code=404, detail="shift not found")
    return ShiftDetail(
        **_to_shift(row).model_dump(),
        assignments=[_to_assignment(a) for a in row["assignments"]],
    )


@router.post("", status_code=201)
def create_shift(org: int, body: ShiftCreate) -> Shift:
    venue = shift_service.get_venue(org, body.venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue not found")
    row = shift_service.create_shift_core(
        org,
        venue,
        body.title,
        int(body.starts_at.astimezone(timezone.utc).timestamp()),
        int(body.ends_at.astimezone(timezone.utc).timestamp()),
        body.slots,
    )
    return _to_shift(row)


@router.post("/{shift_id}/cancel")
def cancel_shift(org: int, shift_id: int) -> CancelResult:
    result = shift_service.cancel_shift(org, shift_id)
    if result is None:
        raise HTTPException(status_code=404, detail="shift not found")
    return CancelResult(**result)
