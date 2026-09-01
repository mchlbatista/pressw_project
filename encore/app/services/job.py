"""Wave 2's background job: stale-offer expiry + queue drain.

Ported from callboard's "nightly" maintenance job (accelerated to every 5 minutes in this
environment - see README.md and main.py's JOB_TICK_SECONDS). Digest logic deliberately stays
on callboard (wave 3, see SEAMS.md's wave plan) - it's not idempotent (confirmed bug: the
digest resends unconditionally every tick), so unlike expiry/drain it can't safely run in two
places at once. That's also why it's safe for this ported job to run alongside callboard's own
uncontrollable job during the migration window (callboard is a black box - its internal job
can't be disabled per-org): expiry is guarded by `WHERE status = 'O'` and drain by row
existence, so a double-run from both services is a no-op, not a double-write. See SEAMS.md's
"Cut couplings & mitigations" for the full argument.

STALE_OFFER_SECONDS is an unconfirmed assumption, not a probed value. Real seed data only
bounds callboard's actual threshold: an offer 45min-2.4h old stays 'O', one 30 days old is
already 'E' - both seed buckets were resolved by the time this was checked, so the exact
cutoff is unknown. Flagged in TRADEOFFS.md as an assumption to revisit (passive observation
of real 'O' rows aging past this default in a later session would tighten it - no synthetic
data was inserted to force the question, at the user's explicit direction).
"""
import os

from sqlalchemy import text

from .. import db

STALE_OFFER_SECONDS = int(os.environ.get("STALE_OFFER_SECONDS", 24 * 3600))


def drain_queue() -> int:
    with db.session() as s:
        result = s.execute(text("DELETE FROM callboard_queue WHERE kind = 'ACCEPT'"))
        s.commit()
    return result.rowcount


def expire_stale_offers() -> int:
    with db.session() as s:
        result = s.execute(
            text(
                "UPDATE assignments SET status = 'E', updated_on = now()::text "
                "WHERE status = 'O' AND offered_at < extract(epoch from now())::int - :threshold"
            ),
            {"threshold": STALE_OFFER_SECONDS},
        )
        s.commit()
    return result.rowcount


def run_tick() -> None:
    # Confirmed order from the clean-tick probe (scratch/DISCOVERIES.md): drain, then expire.
    drain_queue()
    expire_stale_offers()
