"""Airport / city autocomplete.

    GET /api/airports?q=acc&limit=8   -> ranked matches
    GET /api/airports/ACC             -> one airport by IATA code

Powers the search form's "search-as-you-type" origin/destination fields.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.airport import Airport, AirportSearchResponse
from app.services.airport_service import get_airport_service

router = APIRouter(prefix="/api/airports", tags=["airports"])


@router.get("", response_model=AirportSearchResponse, summary="Autocomplete airports")
def search_airports(
    q: str = Query(default="", description="Partial IATA code / city / airport name."),
    limit: int = Query(default=8, ge=1, le=25),
) -> AirportSearchResponse:
    service = get_airport_service()
    results = service.search(q, limit=limit)
    return AirportSearchResponse(query=q, results=results)


@router.get("/{iata}", response_model=Airport, summary="Get one airport")
def get_airport(iata: str) -> Airport:
    airport = get_airport_service().get(iata)
    if airport is None:
        raise HTTPException(status_code=404, detail=f"Unknown airport code: {iata!r}")
    return airport
