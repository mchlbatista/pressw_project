"""Pydantic response models for /v3/shifts - the shape a 2026 API should have.

Deviations from the legacy wire shape are intentional - see TRADEOFFS.md:
- `starts_at`/`ends_at` are real ISO 8601 datetimes (UTC), not "MM/DD/YYYY HH:MM" venue-local
  strings a client has to parse against a separately-fetched venue timezone.
- `status` is a lowercase word (open/full/cancelled), not OPEN/FULL/CXL - CXL in particular
  reads as a typo, not a status, to anyone who hasn't read callboard's source.
- Assignment `status` is a lowercase word (offered/accepted/expired/cancelled), not a bare
  letter code (O/A/E/X).
- No `roster_rows` endpoint - it's a legacy-frontend HTML concern; the same data is already
  in `ShiftDetail.assignments`.
"""
from datetime import datetime

from pydantic import BaseModel, field_validator

_SHIFT_STATUS = {"OPEN": "open", "FULL": "full", "CXL": "cancelled"}
_ASSIGNMENT_STATUS = {"O": "offered", "A": "accepted", "E": "expired", "X": "cancelled"}


class Assignment(BaseModel):
    id: int
    crew_id: int
    crew_email: str
    shift_id: int
    pay_estimate: float | None
    status: str

    @field_validator("pay_estimate", mode="before")
    @classmethod
    def _parse_pay(cls, v):
        return float(v) if v else None

    @field_validator("status", mode="before")
    @classmethod
    def _parse_status(cls, v):
        return _ASSIGNMENT_STATUS.get(v, v)


class Shift(BaseModel):
    id: int
    org: int
    venue: str
    title: str
    starts_at: datetime
    ends_at: datetime
    slots: int
    open_slots: int
    status: str

    @field_validator("status", mode="before")
    @classmethod
    def _parse_status(cls, v):
        return _SHIFT_STATUS.get(v, v)


class ShiftDetail(Shift):
    assignments: list[Assignment]


class ShiftList(BaseModel):
    items: list[Shift]
    page: int
    per_page: int
    total: int


class ShiftCreate(BaseModel):
    venue_id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    slots: int


class CancelResult(BaseModel):
    cancelled: int
    notified: int
