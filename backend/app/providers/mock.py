"""MockProvider — realistic synthetic flight data, no API key required.

Why this exists
---------------
The spec wants the app usable immediately and easy for a non-specialist to run.
Signing up for Duffel/Amadeus/etc. takes time. ``MockProvider`` fills the gap:
it generates plausible itineraries for ANY worldwide route using the bundled
airport coordinates + airline list, so every feature (search, sort, filter,
flexible dates, shortlist, currency, deep links) works end-to-end on day one.

It is deterministic per (route, date) so results don't shuffle on every refresh,
but varies across routes and dates like real inventory does.

**It is not real inventory.** The deep links it produces are metasearch links,
and prices are estimates. Turn on a real provider for real data.
"""

from __future__ import annotations

import json
import zlib
from datetime import datetime, timedelta
from random import Random

from app.config import DATA_DIR
from app.providers.base import FlightProvider, ProviderSearchQuery, QueryLeg
from app.providers.support import build_slice, finalize_offer
from app.models.flight import (
    BaggageAllowance,
    BookingType,
    CabinClass,
    FlightOffer,
    Segment,
)
from app.services.airport_service import get_airport_service

# Cruise speed / taxi assumptions used to turn distance into a duration.
_CRUISE_KMH = 810
_TAXI_MINUTES_PER_SEGMENT = 25

# Price multipliers by cabin, relative to economy.
_CABIN_MULTIPLIER = {
    CabinClass.economy: 1.0,
    CabinClass.premium_economy: 1.6,
    CabinClass.business: 3.4,
    CabinClass.first: 6.0,
}

# Rough USD per km, tapering for long hauls (economies of distance).
def _price_per_km(distance_km: float) -> float:
    if distance_km < 800:
        return 0.28
    if distance_km < 3000:
        return 0.16
    if distance_km < 8000:
        return 0.11
    return 0.09


