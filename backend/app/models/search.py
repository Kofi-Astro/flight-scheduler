"""Request models for the search endpoints.

These are what the frontend POSTs. Keeping them separate from the response
models (``flight.py``) makes the contract obvious and lets us validate input
tightly (date ordering, passenger limits, IATA code shape, ...).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.flight import CabinClass


# A city/airport reference is always a 3-letter IATA code by the time it reaches
# the backend. The frontend autocomplete resolves "Accra" -> "ACC" before
# submitting. We still validate the shape defensively.
IATA = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")


class PassengerCounts(BaseModel):
    """Passenger breakdown. Providers price by passenger type."""

    adults: int = Field(default=1, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=9)  # 2-11 yrs
    infants: int = Field(default=0, ge=0, le=9)  # under 2, on lap

    @property
    def total(self) -> int:
        return self.adults + self.children + self.infants

    @model_validator(mode="after")
    def _infants_not_more_than_adults(self) -> "PassengerCounts":
        # Lap infants need an adult each — a near-universal airline rule.
        if self.infants > self.adults:
            raise ValueError("infants cannot outnumber adults")
        return self


class SearchRequest(BaseModel):
    """Body for ``POST /api/search`` — one-way or round-trip."""

    origin: str = IATA
    destination: str = IATA
    departure_date: date
    return_date: date | None = Field(
        default=None,
        description="Omit for a one-way search; set for a round trip.",
    )

    passengers: PassengerCounts = Field(default_factory=PassengerCounts)
    cabin_class: CabinClass = CabinClass.economy

    # The currency the operator wants prices in. Conversion happens in the
    # search service after providers return their native currencies.
    currency: str = Field(default="USD", min_length=3, max_length=3)

    # Cap results per provider so the UI stays fast. The service still merges
    # across providers.
    max_results_per_provider: int = Field(default=50, ge=1, le=200)

    @field_validator("origin", "destination", "currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate_dates_and_route(self) -> "SearchRequest":
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        if self.departure_date < date.today():
            raise ValueError("departure_date is in the past")
        if self.return_date and self.return_date < self.departure_date:
            raise ValueError("return_date is before departure_date")
        return self

    @property
    def is_round_trip(self) -> bool:
        return self.return_date is not None


class FlexibleDatesRequest(BaseModel):
    """Body for ``POST /api/search/flexible`` — the cheapest-days price grid.

    We search every combination of departure dates in
    ``[departure_date - flex_days, departure_date + flex_days]`` (and likewise
    for return dates on round trips), returning the cheapest price per cell.
    """

    origin: str = IATA
    destination: str = IATA
    departure_date: date
    return_date: date | None = None

    # ±N days around the chosen dates. 3-7 per the spec; capped at 7 to keep the
    # number of provider calls sane (a 7-day round-trip grid = 15x15 = 225 cells
    # -> we sample, see the service).
    flex_days: int = Field(default=3, ge=1, le=7)

    passengers: PassengerCounts = Field(default_factory=PassengerCounts)
    cabin_class: CabinClass = CabinClass.economy
    currency: str = Field(default="USD", min_length=3, max_length=3)

    @field_validator("origin", "destination", "currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate(self) -> "FlexibleDatesRequest":
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        if self.return_date and self.return_date < self.departure_date:
            raise ValueError("return_date is before departure_date")
        return self


class MultiCityLeg(BaseModel):
    """One leg of a multi-city itinerary."""

    origin: str = IATA
    destination: str = IATA
    departure_date: date

    @field_validator("origin", "destination")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class MultiCityRequest(BaseModel):
    """Body for ``POST /api/search/multi-city`` (nice-to-have feature)."""

    legs: list[MultiCityLeg] = Field(min_length=2, max_length=6)
    passengers: PassengerCounts = Field(default_factory=PassengerCounts)
    cabin_class: CabinClass = CabinClass.economy
    currency: str = Field(default="USD", min_length=3, max_length=3)
    max_results_per_provider: int = Field(default=50, ge=1, le=200)

    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _dates_non_decreasing(self) -> "MultiCityRequest":
        for earlier, later in zip(self.legs, self.legs[1:]):
            if later.departure_date < earlier.departure_date:
                raise ValueError("multi-city leg dates must not go backwards")
        return self
