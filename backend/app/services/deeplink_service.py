"""Deep-link builder.

The spec: the "Book" button should send the operator straight to a booking page
for the selected flight — no in-app checkout.

Rules
-----
1. If the provider already gave us a real ``deep_link`` (Kiwi, Travelpayouts),
   use it as-is.
2. Otherwise construct a **metasearch deep link** that pre-fills the exact
   route, dates, passengers and cabin so the operator lands one click from
   booking. We generate links for Google Flights, Skyscanner and Kayak and let
   the frontend show whichever the operator prefers (default: Google Flights).

These constructed links are just pre-filled search URLs — we are NOT scraping or
automating those sites, which keeps us on the right side of their terms.
"""

from __future__ import annotations

from urllib.parse import quote

from app.models.flight import CabinClass, FlightOffer
from app.models.search import PassengerCounts

# Google Flights cabin tokens for the ";c=" tbs parameter.
_GF_CABIN = {
    CabinClass.economy: "e",
    CabinClass.premium_economy: "p",
    CabinClass.business: "b",
    CabinClass.first: "f",
}
_SKYSCANNER_CABIN = {
    CabinClass.economy: "economy",
    CabinClass.premium_economy: "premiumeconomy",
    CabinClass.business: "business",
    CabinClass.first: "first",
}


def build_links(
    offer: FlightOffer,
    passengers: PassengerCounts | None = None,
    cabin: CabinClass | None = None,
) -> dict[str, str]:
    """Return ``{provider_name: url}`` booking/search links for an offer.

    Always includes at least the metasearch links; includes ``"native"`` when
    the provider supplied a real booking deep link.
    """
    pax = passengers or PassengerCounts(adults=offer.passenger_count or 1)
    cab = cabin or offer.cabin_class or CabinClass.economy

    # The route is the first segment's origin -> ... -> the last slice's
    # destination, but for link purposes the outbound + return endpoints and
    # dates matter most.
    first_slice = offer.slices[0]
    last_slice = offer.slices[-1]
    origin = first_slice.origin
    destination = first_slice.destination
    depart_date = first_slice.departure_at.date().isoformat()
    return_date = (
        last_slice.departure_at.date().isoformat()
        if len(offer.slices) > 1
        else None
    )

    links: dict[str, str] = {
        "google_flights": _google_flights(
            origin, destination, depart_date, return_date, pax, cab
        ),
        "skyscanner": _skyscanner(
            origin, destination, depart_date, return_date, pax, cab
        ),
        "kayak": _kayak(origin, destination, depart_date, return_date, pax, cab),
    }
    if offer.deep_link:
        links["native"] = offer.deep_link
    return links


def primary_link(offer: FlightOffer, passengers=None, cabin=None) -> str:
    """The single best link for the 'Book' button."""
    links = build_links(offer, passengers, cabin)
    return links.get("native") or links["google_flights"]


# ---------------------------------------------------------------------------
# per-site builders
# ---------------------------------------------------------------------------
def _google_flights(
    origin: str,
    dest: str,
    depart: str,
    ret: str | None,
    pax: PassengerCounts,
    cabin: CabinClass,
) -> str:
    # Google Flights accepts a readable query string that it parses well.
    # e.g. https://www.google.com/travel/flights?q=Flights%20from%20ACC%20to%20DXB%20on%202026-10-12%20oneway
    trip = f"returning {ret}" if ret else "oneway"
    parts = [f"Flights from {origin} to {dest} on {depart}"]
    if ret:
        parts.append(trip)
    else:
        parts.append("oneway")
    if pax.total > 1:
        parts.append(f"{pax.adults} adults")
        if pax.children:
            parts.append(f"{pax.children} children")
        if pax.infants:
            parts.append(f"{pax.infants} infants")
    if cabin != CabinClass.economy:
        parts.append(cabin.value.replace("_", " "))
    q = quote(" ".join(parts))
    return f"https://www.google.com/travel/flights?q={q}"


def _skyscanner(
    origin: str,
    dest: str,
    depart: str,
    ret: str | None,
    pax: PassengerCounts,
    cabin: CabinClass,
) -> str:
    # Skyscanner date format in the path is YYMMDD.
    d = depart.replace("-", "")[2:]
    r = ret.replace("-", "")[2:] if ret else ""
    path = f"{origin.lower()}/{dest.lower()}/{d}"
    if r:
        path += f"/{r}"
    query = (
        f"?adults={pax.adults}&children={pax.children}&infants={pax.infants}"
        f"&cabinclass={_SKYSCANNER_CABIN.get(cabin, 'economy')}"
    )
    return f"https://www.skyscanner.net/transport/flights/{path}/{query}"


def _kayak(
    origin: str,
    dest: str,
    depart: str,
    ret: str | None,
    pax: PassengerCounts,
    cabin: CabinClass,
) -> str:
    # Kayak: /flights/ORIG-DEST/2026-10-12/2026-10-20/2adults?sort=price_a
    seg = f"{origin}-{dest}/{depart}"
    if ret:
        seg += f"/{ret}"
    people = f"/{pax.adults}adults"
    if pax.children:
        people += f"/children-{'-'.join(['11'] * pax.children)}"
    cabin_q = "" if cabin == CabinClass.economy else f"&fs=cabin={cabin.value}"
    return f"https://www.kayak.com/flights/{seg}{people}?sort=price_a{cabin_q}"
