"""Client (customer) models — the lightweight CRM.

Kept deliberately small for the side-business phase: enough to group shortlisted
flights per client and remember how to reach them. The DB table
(``storage/tables.py``) has room to grow (agent ownership, timestamps) without
touching these API models.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ClientBase(BaseModel):
    """Fields the operator provides when creating/editing a client."""

    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(
        default=None,
        max_length=40,
        description="Ideally E.164 (+233...) so WhatsApp links work.",
    )
    email: EmailStr | None = None
    note: str | None = Field(default=None, max_length=2000)


class ClientCreate(ClientBase):
    """Body for ``POST /api/clients``."""


class ClientUpdate(BaseModel):
    """Body for ``PATCH /api/clients/{id}`` — every field optional."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    note: str | None = Field(default=None, max_length=2000)


class Client(ClientBase):
    """A client as returned by the API."""

    id: int
    created_at: datetime
    updated_at: datetime

    # Convenience counts so the clients list can show "3 saved options" without
    # a second request. Filled in by the service layer.
    shortlist_count: int = 0

    model_config = {"from_attributes": True}
