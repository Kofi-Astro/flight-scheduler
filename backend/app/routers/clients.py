"""Client (CRM) CRUD.

    GET    /api/clients            list all (optionally ?q= to filter)
    POST   /api/clients            create
    GET    /api/clients/{id}       one client
    PATCH  /api/clients/{id}       edit
    DELETE /api/clients/{id}       delete (saved options become unassigned)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.models.client import Client, ClientCreate, ClientUpdate
from app.services import client_service
from app.storage.db import get_session

router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.get("", response_model=list[Client], summary="List clients")
def list_clients(
    q: str | None = Query(default=None, description="Filter by name / phone / email."),
    db: Session = Depends(get_session),
) -> list[Client]:
    return client_service.list_clients(db, query=q)


@router.post("", response_model=Client, status_code=201, summary="Create a client")
def create_client(payload: ClientCreate, db: Session = Depends(get_session)) -> Client:
    return client_service.create(db, payload)


@router.get("/{client_id}", response_model=Client, summary="Get a client")
def get_client(client_id: int, db: Session = Depends(get_session)) -> Client:
    client = client_service.get(db, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.patch("/{client_id}", response_model=Client, summary="Edit a client")
def update_client(
    client_id: int, payload: ClientUpdate, db: Session = Depends(get_session)
) -> Client:
    client = client_service.update(db, client_id, payload)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.delete("/{client_id}", summary="Delete a client")
def delete_client(client_id: int, db: Session = Depends(get_session)) -> dict:
    if not client_service.delete(db, client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    return {"deleted": client_id}
