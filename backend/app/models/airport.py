"""Airport / city models for the search-as-you-type autocomplete.

The dataset itself lives in ``app/data/airports.json`` and is loaded by
``services/airport_service.py``. These models are just the API shape.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Airport(BaseModel):
    """A single airport (or metropolitan area) the operator can pick."""

    iata: str = Field(description="3-letter IATA code, e.g. 'ACC'.")
    name: str = Field(description="Airport name, e.g. 'Kotoka International'.")
    city: str
    country: str
    country_code: str = Field(description="ISO 3166-1 alpha-2, e.g. 'GH'.")

    # True for metro codes that cover several airports (LON, NYC, PAR...).
    # These are useful as origins/destinations because providers expand them.
    is_metro: bool = False

    # Coordinates (decimal degrees). Optional in the model, but present for
    # every entry in the bundled dataset. The mock provider uses these to
    # estimate great-circle flight times; a future map view could use them too.
    latitude: float | None = None
    longitude: float | None = None

    # Rough size hint used only for ranking autocomplete results so big hubs
    # surface first. Not shown in the UI.
    weight: int = 0

    @property
    def label(self) -> str:
        """Human label for the dropdown, e.g. 'Accra (ACC) — Kotoka Intl, GH'."""
        kind = "all airports" if self.is_metro else self.name
        return f"{self.city} ({self.iata}) — {kind}, {self.country_code}"


class AirportSearchResponse(BaseModel):
    query: str
    results: list[Airport]
