"""Shared helpers for building normalised offers.

Providers do the vendor-specific JSON parsing; these functions handle the
tedious-but-identical parts: computing slice/offer durations, stop counts,
layover minutes, and the denormalised fields the frontend sorts on.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.models.flight import (
    BaggageAllowance,
    BookingType,
    CabinClass,
    FlightOffer,
    Slice,
    Segment,
)


def minutes_between(start: datetime, end: datetime) -> int:
    """Whole minutes from ``start`` to ``end`` (never negative)."""
    delta = (end - start).total_seconds() / 60
    return max(0, int(round(delta)))


_ISO8601_DURATION = re.compile(
    r"P(?:(?P<days>\d+)D)?T?(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)


def iso8601_duration_to_minutes(value: str | None) -> int:
    """Parse an ISO-8601 duration like ``PT7H30M`` -> 450 minutes.

    Duffel and Amadeus both express segment/slice durations this way. Returns 0
    for empty/unparseable input so a bad field never crashes a search.
    """
    if not value:
        return 0
    match = _ISO8601_DURATION.fullmatch(value.strip())
    if not match:
        return 0
    parts = {k: int(v) if v else 0 for k, v in match.groupdict().items()}
    return (
        parts["days"] * 24 * 60
        + parts["hours"] * 60
        + parts["minutes"]
        + round(parts["seconds"] / 60)
    )


def build_slice(segments: list[Segment]) -> Slice:
    """Assemble a :class:`Slice` from ordered segments.

    Fills in layover minutes between consecutive segments and the total elapsed
    duration (first departure -> last arrival, which naturally includes
    layovers).
    """
    if not segments:
        raise ValueError("a slice needs at least one segment")

    # Compute layover-after for every segment except the last.
    for current, nxt in zip(segments, segments[1:]):
        current.layover_after_minutes = minutes_between(
            current.arrival_at, nxt.departure_at
        )
    segments[-1].layover_after_minutes = None

    first, last = segments[0], segments[-1]
    return Slice(
        origin=first.origin,
        destination=last.destination,
        departure_at=first.departure_at,
        arrival_at=last.arrival_at,
        duration_minutes=minutes_between(first.departure_at, last.arrival_at),
        stops=len(segments) - 1,
        segments=segments,
    )


def finalize_offer(
    *,
    provider_key: str,
    native_id: str,
    total_amount: float,
    total_currency: str,
    slices: list[Slice],
    passenger_count: int,
    cabin_class: CabinClass | None,
    booking_type: BookingType,
    deep_link: str | None = None,
    baggage: BaggageAllowance | None = None,
    raw: dict | None = None,
) -> FlightOffer:
    """Create a fully-populated :class:`FlightOffer`.

    Derives ``total_duration_minutes``, ``max_stops`` and the airline lists so
    the frontend can sort/filter without touching the nested slices.
    """
    airline_codes: list[str] = []
    airline_names: list[str] = []
    for sl in slices:
        for seg in sl.segments:
            if seg.marketing_carrier_code not in airline_codes:
                airline_codes.append(seg.marketing_carrier_code)
            name = seg.marketing_carrier_name or seg.marketing_carrier_code
            if name not in airline_names:
                airline_names.append(name)

    return FlightOffer(
        id=f"{provider_key}:{native_id}",
        provider=provider_key,
        total_amount=round(float(total_amount), 2),
        total_currency=total_currency.upper(),
        slices=slices,
        passenger_count=passenger_count,
        cabin_class=cabin_class,
        baggage=baggage,
        booking_type=booking_type,
        deep_link=deep_link,
        total_duration_minutes=sum(sl.duration_minutes for sl in slices),
        max_stops=max((sl.stops for sl in slices), default=0),
        airline_codes=airline_codes,
        airline_names=airline_names,
        raw=raw,
    )
