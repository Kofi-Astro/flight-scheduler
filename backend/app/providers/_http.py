"""Shared HTTP plumbing for provider implementations.

Each HTTP-based provider gets ONE long-lived ``httpx.AsyncClient`` (connection
pooling, HTTP/2) created lazily on first use and closed on app shutdown via
``FlightProvider.close()``.
"""

from __future__ import annotations

import httpx

# Sensible timeout: providers can be slow, but we don't want a hung request to
# block a search forever. The search service also races providers with its own
# outer timeout.
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=25.0, write=10.0, pool=5.0)


class HttpProviderMixin:
    """Mix in to a :class:`FlightProvider` to get a lazy shared async client."""

    _client: httpx.AsyncClient | None = None
    # Subclasses set these:
    base_url: str = ""
    default_headers: dict[str, str] = {}

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.default_headers,
                timeout=DEFAULT_TIMEOUT,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
