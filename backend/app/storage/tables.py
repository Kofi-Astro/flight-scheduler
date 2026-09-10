"""ORM table definitions.

Design notes
------------
* Every table has ``created_at`` / ``updated_at`` for audit-ability.
* ``ClientRow`` has an ``owner_agent_id`` column that is unused today but is the
  seam for multi-agent support later — you add an ``agents`` table, backfill
  this column, and start filtering by it. No destructive migration needed.
* ``ShortlistRow`` stores the whole offer as JSON (``offer_json``). Offer ids
  from providers expire fast, so a snapshot is the only reliable record.
* JSON columns use SQLAlchemy's generic ``JSON`` type, which maps to TEXT on
  SQLite and native JSONB-ish on Postgres.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base


class TimestampMixin:
    """Adds created_at / updated_at maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ClientRow(TimestampMixin, Base):
    """A client (customer) of the travel business."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)

    # --- future multi-agent seam (unused for now) ---
    owner_agent_id: Mapped[int | None] = mapped_column(Integer, index=True)

    shortlist_items: Mapped[list["ShortlistRow"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ShortlistRow(TimestampMixin, Base):
    """A bookmarked flight option, optionally tied to a client."""

    __tablename__ = "shortlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Full FlightOffer snapshot (see models/flight.py). Stored as JSON.
    offer_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), index=True
    )
    client_label: Mapped[str | None] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(Text)
    search_summary: Mapped[str | None] = mapped_column(String(300))

    # Denormalised price fields for quick sorting + alert comparison.
    saved_price: Mapped[float] = mapped_column(Float, nullable=False)
    saved_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    latest_price: Mapped[float | None] = mapped_column(Float)
    latest_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    client: Mapped[ClientRow | None] = relationship(back_populates="shortlist_items")


class AlertRow(TimestampMixin, Base):
    """A price-drop watch."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str | None] = mapped_column(String(160))

    origin: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    departure_date: Mapped[str | None] = mapped_column(String(10))  # ISO date
    return_date: Mapped[str | None] = mapped_column(String(10))
    passengers_json: Mapped[dict] = mapped_column(JSON, default=dict)
    cabin_class: Mapped[str] = mapped_column(String(20), default="economy")
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_price: Mapped[float | None] = mapped_column(Float)
    last_seen_price: Mapped[float | None] = mapped_column(Float)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    channel: Mapped[str] = mapped_column(String(20), default="email")
    destination_address: Mapped[str] = mapped_column(String(400), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
