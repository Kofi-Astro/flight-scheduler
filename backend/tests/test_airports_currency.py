"""Airport autocomplete + currency endpoint tests."""

from __future__ import annotations


def test_airport_autocomplete_ranks_exact_iata_first(client):
    resp = client.get("/api/airports", params={"q": "acc"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["iata"] == "ACC"
    assert results[0]["city"] == "Accra"


def test_airport_autocomplete_by_city_name(client):
    resp = client.get("/api/airports", params={"q": "dubai"})
    codes = [r["iata"] for r in resp.json()["results"]]
    assert "DXB" in codes


def test_airport_lookup_404_for_unknown(client):
    assert client.get("/api/airports/ZZZ").status_code == 404


def test_currency_status_lists_required_currencies(client):
    body = client.get("/api/currency").json()
    for required in ("GHS", "USD", "EUR", "TRY", "CNY"):
        assert required in body["supported"]
    assert body["rates"]["USD"] == 1.0


def test_currency_convert_roundtrips(client):
    resp = client.post(
        "/api/currency/convert",
        json={"amount": 100, "from_currency": "USD", "to_currency": "USD"},
    )
    assert resp.json()["converted"] == 100
