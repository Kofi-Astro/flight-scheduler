"""Flight data providers.

The whole point of this package: the rest of the app depends ONLY on the
abstract :class:`~app.providers.base.FlightProvider` interface. Concrete
implementations (Duffel, Amadeus, Kiwi/Tequila, Travelpayouts, Mock) each live
in their own module and map that vendor's response into our normalised
``FlightOffer`` model.

Adding a new provider later = write one file + add its key to
``providers/registry.py``. Nothing else changes.
"""

from app.providers.base import FlightProvider, ProviderSearchQuery, QueryLeg

__all__ = ["FlightProvider", "ProviderSearchQuery", "QueryLeg"]
