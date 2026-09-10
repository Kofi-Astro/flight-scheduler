"""Travelpayouts provider — https://travelpayouts.com  (Skyscanner/Aviasales affiliate)

Why Travelpayouts
-----------------
* Affiliate network covering Aviasales / Skyscanner-style inventory.
* Every result carries an affiliate **deep link** (with your ``marker``) to a
  working booking page — and Travelpayouts pays commission on completed
  bookings. That is the future revenue stream the spec flags for the agency
  idea, wired up from day one.

Important nuance
----------------
The free **Flight Data API** used here (``/aviasales/v3/prices_for_dates``)
returns *cached cheapest prices*, not a live availability search. So:
  * prices are indicative (recently seen), not bookable-to-the-cent;
  * we get the number of transfers and total duration, but not the individual
    layover airports.
It is still very useful for cheap route coverage and the flexible-dates grid.
For live, precise itineraries use Duffel/Amadeus/Kiwi alongside it.

Setup
-----
1. Sign up at https://www.travelpayouts.com/  and get your **API token** and
   **marker** (affiliate id).
2. ``backend/.env``:

       TRAVELPAYOUTS_TOKEN=your_token
       TRAVELPAYOUTS_MARKER=your_marker
       ENABLED_PROVIDERS=mock,travelpayouts

API reference
-------------
https://support.travelpayouts.com/hc/en-us/articles/203956163
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from app.config import get_settings
from app.providers._http import HttpProviderMixin
from app.providers.base import FlightProvider, ProviderSearchQuery
from app.providers.support import finalize_offer, minutes_between
from app.models.flight import (
    BookingType,
    FlightOffer,
    Segment,
    Slice,
)

_AVIASALES_BASE = "https://www.aviasales.com"


class TravelpayoutsProvider(HttpProviderMixin, FlightProvider):
    key = "travelpayouts"
    display_name = "Travelpayouts (Aviasales/Skyscanner affiliate)"

    def __init__(self) -> None:
        settings = get_settings()
        self._token = settings.travelpayouts_token
        self._marker = settings.travelpayouts_marker
        self.base_url = "https://api.travelpayouts.com"
        self.default_headers = {"Accept": "application/json"}

    @property
    def is_configured(self) -> bool:
        # The token is required. Marker is optional but without it you earn no
        # commission and links are generic — warn in logs but still run.
        return bool(self._token)

    async def search(self, query: ProviderSearchQuery) -> list[FlightOffer]:
        if not self.is_configured:
            return []
        if len(query.legs) > 2:
            return []  # multi-city not supported by this endpoint

        out = query.legs[0]
        ret = query.legs[1] if len(query.legs) == 2 else None

        params = {
            "origin": out.origin,
            "destination": out.destination,
            "departure_at": out.departure_date.isoformat(),
            "currency": query.currency.lower(),
            "token": self._token,
            "limit": min(query.max_results, 30),
            "sorting": "price",
            "one_way": "false" if ret else "true",
        }
        if ret is not None:
            params["return_at"] = ret.departure_date.isoformat()

        try:
            resp = await self.client.get(
                "/aviasales/v3/prices_for_dates", params=params
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Travelpayouts {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Travelpayouts request failed: {exc}") from exc

        body = resp.json()
        rows = body.get("data", []) or []
        currency = (body.get("currency") or query.currency).upper()

        offers: list[FlightOffer] = []
        for i, row in enumerate(rows[: query.max_results]):
            parsed = self._parse_row(row, query, currency, ret is not None, i)
            if parsed is not None:
                offers.append(parsed)
        return offers

    # ------------------------------------------------------------------
    def _parse_row(
        self,
        row: dict,
        query: ProviderSearchQuery,
        currency: str,
        is_round: bool,
        index: int,
    ) -> FlightOffer | None:
        try:
            out_slice = self._row_to_slice(
                origin=row["origin"],
                destination=row["destination"],
                depart_iso=row["departure_at"],
                duration_min=int(row.get("duration_to") or row.get("duration") or 0),
                transfers=int(row.get("transfers", 0)),
                airline=row.get("airline", "??"),
                flight_number=str(row.get("flight_number", "")),
                cabin=query,
            )
        except (KeyError, ValueError):
            return None

        slices = [out_slice]
        if is_round and row.get("return_at"):
            try:
                slices.append(
                    self._row_to_slice(
                        origin=row["destination"],
                        destination=row["origin"],
                        depart_iso=row["return_at"],
                        duration_min=int(
                            row.get("duration_back") or row.get("duration") or 0
                        ),
                        transfers=int(row.get("return_transfers", row.get("transfers", 0))),
                        airline=row.get("airline", "??"),
                        flight_number="",
                        cabin=query,
                    )
                )
            except (KeyError, ValueError):
                pass

        deep_link = self._affiliate_link(row.get("link"))

        return finalize_offer(
            provider_key=self.key,
            native_id=f"{row['origin']}{row['destination']}{row.get('departure_at','')}-{index}",
            total_amount=float(row.get("price", 0)),
            total_currency=currency,
            slices=slices,
            passenger_count=query.passengers.total,
            cabin_class=query.cabin_class,
            booking_type=BookingType.deep_link,
            deep_link=deep_link,
            raw=row,
        )

    def _row_to_slice(
        self,
        *,
        origin: str,
        destination: str,
        depart_iso: str,
        duration_min: int,
        transfers: int,
        airline: str,
        flight_number: str,
        cabin: ProviderSearchQuery,
    ) -> Slice:
        """Build a slice from the aggregate row.

        We only have one aggregate flight record (no per-hop breakdown), so we
        model it as a single segment and set the slice's ``stops`` from the
        ``transfers`` field. Layover airports are unknown for this data source.
        """
        dep = _tp_dt(depart_iso)
        if duration_min <= 0:
            duration_min = 120 + transfers * 90  # rough fallback
        arr = dep + timedelta(minutes=duration_min)

        segment = Segment(
            origin=origin,
            destination=destination,
            departure_at=dep,
            arrival_at=arr,
            marketing_carrier_code=airline,
            marketing_carrier_name=airline,
            flight_number=flight_number or None,
            duration_minutes=minutes_between(dep, arr),
            cabin_class=cabin.cabin_class,
        )
        return Slice(
            origin=origin,
            destination=destination,
            departure_at=dep,
            arrival_at=arr,
            duration_minutes=minutes_between(dep, arr),
            stops=max(0, transfers),
            segments=[segment],
        )

    def _affiliate_link(self, link: str | None) -> str | None:
        if not link:
            return None
        full = link if link.startswith("http") else f"{_AVIASALES_BASE}{link}"
        if self._marker:
            sep = "&" if "?" in full else "?"
            full = f"{full}{sep}marker={self._marker}"
        return full


def _tp_dt(value: str) -> datetime:
    """Parse '2026-10-12T08:45:00Z' or with offset."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.fromisoformat(value.split("T")[0])
