"""Assignment business logic, shared by /v3 and /callboard/assignment/*.

Only `offer` lives in wave 2. `accept` stays on callboard until wave 3 - see SEAMS.md's
wave 2/3 boundary mitigation: splitting `accept` from `message/confirm` (which reimplements
the accept path internally) would create two independent implementations of "accept an
assignment" racing on the same rows.

Confirmed live against callboard: offering an assignment does NOT touch `shifts` (an
`O`-status row doesn't count toward `open_slots`, so there's nothing to recompute) - see
SEAMS.md's corrected shifts<->assignments coupling finding.
"""
from sqlalchemy import text

from .. import db
from . import messages_write

_ASSIGNMENT_FIELDS = (
    "a.id AS assignment_id, a.crew_id, c.user_name AS crew_name, "
    "a.pay_estimate::text AS pay_estimate, a.shift_id, a.shift_title, a.status"
)


def offer_assignment(org: int, shift_id, crew_id) -> dict | None:
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
        crew = (
            s.execute(
                text("SELECT id FROM tg_crew WHERE id = :crew_id AND org = :org"),
                {"crew_id": crew_id, "org": org},
            )
            .mappings()
            .first()
        )
        if crew is None:
            return None
        assignment_id = s.execute(
            text(
                "INSERT INTO assignments (org_id, shift_id, crew_id, status, shift_title, offered_at, updated_on) "
                "VALUES (:org, :shift_id, :crew_id, 'O', :shift_title, extract(epoch from now())::int, now()::text) "
                "RETURNING id"
            ),
            {"org": org, "shift_id": shift["id"], "crew_id": crew["id"], "shift_title": shift["title"]},
        ).scalar_one()
        messages_write.insert_callout(s, org, crew["id"], assignment_id, shift["title"])
        row = (
            s.execute(
                text(
                    f"SELECT {_ASSIGNMENT_FIELDS} FROM assignments a JOIN tg_crew c ON c.id = a.crew_id "
                    "WHERE a.id = :assignment_id"
                ),
                {"assignment_id": assignment_id},
            )
            .mappings()
            .first()
        )
        s.commit()
    return dict(row)
