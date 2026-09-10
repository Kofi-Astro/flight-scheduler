# Flight Scheduler — flight scouting & booking assistant

A full-stack web app for a travel booking business. Search, compare and sort
flights from **any origin to any destination worldwide** across multiple flight
APIs, shortlist good options per client, and send clients a ready-made booking
link — no in-app checkout.

Built to start small (one operator, SQLite, synthetic data on day one) and grow
into a multi-agent agency tool without a rewrite.

---

## What's in the box

| Area | Tech | Notes |
|---|---|---|
| **Frontend** | HTML + CSS + vanilla JS (ES modules) | No framework, no build step. Componentised. |
| **Backend** | Python 3.12 + FastAPI | Routers / services / providers cleanly separated. |
| **Database** | SQLAlchemy 2.0 → SQLite (local) / Postgres (prod) | One env var to switch. |
| **Deploy** | Railway | Two services (backend + frontend), configs included. |
| **Flight data** | Duffel · Amadeus · Kiwi/Tequila · Travelpayouts · Mock | Pluggable `FlightProvider` interface; combine or swap freely. |

### Features

- **Search form** — origin/destination with worldwide airport autocomplete,
  one-way / round-trip / multi-city, passengers, cabin class.
- **Flexible dates** — a cheapest-days price grid across a ±3–7 day window.
- **Results** — airline, price, total duration, stops, layover airports & times,
  departure/arrival times, baggage allowance (where the API provides it).
- **Sort & filter** — price, duration, stops, airline, price range, max duration.
- **Shortlist** — bookmark options with a client name/note; grouped per client;
  re-check the price of any saved option.
- **Currency toggle** — GHS, USD, EUR, GBP, TRY, CNY + more. Live FX with an
  offline fallback. Conversion happens in the browser so toggling is instant.
- **Deep links** — provider-native booking links where available, otherwise a
  pre-filled Google Flights / Skyscanner / Kayak link. Travelpayouts links carry
  your affiliate marker (a future revenue stream).
- **WhatsApp share** — a formatted, printable summary + a `wa.me` link.
- **Client CRM** — name, phone, email, note, saved-option count.
- **Price-drop alerts** — watch a route or a saved option; email on drop;
  driven by a scheduled `/api/alerts/check` call (Railway Cron).
- **Mobile-responsive**, dark-mode aware.

---

## Repo layout

```
flight-scheduler/
├── backend/          FastAPI app        (see backend/README.md)
│   ├── app/
│   │   ├── main.py           app wiring (CORS, lifespan, routers)
│   │   ├── config.py         all settings from env vars
│   │   ├── models/           Pydantic request/response shapes
│   │   ├── routers/          thin HTTP handlers
│   │   ├── services/         business logic (search, currency, CRM, alerts…)
│   │   ├── providers/        FlightProvider interface + one file per vendor
│   │   ├── storage/          SQLAlchemy engine + tables
│   │   └── data/             bundled airports.json + airlines.json
│   ├── scripts/build_airports.py
│   ├── tests/
│   ├── requirements.txt / requirements-dev.txt
│   ├── railway.json · Procfile · nixpacks.toml
│   └── .env.example
├── frontend/         Vanilla JS SPA     (see frontend/README.md)
│   ├── index.html
│   ├── server.py             stdlib static server + /env.js injector
│   ├── css/ · js/            design system + components/views
│   ├── railway.json · Procfile · nixpacks.toml
│   └── .env.example
├── .env.example      combined reference of every variable
├── DEPLOYMENT.md     step-by-step Railway guide
└── README.md         you are here
```

---

## Run locally

Two terminals. **Nothing but Python is required, and no API keys** — the mock
provider serves realistic synthetic flights so every feature works immediately.

### 1. Backend (port 8000)

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                  # defaults are fine to start
uvicorn app.main:app --reload --port 8000
```

Check: <http://localhost:8000/docs> (interactive API) ·
<http://localhost:8000/api/health>

### 2. Frontend (port 5173)

```bash
cd frontend
cp .env.example .env                  # API_BASE_URL=http://localhost:8000
python server.py
```

Open <http://localhost:5173>.

### 3. Run the tests (optional)

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest
```

---

## Turning on real flight data

The app queries every provider listed in `ENABLED_PROVIDERS` (comma-separated,
priority order) **that also has its credentials set**. Start with `mock`, then
add providers as you get keys. Edit `backend/.env`:

```dotenv
ENABLED_PROVIDERS=mock,duffel,amadeus
```

| Provider | Get keys | Env vars | Cost to start |
|---|---|---|---|
| **Duffel** | <https://duffel.com> → create a **test** access token | `DUFFEL_API_TOKEN` (`duffel_test_…`), `DUFFEL_API_VERSION=v2` | Free sandbox, self-serve |
| **Amadeus Self-Service** | <https://developers.amadeus.com> → create an app | `AMADEUS_CLIENT_ID`, `AMADEUS_CLIENT_SECRET`, `AMADEUS_HOSTNAME=test.api.amadeus.com` | Free test tier |
| **Kiwi.com (Tequila)** | <https://tequila.kiwi.com> → create a Solution | `TEQUILA_API_KEY` | Sandbox free; production needs approval |
| **Travelpayouts / Skyscanner** | <https://travelpayouts.com> | `TRAVELPAYOUTS_TOKEN`, `TRAVELPAYOUTS_MARKER` | Free; affiliate commission later |

Each provider file (`backend/app/providers/<name>.py`) has a header comment with
its exact setup steps and API docs links. The **Providers** button (ⓘ, top-right
of the app) shows which are active vs. missing a key.

The full variable list with explanations is in
[`.env.example`](.env.example) (combined) and each service's own
`backend/.env.example` / `frontend/.env.example`.

---

## Deploy to Railway

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for the full walkthrough. In short:

1. Push this repo to GitHub.
2. Railway → **New Project → Deploy from GitHub**.
3. Add a **service for the backend**: Root Directory `backend`, add env vars
   (at least `ENABLED_PROVIDERS`, `CORS_ALLOW_ORIGINS`), optionally add the
   **Postgres** plugin and set `DATABASE_URL`.
4. Add a **service for the frontend**: Root Directory `frontend`, set
   `API_BASE_URL` to the backend's public URL.
5. Set the backend's `CORS_ALLOW_ORIGINS` to the frontend's public URL and
   redeploy.
6. (Optional) Add a **Cron** service hitting `POST /api/alerts/check` for
   price-drop alerts.

---

## Extending it later (the "grows into an agency" path)

- **User accounts / multiple agents** — the `clients` table already has an
  `owner_agent_id` column. Add an `agents` table + auth (FastAPI dependency),
  filter services by agent. No destructive migration.
- **Postgres** — set `DATABASE_URL` to a Railway Postgres URL. Code is
  unchanged. Introduce Alembic when you need real migrations.
- **More providers** — drop a file in `backend/app/providers/`, register it in
  `registry.py`. Everything downstream is provider-agnostic.
- **WhatsApp / SMS notifications** — implement a `send_*` in
  `services/notifications.py` and branch on `alert.channel`.
- **Commission tracking** — Travelpayouts deep links already carry your marker.

---

## Legal / data sources

This app **does not scrape** airline, Google Flights or OTA websites. It
integrates with official flight-search APIs, and the "constructed" deep links
are ordinary pre-filled search URLs. Prices and availability are always
indicative until a ticket is issued — the UI says so.
