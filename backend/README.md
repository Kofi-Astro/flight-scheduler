# Flight Scheduler — Backend (FastAPI)

The API that powers the flight scouting assistant: multi-provider flight search,
shortlists, a lightweight client CRM, currency conversion, deep links, and
price-drop alerts.

> Full project overview, deployment, and API-key setup live in the repo-root
> [`README.md`](../README.md) and [`DEPLOYMENT.md`](../DEPLOYMENT.md). This file
> is the quick backend-only reference.

## Run locally

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # defaults work out of the box (mock provider)
uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- Health:   http://localhost:8000/api/health

With no API keys the **mock provider** returns realistic synthetic flights so
every feature works. Add real providers by putting their keys in `.env` and
listing them in `ENABLED_PROVIDERS` (e.g. `mock,duffel,amadeus`).

## Tests

```bash
cd backend
python -m pytest
```

Tests use a throwaway SQLite DB and the mock provider only (no external calls
except an optional FX-rate fetch that falls back gracefully offline).

## Layout

```
app/
  main.py            FastAPI app: CORS, lifespan, router wiring
  config.py          all settings from env vars (pydantic-settings)
  models/            Pydantic request/response shapes
  routers/           thin HTTP handlers (one file per area)
  services/          business logic (search orchestration, currency, CRM, alerts)
  providers/         FlightProvider interface + registry + one file per vendor
  storage/           SQLAlchemy engine + ORM tables
  data/              bundled airports.json + airlines.json
scripts/
  build_airports.py  regenerate airports.json from OurAirports
tests/
```

## Adding a flight provider

1. Create `app/providers/yourprovider.py` implementing `FlightProvider`
   (`key`, `display_name`, `is_configured`, `async search()`).
2. Map the vendor response into `FlightOffer` (use helpers in
   `providers/support.py`).
3. Register it in `app/providers/registry.py` (`_PROVIDER_CLASSES`).
4. Add its settings to `app/config.py` and `.env.example`.

Nothing else changes — the search service, routers and frontend are
provider-agnostic.
