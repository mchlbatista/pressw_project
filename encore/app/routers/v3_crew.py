"""Modern /v3/crew endpoints - real pagination, booleans, a parsed prefs
object, and no per_page=0 unbounded-result escape hatch (see TRADEOFFS.md).
"""
from fastapi import APIRouter, HTTPException, Query

from ..schemas.crew import Crew, CrewDetail, CrewList, CrewUpdate
from ..services import crew as crew_service

router = APIRouter(prefix="/v3/crew", tags=["crew"])

MAX_PER_PAGE = 100


def _to_crew(row: dict) -> Crew:
    return Crew(
        id=row["crew_id"],
        org=row["org"],
        email=row["crew_name"],
        display_name=row["display_name"],
        rate=row["rate"],
        is_lead=row["is_lead"],
        notes=row["notes"],
    )


@router.get("")
def list_crew(
    org: int, page: int = 1, per_page: int = Query(default=25, le=MAX_PER_PAGE)
) -> CrewList:
    rows, total = crew_service.list_crew(org, page, per_page)
    return CrewList(
        items=[_to_crew(r) for r in rows], page=page, per_page=per_page, total=total
    )


@router.get("/{crew_id}")
def get_crew(org: int, crew_id: int) -> CrewDetail:
    row = crew_service.get_crew(org, str(crew_id))
    if row is None:
        raise HTTPException(status_code=404, detail="crew not found")
    return CrewDetail(**_to_crew(row).model_dump(), prefs=row["prefs_blob"])


@router.patch("/{crew_id}")
def update_crew(org: int, crew_id: int, body: CrewUpdate) -> Crew:
    fields = body.model_dump(exclude_unset=True)
    row = crew_service.update_crew(org, str(crew_id), fields)
    if row is None:
        raise HTTPException(status_code=404, detail="crew not found")
    return _to_crew(row)
