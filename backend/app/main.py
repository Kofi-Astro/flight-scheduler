"""FastAPI application entrypoint.

Run locally:
    cd backend
    uvicorn app.main:app --reload --port 8000

Interactive API docs are then at http://localhost:8000/docs

Structure
---------
This file only *wires things together*:
  * creates the app + CORS,
  * runs startup/shutdown (DB tables, warm the FX cache, close provider clients),
  * mounts each router under ``/api``.

All real logic lives in ``routers/`` (thin) and ``services/`` (thick).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.providers.registry import close_all_providers, describe_providers
from app.routers import (
    airports,
    alerts,
    clients,
    currency,
    search,
    shortlist,
    summary,
)
from app.services.currency_service import get_currency_service
from app.storage.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("flight_scheduler")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    # --- startup ---
    logger.info("Starting Flight Scheduler API v%s (env=%s)", __version__, settings.app_env)
    init_db()  # create tables if missing
    try:
        # Warm the FX cache so the first search isn't slowed by an FX fetch.
        await get_currency_service().rates()
    except Exception:  # noqa: BLE001 - fallback rates cover us
        logger.warning("Could not warm FX cache at startup; will retry on demand")

    active = [p["key"] for p in describe_providers() if p["enabled"] and p["configured"]]
    logger.info("Active flight providers: %s", active or ["mock (fallback)"])

    yield

    # --- shutdown ---
    await close_all_providers()
    logger.info("Shut down cleanly")


app = FastAPI(
    title="Flight Scheduler API",
    version=__version__,
    description=(
        "Backend for the flight scouting & booking assistant. "
        "Search flights worldwide across multiple providers, compare and sort, "
        "shortlist options per client, and generate booking deep links."
    ),
    lifespan=lifespan,
    # Hide the schema in production if you like; docs are handy for a solo
    # operator though, so we keep them on.
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- CORS -----------------------------------------------------------------
# The frontend is a separate origin (different Railway service / localhost port),
# so the browser needs these headers to let it call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,  # we don't use cookies; tokens (later) go in headers
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ------------------------------------------------------------
# Every router already declares its own prefix + tags.
app.include_router(search.router)
app.include_router(airports.router)
app.include_router(shortlist.router)
app.include_router(clients.router)
app.include_router(currency.router)
app.include_router(alerts.router)
app.include_router(summary.router)


# --- Meta endpoints -------------------------------------------------
@app.get("/", tags=["meta"], summary="Service banner")
def root() -> dict:
    return {
        "service": "flight-scheduler-api",
        "version": __version__,
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health", tags=["meta"], summary="Health check")
def health() -> dict:
    """Cheap liveness probe for Railway / uptime monitors."""
    return {"status": "ok", "version": __version__}


@app.get("/api/providers", tags=["meta"], summary="Provider status")
def providers() -> list[dict]:
    """Which providers are known, enabled, and correctly configured.

    The frontend shows this so the operator understands their data coverage
    (e.g. "Amadeus enabled but missing credentials").
    """
    return describe_providers()
