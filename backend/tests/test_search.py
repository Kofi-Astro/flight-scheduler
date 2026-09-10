"""Search endpoint tests (mock provider)."""

from __future__ import annotations


def test_one_way_search_returns_sorted_offers(client, future_dates):
    dep, _ = future_dates
    resp = client.post(
        "/api/search",
        json={
            "origin": "ACC",
            "destination": "DXB",
            "departure_date": dep,
            "currency": "USD",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["currency"] == "USD"
    assert len(body["offers"]) > 0

    # Cheapest first.
    prices = [o["total_amount"] for o in body["offers"]]
    assert prices == sorted(prices)

    offer = body["offers"][0]
    assert offer["slices"][0]["origin"] == "ACC"
    assert offer["slices"][-1]["destination"] == "DXB"
    assert offer["total_duration_minutes"] > 0
    assert "google_flights" in offer["booking_links"]
    assert offer["deep_link"]


def test_round_trip_has_two_slices_and_currency_conversion(client, future_dates):
    dep, ret = future_dates
    resp = client.post(
        "/api/search",
        json={
            "origin": "ACC",
            "destination": "LHR",
            "departure_date": dep,
            "return_date": ret,
            "passengers": {"adults": 2},
            "currency": "GHS",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["currency"] == "GHS"
    offer = body["offers"][0]
    assert len(offer["slices"]) == 2
    assert offer["total_currency"] == "GHS"
    assert offer["passenger_count"] == 2


def test_search_validates_dates(client):
    resp = client.post(
        "/api/search",
        json={"origin": "ACC", "destination": "DXB", "departure_date": "2000-01-01"},
    )
    assert resp.status_code == 422


def test_search_rejects_same_origin_destination(client, future_dates):
    dep, _ = future_dates
    resp = client.post(
        "/api/search",
        json={"origin": "ACC", "destination": "ACC", "departure_date": dep},
    )
    assert resp.status_code == 422


def test_flexible_dates_grid(client, future_dates):
    dep, ret = future_dates
    resp = client.post(
        "/api/search/flexible",
        json={
            "origin": "ACC",
            "destination": "DXB",
            "departure_date": dep,
            "return_date": ret,
            "flex_days": 3,
            "currency": "USD",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["cells"]) > 0
    assert body["cheapest"] is not None
    # Every cell reports the target currency.
    assert all(c["currency"] == "USD" for c in body["cells"])


def test_multi_city_search(client, future_dates):
    dep, _ = future_dates
    from datetime import date, timedelta

    mid = (date.today() + timedelta(days=34)).isoformat()
    resp = client.post(
        "/api/search/multi-city",
        json={
            "legs": [
                {"origin": "ACC", "destination": "IST", "departure_date": dep},
                {"origin": "IST", "destination": "CDG", "departure_date": mid},
            ],
            "currency": "EUR",
        },
    )
    assert resp.status_code == 200
    offer = resp.json()["offers"][0]
    assert len(offer["slices"]) == 2
