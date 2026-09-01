"""Insert-only helpers for `messages`, used by wave 2's `shifts`/`assignments` services.

`messages` is a wave-3 table (see SEAMS.md's wave plan) - `message/{list,send,confirm}` stay
on callboard until wave 3. But `assignment/offer` and `shift/cancel` (wave 2) each insert a
row here (`CALLOUT`, `CXL`) on the real callboard, so encore's wave-2 wrapper has to as well
to stay byte-compatible with what callboard's `message/list` will show. This is a deliberate,
documented cross-wave write - see SEAMS.md's "Cut couplings & mitigations" - not scope creep
into wave 3, which is why this module only inserts and has no list/read logic.
"""
from sqlalchemy.orm import Session
from sqlalchemy import text


def insert_callout(s: Session, org: int, crew_id: int, assignment_id: int, shift_title: str) -> None:
    s.execute(
        text(
            "INSERT INTO messages (org, crew_id, assignment_id, kind, body, shift_title, sent, read) "
            "VALUES (:org, :crew_id, :assignment_id, 'CALLOUT', :body, :shift_title, "
            "extract(epoch from now())::int, 'N')"
        ),
        {
            "org": org,
            "crew_id": crew_id,
            "assignment_id": assignment_id,
            "body": f"You have been offered a call: {shift_title}",
            "shift_title": shift_title,
        },
    )


def insert_cxl(s: Session, org: int, crew_id: int, assignment_id: int, shift_title: str) -> None:
    s.execute(
        text(
            "INSERT INTO messages (org, crew_id, assignment_id, kind, body, shift_title, sent, read) "
            "VALUES (:org, :crew_id, :assignment_id, 'CXL', :body, :shift_title, "
            "extract(epoch from now())::int, 'N')"
        ),
        {
            "org": org,
            "crew_id": crew_id,
            "assignment_id": assignment_id,
            "body": f"Shift cancelled: {shift_title}",
            "shift_title": shift_title,
        },
    )
