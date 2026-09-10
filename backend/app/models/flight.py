"""Normalised flight-offer models.

Every provider (Duffel, Amadeus, Kiwi, ...) returns data in its own shape. Each
``FlightProvider`` implementation is responsible for mapping its raw response
into these models, so the rest of the app — services, routers, frontend — only
ever deals with ONE consistent structure.

Vocabulary
----------
* **Segment** — a single takeoff-to-landing flight on one aircraft
  (e.g. ACC -> IST on TK568).
* **Slice**   — one directional journey made of 1+ segments
  (e.g. ACC -> IST -> LHR is one slice with two segments and one layover).
  A one-way trip has 1 slice; a round trip has 2; multi-city has N.
* **Offer**   — a complete priced itinerary: all slices + a total price.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class CabinClass(str, Enum):
    """IATA-ish cabin classes. Kept as a small closed set for filtering."""

    economy = "economy"
    premium_economy = "premium_economy"
    business = "business"
    first = "first"


class BaggageAllowance(BaseModel):
    """Baggage info for a segment or offer, when the provider supplies it.

    Providers are inconsistent here — some give piece counts, some give weight,
    many give nothing. All fields are optional; the frontend shows "—" when we
    don't know.
    """

    checked_bags: int | None = Field(
        default=None, description="Number of included checked bags."
    )
    carry_on_bags: int | None = Field(
        default=None, description="Number of included carry-on bags."
    )
    weight_kg: int | None = Field(
        default=None, description="Weight limit per checked bag, if given in kg."
    )
    description: str | None = Field(
        default=None, description="Free-text fallback, e.g. '1 x 23kg'."
    )


class Segment(BaseModel):
    """One flight on one aircraft."""

    origin: str = Field(description="Departure airport IATA code, e.g. 'ACC'.")
    destination: str = Field(description="Arrival airport IATA code, e.g. 'IST'.")
    departure_at: datetime = Field(description="Scheduled local departure time.")
    arrival_at: datetime = Field(description="Scheduled local arrival time.")

    marketing_carrier_code: str = Field(
        description="2-letter IATA code of the airline selling the ticket, e.g. 'TK'."
    )
    marketing_carrier_name: str | None = None
    operating_carrier_code: str | None = Field(
        default=None, description="Airline actually flying the plane (codeshares)."
    )
    flight_number: str | None = None
    aircraft: str | None = None

    duration_minutes: int = Field(description="Flight time for this segment.")

    # Layover AFTER this segment, before the next one in the same slice.
    # Null on the final segment of a slice.
    layover_after_minutes: int | None = None

    cabin_class: CabinClass | None = None
    baggage: BaggageAllowance | None = None


class Slice(BaseModel):
    """One directional journey (may include stops)."""

    origin: str = Field(description="First segment's origin IATA code.")
    destination: str = Field(description="Last segment's destination IATA code.")
    departure_at: datetime
    arrival_at: datetime
    duration_minutes: int = Field(
        description="Total elapsed time including layovers."
    )
    stops: int = Field(description="Number of layovers (segments - 1).")
    segments: list[Segment]

    @property
    def layover_airports(self) -> list[str]:
        """IATA codes of intermediate airports (helper for summaries)."""
        return [seg.destination for seg in self.segments[:-1]]


class BookingType(str, Enum):
    """How the operator actually books this offer."""

    # We could complete the booking through the provider's API (Duffel).
    book_via_provider = "book_via_provider"
    # Provider gave us a real deep link to an airline/OTA checkout.
    deep_link = "deep_link"
    # No native link; we constructed a metasearch link (Google Flights etc.).
    search_link = "search_link"


class FlightOffer(BaseModel):
    """A complete, priced itinerary — the unit the results view renders."""

    # Opaque id, unique within a single search response. Format:
    # "<provider>:<provider-native-id>". Used by the shortlist feature.
    id: str
    provider: str = Field(description="Which provider produced this offer.")

    total_amount: float = Field(description="Total price for all passengers.")
    total_currency: str = Field(description="ISO 4217 code, e.g. 'USD', 'GHS'.")

    slices: list[Slice]

    passenger_count: int = 1
    cabin_class: CabinClass | None = None

    # Offer-level baggage summary (per passenger). Segment-level detail lives on
    # each ``Segment.baggage`` when available.
    baggage: BaggageAllowance | None = None

    # Booking / linking
    booking_type: BookingType = BookingType.search_link
    deep_link: str | None = Field(
        default=None,
        description="Where the 'Book' button sends the operator (best single link).",
    )
    # Extra links keyed by site name (google_flights, skyscanner, kayak, native).
    # Filled by the search service via deeplink_service so the frontend can offer
    # a choice. Not stored by providers.
    booking_links: dict[str, str] = Field(default_factory=dict)

    # A few denormalised fields make sorting/filtering on the frontend trivial
    # without re-deriving them from the slices every time.
    total_duration_minutes: int = Field(
        description="Sum of all slice durations."
    )
    max_stops: int = Field(description="Worst (highest) stop count across slices.")
    airline_codes: list[str] = Field(
        default_factory=list,
        description="Distinct marketing carrier codes across the whole offer.",
    )
    airline_names: list[str] = Field(default_factory=list)

    # When the price was fetched — offers are volatile, this helps the UI warn
    # the operator if a shortlisted price is stale.
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Kept for debugging / future fields. Excluded from responses unless asked
    # for via ?debug=1 (see the search router).
    raw: dict | None = Field(default=None, exclude=True)


class ProviderError(BaseModel):
    """Reported (not raised) when one provider fails but others succeed.

    The search endpoint always returns 200 with whatever offers it could get,
    plus this list so the operator knows coverage was partial.
    """

    provider: str
    message: str


class SearchResponse(BaseModel):
    """Envelope returned by ``POST /api/search``."""

    offers: list[FlightOffer]
    currency: str = Field(description="Currency all offers are expressed in.")
    provider_errors: list[ProviderError] = Field(default_factory=list)
    providers_queried: list[str] = Field(default_factory=list)

    # Small summary block the frontend uses to seed filter ranges.
    min_price: float | None = None
    max_price: float | None = None
    min_duration_minutes: int | None = None
    max_duration_minutes: int | None = None


class PriceGridCell(BaseModel):
    """One (outbound date, return date) combination in flexible-dates mode."""

    departure_date: str = Field(description="ISO date 'YYYY-MM-DD'.")
    return_date: str | None = Field(
        default=None, description="ISO date, or null for one-way grids."
    )
    cheapest_price: float | None = None
    currency: str
    offer_id: str | None = Field(
        default=None, description="Id of the cheapest offer for this cell."
    )


class PriceGridResponse(BaseModel):
    """Envelope returned by ``POST /api/search/flexible``."""

    currency: str
    cells: list[PriceGridCell]
    cheapest: PriceGridCell | None = None
    provider_errors: list[ProviderError] = Field(default_factory=list)
