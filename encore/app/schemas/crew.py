"""Pydantic response models for /v3/crew - the shape a 2026 API should have.

`password` is never selected by services/crew.py, so there's nothing here to
accidentally expose. Deviations from the legacy wire shape (booleans instead
of Y/N, a parsed prefs object, `email` instead of `crew_name`, real
pagination instead of per_page=0) are intentional - see TRADEOFFS.md.
"""
import json

from pydantic import BaseModel, field_validator


class Crew(BaseModel):
    id: int
    org: int
    email: str
    display_name: str | None
    rate: float
    is_lead: bool
    notes: str

    @field_validator("is_lead", mode="before")
    @classmethod
    def _parse_is_lead(cls, v):
        return v == "Y" if isinstance(v, str) else v


class CrewDetail(Crew):
    prefs: dict

    @field_validator("prefs", mode="before")
    @classmethod
    def _parse_prefs(cls, v):
        return json.loads(v) if isinstance(v, str) else v


class CrewList(BaseModel):
    items: list[Crew]
    page: int
    per_page: int
    total: int


class CrewUpdate(BaseModel):
    notes: str | None = None
    rate: float | None = None
