"""Currency conversion.

Providers return prices in their own currencies (USD, EUR, local...). The
operator wants to see everything in one currency they pick (GHS, USD, EUR, TRY,
CNY, ...). This service:

  * fetches live FX rates (base = USD) from a free source,
  * caches them in memory for ``_TTL_SECONDS`` so we don't hammer the API,
  * falls back to a baked-in table if the network/API is unavailable, so the
    app NEVER breaks just because FX lookup failed,
  * exposes ``convert()`` and ``convert_offer_currency()``.

FX source
---------
Default ``CURRENCY_PROVIDER=er_api`` -> https://open.er-api.com/v6/latest/USD
(no API key, generous free use). Set ``CURRENCY_PROVIDER=exchangerate_host`` to
use exchangerate.host instead (optional ``EXCHANGERATE_HOST_ACCESS_KEY``).
"""

from __future__ import annotations

import logging
import time

import httpx

from app.config import get_settings
from app.providers._http import DEFAULT_TIMEOUT

logger = logging.getLogger("flight_scheduler.currency")

_TTL_SECONDS = 6 * 60 * 60  # refresh rates every 6 hours

# Currencies we advertise in the UI toggle. GHS + USD are required by the spec;
# the rest cover the operator's common destinations. Add more freely — as long
# as the FX source knows the code, conversion just works.
SUPPORTED_CURRENCIES: list[str] = [
    "GHS", "USD", "EUR", "GBP", "TRY", "CNY",
    "NGN", "ZAR", "AED", "CAD", "INR", "KES",
    "XOF", "EGP", "MAD", "SAR", "JPY", "AUD", "CHF",
]

# Approximate rates per 1 USD, used ONLY when the live fetch fails. Rough is
# fine — it keeps the app usable offline; refresh happens on the next request.
_FALLBACK_RATES: dict[str, float] = {
    "USD": 1.0, "EUR": 0.92, "GBP": 0.79, "GHS": 15.6, "TRY": 34.0,
    "CNY": 7.2, "NGN": 1550.0, "ZAR": 18.2, "AED": 3.67, "CAD": 1.36,
    "INR": 83.0, "KES": 129.0, "XOF": 605.0, "EGP": 48.0, "MAD": 9.9,
    "SAR": 3.75, "JPY": 148.0, "AUD": 1.5, "CHF": 0.88,
}


class CurrencyService:
    """Holds cached USD-based rates and converts between currencies."""

    def __init__(self) -> None:
        self._base = "USD"
        self._rates: dict[str, float] = dict(_FALLBACK_RATES)
        self._fetched_at: float = 0.0
        self._is_live = False

    # ------------------------------------------------------------------
    async def rates(self) -> dict[str, float]:
        """Return current USD-based rates, refreshing if the cache is stale."""
        if time.time() - self._fetched_at > _TTL_SECONDS:
            await self._refresh()
        return self._rates

    async def _refresh(self) -> None:
        settings = get_settings()
        try:
            if settings.currency_provider == "exchangerate_host":
                rates = await self._fetch_exchangerate_host(
                    settings.exchangerate_host_access_key
                )
            else:
                rates = await self._fetch_er_api()
            if rates:
                # Keep any fallback codes the source didn't return.
                self._rates = {**_FALLBACK_RATES, **rates, "USD": 1.0}
                self._fetched_at = time.time()
                self._is_live = True
                logger.info("Refreshed FX rates (%d currencies)", len(rates))
        except Exception as exc:  # noqa: BLE001 - never let FX break a search
            logger.warning("FX refresh failed (%s); using cached/fallback rates", exc)
            # Push the timestamp forward a little so we don't retry on every
            # single request during an outage.
            self._fetched_at = time.time() - _TTL_SECONDS + 300

    async def _fetch_er_api(self) -> dict[str, float]:
        url = "https://open.er-api.com/v6/latest/USD"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        if data.get("result") != "success":
            raise RuntimeError(data.get("error-type", "unknown er-api error"))
        return {k: float(v) for k, v in data["rates"].items()}

    async def _fetch_exchangerate_host(self, access_key: str) -> dict[str, float]:
        params = {"base": "USD"}
        if access_key:
            params["access_key"] = access_key
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get("https://api.exchangerate.host/latest", params=params)
            resp.raise_for_status()
            data = resp.json()
        return {k: float(v) for k, v in (data.get("rates") or {}).items()}

    # ------------------------------------------------------------------
    async def convert(self, amount: float, from_ccy: str, to_ccy: str) -> float:
        """Convert ``amount`` from one ISO currency to another."""
        from_ccy, to_ccy = from_ccy.upper(), to_ccy.upper()
        if from_ccy == to_ccy:
            return round(amount, 2)

        rates = await self.rates()
        # Everything is quoted per 1 USD. amount_in_usd = amount / rate[from]
        # then * rate[to].
        rate_from = rates.get(from_ccy)
        rate_to = rates.get(to_ccy)
        if not rate_from or not rate_to:
            logger.warning("Missing FX rate for %s or %s; returning unconverted", from_ccy, to_ccy)
            return round(amount, 2)
        usd = amount / rate_from
        return round(usd * rate_to, 2)

    async def status(self) -> dict:
        """For ``GET /api/currency`` — what the frontend needs to build the toggle."""
        rates = await self.rates()
        return {
            "base": self._base,
            "supported": SUPPORTED_CURRENCIES,
            "rates": {c: rates.get(c) for c in SUPPORTED_CURRENCIES},
            "live": self._is_live,
            "fetched_at": self._fetched_at,
        }


# Process-wide singleton (created in app.main and shared via dependency).
_service: CurrencyService | None = None


def get_currency_service() -> CurrencyService:
    global _service
    if _service is None:
        _service = CurrencyService()
    return _service
