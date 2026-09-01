"""Tests for the ported background job (services/job.py): stale-offer expiry + queue drain.

Each test inserts its own throwaway fixture rows and deletes them in a `finally`, rather than
relying on or permanently mutating the shared seed data - this stack is treated like a real
shared database, not a scratch pad (see SEAMS.md/TRADEOFFS.md on the job's threshold being an
unconfirmed assumption, not something to pin down by inserting probe rows into it).
"""
from sqlalchemy import text

from app import db
from app.services import job


def test_expire_stale_offers_flips_old_offers_and_is_idempotent():
    with db.session() as s:
        assignment_id = s.execute(
            text(
                "INSERT INTO assignments (org_id, shift_id, crew_id, status, shift_title, offered_at, updated_on) "
                "VALUES (3, 3, 1, 'O', 'job test fixture', "
                "extract(epoch from now())::int - :age, now()::text) RETURNING id"
            ),
            {"age": job.STALE_OFFER_SECONDS + 60},
        ).scalar_one()
        s.commit()
    try:
        changed = job.expire_stale_offers()
        assert changed >= 1
        with db.session() as s:
            status = s.execute(
                text("SELECT status FROM assignments WHERE id = :id"), {"id": assignment_id}
            ).scalar_one()
        assert status == "E"

        # idempotent: a second run doesn't touch the now-'E' row again
        changed_again = job.expire_stale_offers()
        with db.session() as s:
            still = s.execute(
                text("SELECT status FROM assignments WHERE id = :id"), {"id": assignment_id}
            ).scalar_one()
        assert still == "E"
    finally:
        with db.session() as s:
            s.execute(text("DELETE FROM assignments WHERE id = :id"), {"id": assignment_id})
            s.commit()


def test_expire_stale_offers_leaves_fresh_offers_alone():
    with db.session() as s:
        assignment_id = s.execute(
            text(
                "INSERT INTO assignments (org_id, shift_id, crew_id, status, shift_title, offered_at, updated_on) "
                "VALUES (3, 3, 1, 'O', 'job test fixture (fresh)', "
                "extract(epoch from now())::int, now()::text) RETURNING id"
            )
        ).scalar_one()
        s.commit()
    try:
        job.expire_stale_offers()
        with db.session() as s:
            status = s.execute(
                text("SELECT status FROM assignments WHERE id = :id"), {"id": assignment_id}
            ).scalar_one()
        assert status == "O"
    finally:
        with db.session() as s:
            s.execute(text("DELETE FROM assignments WHERE id = :id"), {"id": assignment_id})
            s.commit()


def test_drain_queue_deletes_accept_rows_and_is_idempotent():
    with db.session() as s:
        queue_id = s.execute(
            text(
                "INSERT INTO callboard_queue (org_id, kind, payload, queued_at) "
                "VALUES (3, 'ACCEPT', '{\"job test fixture\": true}', extract(epoch from now())::int) "
                "RETURNING id"
            )
        ).scalar_one()
        s.commit()

    deleted = job.drain_queue()
    assert deleted >= 1
    with db.session() as s:
        remaining = s.execute(
            text("SELECT count(*) FROM callboard_queue WHERE id = :id"), {"id": queue_id}
        ).scalar_one()
    assert remaining == 0

    # idempotent: nothing left to delete on a second run for this row
    second_pass_deleted = job.drain_queue()
    assert second_pass_deleted == 0
