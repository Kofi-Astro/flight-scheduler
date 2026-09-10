"""Search orchestration — the heart of the app.

Responsibilities
----------------
1. Translate a :class:`SearchRequest` into the provider-agnostic
   :class:`ProviderSearchQuery`.
2. Fan the query out to every active provider **concurrently**, with a per-
   provider timeout, collecting offers and (separately) errors.
3. Normalise every offer into the operator's chosen currency.
4. Attach booking / deep links.
5. De-duplicate near-identical offers across providers.
6. Compute the summary block the frontend uses to seed filter ranges.

The flexible-dates ("cheapest days") grid reuses the same machinery, one search
per date cell, with sampling + a concurrency cap so it stays responsive.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from app.models.flight import (
    FlightOffer,
    PriceGridCell,
    PriceGridResponse,
    ProviderError,
    SearchResponse,
)
from app.models.search import (
    FlexibleDatesRequest,
    MultiCityRequest,
    SearchRequest,
)
from app.providers.base import FlightProvider, ProviderSearchQuery, QueryLeg
from app.providers.registry import get_active_providers
from app.services import deeplink_service
from app.services.currency_service import get_currency_service

logger = logging.getLogger("flight_scheduler.search")

# One provider must answer within this many seconds or it's dropped for that
# search (its partial-coverage error is reported to the operator).
_PER_PROVIDER_TIMEOUT = 30.0

# Flexible-dates mode: never fire more than this many cell-searches, and never
# more than this many at once.
_FLEX_MAX_CELLS = 45
_FLEX_CONCURRENCY = 6


# ---------------------------------------------------------------------------
# Standard search (one-way / round-trip / multi-city)
# ---------------------------------------------------------------------------
async def search_flights(request: SearchRequest) -> SearchResponse:
    legs = [QueryLeg(request.origin, request.destination, request.departure_date)]
    if request.return_date:
        legs.append(
            QueryLeg(request.destination, request.origin, request.return_date)
        )
    query = ProviderSearchQuery(
        legs=legs,
        passengers=request.passengers,
        cabin_class=request.cabin_class,
        currency=request.currency,
        max_results=request.max_results_per_provider,
    )
    return await _run_search(query, request.currency)


async def search_multi_city(request: MultiCityRequest) -> SearchResponse:
    legs = [
        QueryLeg(leg.origin, leg.destination, leg.departure_date)
        for leg in request.legs
    ]
    query = ProviderSearchQuery(
        legs=legs,
        passengers=request.passengers,
        cabin_class=request.cabin_class,
        currency=request.currency,
        max_results=request.max_results_per_provider,
    )
    return await _run_search(query, request.currency)


async def _run_search(
    query: ProviderSearchQuery, target_currency: str
) -> SearchResponse:
    providers = get_active_providers()

    # --- fan out ---------------------------------------------------------
    results = await asyncio.gather(
        *(_search_one_provider(p, query) for p in providers),
        return_exceptions=False,  # _search_one_provider never raises
    )

    all_offers: list[FlightOffer] = []
    errors: list[ProviderError] = []
    for provider, (offers, error) in zip(providers, results):
        if error is not None:
            errors.append(ProviderError(provider=provider.key, message=error))
        all_offers.extend(offers)

    # --- currency normalisation ----------------------------------------
    currency_service = get_currency_service()
    for offer in all_offers:
        if offer.total_currency != target_currency:
            offer.total_amount = await currency_service.convert(
                offer.total_amount, offer.total_currency, target_currency
            )
            offer.total_currency = target_currency

    # --- de-duplicate across providers -------------------------------
    deduped = _dedupe(all_offers)

    # --- attach booking links --------------------------------------
    for offer in deduped:
        offer.booking_links = deeplink_service.build_links(
            offer,
            passengers=query.passengers,
            cabin=query.cabin_class,
        )
        if not offer.deep_link:
            offer.deep_link = offer.booking_links.get("native") or offer.booking_links[
                "google_flights"
            ]

    # --- default sort: cheapest first --------------------------------
    deduped.sort(key=lambda o: (o.total_amount, o.total_duration_minutes))

    # --- summary block ------------------------------------------
    summary = _summary(deduped)

    return SearchResponse(
        offers=deduped,
        currency=target_currency,
        provider_errors=errors,
        providers_queried=[p.key for p in providers],
        **summary,
    )


async def _search_one_provider(
    provider: FlightProvider, query: ProviderSearchQuery
) -> tuple[list[FlightOffer], str | None]:
    """Run one provider, converting any failure into a message string.

    Returns ``(offers, error_message_or_None)``. Never raises — a broken
    provider must not fail the whole search.
    """
    try:
        offers = await asyncio.wait_for(
            provider.search(query), timeout=_PER_PROVIDER_TIMEOUT
        )
        return offers, None
    except asyncio.TimeoutError:
        logger.warning("Provider %s timed out", provider.key)
        return [], f"{provider.display_name} timed out after {_PER_PROVIDER_TIMEOUT:.0f}s"
    except Exception as exc:  # noqa: BLE001 - deliberately broad; report it
        logger.warning("Provider %s failed: %s", provider.key, exc)
        return [], str(exc)


def _dedupe(offers: list[FlightOffer]) -> list[FlightOffer]:
    """Drop offers that are effectively the same itinerary + price.

    Two offers collide when every slice has the same operating carriers and the
    same departure/arrival minutes, AND the price is within 1 unit. We keep the
    first (providers earlier in ``ENABLED_PROVIDERS`` win, which is why order is
    a priority list).
    """
    seen: set[tuple] = set()
    out: list[FlightOffer] = []
    for offer in offers:
        signature = (
            round(offer.total_amount),
            tuple(
                (
                    seg.marketing_carrier_code,
                    seg.origin,
                    seg.destination,
                    seg.departure_at.strftime("%Y%m%d%H%M"),
                )
                for sl in offer.slices
                for seg in sl.segments
            ),
        )
        if signature in seen:
            continue
        seen.add(signature)
        out.append(offer)
    return out


def _summary(offers: list[FlightOffer]) -> dict:
    if not offers:
        return {
            "min_price": None,
            "max_price": None,
            "min_duration_minutes": None,
            "max_duration_minutes": None,
        }
    prices = [o.total_amount for o in offers]
    durations = [o.total_duration_minutes for o in offers]
    return {
        "min_price": min(prices),
        "max_price": max(prices),
        "min_duration_minutes": min(durations),
        "max_duration_minutes": max(durations),
    }


# ---------------------------------------------------------------------------
# Flexible dates (cheapest-days price grid)
# ---------------------------------------------------------------------------
async def search_flexible_dates(
    request: FlexibleDatesRequest,
) -> PriceGridResponse:
    """Build a price grid over ±``flex_days`` around the chosen date(s).

    * One-way  -> a 1-D grid of departure dates.
    * Round    -> a 2-D grid (departure x return). To respect ``_FLEX_MAX_CELLS``
      we sample the return offsets so the grid stays small and fast.
    """
    is_round = request.return_date is not None
    dep_offsets = list(range(-request.flex_days, request.flex_days + 1))

    # Build the list of (departure_date, return_date | None) cells.
    cells: list[tuple[date, date | None]] = []
    if not is_round:
        cells = [(request.departure_date + timedelta(days=o), None) for o in dep_offsets]
    else:
        ret_offsets = _sample_offsets(request.flex_days, len(dep_offsets))
        for do in dep_offsets:
            for ro in ret_offsets:
                dep = request.departure_date + timedelta(days=do)
                ret = request.return_date + timedelta(days=ro)
                if ret >= dep:  # never return before you leave
                    cells.append((dep, ret))

    # Trim to the cap, keeping an even spread.
    if len(cells) > _FLEX_MAX_CELLS:
        step = len(cells) / _FLEX_MAX_CELLS
        cells = [cells[int(i * step)] for i in range(_FLEX_MAX_CELLS)]

    # Skip cells whose departure is in the past.
    today = date.today()
    cells = [c for c in cells if c[0] >= today]

    semaphore = asyncio.Semaphore(_FLEX_CONCURRENCY)
    errors: list[ProviderError] = []

    async def price_cell(dep: date, ret: date | None) -> PriceGridCell:
        async with semaphore:
            sub = SearchRequest(
                origin=request.origin,
                destination=request.destination,
                departure_date=dep,
                return_date=ret,
                passengers=request.passengers,
                cabin_class=request.cabin_class,
                currency=request.currency,
                max_results_per_provider=8,  # we only need the cheapest
            )
            try:
                response = await search_flights(sub)
            except Exception as exc:  # noqa: BLE001
                logger.warning("flex cell %s/%s failed: %s", dep, ret, exc)
                return PriceGridCell(
                    departure_date=dep.isoformat(),
                    return_date=ret.isoformat() if ret else None,
                    cheapest_price=None,
                    currency=request.currency,
                )
            cheapest = response.offers[0] if response.offers else None
            return PriceGridCell(
                departure_date=dep.isoformat(),
                return_date=ret.isoformat() if ret else None,
                cheapest_price=cheapest.total_amount if cheapest else None,
                currency=request.currency,
                offer_id=cheapest.id if cheapest else None,
            )

    grid = await asyncio.gather(*(price_cell(dep, ret) for dep, ret in cells))

    priced = [c for c in grid if c.cheapest_price is not None]
    cheapest_cell = min(priced, key=lambda c: c.cheapest_price) if priced else None

    return PriceGridResponse(
        currency=request.currency,
        cells=list(grid),
        cheapest=cheapest_cell,
        provider_errors=errors,
    )


def _sample_offsets(flex_days: int, dep_count: int) -> list[int]:
    """Pick a manageable set of return-date offsets.

    For small windows use them all; for large ones keep the extremes + middle so
    the grid still shows the useful spread without exploding the cell count.
    """
    full = list(range(-flex_days, flex_days + 1))
    if dep_count * len(full) <= _FLEX_MAX_CELLS:
        return full
    if flex_days <= 2:
        return full
    return sorted({-flex_days, -flex_days // 2, 0, flex_days // 2, flex_days})
