from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import database
from main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DIVTRACK_DB_PATH", str(tmp_path / "test.db"))
    database._repository = None
    with TestClient(app) as test_client:
        yield test_client


def sample_dividend(**overrides):
    payload = {
        "ticker": "petr4",
        "ex_date": "2026-05-10",
        "payment_date": "2026-05-20",
        "amount_per_share": "1.25",
        "shares": "100",
        "currency": "brl",
    }
    payload.update(overrides)
    return payload


def test_health(client: TestClient):
    assert client.get("/").json() == {"status": "ok"}


def test_dividend_crud(client: TestClient):
    created = client.post("/dividends", json=sample_dividend())
    assert created.status_code == 201
    dividend = created.json()
    assert dividend["ticker"] == "PETR4"
    assert dividend["currency"] == "BRL"
    assert dividend["total_amount"] == "125.00"

    dividend_id = dividend["id"]
    assert client.get(f"/dividends/{dividend_id}").status_code == 200

    updated = client.patch(f"/dividends/{dividend_id}", json={"shares": "120"})
    assert updated.status_code == 200
    assert updated.json()["total_amount"] == "150.00"

    deleted = client.delete(f"/dividends/{dividend_id}")
    assert deleted.status_code == 204
    assert client.get(f"/dividends/{dividend_id}").status_code == 404


def test_filters_and_summary(client: TestClient):
    client.post("/dividends", json=sample_dividend())
    client.post(
        "/dividends",
        json=sample_dividend(ticker="VALE3", amount_per_share="2", currency="USD"),
    )

    filtered = client.get("/dividends?ticker=petr4")
    assert [item["ticker"] for item in filtered.json()] == ["PETR4"]

    summary = client.get("/dividends/summary").json()
    assert summary == {
        "records": 2,
        "totals": [
            {"currency": "BRL", "amount": "125.00"},
            {"currency": "USD", "amount": "200"},
        ],
    }


def test_rejects_invalid_payment_date(client: TestClient):
    response = client.post(
        "/dividends", json=sample_dividend(payment_date="2026-05-01")
    )
    assert response.status_code == 422
