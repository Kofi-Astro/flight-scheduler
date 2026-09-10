"""Currency endpoints for the UI's currency toggle.

    GET  /api/currency               supported currencies + current rates
    POST /api/currency/convert       convert an amount between two currencies

The frontend mostly converts prices *client-side* using the rate table from
``GET /api/currency`` (instant, no round-trip per toggle). ``/convert`` exists
for one-off server-side needs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter

from app.services.currency_service import get_currency_service

router = APIRouter(prefix="/api/currency", tags=["currency"])


class ConvertRequest(BaseModel):
    amount: float = Field(ge=0)
    from_currency: str = Field(min_length=3, max_length=3)
    to_currency: str = Field(min_length=3, max_length=3)


class ConvertResponse(BaseModel):
    amount: float
    from_currency: str
    to_currency: str
    converted: float


@router.get("", summary="Supported currencies + rates")
async def currency_status() -> dict:
    return await get_currency_service().status()


@router.post("/convert", response_model=ConvertResponse, summary="Convert an amount")
async def convert(payload: ConvertRequest) -> ConvertResponse:
    service = get_currency_service()
    converted = await service.convert(
        payload.amount, payload.from_currency, payload.to_currency
    )
    return ConvertResponse(
        amount=payload.amount,
        from_currency=payload.from_currency.upper(),
        to_currency=payload.to_currency.upper(),
        converted=converted,
    )
