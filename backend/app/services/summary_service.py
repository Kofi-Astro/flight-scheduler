"""Build a printable / shareable flight summary formatted for WhatsApp.

The operator's workflow: find a good option -> send it to the client on
WhatsApp. This produces the message text (and a ``wa.me`` link that opens
WhatsApp with the text pre-filled).

Kept plain-text on purpose — WhatsApp only supports *simple* markdown
(``*bold*``, ``_italic_``), which we use sparingly.
"""

from __future__ import annotations

from urllib.parse import quote

from app.models.flight import FlightOffer, Slice

# Weekday / month names without importing locale machinery.
_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _fmt_time(dt) -> str:
    return dt.strftime("%H:%M")


def _fmt_date(dt) -> str:
    return f"{dt.day} {_MONTHS[dt.month - 1]}"


def _fmt_duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60:02d}m"


def _slice_lines(sl: Slice, index_label: str) -> list[str]:
    lines = [
        f"{index_label}: {sl.origin} -> {sl.destination}  "
        f"({_fmt_date(sl.departure_at)})"
    ]
    for seg in sl.segments:
        carrier = seg.marketing_carrier_name or seg.marketing_carrier_code
        flt = f" {seg.marketing_carrier_code}{seg.flight_number}" if seg.flight_number else ""
        lines.append(
            f"  {_fmt_time(seg.departure_at)} {seg.origin} -> "
            f"{_fmt_time(seg.arrival_at)} {seg.destination}  "
            f"{carrier}{flt}"
        )
        if seg.layover_after_minutes:
            lines.append(
                f"    layover {seg.destination} {_fmt_duration(seg.layover_after_minutes)}"
            )
    stops = "non-stop" if sl.stops == 0 else f"{sl.stops} stop(s)"
    lines.append(f"  Total: {_fmt_duration(sl.duration_minutes)} · {stops}")
    return lines


def build_summary_text(
    offer: FlightOffer,
    *,
    client_name: str | None = None,
    note: str | None = None,
    booking_url: str | None = None,
) -> str:
    """Return the multi-line WhatsApp message for an offer."""
    airlines = ", ".join(offer.airline_names or offer.airline_codes)
    header = "*Flight option*"
    if client_name:
        header += f" for {client_name}"

    lines = [header, ""]
    labels = ["Outbound", "Return", "Leg 3", "Leg 4", "Leg 5", "Leg 6"]
    for i, sl in enumerate(offer.slices):
        lines += _slice_lines(sl, labels[i] if i < len(labels) else f"Leg {i + 1}")
        lines.append("")

    lines.append(f"*Price: {offer.total_amount:,.0f} {offer.total_currency}*"
                 f"  ({offer.passenger_count} pax, "
                 f"{(offer.cabin_class.value if offer.cabin_class else 'economy').replace('_', ' ')})")
    if airlines:
        lines.append(f"Airline: {airlines}")
    if offer.baggage and (offer.baggage.description or offer.baggage.checked_bags):
        lines.append(
            f"Baggage: {offer.baggage.description or f'{offer.baggage.checked_bags} checked'}"
        )
    if note:
        lines += ["", f"_{note}_"]

    link = booking_url or offer.deep_link
    if link:
        lines += ["", f"Book: {link}"]

    lines += ["", "_Prices/availability can change until ticketed._"]
    return "\n".join(lines)


def whatsapp_link(text: str, phone: str | None = None) -> str:
    """A wa.me link that opens WhatsApp with ``text`` pre-filled.

    ``phone`` (E.164 digits, no '+') targets a specific contact; without it the
    operator picks the chat.
    """
    encoded = quote(text)
    if phone:
        digits = "".join(ch for ch in phone if ch.isdigit())
        return f"https://wa.me/{digits}?text={encoded}"
    return f"https://wa.me/?text={encoded}"
