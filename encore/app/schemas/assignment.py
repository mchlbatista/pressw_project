"""Pydantic models for /v3/shifts/{id}/assignments - see schemas/shift.py's Assignment for
the response shape; this only adds the offer request body.
"""
from pydantic import BaseModel


class AssignmentOffer(BaseModel):
    crew_id: int
