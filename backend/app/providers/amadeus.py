"""Amadeus provider — https://developers.amadeus.com  (Self-Service APIs)

Why Amadeus
-----------
* Very broad global airline / GDS coverage.
* Free **test** tier (host ``test.api.amadeus.com``) with a monthly quota.
* Data is richer but more complex than Duffel's — we normalise it here.

Setup
-----
1. Register at https://developers.amadeus.com/ and create an app.
2. Copy the **API Key** and **API Secret**.
3. ``backend/.env``:

       AMADEUS_CLIENT_ID=your_api_key
       AMADEUS_CLIENT_SECRET=your_api_secret
       AMADEUS_HOSTNAME=test.api.amadeus.com     # or api.amadeus.com in prod
       ENABLED_PROVIDERS=mock,amadeus

Auth
----
OAuth2 client-credentials. We fetch a bearer token and cache it in memory until
~30s before it expires, refreshing on demand.

API reference
-------------
* Token:  POST /v1/security/oauth2/token   (form-encoded)
* Search: POST /v2/shopping/flight-offers   (JSON body — handles one-way,
  round-trip AND multi-city with one shape)
  https://developers.amadeus.com/self-service/category/flights/api-doc/flight-offers-search
"""

from __future__ import annotations

import time
from datetime import datetime

import httpx

from app.config import get_settings
from app.providers._http import HttpProviderMixin
from app.providers.base import FlightProvider, ProviderSearchQuery
from app.providers.support import (
    build_slice,
    finalize_offer,
    iso8601_duration_to_minutes,
    minutes_between,
)
from app.models.flight import (
    BaggageAllowance,
    BookingType,
    CabinClass,
    FlightOffer,
    Segment,
)

_CABIN_TO_AMADEUS = {
    CabinClass.economy: "ECONOMY",
    CabinClass.premium_economy: "PREMIUM_ECONOMY",
    CabinClass.business: "BUSINESS",
    CabinClass.first: "FIRST",
}


