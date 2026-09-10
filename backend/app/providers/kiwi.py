"""Kiwi.com provider — Tequila API — https://tequila.kiwi.com

Why Kiwi
--------
* Aggregates low-cost / budget carriers that GDS-based APIs (Amadeus) miss, plus
  Kiwi's own "virtual interlining" (self-transfer) itineraries — great for wider
  route coverage and cheap options.
* Returns a real **deep_link** straight to Kiwi's checkout for each result, so
  the operator can send the client a working booking link immediately.

Setup
-----
1. Register at https://tequila.kiwi.com/  and create a "Solution".
   Production access needs approval; the sandbox key works for building.
2. ``backend/.env``:

       TEQUILA_API_KEY=your_tequila_api_key
       ENABLED_PROVIDERS=mock,kiwi

API reference
-------------
* Search: GET https://api.tequila.kiwi.com/v2/search
  Auth header: ``apikey: <key>``
  Dates are ``dd/mm/YYYY``. ``selected_cabins``: M=economy, W=premium,
  C=business, F=first.
  https://tequila.kiwi.com/portal/docs/tequila_api/search_api

Limitation
----------
This implementation covers one-way and round-trip. Kiwi's multi-city ("nomad")
search uses a different request shape; ``search()`` returns ``[]`` for 3+ legs
so the other providers still answer a multi-city query.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from app.config import get_settings
from app.providers._http import HttpProviderMixin
from app.providers.base import FlightProvider, ProviderSearchQuery
from app.providers.support import build_slice, finalize_offer
from app.models.flight import (
    BaggageAllowance,
    BookingType,
    CabinClass,
    FlightOffer,
    Segment,
)

_CABIN_TO_KIWI = {
    CabinClass.economy: "M",
    CabinClass.premium_economy: "W",
    CabinClass.business: "C",
    CabinClass.first: "F",
}


class KiwiProvider(HttpProviderMixin, FlightProvider):
    key = "kiwi"
    display_name = "Kiwi.com (Tequila)"

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.tequila_api_key
        self.base_url = "https://api.tequila.kiwi.com"
        self.default_headers = {"apikey": self._api_key, "Accept": "application/json"}

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: ProviderSearchQuery) -> list[FlightOffer]:
        if not self.is_configured:
            return []
        # Only one-way / round-trip supported here (see module docstring).
        if len(query.legs) > 2:
            return []

        out = query.legs[0]
        ret = query.legs[1] if len(query.legs) == 2 else None

        params = {
            "fly_from": out.origin,
            "fly_to": out.destination,
            "date_from": _kiwi_date(out.departure_date),
            "date_to": _kiwi_date(out.departure_date),
            "adults": query.passengers.adults,
            "children": query.passengers.children,
            "infants": query.passengers.infants,
            "selected_cabins": _CABIN_TO_KIWI.get(query.cabin_class, "M"),
            "curr": query.currency,
            "limit": min(query.max_results, 100),
            "vehicle_type": "aircraft",
            # Sort by price; the app re-sorts anyway but this gives a good sample.
            "sort": "price",
        }
        if ret is not None:
            params["flight_type"] = "round"
            params["return_from"] = _kiwi_date(ret.departure_date)
            params["return_to"] = _kiwi_date(ret.departure_date)
        else:
            params["flight_type"] = "oneway"

        try:
            resp = await self.client.get("/v2/search", params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Kiwi {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Kiwi request failed: {exc}") from exc

        data = resp.json().get("data", []) or []
        currency = resp.json().get("currency", query.currency)

        offers: list[FlightOffer] = []
        for raw in data[: query.max_results]:
            parsed = self._parse_offer(raw, query, currency, is_round=ret is not None)
            if parsed is not None:
                offers.append(parsed)
        return offers

    # ------------------------------------------------------------------
    def _parse_offer(
        self,
        raw: dict,
        query: ProviderSearchQuery,
        currency: str,
        is_round: bool,
    ) -> FlightOffer | None:
        route = raw.get("route", []) or []
        if not route:
            return None

        # Kiwi flattens all hops into ``route``; the ``return`` flag (0/1) marks
        # which direction each hop belongs to.
        outbound_hops = [h for h in route if not h.get("return")]
        inbound_hops = [h for h in route if h.get("return")]

        try:
            slices = [self._hops_to_slice(outbound_hops, query)]
            if is_round and inbound_hops:
                slices.append(self._hops_to_slice(inbound_hops, query))
        except (KeyError, ValueError):
            return None

        baggage = _kiwi_baggage(raw)

        return finalize_offer(
            provider_key=self.key,
            native_id=str(raw.get("id", raw.get("booking_token", "?"))),
            total_amount=float(raw.get("price", 0)),
            total_currency=currency,
            slices=slices,
            passenger_count=query.passengers.total,
            cabin_class=query.cabin_class,
            booking_type=BookingType.deep_link,
            deep_link=raw.get("deep_link"),
            baggage=baggage,
            raw=raw,
        )

    def _hops_to_slice(self, hops: list[dict], query: ProviderSearchQuery):
        segments: list[Segment] = []
        for hop in hops:
            dep = _kiwi_dt(hop["local_departure"])
            arr = _kiwi_dt(hop["local_arrival"])
            segments.append(
                Segment(
                    origin=hop["flyFrom"],
                    destination=hop["flyTo"],
                    departure_at=dep,
                    arrival_at=arr,
                    marketing_carrier_code=hop.get("airline", "??"),
                    marketing_carrier_name=hop.get("airline"),
                    operating_carrier_code=hop.get("operating_carrier") or None,
                    flight_number=str(hop.get("flight_no", "")),
                    aircraft=hop.get("equipment") or None,
                    duration_minutes=max(1, int((arr - dep).total_seconds() // 60)),
                    cabin_class=query.cabin_class,
                )
            )
        return build_slice(segments)


# ---------------------------------------------------------------------------
def _kiwi_date(d) -> str:
    """Tequila wants dd/mm/YYYY."""
    return d.strftime("%d/%m/%Y")


def _kiwi_dt(value: str) -> datetime:
    """Kiwi timestamps look like '2026-10-12T09:30:00.000Z' (already local)."""
    return datetime.fromisoformat(value.replace("Z", "").split(".")[0])


def _kiwi_baggage(raw: dict) -> BaggageAllowance | None:
    limits = raw.get("baglimit") or {}
    # hold_weight is per-bag kg; hold_dimensions_sum etc. also present.
    weight = limits.get("hold_weight")
    if weight:
        return BaggageAllowance(weight_kg=int(weight), description=f"{int(weight)}kg hold")
    if limits.get("hand_weight"):
        return BaggageAllowance(
            carry_on_bags=1,
            description=f"{int(limits['hand_weight'])}kg cabin only",
        )
    return None
