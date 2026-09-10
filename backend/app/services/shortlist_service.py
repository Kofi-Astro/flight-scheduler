"""Shortlist service — save / group / revisit flight options per client.

A shortlist item stores a full JSON snapshot of the offer (provider offer ids
expire within minutes, so a reference is useless). The operator can:
  * save an offer with a note and either an existing client or a free-text label
  * list everything, or filter to one client
  * re-check the current price for a saved option (``refresh_price``)
  * build a WhatsApp-ready summary (see ``services/summary_service``)
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.flight import FlightOffer
from app.models.search import PassengerCounts, SearchRequest
from app.models.shortlist import (
    ShortlistCreate,
    ShortlistItem,
    ShortlistUpdate,
)
from app.services import search_service
from app.storage.tables import ClientRow, ShortlistRow


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------
def _row_to_item(row: ShortlistRow) -> ShortlistItem:
    offer = FlightOffer.model_validate(row.offer_json)
    return ShortlistItem(
        id=row.id,
        offer=offer,
        client_id=row.client_id,
        client_label=row.client_label,
        client_name=row.client.name if row.client else None,
        note=row.note,
        search_summary=row.search_summary,
        saved_price=row.saved_price,
        saved_currency=row.saved_currency,
        latest_price=row.latest_price,
        latest_checked_at=row.latest_checked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _auto_summary(offer: FlightOffer) -> str:
    """Fallback 'ACC->DXB, 12 Oct, 1 pax, economy' if the caller gave none."""
    first = offer.slices[0]
    route = f"{first.origin}->{first.destination}"
    if len(offer.slices) > 1:
        route += f" / {offer.slices[-1].origin}->{offer.slices[-1].destination}"
    date_str = first.departure_at.strftime("%d %b")
    cabin = (offer.cabin_class.value if offer.cabin_class else "economy").replace("_", " ")
    return f"{route}, {date_str}, {offer.passenger_count} pax, {cabin}"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def create(db: Session, payload: ShortlistCreate) -> ShortlistItem:
    offer = payload.offer

    # If a client_id was given, make sure it exists (400 otherwise handled in
    # the router by catching ValueError).
    if payload.client_id is not None:
        exists = db.get(ClientRow, payload.client_id)
        if exists is None:
            raise ValueError(f"client {payload.client_id} does not exist")

    row = ShortlistRow(
        offer_json=offer.model_dump(mode="json"),
        client_id=payload.client_id,
        client_label=payload.client_label,
        note=payload.note,
        search_summary=payload.search_summary or _auto_summary(offer),
        saved_price=offer.total_amount,
        saved_currency=offer.total_currency,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_item(row)


def list_items(db: Session, client_id: int | None = None) -> list[ShortlistItem]:
    stmt = select(ShortlistRow).order_by(ShortlistRow.created_at.desc())
    if client_id is not None:
        stmt = stmt.where(ShortlistRow.client_id == client_id)
    return [_row_to_item(r) for r in db.execute(stmt).scalars().all()]


def get(db: Session, item_id: int) -> ShortlistItem | None:
    row = db.get(ShortlistRow, item_id)
    return _row_to_item(row) if row else None


def update(db: Session, item_id: int, payload: ShortlistUpdate) -> ShortlistItem | None:
    row = db.get(ShortlistRow, item_id)
    if row is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "client_id" in data and data["client_id"] is not None:
        if db.get(ClientRow, data["client_id"]) is None:
            raise ValueError(f"client {data['client_id']} does not exist")
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _row_to_item(row)


def delete(db: Session, item_id: int) -> bool:
    row = db.get(ShortlistRow, item_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Price re-check
# ---------------------------------------------------------------------------
async def refresh_price(db: Session, item_id: int) -> ShortlistItem | None:
    """Re-run a search for the saved option's route and store the new cheapest.

    Used both by the "refresh" button in the UI and by the price-drop alert
    checker. Compares like-for-like on route + cabin + passengers; it does NOT
    guarantee the exact same flight numbers are still available.
    """
    row = db.get(ShortlistRow, item_id)
    if row is None:
        return None

    offer = FlightOffer.model_validate(row.offer_json)
    first, last = offer.slices[0], offer.slices[-1]
    is_round = len(offer.slices) > 1

    request = SearchRequest(
        origin=first.origin,
        destination=first.destination,
        departure_date=first.departure_at.date(),
        return_date=last.departure_at.date() if is_round else None,
        passengers=PassengerCounts(adults=max(1, offer.passenger_count)),
        cabin_class=offer.cabin_class or "economy",
        currency=row.saved_currency,
        max_results_per_provider=15,
    )
    response = await search_service.search_flights(request)
    cheapest = response.offers[0] if response.offers else None

    row.latest_price = cheapest.total_amount if cheapest else None
    row.latest_checked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _row_to_item(row)
