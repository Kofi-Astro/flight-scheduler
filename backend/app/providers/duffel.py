"""Duffel provider — https://duffel.com

Why Duffel first
----------------
* Modern JSON API, clean docs, self-serve signup.
* Free **test mode**: a token that looks like ``duffel_test_xxx`` returns
  synthetic-but-well-formed offers with no billing. Great for building.
* Good airline coverage for a booking-capable API.

Setup
-----
1. Sign up at https://app.duffel.com/  (no credit card for test mode).
2. Settings -> Access tokens -> create a **test** token.
3. Put it in ``backend/.env``:

       DUFFEL_API_TOKEN=duffel_test_xxxxxxxxxxxxxxxxxxxx
       DUFFEL_API_VERSION=v2
       ENABLED_PROVIDERS=mock,duffel

API reference
-------------
* Offer requests: https://duffel.com/docs/api/offer-requests/create-offer-request
* We call it with ``?return_offers=true`` so the offers come back in one round
  trip (fine for a scouting tool; for production you might paginate).

Booking note
------------
Duffel is a *booking* API — it doesn't hand out OTA deep links. We mark these
offers ``book_via_provider`` and record that fact; the deep-link service still
attaches a metasearch fallback link so the operator always has somewhere to
send the client. Actually completing a Duffel order is a future feature (the
spec explicitly does not want in-app checkout yet).
"""

from __future__ import annotations

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

# Map our cabin enum -> Duffel's accepted strings (they happen to match, but be
# explicit so a rename on our side doesn't silently break the API call).
_CABIN_TO_DUFFEL = {
    CabinClass.economy: "economy",
    CabinClass.premium_economy: "premium_economy",
    CabinClass.business: "business",
    CabinClass.first: "first",
}


class DuffelProvider(HttpProviderMixin, FlightProvider):
    key = "duffel"
    display_name = "Duffel"

    def __init__(self) -> None:
        settings = get_settings()
        self._token = settings.duffel_api_token
        self._version = settings.duffel_api_version or "v2"
        self.base_url = "https://api.duffel.com"
        self.default_headers = {
            "Authorization": f"Bearer {self._token}",
            "Duffel-Version": self._version,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @property
    def is_configured(self) -> bool:
        return bool(self._token)

    async def search(self, query: ProviderSearchQuery) -> list[FlightOffer]:
        if not self.is_configured:
            return []

        # --- build the request body -------------------------------------
        passengers: list[dict] = []
        passengers += [{"type": "adult"} for _ in range(query.passengers.adults)]
        passengers += [{"type": "child"} for _ in range(query.passengers.children)]
        passengers += [
            {"type": "infant_without_seat"}
            for _ in range(query.passengers.infants)
        ]

        body = {
            "data": {
                "slices": [
                    {
                        "origin": leg.origin,
                        "destination": leg.destination,
                        "departure_date": leg.departure_date.isoformat(),
                    }
                    for leg in query.legs
                ],
                "passengers": passengers,
                "cabin_class": _CABIN_TO_DUFFEL.get(query.cabin_class, "economy"),
            }
        }

        # --- call the API --------------------------------------------
        try:
            resp = await self.client.post(
                "/air/offer_requests",
                params={"return_offers": "true", "supplier_timeout": "20000"},
                json=body,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Surface a readable message; the service turns this into a
            # per-provider error without failing the whole search.
            detail = _first_error_message(exc.response)
            raise RuntimeError(f"Duffel {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Duffel request failed: {exc}") from exc

        payload = resp.json().get("data", {})
        raw_offers = payload.get("offers", []) or []

        offers: list[FlightOffer] = []
        for raw in raw_offers[: query.max_results]:
            parsed = self._parse_offer(raw, query)
            if parsed is not None:
                offers.append(parsed)
        return offers

    # ------------------------------------------------------------------
    def _parse_offer(
        self, raw: dict, query: ProviderSearchQuery
    ) -> FlightOffer | None:
        try:
            slices = [self._parse_slice(s, query) for s in raw["slices"]]
        except (KeyError, ValueError):
            return None

        owner = (raw.get("owner") or {}).get("name")

        # Offer-level baggage: Duffel puts baggage on
        # offer.slices[].segments[].passengers[].baggages — we summarise the
        # first checked-bag entry we see.
        baggage = _summarise_baggage(raw)

        return finalize_offer(
            provider_key=self.key,
            native_id=raw["id"],
            total_amount=float(raw["total_amount"]),
            total_currency=raw["total_currency"],
            slices=slices,
            passenger_count=query.passengers.total,
            cabin_class=query.cabin_class,
            booking_type=BookingType.book_via_provider,
            deep_link=None,  # filled with a metasearch fallback by the service
            baggage=baggage,
            raw=raw,
        )

    def _parse_slice(self, s: dict, query: ProviderSearchQuery):
        segments = [self._parse_segment(seg, query) for seg in s["segments"]]
        # ``build_slice`` recomputes layovers + total duration from the segment
        # times, which is more reliable than trusting the slice-level field.
        return build_slice(segments)

    def _parse_segment(self, seg: dict, query: ProviderSearchQuery) -> Segment:
        dep = datetime.fromisoformat(seg["departing_at"])
        arr = datetime.fromisoformat(seg["arriving_at"])
        mk = seg.get("marketing_carrier") or {}
        op = seg.get("operating_carrier") or {}

        duration = iso8601_duration_to_minutes(seg.get("duration")) or minutes_between(
            dep, arr
        )

        # Per-segment baggage from the first passenger entry.
        seg_bag = None
        pax = seg.get("passengers") or []
        if pax:
            seg_bag = _baggage_from_list(pax[0].get("baggages") or [])

        return Segment(
            origin=seg["origin"]["iata_code"],
            destination=seg["destination"]["iata_code"],
            departure_at=dep,
            arrival_at=arr,
            marketing_carrier_code=mk.get("iata_code", "??"),
            marketing_carrier_name=mk.get("name"),
            operating_carrier_code=op.get("iata_code"),
            flight_number=seg.get("marketing_carrier_flight_number"),
            aircraft=(seg.get("aircraft") or {}).get("name"),
            duration_minutes=duration,
            cabin_class=query.cabin_class,
            baggage=seg_bag,
        )


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _first_error_message(response: httpx.Response) -> str:
    try:
        errors = response.json().get("errors") or []
        if errors:
            return errors[0].get("message") or errors[0].get("title") or "unknown"
    except Exception:  # noqa: BLE001 - defensive: any parse failure -> generic
        pass
    return response.text[:200]


def _baggage_from_list(baggages: list[dict]) -> BaggageAllowance | None:
    checked = sum(
        b.get("quantity", 0) for b in baggages if b.get("type") == "checked"
    )
    carry = sum(
        b.get("quantity", 0) for b in baggages if b.get("type") == "carry_on"
    )
    if not checked and not carry:
        return None
    return BaggageAllowance(
        checked_bags=checked or None,
        carry_on_bags=carry or None,
        description=f"{checked} checked" if checked else "carry-on only",
    )


def _summarise_baggage(raw_offer: dict) -> BaggageAllowance | None:
    for s in raw_offer.get("slices", []):
        for seg in s.get("segments", []):
            for p in seg.get("passengers", []):
                bag = _baggage_from_list(p.get("baggages") or [])
                if bag:
                    return bag
    return None