class AmadeusProvider(HttpProviderMixin, FlightProvider):
    key = "amadeus"
    display_name = "Amadeus"

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = settings.amadeus_client_id
        self._client_secret = settings.amadeus_client_secret
        host = settings.amadeus_hostname or "test.api.amadeus.com"
        self.base_url = f"https://{host}"
        self.default_headers = {"Accept": "application/json"}

        # cached token
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def is_configured(self) -> bool:
        return bool(self._client_id and self._client_secret)

    # ------------------------------------------------------------------
    async def _get_token(self) -> str:
        """Return a valid bearer token, refreshing if needed."""
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token

        resp = await self.client.post(
            "/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 1799))
        return self._token

    # ------------------------------------------------------------------
    async def search(self, query: ProviderSearchQuery) -> list[FlightOffer]:
        if not self.is_configured:
            return []

        try:
            token = await self._get_token()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Amadeus auth failed: {exc}") from exc

        travelers: list[dict] = []
        tid = 1
        for _ in range(query.passengers.adults):
            travelers.append({"id": str(tid), "travelerType": "ADULT"})
            tid += 1
        for _ in range(query.passengers.children):
            travelers.append({"id": str(tid), "travelerType": "CHILD"})
            tid += 1
        for _ in range(query.passengers.infants):
            # HELD_INFANT must reference an adult's id.
            travelers.append(
                {"id": str(tid), "travelerType": "HELD_INFANT", "associatedAdultId": "1"}
            )
            tid += 1

        origin_destinations = [
            {
                "id": str(i + 1),
                "originLocationCode": leg.origin,
                "destinationLocationCode": leg.destination,
                "departureDateTimeRange": {"date": leg.departure_date.isoformat()},
            }
            for i, leg in enumerate(query.legs)
        ]

        body = {
            "currencyCode": query.currency,
            "originDestinations": origin_destinations,
            "travelers": travelers,
            "sources": ["GDS"],
            "searchCriteria": {
                "maxFlightOffers": min(query.max_results, 100),
                "flightFilters": {
                    "cabinRestrictions": [
                        {
                            "cabin": _CABIN_TO_AMADEUS.get(query.cabin_class, "ECONOMY"),
                            "coverage": "MOST_SEGMENTS",
                            "originDestinationIds": [od["id"] for od in origin_destinations],
                        }
                    ]
                },
            },
        }

        try:
            resp = await self.client.post(
                "/v2/shopping/flight-offers",
                json=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Amadeus {exc.response.status_code}: {_amadeus_error(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Amadeus request failed: {exc}") from exc

        payload = resp.json()
        dictionaries = payload.get("dictionaries", {}) or {}
        carriers: dict[str, str] = dictionaries.get("carriers", {}) or {}

        offers: list[FlightOffer] = []
        for raw in payload.get("data", []) or []:
            parsed = self._parse_offer(raw, query, carriers)
            if parsed is not None:
                offers.append(parsed)
        return offers

    # ------------------------------------------------------------------
    def _parse_offer(
        self, raw: dict, query: ProviderSearchQuery, carriers: dict[str, str]
    ) -> FlightOffer | None:
        try:
            slices = [
                self._parse_itinerary(it, query, carriers)
                for it in raw["itineraries"]
            ]
        except (KeyError, ValueError):
            return None

        price = raw.get("price", {})
        total = float(price.get("grandTotal") or price.get("total") or 0)
        currency = price.get("currency", query.currency)

        baggage = _offer_baggage(raw)

        return finalize_offer(
            provider_key=self.key,
            native_id=raw["id"],
            total_amount=total,
            total_currency=currency,
            slices=slices,
            passenger_count=query.passengers.total,
            cabin_class=query.cabin_class,
            # Amadeus Self-Service search results are not directly bookable
            # without the Flight Offers Price + Create Orders flow, which we
            # don't build (no in-app checkout). Treat as a search link.
            booking_type=BookingType.search_link,
            baggage=baggage,
            raw=raw,
        )

    def _parse_itinerary(
        self, it: dict, query: ProviderSearchQuery, carriers: dict[str, str]
    ):
        segments = [
            self._parse_segment(seg, query, carriers) for seg in it["segments"]
        ]
        return build_slice(segments)

    def _parse_segment(
        self, seg: dict, query: ProviderSearchQuery, carriers: dict[str, str]
    ) -> Segment:
        dep = datetime.fromisoformat(seg["departure"]["at"])
        arr = datetime.fromisoformat(seg["arrival"]["at"])
        carrier_code = seg.get("carrierCode", "??")
        duration = iso8601_duration_to_minutes(seg.get("duration")) or minutes_between(
            dep, arr
        )
        return Segment(
            origin=seg["departure"]["iataCode"],
            destination=seg["arrival"]["iataCode"],
            departure_at=dep,
            arrival_at=arr,
            marketing_carrier_code=carrier_code,
            marketing_carrier_name=carriers.get(carrier_code),
            operating_carrier_code=(seg.get("operating") or {}).get("carrierCode"),
            flight_number=seg.get("number"),
            aircraft=(seg.get("aircraft") or {}).get("code"),
            duration_minutes=duration,
            cabin_class=query.cabin_class,
        )


def _amadeus_error(response: httpx.Response) -> str:
    try:
        errs = response.json().get("errors") or []
        if errs:
            first = errs[0]
            return f"{first.get('title')} — {first.get('detail')}"
    except Exception:  # noqa: BLE001
        pass
    return response.text[:200]


def _offer_baggage(raw_offer: dict) -> BaggageAllowance | None:
    """Pull the first includedCheckedBags block from travelerPricings."""
    for tp in raw_offer.get("travelerPricings", []):
        for fd in tp.get("fareDetailsBySegment", []):
            bags = fd.get("includedCheckedBags") or {}
            qty = bags.get("quantity")
            weight = bags.get("weight")
            if qty:
                return BaggageAllowance(checked_bags=qty, description=f"{qty} checked")
            if weight:
                unit = bags.get("weightUnit", "KG")
                return BaggageAllowance(
                    weight_kg=weight if unit.upper().startswith("K") else None,
                    description=f"{weight}{unit}",
                )
    return None