class MockProvider(FlightProvider):
    key = "mock"
    display_name = "Mock (synthetic data)"

    def __init__(self) -> None:
        airlines_file = DATA_DIR / "airlines.json"
        self._airlines: list[dict] = json.loads(
            airlines_file.read_text(encoding="utf-8")
        )["airlines"]
        self._airports = get_airport_service()

    # The mock provider is always "configured" — that's the whole point.
    @property
    def is_configured(self) -> bool:
        return True

    async def search(self, query: ProviderSearchQuery) -> list[FlightOffer]:
        # One RNG seeded from the whole query so a given search is reproducible.
        seed_material = "|".join(
            f"{leg.origin}-{leg.destination}-{leg.departure_date.isoformat()}"
            for leg in query.legs
        )
        rng = Random(zlib.crc32(seed_material.encode()))

        # How many offers to synthesise. Real searches return dozens; cap for UI.
        count = min(query.max_results, 16)
        offers: list[FlightOffer] = []

        for i in range(count):
            slices = []
            total = 0.0
            ok = True
            for leg in query.legs:
                built = self._build_slice_for_leg(leg, query, rng, variant=i)
                if built is None:
                    ok = False
                    break
                sl, leg_price = built
                slices.append(sl)
                total += leg_price
            if not ok:
                continue

            # Passenger scaling: children ~75% fare, infants ~10%.
            pax = query.passengers
            pax_factor = pax.adults + 0.75 * pax.children + 0.10 * pax.infants
            total *= max(pax_factor, 1.0)

            baggage = self._baggage_for_cabin(query.cabin_class)
            offer = finalize_offer(
                provider_key=self.key,
                native_id=f"{seed_material}-{i}".encode().hex()[:16],
                total_amount=total,
                total_currency="USD",
                slices=slices,
                passenger_count=pax.total,
                cabin_class=query.cabin_class,
                booking_type=BookingType.search_link,
                baggage=baggage,
                raw={"synthetic": True, "variant": i},
            )
            offers.append(offer)

        # Sort cheapest-first so the caller sees a sensible default order.
        offers.sort(key=lambda o: o.total_amount)
        return offers

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _build_slice_for_leg(
        self,
        leg: QueryLeg,
        query: ProviderSearchQuery,
        rng: Random,
        variant: int,
    ):
        """Return (Slice, leg_price_usd) or None if we can't route this leg."""
        distance = self._airports.distance_km(leg.origin, leg.destination)
        if distance is None:
            # Unknown airport(s): still produce something rather than nothing,
            # using a generic mid-haul distance so the app degrades gracefully.
            distance = 4500.0

        # Decide stop count for this variant. Short hops lean non-stop; long
        # hauls often need a connection. Variant index adds spread.
        stops = self._pick_stops(distance, variant, rng)

        airline = self._pick_airline(leg, rng)
        via = self._pick_connections(leg, airline, stops, rng)

        airports_path = [leg.origin, *via, leg.destination]
        segments: list[Segment] = []
        # Start the first departure at a plausible local hour.
        depart = datetime.combine(
            leg.departure_date,
            datetime.min.time(),
        ) + timedelta(hours=rng.choice([6, 7, 8, 9, 11, 13, 15, 17, 19, 21]))

        leg_distance_total = 0.0
        for a, b in zip(airports_path, airports_path[1:]):
            seg_dist = self._airports.distance_km(a, b) or (distance / (stops + 1))
            leg_distance_total += seg_dist
            flight_minutes = int(
                seg_dist / _CRUISE_KMH * 60 + _TAXI_MINUTES_PER_SEGMENT
            )
            arrive = depart + timedelta(minutes=flight_minutes)
            segments.append(
                Segment(
                    origin=a,
                    destination=b,
                    departure_at=depart,
                    arrival_at=arrive,
                    marketing_carrier_code=airline["code"],
                    marketing_carrier_name=airline["name"],
                    operating_carrier_code=airline["code"],
                    flight_number=str(rng.randint(100, 3999)),
                    aircraft=rng.choice(
                        ["Airbus A320", "Airbus A350", "Boeing 737", "Boeing 787", "Boeing 777"]
                    ),
                    duration_minutes=flight_minutes,
                    cabin_class=query.cabin_class,
                    baggage=self._baggage_for_cabin(query.cabin_class),
                )
            )
            # Layover before the next segment (if any).
            layover = timedelta(minutes=rng.choice([65, 80, 95, 120, 150, 190, 240]))
            depart = arrive + layover

        sl = build_slice(segments)

        # Price: distance-based, cabin-scaled, with a per-variant jitter and a
        # discount for extra stops (less convenient => cheaper).
        base = leg_distance_total * _price_per_km(leg_distance_total)
        base *= _CABIN_MULTIPLIER.get(query.cabin_class, 1.0)
        base *= 1.0 - 0.06 * stops  # each stop ~6% cheaper
        base *= 1.0 + rng.uniform(-0.12, 0.28)  # market spread
        base += rng.uniform(15, 60)  # taxes/fees floor
        # Seasonality: flights land pricier on weekends.
        if leg.departure_date.weekday() in (4, 6):
            base *= 1.08

        return sl, round(base, 2)

    def _pick_stops(self, distance: float, variant: int, rng: Random) -> int:
        if distance < 1500:
            options = [0, 0, 0, 1]
        elif distance < 5000:
            options = [0, 0, 1, 1, 2]
        elif distance < 10000:
            options = [0, 1, 1, 1, 2]
        else:
            options = [1, 1, 2, 2]
        return options[variant % len(options)] if variant < 4 else rng.choice(options)

    def _pick_airline(self, leg: QueryLeg, rng: Random) -> dict:
        """Prefer an airline whose hub is near the route; else random."""
        candidates = [
            a
            for a in self._airlines
            if leg.origin in a["hubs"] or leg.destination in a["hubs"]
        ]
        pool = candidates or self._airlines
        return rng.choice(pool)

    def _pick_connections(
        self, leg: QueryLeg, airline: dict, stops: int, rng: Random
    ) -> list[str]:
        """Choose intermediate airports for the connection(s)."""
        if stops <= 0:
            return []
        # First choice: the airline's own hub(s).
        hubs = [h for h in airline["hubs"] if h not in (leg.origin, leg.destination)]
        via: list[str] = []
        if hubs:
            via.append(rng.choice(hubs))
        # If we still need more stops, borrow another carrier's hub.
        while len(via) < stops:
            other = rng.choice(self._airlines)
            extra = [
                h
                for h in other["hubs"]
                if h not in (leg.origin, leg.destination, *via)
            ]
            if extra:
                via.append(rng.choice(extra))
            else:
                break
        return via[:stops]

    def _baggage_for_cabin(self, cabin: CabinClass) -> BaggageAllowance:
        if cabin in (CabinClass.business, CabinClass.first):
            return BaggageAllowance(
                checked_bags=2, carry_on_bags=1, weight_kg=32, description="2 x 32kg"
            )
        if cabin == CabinClass.premium_economy:
            return BaggageAllowance(
                checked_bags=1, carry_on_bags=1, weight_kg=23, description="1 x 23kg"
            )
        return BaggageAllowance(
            checked_bags=1, carry_on_bags=1, weight_kg=23, description="1 x 23kg"
        )
