"""Airport lookup + search-as-you-type.

Loads the bundled ``app/data/airports.json`` once into memory (it's ~800 KB /
~4,600 entries — trivial) and builds a couple of indexes for fast prefix search.

Public API
----------
* ``search(query, limit)``  -> ranked list[Airport] for the autocomplete
* ``get(iata)``             -> Airport | None
* ``coordinates(iata)``     -> (lat, lon) | None   (used by the mock provider)
* ``distance_km(a, b)``     -> great-circle km between two IATA codes
"""

from __future__ import annotations

import json
import math
from functools import lru_cache

from app.config import DATA_DIR
from app.models.airport import Airport

_AIRPORTS_FILE = DATA_DIR / "airports.json"


class AirportService:
    """In-memory airport dataset with prefix search."""

    def __init__(self, airports: list[Airport]) -> None:
        self._all = airports
        # Fast exact lookup by IATA.
        self._by_iata: dict[str, Airport] = {a.iata: a for a in airports}
        # Pre-lower-cased search haystack per airport, so we don't re-lower on
        # every keystroke.
        self._haystack: list[tuple[Airport, str]] = [
            (
                a,
                f"{a.iata} {a.city} {a.name} {a.country} {a.country_code}".lower(),
            )
            for a in airports
        ]

    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> "AirportService":
        raw = json.loads(_AIRPORTS_FILE.read_text(encoding="utf-8"))
        airports = [Airport(**item) for item in raw]
        return cls(airports)

    # ------------------------------------------------------------------
    def get(self, iata: str) -> Airport | None:
        return self._by_iata.get(iata.upper())

    def coordinates(self, iata: str) -> tuple[float, float] | None:
        a = self.get(iata)
        if a and a.latitude is not None and a.longitude is not None:
            return (a.latitude, a.longitude)
        return None

    def distance_km(self, origin: str, destination: str) -> float | None:
        """Great-circle distance in km, or None if either coord is missing."""
        a = self.coordinates(origin)
        b = self.coordinates(destination)
        if not a or not b:
            return None
        return _haversine_km(a[0], a[1], b[0], b[1])

    # ------------------------------------------------------------------
    def search(self, query: str, limit: int = 8) -> list[Airport]:
        """Rank airports for an autocomplete query.

        Ranking, best first:
          1. exact IATA match
          2. IATA / city / name starts with the query
          3. query appears anywhere in the haystack
        Ties broken by the dataset ``weight`` (hub size), so big airports win.
        """
        q = query.strip().lower()
        if not q:
            # Empty query -> show the biggest hubs as sensible defaults.
            return sorted(self._all, key=lambda a: -a.weight)[:limit]

        exact: list[Airport] = []
        prefix: list[Airport] = []
        contains: list[Airport] = []

        for airport, hay in self._haystack:
            if airport.iata.lower() == q:
                exact.append(airport)
            elif (
                airport.iata.lower().startswith(q)
                or airport.city.lower().startswith(q)
                or airport.name.lower().startswith(q)
            ):
                prefix.append(airport)
            elif q in hay:
                contains.append(airport)

        for bucket in (prefix, contains):
            bucket.sort(key=lambda a: -a.weight)

        # Concatenate buckets, de-dup, cap at ``limit``.
        seen: set[str] = set()
        out: list[Airport] = []
        for airport in (*exact, *prefix, *contains):
            if airport.iata in seen:
                continue
            seen.add(airport.iata)
            out.append(airport)
            if len(out) >= limit:
                break
        return out


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in kilometres."""
    radius = 6371.0088  # mean Earth radius (km)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


@lru_cache
def get_airport_service() -> AirportService:
    """Process-wide singleton. Cached so the JSON is parsed once."""
    return AirportService.load()
