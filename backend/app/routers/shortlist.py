"""Shortlist (saved options) CRUD.

    GET    /api/shortlist                list all (optionally ?client_id=)
    POST   /api/shortlist                save an offer
    GET    /api/shortlist/{id}           one item
    PATCH  /api/shortlist/{id}           edit note / reassign client
    DELETE /api/shortlist/{id}           remove
    POST   /api/shortlist/{id}/refresh-price   re-check current price
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.models.shortlist import ShortlistCreate, ShortlistItem, ShortlistUpdate
from app.services import shortlist_service
from app.storage.db import get_session

router = APIRouter(prefix="/api/shortlist", tags=["shortlist"])


@router.get("", response_model=list[ShortlistItem], summary="List saved options")
def list_shortlist(
    client_id: int | None = Query(default=None),
    db: Session = Depends(get_session),
) -> list[ShortlistItem]:
    return shortlist_service.list_items(db, client_id=client_id)


@router.post("", response_model=ShortlistItem, status_code=201, summary="Save an option")
def create_shortlist(
    payload: ShortlistCreate, db: Session = Depends(get_session)
) -> ShortlistItem:
    try:
        return shortlist_service.create(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{item_id}", response_model=ShortlistItem, summary="Get a saved option")
def get_shortlist(item_id: int, db: Session = Depends(get_session)) -> ShortlistItem:
    item = shortlist_service.get(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Shortlist item not found")
    return item


@router.patch("/{item_id}", response_model=ShortlistItem, summary="Edit a saved option")
def update_shortlist(
    item_id: int, payload: ShortlistUpdate, db: Session = Depends(get_session)
) -> ShortlistItem:
    try:
        item = shortlist_service.update(db, item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Shortlist item not found")
    return item


@router.delete("/{item_id}", summary="Delete a saved option")
def delete_shortlist(item_id: int, db: Session = Depends(get_session)) -> dict:
    if not shortlist_service.delete(db, item_id):
        raise HTTPException(status_code=404, detail="Shortlist item not found")
    return {"deleted": item_id}


@router.post(
    "/{item_id}/refresh-price",
    response_model=ShortlistItem,
    summary="Re-check the current price for a saved option",
)
async def refresh_price(
    item_id: int, db: Session = Depends(get_session)
) -> ShortlistItem:
    item = await shortlist_service.refresh_price(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Shortlist item not found")
    return item
