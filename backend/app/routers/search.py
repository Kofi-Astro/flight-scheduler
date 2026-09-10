"""Search endpoints.

    POST /api/search              one-way / round-trip
    POST /api/search/flexible     cheapest-days price grid
    POST /api/search/multi-city   multi-city itinerary (nice-to-have)

All three accept JSON bodies (see ``app/models/search.py``) and return
normalised offers already converted to the requested currency with booking
links attached.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.models.flight import PriceGridResponse, SearchResponse
from app.models.search import (
    FlexibleDatesRequest,
    MultiCityRequest,
    SearchRequest,
)
from app.services import search_service

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse, summary="Search flights")
async def search(request: SearchRequest) -> SearchResponse:
    """Search all active providers for one-way or round-trip flights.

    The response is always ``200`` even if some providers failed — check
    ``provider_errors`` for partial-coverage warnings. Offers come back sorted
    cheapest-first; the frontend re-sorts/filters client-side.
    """
    return await search_service.search_flights(request)


@router.post(
    "/search/flexible",
    response_model=PriceGridResponse,
    summary="Flexible-dates price grid",
)
async def search_flexible(request: FlexibleDatesRequest) -> PriceGridResponse:
    """Return the cheapest price for each date (or date-pair) in a ±N-day window.

    Use it to spot the cheapest days to fly. This fires many small searches, so
    it's slower than a single search — the window and cell count are capped
    server-side to keep it responsive.
    """
    return await search_service.search_flexible_dates(request)


@router.post(
    "/search/multi-city",
    response_model=SearchResponse,
    summary="Multi-city search",
)
async def search_multi_city(request: MultiCityRequest) -> SearchResponse:
    """Search an itinerary with 2-6 legs (e.g. ACC->IST->CDG->ACC).

    Not every provider supports multi-city; those that don't are simply absent
    from the results (see ``providers_queried`` vs ``provider_errors``).
    """
    return await search_service.search_multi_city(request)
