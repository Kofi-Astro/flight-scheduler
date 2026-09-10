# Deployment guide — Railway

This deploys **two services** from one repo:

- **`backend`** — the FastAPI API
- **`frontend`** — the static site (served by a tiny Python server)

Plus, optionally, a **Postgres** database and a **Cron** job for price alerts.

Railway is the target, but the app is plain Python + static files, so it also
runs on Render, Fly.io, a VPS, etc. The only platform-specific files are
`railway.json` / `Procfile` / `nixpacks.toml` in each service folder.

---

## 0. Prerequisites

- A [Railway](https://railway.app) account.
- This repository pushed to GitHub.
- (Optional) API keys for the flight providers you want live — see the main
  [README](README.md#turning-on-real-flight-data). You can deploy with just the
  mock provider and add keys later.

---

## 1. Create the project

1. Railway dashboard → **New Project** → **Deploy from GitHub repo** → pick this
   repo.
2. Railway will create one service and try to build the repo root. We'll point
   it at `backend/` next, then add the frontend as a second service.

---

## 2. Backend service

### 2a. Configure the service

Open the service → **Settings**:

| Setting | Value |
|---|---|
| **Service name** | `backend` (or `flight-api`) |
| **Root Directory** | `backend` |
| **Build** | Nixpacks (auto-detected from `requirements.txt`) |
| **Start Command** | leave blank — `railway.json` sets it to `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Healthcheck Path** | `/api/health` (already in `railway.json`) |

### 2b. Environment variables

Service → **Variables** → add:

```dotenv
APP_ENV=production

# Set this AFTER you know the frontend URL (step 4). For now, a placeholder:
CORS_ALLOW_ORIGINS=https://your-frontend.up.railway.app

# Start with mock; add real providers once their keys are set below.
ENABLED_PROVIDERS=mock

# --- add the providers you have keys for ---
# DUFFEL_API_TOKEN=duffel_test_xxx
# DUFFEL_API_VERSION=v2
# AMADEUS_CLIENT_ID=xxx
# AMADEUS_CLIENT_SECRET=xxx
# AMADEUS_HOSTNAME=test.api.amadeus.com
# TEQUILA_API_KEY=xxx
# TRAVELPAYOUTS_TOKEN=xxx
# TRAVELPAYOUTS_MARKER=xxx

# --- price-drop alerts (optional) ---
# SMTP_HOST=smtp.example.com
# SMTP_PORT=587
# SMTP_USERNAME=xxx
# SMTP_PASSWORD=xxx
# SMTP_FROM=alerts@yourdomain.com
# ALERTS_CRON_SECRET=make-a-long-random-string
```

### 2c. Database — pick one

**Option A — SQLite (simplest, fine for one operator).**
Do nothing: the app defaults to a SQLite file. ⚠️ Railway's filesystem is
**ephemeral** — the DB (shortlists, clients, alerts) resets on every redeploy.
To keep it, add a **Volume** (service → **Settings → Volumes**) mounted at
`/app/app/data`, so `app/data/local.sqlite3` persists.

**Option B — Postgres (recommended once it matters).**
1. Project → **New** → **Database** → **Add PostgreSQL**.
2. Copy its **`DATABASE_URL`** (`postgresql://…`) from the Postgres service's
   **Variables**.
3. Add it to the **backend** service's variables as `DATABASE_URL`.
The app detects Postgres automatically; `psycopg` is already in
`requirements.txt`. Tables are created on startup.

### 2d. Networking

Service → **Settings → Networking** → **Generate Domain**. Note the URL, e.g.
`https://backend-production-abcd.up.railway.app`. Test:

```bash
curl https://backend-production-abcd.up.railway.app/api/health
# {"status":"ok","version":"0.1.0"}
```

---

## 3. Frontend service

1. Project → **New** → **GitHub Repo** → same repo again (creates a 2nd service).
2. Service → **Settings**:

   | Setting | Value |
   |---|---|
   | **Service name** | `frontend` |
   | **Root Directory** | `frontend` |
   | **Start Command** | blank — `railway.json` sets `python server.py` |

3. Service → **Variables**:

   ```dotenv
   API_BASE_URL=https://backend-production-abcd.up.railway.app
   ```

   (the backend URL from step 2d, no trailing slash)

4. Service → **Settings → Networking → Generate Domain**. This is the URL you
   open in a browser, e.g. `https://frontend-production-wxyz.up.railway.app`.

---

## 4. Connect them (CORS)

Go back to the **backend** service → **Variables** and set
`CORS_ALLOW_ORIGINS` to the **frontend's** real URL:

```dotenv
CORS_ALLOW_ORIGINS=https://frontend-production-wxyz.up.railway.app
```

You can list several, comma-separated (e.g. a custom domain + the railway.app
one). Redeploy the backend (**Deployments → Redeploy**).

Open the frontend URL — the search form should work. The ⓘ button (top-right)
shows provider status.

---

## 5. Price-drop alerts cron (optional)

Alerts are re-priced only when something calls `POST /api/alerts/check`.

1. Backend variables: set `ALERTS_CRON_SECRET` to a long random string.
2. Project → **New** → **Cron** (or a new service running a one-line script).
   Railway's native cron: add a service whose **Start Command** is:

   ```bash
   curl -fsS -X POST "$BACKEND_URL/api/alerts/check" -H "X-Cron-Secret: $ALERTS_CRON_SECRET"
   ```

   with variables `BACKEND_URL` and `ALERTS_CRON_SECRET`, and a **Cron Schedule**
   like `0 */6 * * *` (every 6 hours).

Without the cron, alerts still store correctly and you can trigger a check
manually from the API docs.

---

## 6. Custom domains (optional)

Each service → **Settings → Networking → Custom Domain**. Add a CNAME at your
DNS provider as Railway instructs. Then:

- Update the frontend's `API_BASE_URL` to the backend's custom domain.
- Add the frontend's custom domain to the backend's `CORS_ALLOW_ORIGINS`.

---

## 7. Redeploys & updates

Every `git push` to the default branch redeploys both services (Railway watches
the repo). To refresh the bundled airport list:

```bash
cd backend
python scripts/build_airports.py
git commit -am "Refresh airport dataset"
git push
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Frontend loads but "Can't reach the backend" toast | `API_BASE_URL` on the frontend is wrong, or the backend domain isn't generated. |
| Search works locally, fails in prod with a CORS error in the browser console | `CORS_ALLOW_ORIGINS` on the backend doesn't exactly match the frontend origin (scheme + host, no path). |
| Shortlists/clients vanish after a deploy | You're on SQLite with no volume. Add a volume (2c option A) or switch to Postgres (2c option B). |
| A provider returns nothing | Check the ⓘ panel — it's likely "missing key". Add the key and make sure the provider is in `ENABLED_PROVIDERS`. |
| Amadeus works in test but not prod | Set `AMADEUS_HOSTNAME=api.amadeus.com` and use production credentials. |
| `/api/alerts/check` returns 401 | Send the `X-Cron-Secret` header matching `ALERTS_CRON_SECRET`. |
| Backend build fails on `psycopg` | It ships as a binary wheel; if a platform lacks it, use `DATABASE_URL=sqlite://…` or add build deps. |
