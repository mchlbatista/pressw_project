"""Crew business logic, shared by /v3/crew and /callboard/crew/*.

Returns plain dicts keyed to match the wire vocabulary (crew_id, crew_name,
...) so each router can shape its own response independently. `password` is
never selected here - see TRADEOFFS.md.

crew_id is deliberately taken as a raw string and bound straight into the SQL
rather than validated in Python first: callboard doesn't pre-validate either,
so a malformed crew_id reaches Postgres and raises there. Reproducing that
(instead of pre-empting it with a clean 422) is what makes the legacy
wrapper's error text byte-identical to callboard's - see SEAMS.md.
"""
from sqlalchemy import text

from .. import db

_UPDATABLE_COLUMNS = {"notes", "rate"}

_ROW_FIELDS = (
    "id AS crew_id, user_name AS crew_name, display_name, is_lead, notes, "
    "org, rate::text AS rate"
)


def list_crew(org: int, page: int, per_page: int) -> tuple[list[dict], int]:
    with db.session() as s:
        total = s.execute(
            text("SELECT count(*) FROM tg_crew WHERE org = :org"), {"org": org}
        ).scalar_one()
        query = f"SELECT {_ROW_FIELDS} FROM tg_crew WHERE org = :org ORDER BY id"
        params = {"org": org}
        if per_page:
            query += " LIMIT :limit OFFSET :offset"
            params["limit"] = per_page
            params["offset"] = (page - 1) * per_page
        rows = s.execute(text(query), params).mappings().all()
    return [dict(r) for r in rows], total


def get_crew(org: int, crew_id: str) -> dict | None:
    with db.session() as s:
        row = (
            s.execute(
                text(
                    f"SELECT {_ROW_FIELDS}, prefs_blob FROM tg_crew "
                    "WHERE id = :crew_id AND org = :org"
                ),
                {"crew_id": crew_id, "org": org},
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


def update_crew(org: int, crew_id: str, fields: dict) -> dict | None:
    updates = {k: v for k, v in fields.items() if k in _UPDATABLE_COLUMNS}
    select_sql = text(
        f"SELECT {_ROW_FIELDS} FROM tg_crew WHERE id = :crew_id AND org = :org"
    )
    with db.session() as s:
        # crew_id is validated by this lookup *before* any UPDATE runs, and as
        # the query's only earlier-bound parameter it's always Postgres's `$1`
        # on a bad-input error - matching callboard's error text exactly (a
        # crew_id bound alongside SET columns in one UPDATE would shift to
        # `$2`, which broke byte-parity when this was tried - see SEAMS.md).
        row = s.execute(select_sql, {"crew_id": crew_id, "org": org}).mappings().first()
        if row is None:
            return None
        if updates:
            set_clause = ", ".join(f"{col} = :{col}" for col in updates)
            s.execute(
                text(f"UPDATE tg_crew SET {set_clause} WHERE id = :crew_id"),
                {**updates, "crew_id": crew_id},
            )
            row = s.execute(select_sql, {"crew_id": crew_id, "org": org}).mappings().first()
        s.commit()
    return dict(row) if row else None
