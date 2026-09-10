"""Unit tests for provider-layer helpers and the registry."""

from __future__ import annotations

import asyncio
from datetime import date

from app.providers.base import ProviderSearchQuery, QueryLeg
from app.providers.registry import describe_providers, get_active_providers
from app.providers.support import iso8601_duration_to_minutes


def test_iso8601_duration_parsing():
    assert iso8601_duration_to_minutes("PT7H30M") == 450
    assert iso8601_duration_to_minutes("PT45M") == 45
    assert iso8601_duration_to_minutes("P1DT2H") == 26 * 60
    assert iso8601_duration_to_minutes("") == 0
    assert iso8601_duration_to_minutes(None) == 0
    assert iso8601_duration_to_minutes("garbage") == 0


def test_registry_falls_back_to_mock_when_nothing_configured():
    active = get_active_providers()
    assert [p.key for p in active] == ["mock"]


def test_describe_providers_reports_status():
    described = {p["key"]: p for p in describe_providers()}
    assert described["mock"]["configured"] is True
    assert described["duffel"]["configured"] is False


def test_mock_provider_is_deterministic():
    from app.providers.mock import MockProvider

    provider = MockProvider()
    query = ProviderSearchQuery(
        legs=[QueryLeg("ACC", "JFK", date(2030, 1, 15))],
        currency="USD",
    )
    first = asyncio.run(provider.search(query))
    second = asyncio.run(provider.search(query))
    assert [o.total_amount for o in first] == [o.total_amount for o in second]
    assert all(o.slices[0].origin == "ACC" for o in first)
    assert all(o.slices[-1].destination == "JFK" for o in first)
