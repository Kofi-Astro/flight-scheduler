"""Price-drop alert service (nice-to-have feature).

An alert watches a route (given directly or taken from a saved shortlist item).
A scheduled job calls ``check_all`` periodically; when the cheapest live price
for the route is at or below the alert's ``target_price`` the alert fires once
(email now, webhook-ready for later) and is marked triggered.

Scheduling on Railway
---------------------
Add a Railway **Cron** service that hits:

    POST https://<your-backend>/api/alerts/check
    Header: X-Cron-Secret: <ALERTS_CRON_SECRET>

e.g. every 6 hours: ``0 */6 * * *``. See DEPLOYMENT.md.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alerts import Alert, AlertCheckResult, AlertCreate
from app.models.flight import FlightOffer
from app.models.search import PassengerCounts, SearchRequest
from app.services import search_service, summary_service
from app.services.notifications import send_email, send_webhook
from app.storage.tables import AlertRow, ShortlistRow


def _row_to_model(row: AlertRow) -> Alert:
    return Alert(
        id=row.id,
        label=row.label,
        origin=row.origin,
        destination=row.destination,
        departure_date=date.fromisoformat(row.departure_date) if row.departure_date else None,
        return_date=date.fromisoformat(row.return_date) if row.return_date else None,
        cabin_class=row.cabin_class,
        currency=row.currency,
        target_price=row.target_price,
        baseline_price=row.baseline_price,
        last_seen_price=row.last_seen_price,
        last_checked_at=row.last_checked_at,
        triggered_at=row.triggered_at,
        channel=row.channel,
        destination_address=row.destination_address,
        active=row.active,
        created_at=row.created_at,
    )


def _search_request_for(row: AlertRow) -> SearchRequest:
    return SearchRequest(
        origin=row.origin,
        destination=row.destination,
        departure_date=date.fromisoformat(row.departure_date),
        return_date=date.fromisoformat(row.return_date) if row.return_date else None,
        passengers=PassengerCounts(**(row.passengers_json or {"adults": 1})),
        cabin_class=row.cabin_class,
        currency=row.currency,
        max_results_per_provider=15,
    )


# ---------------------------------------------------------------------------
async def create(db: Session, payload: AlertCreate) -> Alert:
    """Create an alert, computing a baseline price from a live search."""
    origin = payload.origin
    destination = payload.destination
    departure = payload.departure_date
    return_date = payload.return_date
    passengers = payload.passengers
    cabin = payload.cabin_class
    currency = payload.currency

    # Pull route from a shortlist item if that's what was given.
    if payload.shortlist_id is not None:
        row = db.get(ShortlistRow, payload.shortlist_id)
        if row is None:
            raise ValueError(f"shortlist item {payload.shortlist_id} not found")
        offer = FlightOffer.model_validate(row.offer_json)
        first, last = offer.slices[0], offer.slices[-1]
        origin = first.origin
        destination = first.destination
        departure = first.departure_at.date()
        return_date = last.departure_at.date() if len(offer.slices) > 1 else None
        cabin = offer.cabin_class or cabin
        currency = row.saved_currency
        passengers = PassengerCounts(adults=max(1, offer.passenger_count))

    if not (origin and destination and departure):
        raise ValueError(
            "provide either shortlist_id or origin+destination+departure_date"
        )

    # Baseline: cheapest price right now.
    request = SearchRequest(
        origin=origin,
        destination=destination,
        departure_date=departure,
        return_date=return_date,
        passengers=passengers,
        cabin_class=cabin,
        currency=currency,
        max_results_per_provider=15,
    )
    response = await search_service.search_flights(request)
    baseline = response.offers[0].total_amount if response.offers else None

    target = payload.target_price or baseline
    if target is None:
        raise ValueError(
            "could not determine a baseline price; pass target_price explicitly"
        )

    row = AlertRow(
        label=payload.label,
        origin=origin,
        destination=destination,
        departure_date=departure.isoformat(),
        return_date=return_date.isoformat() if return_date else None,
        passengers_json=passengers.model_dump(),
        cabin_class=cabin.value if hasattr(cabin, "value") else str(cabin),
        currency=currency,
        target_price=round(float(target), 2),
        baseline_price=baseline,
        last_seen_price=baseline,
        last_checked_at=datetime.now(timezone.utc),
        channel=payload.channel.value,
        destination_address=str(payload.destination_address),
        active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_model(row)


def list_alerts(db: Session) -> list[Alert]:
    rows = db.execute(select(AlertRow).order_by(AlertRow.created_at.desc())).scalars().all()
    return [_row_to_model(r) for r in rows]


def get(db: Session, alert_id: int) -> Alert | None:
    row = db.get(AlertRow, alert_id)
    return _row_to_model(row) if row else None


def set_active(db: Session, alert_id: int, active: bool) -> Alert | None:
    row = db.get(AlertRow, alert_id)
    if row is None:
        return None
    row.active = active
    db.commit()
    db.refresh(row)
    return _row_to_model(row)


def delete(db: Session, alert_id: int) -> bool:
    row = db.get(AlertRow, alert_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


# ---------------------------------------------------------------------------
async def check_all(db: Session) -> AlertCheckResult:
    """Re-price every active, not-yet-triggered alert. Fire the ones that hit."""
    rows = (
        db.execute(select(AlertRow).where(AlertRow.active.is_(True)))
        .scalars()
        .all()
    )
    triggered: list[int] = []
    errors: list[str] = []
    checked = 0

    for row in rows:
        if row.triggered_at is not None:
            continue
        checked += 1
        try:
            response = await search_service.search_flights(_search_request_for(row))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"alert {row.id}: {exc}")
            continue

        cheapest = response.offers[0] if response.offers else None
        row.last_checked_at = datetime.now(timezone.utc)
        if cheapest is None:
            continue
        row.last_seen_price = cheapest.total_amount

        if cheapest.total_amount <= row.target_price:
            row.triggered_at = datetime.now(timezone.utc)
            triggered.append(row.id)
            _notify(row, cheapest)

    db.commit()
    return AlertCheckResult(checked=checked, triggered=triggered, errors=errors)


def _notify(row: AlertRow, offer: FlightOffer) -> None:
    label = row.label or f"{row.origin}->{row.destination}"
    subject = (
        f"Price drop: {label} now {offer.total_amount:,.0f} {offer.total_currency}"
    )
    body = summary_service.build_summary_text(
        offer,
        note=(
            f"Alert '{label}' target was {row.target_price:,.0f} {row.currency}; "
            f"baseline {row.baseline_price:,.0f}."
            if row.baseline_price
            else None
        ),
    )
    if row.channel == "email":
        send_email(row.destination_address, subject, body)
    elif row.channel == "webhook":
        send_webhook(
            row.destination_address,
            {"alert_id": row.id, "label": label, "price": offer.total_amount, "summary": body},
        )
