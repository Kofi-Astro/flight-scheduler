"""Client service — the lightweight CRM.

Just enough to group shortlisted flights per client and keep contact details.
Built to grow: when multi-agent support lands, add an ``owner_agent_id`` filter
here and everything else keeps working.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.client import Client, ClientCreate, ClientUpdate
from app.storage.tables import ClientRow, ShortlistRow


def _row_to_model(row: ClientRow, shortlist_count: int = 0) -> Client:
    return Client(
        id=row.id,
        name=row.name,
        phone=row.phone,
        email=row.email,
        note=row.note,
        created_at=row.created_at,
        updated_at=row.updated_at,
        shortlist_count=shortlist_count,
    )


def create(db: Session, payload: ClientCreate) -> Client:
    row = ClientRow(
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        note=payload.note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_model(row, 0)


def list_clients(db: Session, query: str | None = None) -> list[Client]:
    """All clients (newest first), optionally filtered by a name/phone substring.

    One extra query counts shortlist items per client so the list can show
    "N saved options" without an N+1.
    """
    stmt = select(ClientRow).order_by(ClientRow.created_at.desc())
    if query:
        like = f"%{query.lower()}%"
        stmt = stmt.where(
            func.lower(ClientRow.name).like(like)
            | func.lower(func.coalesce(ClientRow.phone, "")).like(like)
            | func.lower(func.coalesce(ClientRow.email, "")).like(like)
        )
    rows = db.execute(stmt).scalars().all()

    counts = dict(
        db.execute(
            select(ShortlistRow.client_id, func.count(ShortlistRow.id))
            .group_by(ShortlistRow.client_id)
        ).all()
    )
    return [_row_to_model(r, counts.get(r.id, 0)) for r in rows]


def get(db: Session, client_id: int) -> Client | None:
    row = db.get(ClientRow, client_id)
    if row is None:
        return None
    count = db.execute(
        select(func.count(ShortlistRow.id)).where(ShortlistRow.client_id == client_id)
    ).scalar_one()
    return _row_to_model(row, count)


def update(db: Session, client_id: int, payload: ClientUpdate) -> Client | None:
    row = db.get(ClientRow, client_id)
    if row is None:
        return None
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return get(db, client_id)


def delete(db: Session, client_id: int) -> bool:
    row = db.get(ClientRow, client_id)
    if row is None:
        return False
    # Shortlist items' client_id is set NULL by the FK rule — the saved options
    # survive, they just become unassigned.
    db.delete(row)
    db.commit()
    return True
