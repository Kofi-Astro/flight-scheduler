"""WhatsApp / printable summary endpoint.

    POST /api/summary   -> { text, whatsapp_url }

Give it a flight offer (straight from a search response) plus optional client
name / note / phone; get back a formatted plain-text summary and a ``wa.me``
link that opens WhatsApp with the text pre-filled, ready to send to the client.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter

from app.models.flight import FlightOffer
from app.services import summary_service

router = APIRouter(prefix="/api/summary", tags=["summary"])


class SummaryRequest(BaseModel):
    offer: FlightOffer
    client_name: str | None = Field(default=None, max_length=120)
    client_phone: str | None = Field(
        default=None,
        max_length=40,
        description="E.164 preferred (+233...) so the wa.me link targets them.",
    )
    note: str | None = Field(default=None, max_length=2000)
    booking_url: str | None = Field(
        default=None, description="Override the link shown in the message."
    )


class SummaryResponse(BaseModel):
    text: str
    whatsapp_url: str


@router.post("", response_model=SummaryResponse, summary="Build a shareable summary")
def build_summary(payload: SummaryRequest) -> SummaryResponse:
    text = summary_service.build_summary_text(
        payload.offer,
        client_name=payload.client_name,
        note=payload.note,
        booking_url=payload.booking_url,
    )
    return SummaryResponse(
        text=text,
        whatsapp_url=summary_service.whatsapp_link(text, payload.client_phone),
    )
