#!/usr/bin/env python3
"""Build / refresh the bundled airport dataset used by autocomplete.

Source: OurAirports (public domain) — https://ourairports.com/data/

What it does
------------
1. Downloads ``airports.csv`` from the OurAirports mirror.
2. Keeps only airports that have an IATA code and are ``large_airport`` or
   ``medium_airport`` (plus a curated allow-list of smaller but useful ones).
3. Adds a handful of IATA *metro* codes (LON, NYC, PAR, ...) that providers
   understand and operators often type.
4. Writes ``app/data/airports.json`` — a compact list the backend loads at
   startup.

Run it whenever you want fresher data:

    cd backend
    python scripts/build_airports.py

The repo already ships a generated ``airports.json`` so you don't *have* to run
this to get started.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
COUNTRIES_URL = "https://davidmegginson.github.io/ourairports-data/countries.csv"

BACKEND_DIR = Path(__file__).resolve().parent.parent
OUT_PATH = BACKEND_DIR / "app" / "data" / "airports.json"

# Airport "types" from OurAirports we consider worth offering.
KEEP_TYPES = {"large_airport", "medium_airport"}

# Small airports that punch above their size for this business (island hubs,
# regional gateways). Add codes here as needed.
ALWAYS_KEEP_IATA = {
    "TML",  # Tamale, Ghana
    "KMS",  # Kumasi, Ghana
    "NYI",  # Sunyani, Ghana
}

# IATA metropolitan-area codes. Providers (Duffel/Amadeus/Kiwi) expand these to
# all airports in the city, which is exactly what an operator wants when a
# client says "fly me to London".
METRO_CODES = [
    # iata, city, country, country_code, lat, lon
    ("LON", "London", "United Kingdom", "GB", 51.5074, -0.1278),
    ("NYC", "New York", "United States", "US", 40.7128, -74.0060),
    ("PAR", "Paris", "France", "FR", 48.8566, 2.3522),
    ("MIL", "Milan", "Italy", "IT", 45.4642, 9.1900),
    ("TYO", "Tokyo", "Japan", "JP", 35.6762, 139.6503),
    ("MOW", "Moscow", "Russia", "RU", 55.7558, 37.6173),
    ("BJS", "Beijing", "China", "CN", 39.9042, 116.4074),
    ("WAS", "Washington", "United States", "US", 38.9072, -77.0369),
    ("CHI", "Chicago", "United States", "US", 41.8781, -87.6298),
    ("SAO", "Sao Paulo", "Brazil", "BR", -23.5558, -46.6396),
    ("RIO", "Rio de Janeiro", "Brazil", "BR", -22.9068, -43.1729),
    ("BUE", "Buenos Aires", "Argentina", "AR", -34.6037, -58.3816),
]


def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: str) -> float | None:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _fetch_csv(url: str) -> list[dict]:
    print(f"Downloading {url} ...", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        text = resp.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def build() -> list[dict]:
    # country code (ISO alpha-2) -> country name
    country_names = {
        (r.get("code") or "").strip().upper(): (r.get("name") or "").strip()
        for r in _fetch_csv(COUNTRIES_URL)
    }

    reader = _fetch_csv(SOURCE_URL)
    airports: list[dict] = []

    for row in reader:
        iata = (row.get("iata_code") or "").strip().upper()
        if not iata or len(iata) != 3:
            continue

        atype = row.get("type", "")
        if atype not in KEEP_TYPES and iata not in ALWAYS_KEEP_IATA:
            continue

        # Weight: large hubs first in autocomplete. Scheduled-service flag and
        # airport type both feed the score.
        weight = 0
        if atype == "large_airport":
            weight += 100
        elif atype == "medium_airport":
            weight += 40
        if (row.get("scheduled_service") or "").lower() == "yes":
            weight += 20

        cc = (row.get("iso_country") or "").strip().upper()
        airports.append(
            {
                "iata": iata,
                "name": (row.get("name") or "").strip(),
                "city": (row.get("municipality") or "").strip()
                or (row.get("name") or "").strip(),
                "country": country_names.get(cc, cc),
                "country_code": cc,
                "is_metro": False,
                "latitude": _to_float(row.get("latitude_deg", "")),
                "longitude": _to_float(row.get("longitude_deg", "")),
                "weight": weight,
            }
        )

    # Add metro codes with a high weight so they rank near the top.
    for iata, city, country, cc, lat, lon in METRO_CODES:
        airports.append(
            {
                "iata": iata,
                "name": f"{city} — all airports",
                "city": city,
                "country": country,
                "country_code": cc,
                "is_metro": True,
                "latitude": lat,
                "longitude": lon,
                "weight": 250,
            }
        )

    # De-duplicate by IATA, keeping the highest-weight entry.
    best: dict[str, dict] = {}
    for a in airports:
        cur = best.get(a["iata"])
        if cur is None or a["weight"] > cur["weight"]:
            best[a["iata"]] = a

    result = sorted(best.values(), key=lambda a: (-a["weight"], a["iata"]))
    print(f"Kept {len(result)} airports.", file=sys.stderr)
    return result


def main() -> None:
    data = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Compact (no whitespace) — this file is bundled in the repo and loaded at
    # startup; keep it small.
    OUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    )
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
