"""Shift business logic, shared by /v3/shifts and /callboard/shift/*.

Returns plain dicts keyed to the wire vocabulary (shift_id, org_id, venue, starts, ends, ...)
so each router shapes its own response independently - same pattern as services/crew.py.

Dates are stored as UTC unix epoch (`start_ts`/`end_ts`) with a per-shift IANA `venue_tz`
column; `_fmt_local`/`_parse_local` convert to/from callboard's wire format
("MM/DD/YYYY HH:MM", venue-local, 24h) - confirmed by round-tripping shift/create's exact
input/output strings against callboard direct (see SEAMS.md).

shift_id/venue_id/crew_id are taken as raw strings and bound straight into SQL, same as
services/crew.py's crew_id - see that file's docstring for why (byte-identical DB-error
passthrough on malformed input).

Cancel does NOT recompute `open_slots` - confirmed live against callboard: cancelling shift 30
(1 accepted assignment out of 6 slots, open_slots already 5) left open_slots at 5 afterward,
not reset to 6. It only sets `staffing_status = 'CXL'` (a third literal value alongside
OPEN/FULL, confirmed via `SELECT DISTINCT staffing_status`) and touches `updated_on`.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .. import db
from . import messages_write

_SHIFT_FIELDS = (
    "s.id AS shift_id, s.org_id, s.venue_name AS venue, s.venue_tz, s.title, "
    "s.start_ts, s.end_ts, s.slots, s.open_slots, s.staffing_status, s.lead_assignment_id"
)

_ASSIGNMENT_FIELDS = (
    "a.id AS assignment_id, a.crew_id, c.user_name AS crew_name, "
    "a.pay_estimate::text AS pay_estimate, a.shift_id, a.shift_title, a.status"
)


def _fmt_local(epoch: int, tz: str) -> str:
    return datetime.fromtimestamp(epoch, tz=ZoneInfo(tz)).strftime("%m/%d/%Y %H:%M")


def _parse_local(value: str, tz: str) -> int:
    naive = datetime.strptime(value, "%m/%d/%Y %H:%M")
    return int(naive.replace(tzinfo=ZoneInfo(tz)).timestamp())


def _finish_row(row: dict) -> dict:
    # lead_assignment_id is never set by any wave-2 endpoint (no confirmed sample of the
    # non-null case exists to shape it from) - always "" in every probe and in the seed.
    out = dict(row)
    out["starts"] = _fmt_local(out["start_ts"], out["venue_tz"])
    out["ends"] = _fmt_local(out["end_ts"], out["venue_tz"])
    out["lead"] = ""
    return out


def list_shifts(
    org: int, page: int, per_page: int, start: date | None, end: date | None
) -> tuple[list[dict], int]:
    filters = ["s.org_id = :org"]
    params: dict = {"org": org}
    if start is not None:
        filters.append("(to_timestamp(s.start_ts) AT TIME ZONE s.venue_tz)::date >= :start")
        params["start"] = start
    if end is not None:
        filters.append("(to_timestamp(s.start_ts) AT TIME ZONE s.venue_tz)::date <= :end")
        params["end"] = end
    where = " AND ".join(filters)
    with db.session() as s:
        total = s.execute(
            text(f"SELECT count(*) FROM shifts s WHERE {where}"), params
        ).scalar_one()
        # Confirmed ordering from callboard direct: start_ts ASC, venue name ASC (ties at the
        # same start_ts interleave venues alphabetically, e.g. Meridian Hall before The Aldwych).
        query = f"SELECT {_SHIFT_FIELDS} FROM shifts s WHERE {where} ORDER BY s.start_ts, s.venue_name"
        if per_page:
            query += " LIMIT :limit OFFSET :offset"
            params["limit"] = per_page
            params["offset"] = (page - 1) * per_page
        rows = s.execute(text(query), params).mappings().all()
    return [_finish_row(dict(r)) for r in rows], total


def shift_assignments(org, shift_id) -> list[dict]:
    with db.session() as s:
        rows = (
            s.execute(
                text(
                    f"SELECT {_ASSIGNMENT_FIELDS}, c.display_name FROM assignments a "
                    "JOIN tg_crew c ON c.id = a.crew_id "
                    "JOIN shifts sh ON sh.id = a.shift_id "
                    "WHERE a.shift_id = :shift_id AND sh.org_id = :org ORDER BY a.id"
                ),
                {"shift_id": shift_id, "org": org},
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]


def get_shift(org, shift_id) -> dict | None:
    with db.session() as s:
        row = (
            s.execute(
                text(f"SELECT {_SHIFT_FIELDS} FROM shifts s WHERE s.id = :shift_id AND s.org_id = :org"),
                {"shift_id": shift_id, "org": org},
            )
            .mappings()
            .first()
        )
    if row is None:
        return None
    result = _finish_row(dict(row))
    result["assignments"] = shift_assignments(org, result["shift_id"])
    return result


def get_venue(org, venue_id) -> dict | None:
    with db.session() as s:
        venue = (
            s.execute(
                text("SELECT id, venue_name, tz FROM venues WHERE id = :venue_id AND company_no = :org"),
                {"venue_id": venue_id, "org": org},
            )
            .mappings()
            .first()
        )
    return dict(venue) if venue else None


def create_shift(org, fields: dict) -> dict | None:
    """Legacy entry point - venue-local "MM/DD/YYYY HH:MM" strings, resolved against the
    venue's own tz. /v3 uses `create_shift_core` directly with an already-resolved venue and
    tz-aware datetimes, since it has no venue-local string to parse - see routers/v3_shift.py.
    """
    venue = get_venue(org, fields.get("venue_id", ""))
    if venue is None:
        return None
    start_ts = _parse_local(fields["starts"], venue["tz"])
    end_ts = _parse_local(fields["ends"], venue["tz"])
    return create_shift_core(org, venue, fields.get("title", ""), start_ts, end_ts, fields.get("slots", ""))


def create_shift_core(org, venue: dict, title: str, start_ts: int, end_ts: int, slots) -> dict:
    with db.session() as s:
        shift_id = s.execute(
            text(
                "INSERT INTO shifts (org_id, venue_id, venue_name, venue_tz, title, start_ts, end_ts, "
                "slots, open_slots, staffing_status, created, updated_on) "
                "VALUES (:org, :venue_id, :venue_name, :venue_tz, :title, :start_ts, :end_ts, "
                ":slots, :slots, 'OPEN', extract(epoch from now())::int, now()::text) "
                "RETURNING id"
            ),
            {
                "org": org,
                "venue_id": venue["id"],
                "venue_name": venue["venue_name"],
                "venue_tz": venue["tz"],
                "title": title,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "slots": slots,
            },
        ).scalar_one()
        s.commit()
    return get_shift(org, shift_id)


def cancel_shift(org, shift_id) -> dict | None:
    with db.session() as s:
        shift = (
            s.execute(
                text("SELECT id, title FROM shifts WHERE id = :shift_id AND org_id = :org"),
                {"shift_id": shift_id, "org": org},
            )
            .mappings()
            .first()
        )
        if shift is None:
            return None
        targets = (
            s.execute(
                text(
                    "SELECT id AS assignment_id, crew_id FROM assignments "
                    "WHERE shift_id = :shift_id AND status IN ('O', 'A')"
                ),
                {"shift_id": shift["id"]},
            )
            .mappings()
            .all()
        )
        s.execute(
            text(
                "UPDATE assignments SET status = 'X', updated_on = now()::text "
                "WHERE shift_id = :shift_id AND status IN ('O', 'A')"
            ),
            {"shift_id": shift["id"]},
        )
        for t in targets:
            messages_write.insert_cxl(s, org, t["crew_id"], t["assignment_id"], shift["title"])
        s.execute(
            text("UPDATE shifts SET staffing_status = 'CXL', updated_on = now()::text WHERE id = :shift_id"),
            {"shift_id": shift["id"]},
        )
        s.commit()
    return {"cancelled": shift["id"], "notified": len(targets)}
