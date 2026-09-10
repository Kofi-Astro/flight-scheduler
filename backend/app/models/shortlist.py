"""Shortlist models — bookmarked flight options with a client/note attached.

The operator searches, finds a good option, and saves it. We store a *snapshot*
of the offer (JSON) rather than a reference, because provider offer ids expire
within minutes. The snapshot is what the operator shows the client and what the
price-drop alert compares against.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.flight import FlightOffer


class ShortlistCreate(BaseModel):
    """Body for ``POST /api/shortlist``."""

    # The full offer object straight from a search response. Storing the whole
    # thing keeps the feature working even after the provider's id expires.
    offer: FlightOffer

    # Either attach to an existing client by id, or pass a free-text label
    # (e.g. "Auntie Ama - Dubai trip") for quick grouping before the client
    # exists in the CRM.
    client_id: int | None = None
    client_label: str | None = Field(default=None, max_length=120)

    note: str | None = Field(default=None, max_length=2000)

    # Original search context, so the operator remembers what they searched.
    search_summary: str | None = Field(
        default=None,
        max_length=300,
        description="e.g. 'ACC->DXB, 12 Oct, 1 adult, economy'.",
    )


class ShortlistUpdate(BaseModel):
    """Body for ``PATCH /api/shortlist/{id}`` — reassign client or edit note."""

    client_id: int | None = None
    client_label: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=2000)


class ShortlistItem(BaseModel):
    """A saved option as returned by the API."""

    id: int
    offer: FlightOffer
    client_id: int | None = None
    client_label: str | None = None
    client_name: str | None = Field(
        default=None, description="Resolved from client_id when present."
    )
    note: str | None = None
    search_summary: str | None = None

    # Price tracking: the price when saved vs. the latest re-checked price.
    saved_price: float
    saved_currency: str
    latest_price: float | None = None
    latest_checked_at: datetime | None = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @property
    def price_delta(self) -> float | None:
        """Latest minus saved. Negative means the fare dropped (good)."""
        if self.latest_price is None:
            return None
        return round(self.latest_price - self.saved_price, 2)
