"""Shortlist + client (CRM) + summary + alert flow tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def an_offer(client, future_dates):
    """A real offer object from a search, to feed into shortlist/summary."""
    dep, _ = future_dates
    resp = client.post(
        "/api/search",
        json={"origin": "ACC", "destination": "DXB", "departure_date": dep, "currency": "USD"},
    )
    return resp.json()["offers"][0]


def test_client_crud(client):
    created = client.post(
        "/api/clients", json={"name": "Kojo Mensah", "phone": "+233201112222"}
    ).json()
    cid = created["id"]

    assert client.get(f"/api/clients/{cid}").json()["name"] == "Kojo Mensah"

    client.patch(f"/api/clients/{cid}", json={"note": "prefers window seat"})
    assert client.get(f"/api/clients/{cid}").json()["note"] == "prefers window seat"

    # filter
    assert any(
        c["id"] == cid for c in client.get("/api/clients", params={"q": "kojo"}).json()
    )

    assert client.delete(f"/api/clients/{cid}").status_code == 200
    assert client.get(f"/api/clients/{cid}").status_code == 404


def test_shortlist_save_and_group_by_client(client, an_offer):
    cid = client.post("/api/clients", json={"name": "Ama"}).json()["id"]

    item = client.post(
        "/api/shortlist",
        json={"offer": an_offer, "client_id": cid, "note": "morning flight"},
    ).json()
    assert item["client_name"] == "Ama"
    assert item["saved_price"] == an_offer["total_amount"]
    assert item["search_summary"]  # auto-generated

    # shows up when filtering by client
    listed = client.get("/api/shortlist", params={"client_id": cid}).json()
    assert [i["id"] for i in listed] == [item["id"]]

    # client's shortlist_count reflects it
    assert client.get(f"/api/clients/{cid}").json()["shortlist_count"] == 1


def test_shortlist_refresh_price(client, an_offer):
    item = client.post("/api/shortlist", json={"offer": an_offer}).json()
    refreshed = client.post(f"/api/shortlist/{item['id']}/refresh-price").json()
    assert refreshed["latest_price"] is not None
    assert refreshed["latest_checked_at"] is not None


def test_shortlist_rejects_unknown_client(client, an_offer):
    resp = client.post(
        "/api/shortlist", json={"offer": an_offer, "client_id": 99999}
    )
    assert resp.status_code == 400


def test_summary_endpoint_builds_whatsapp_link(client, an_offer):
    resp = client.post(
        "/api/summary",
        json={"offer": an_offer, "client_name": "Ama", "client_phone": "+233241234567"},
    )
    body = resp.json()
    assert "Flight option" in body["text"]
    assert body["whatsapp_url"].startswith("https://wa.me/233241234567")


def test_alert_create_and_check(client, an_offer):
    item = client.post("/api/shortlist", json={"offer": an_offer}).json()
    # target far above current price => fires immediately on check
    alert = client.post(
        "/api/alerts",
        json={
            "shortlist_id": item["id"],
            "destination_address": "ops@example.com",
            "target_price": 10_000_000,
        },
    ).json()
    assert alert["baseline_price"] is not None

    result = client.post("/api/alerts/check").json()
    assert alert["id"] in result["triggered"]
