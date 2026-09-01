"""Legacy-compatible wrappers for callboard's /callboard/shift/* endpoints.

See legacy_crew.py's docstring for the general fidelity contract (envelope, org header,
DBAPIError passthrough on malformed ids). `roster_rows` is the one exception to the envelope:
it returns a raw HTML fragment (`text/html; charset=utf-8`, confirmed via `curl -i` against
callboard direct), one `<tr>` per assignment, ending in a trailing newline when non-empty -
see SEAMS.md.

Status labels (`_STATUS_LABELS`) and the pay-or-em-dash rule were both confirmed live against
callboard direct, not guessed: shift 1's originally-fresh offers had aged into `E` by the time
this was checked ("Expired"), and shift 30's cancelled assignments came back "Cancelled" -
still showing their (frozen) pay estimate where one was set, `&mdash;` where it wasn't.
"""
from datetime import datetime

from fastapi import APIRouter, Request, Response
from sqlalchemy.exc import DBAPIError

from .. import legacy
from ..services import shifts as shift_service

router = APIRouter(prefix="/callboard/shift", tags=["legacy-shift"])

_STATUS_LABELS = {"O": "Offered", "A": "Accepted", "E": "Expired", "X": "Cancelled"}


def _shape_assignment(row: dict) -> dict:
    return {
        "assignment_id": row["assignment_id"],
        "crew_id": row["crew_id"],
        "crew_name": row["crew_name"],
        "pay_estimate": row["pay_estimate"] or "",
        "shift_id": row["shift_id"],
        "shift_title": row["shift_title"],
        "status": row["status"],
    }


def _shape(row: dict) -> dict:
    return {
        "ends": row["ends"],
        "lead": row["lead"],
        "open_slots": row["open_slots"],
        "org_id": row["org_id"],
        "shift_id": row["shift_id"],
        "slots": row["slots"],
        "staffing_status": row["staffing_status"],
        "starts": row["starts"],
        "title": row["title"],
        "venue": row["venue"],
    }


def _shape_detail(row: dict) -> dict:
    return {
        "assignments": [_shape_assignment(a) for a in row["assignments"]],
        **_shape(row),
    }


@router.get("/list")
def list_shifts(
    request: Request,
    page: int = 1,
    per_page: int = 0,
    start: str | None = None,
    end: str | None = None,
):
    org = legacy.resolve_org(request.headers.get("x-org-id"))
    if org is None:
        return legacy.render(legacy.fail("missing org"))
    start_date = datetime.strptime(start, "%m/%d/%Y").date() if start else None
    end_date = datetime.strptime(end, "%m/%d/%Y").date() if end else None
    rows, total = shift_service.list_shifts(org, page, per_page, start_date, end_date)
    payload = legacy.ok({"page": page, "shifts": [_shape(r) for r in rows], "total": total})
    return legacy.render(payload)


@router.get("/show")
def show_shift(request: Request, shift_id: str = ""):
    org = legacy.resolve_org(request.headers.get("x-org-id"))
    if org is None:
        return legacy.render(legacy.fail("missing org"))
    try:
        row = shift_service.get_shift(org, shift_id)
    except DBAPIError as exc:
        return legacy.render(legacy.fail(str(exc.orig)))
    if row is None:
        return legacy.render(legacy.fail("not found"))
    return legacy.render(legacy.ok(_shape_detail(row)))


@router.post("/create")
async def create_shift(request: Request):
    org = legacy.resolve_org(request.headers.get("x-org-id"))
    if org is None:
        return legacy.render(legacy.fail("missing org"))
    form = await request.form()
    try:
        row = shift_service.create_shift(org, dict(form))
    except DBAPIError as exc:
        return legacy.render(legacy.fail(str(exc.orig)))
    if row is None:
        return legacy.render(legacy.fail("not found"))
    return legacy.render(legacy.ok(_shape(row)))


@router.post("/cancel")
async def cancel_shift(request: Request):
    org = legacy.resolve_org(request.headers.get("x-org-id"))
    if org is None:
        return legacy.render(legacy.fail("missing org"))
    form = await request.form()
    shift_id = form.get("shift_id", "")
    try:
        result = shift_service.cancel_shift(org, shift_id)
    except DBAPIError as exc:
        return legacy.render(legacy.fail(str(exc.orig)))
    if result is None:
        return legacy.render(legacy.fail("not found"))
    return legacy.render(legacy.ok(result))


@router.get("/roster_rows")
def roster_rows(request: Request, shift_id: str = ""):
    org = legacy.resolve_org(request.headers.get("x-org-id"))
    rows = shift_service.shift_assignments(org, shift_id)
    lines = [
        f'<tr class="cb-row" data-aid="{r["assignment_id"]}">'
        f'<td>{r["display_name"]}</td>'
        f'<td>{_STATUS_LABELS.get(r["status"], r["status"])}</td>'
        f'<td>{"$" + r["pay_estimate"] if r["pay_estimate"] else "&mdash;"}</td></tr>'
        for r in rows
    ]
    body = "\n".join(lines) + ("\n" if lines else "")
    return Response(content=body, media_type="text/html; charset=utf-8")
