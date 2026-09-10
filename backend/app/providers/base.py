"""The abstract ``FlightProvider`` interface.

Every integration implements this. The search service (``services/search_service``)
fans a query out to all enabled providers concurrently, then merges the results.

Contract
--------
* ``search()`` is **async** and must not raise for "no results" — return ``[]``.
  It *may* raise for genuine failures (bad credentials, network error); the
  service catches those and reports them per-provider without failing the whole
  request.
* Implementations return offers priced in whatever currency the vendor gives.
  Currency conversion to the operator's chosen currency happens later, in the
  service, so providers stay simple.
* Implementations should respect ``query.max_results`` to keep responses small.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import date

from app.models.flight import CabinClass
from app.models.search import PassengerCounts


@dataclass(slots=True)
class QueryLeg:
    """One directional leg of a search: from A to B on a given date.

    * one-way  -> 1 leg
    * round    -> 2 legs (out and back)
    * multi-city-> N legs
    """

    origin: str  # IATA, upper-case
    destination: str  # IATA, upper-case
    departure_date: date


@dataclass(slots=True)
class ProviderSearchQuery:
    """Normalised, provider-agnostic search request.

    This is what the service hands to every provider. It deliberately does NOT
    mention "return_date" etc. — legs cover all trip shapes uniformly.
    """

    legs: list[QueryLeg]
    passengers: PassengerCounts = field(default_factory=PassengerCounts)
    cabin_class: CabinClass = CabinClass.economy
    # Currency the operator ultimately wants. Some providers accept a currency
    # param (Duffel, Amadeus); for those we pass it through as a hint. Others
    # ignore it and the service converts afterwards.
    currency: str = "USD"
    max_results: int = 50

    # --- small helpers used by provider implementations -------------------
    @property
    def is_one_way(self) -> bool:
        return len(self.legs) == 1

    @property
    def is_round_trip(self) -> bool:
        return (
            len(self.legs) == 2
            and self.legs[0].origin == self.legs[1].destination
            and self.legs[0].destination == self.legs[1].origin
        )


class FlightProvider(abc.ABC):
    """Base class for all flight-search integrations."""

    #: Short stable key used in settings (``ENABLED_PROVIDERS``) and in offer ids.
    key: str = "base"
    #: Human-friendly name shown in the UI / logs.
    display_name: str = "Base Provider"

    @property
    @abc.abstractmethod
    def is_configured(self) -> bool:
        """True when this provider has the credentials it needs to run.

        The registry skips providers that are enabled but not configured, and
        the ``/api/providers`` endpoint surfaces this so the operator knows why
        a provider isn't returning results.
        """

    @abc.abstractmethod
    async def search(self, query: ProviderSearchQuery) -> list["FlightOffer"]:
        """Return normalised offers for ``query`` (possibly empty)."""

    async def close(self) -> None:
        """Release resources (e.g. the shared httpx client).

        Default is a no-op; HTTP-based providers override it.
        """
        return None


# Imported at the bottom to avoid a circular import in type hints above.
from app.models.flight import FlightOffer  # noqa: E402
