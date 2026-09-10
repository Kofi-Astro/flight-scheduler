"""Price-drop alert models (nice-to-have feature).

An alert watches a saved shortlist item (or a raw route) and notifies the
operator when the price falls at/below a threshold. Delivery is via email
(SMTP) for now; the model leaves room for a WhatsApp channel later.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field

from app.models.flight import CabinClass
from app.models.search import PassengerCounts


class AlertChannel(str, Enum):
    email = "email"
    # webhook / whatsapp can be added without changing the table schema.
    webhook = "webhook"


class AlertCreate(BaseModel):
    """Body for ``POST /api/alerts``.

    Provide EITHER ``shortlist_id`` (watch a saved option's route) OR the raw
    route fields.
    """

    shortlist_id: int | None = None

    origin: str | None = Field(default=None, min_length=3, max_length=3)
    destination: str | None = Field(default=None, min_length=3, max_length=3)
    departure_date: date | None = None
    return_date: date | None = None
    passengers: PassengerCounts = Field(default_factory=PassengerCounts)
    cabin_class: CabinClass = CabinClass.economy
    currency: str = Field(default="USD", min_length=3, max_length=3)

    # Notify when the cheapest price is <= this. If omitted we use the current
    # cheapest price at creation time (so any drop triggers).
    target_price: float | None = Field(default=None, gt=0)

    channel: AlertChannel = AlertChannel.email
    destination_address: EmailStr | str = Field(
        description="Email address (channel=email) or webhook URL."
    )
    label: str | None = Field(default=None, max_length=160)


class Alert(BaseModel):
    """An alert as returned by the API."""

    id: int
    label: str | None = None

    origin: str
    destination: str
    departure_date: date | None = None
    return_date: date | None = None
    cabin_class: CabinClass
    currency: str

    target_price: float
    baseline_price: float | None = None
    last_seen_price: float | None = None
    last_checked_at: datetime | None = None
    triggered_at: datetime | None = None

    channel: AlertChannel
    destination_address: str
    active: bool = True

    created_at: datetime

    model_config = {"from_attributes": True}


class AlertCheckResult(BaseModel):
    """Returned by ``POST /api/alerts/check`` (called by a cron job)."""

    checked: int
    triggered: list[int] = Field(
        default_factory=list, description="Ids of alerts that fired this run."
    )
    errors: list[str] = Field(default_factory=list)
