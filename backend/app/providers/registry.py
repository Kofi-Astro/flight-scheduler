"""Provider registry — turns ``ENABLED_PROVIDERS`` into live provider objects.

This is the ONE place that knows every concrete provider class. Adding a
provider = import it here and add a line to ``_PROVIDER_CLASSES``.

The rest of the app calls :func:`get_active_providers` and gets back a list of
ready-to-use :class:`FlightProvider` instances, in the priority order the
operator configured.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings
from app.providers.base import FlightProvider
from app.providers.amadeus import AmadeusProvider
from app.providers.duffel import DuffelProvider
from app.providers.kiwi import KiwiProvider
from app.providers.mock import MockProvider
from app.providers.travelpayouts import TravelpayoutsProvider

logger = logging.getLogger("flight_scheduler.providers")

# key -> class. Keys must match what users put in ENABLED_PROVIDERS.
_PROVIDER_CLASSES: dict[str, type[FlightProvider]] = {
    MockProvider.key: MockProvider,
    DuffelProvider.key: DuffelProvider,
    AmadeusProvider.key: AmadeusProvider,
    KiwiProvider.key: KiwiProvider,
    TravelpayoutsProvider.key: TravelpayoutsProvider,
}


@lru_cache
def _instances() -> dict[str, FlightProvider]:
    """Instantiate every known provider once (cheap — no network in __init__)."""
    return {key: cls() for key, cls in _PROVIDER_CLASSES.items()}


def get_active_providers() -> list[FlightProvider]:
    """Providers that are BOTH enabled in settings AND properly configured.

    Order follows ``ENABLED_PROVIDERS``. Enabled-but-unconfigured providers are
    logged and skipped (so a missing key degrades gracefully instead of
    500-ing).
    """
    settings = get_settings()
    instances = _instances()
    active: list[FlightProvider] = []

    for key in settings.enabled_providers:
        provider = instances.get(key)
        if provider is None:
            logger.warning("Unknown provider %r in ENABLED_PROVIDERS — ignoring", key)
            continue
        if not provider.is_configured:
            logger.warning(
                "Provider %r is enabled but missing credentials — skipping", key
            )
            continue
        active.append(provider)

    if not active:
        # Never leave the app with zero providers — fall back to mock so the UI
        # still works and the operator sees *something*.
        logger.warning("No configured providers; falling back to MockProvider")
        active.append(instances[MockProvider.key])

    return active


def describe_providers() -> list[dict]:
    """Status list for ``GET /api/providers`` (shown in the UI's settings area)."""
    settings = get_settings()
    instances = _instances()
    out: list[dict] = []
    for key, cls in _PROVIDER_CLASSES.items():
        provider = instances[key]
        out.append(
            {
                "key": key,
                "display_name": cls.display_name,
                "enabled": key in settings.enabled_providers,
                "configured": provider.is_configured,
            }
        )
    return out


async def close_all_providers() -> None:
    """Close every provider's HTTP client. Called on app shutdown."""
    for provider in _instances().values():
        try:
            await provider.close()
        except Exception:  # noqa: BLE001 - shutdown must not raise
            logger.exception("Error closing provider %s", provider.key)
