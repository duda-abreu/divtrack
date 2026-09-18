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
    assert client.get("/health").json() == {"status": "ok"}
    assert "DivTrack" in client.get("/").text


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


def test_portfolio_crud_and_dividend_filter(client: TestClient):
    created = client.post(
        "/portfolios", json={"name": "Longo prazo", "description": "Ações BR"}
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    dividend = client.post(
        "/dividends", json=sample_dividend(portfolio_id=portfolio_id)
    )
    assert dividend.status_code == 201
    assert dividend.json()["portfolio_id"] == portfolio_id

    filtered = client.get(f"/dividends?portfolio_id={portfolio_id}")
    assert len(filtered.json()) == 1
    assert client.get(f"/dividends/summary?portfolio_id={portfolio_id}").json()[
        "records"
    ] == 1

    updated = client.patch(
        f"/portfolios/{portfolio_id}", json={"name": "Aposentadoria"}
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Aposentadoria"

    assert client.delete(f"/portfolios/{portfolio_id}").status_code == 204
    assert client.get(f"/dividends/{dividend.json()['id']}").json()["portfolio_id"] is None


def test_rejects_unknown_portfolio(client: TestClient):
    response = client.post("/dividends", json=sample_dividend(portfolio_id=999))
    assert response.status_code == 404
    assert response.json() == {"detail": "Portfolio not found"}


def test_holding_crud(client: TestClient):
    portfolio_id = client.post("/portfolios", json={"name": "Principal"}).json()["id"]
    created = client.post(
        "/holdings",
        json={
            "portfolio_id": portfolio_id,
            "ticker": "petr4",
            "shares": "75",
            "average_price": "34.50",
            "acquired_on": "2025-01-10",
        },
    )
    assert created.status_code == 201
    holding = created.json()
    assert holding["ticker"] == "PETR4"

    updated = client.patch(f"/holdings/{holding['id']}", json={"shares": "80"})
    assert updated.status_code == 200
    assert updated.json()["shares"] == "80"

    assert len(client.get(f"/holdings?portfolio_id={portfolio_id}").json()) == 1
    assert client.delete(f"/holdings/{holding['id']}").status_code == 204


def test_sync_imports_once(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    portfolio_id = client.post("/portfolios", json={"name": "Principal"}).json()["id"]
    client.post(
        "/holdings",
        json={"portfolio_id": portfolio_id, "ticker": "PETR4", "shares": "100"},
    )
    payload = {
        "results": [
            {
                "symbol": "PETR4",
                "data": {
                    "cashDividends": [
                        {
                            "label": "DIVIDENDO",
                            "rate": 1.25,
                            "lastDatePrior": "2026-08-01T00:00:00Z",
                            "paymentDate": "2026-09-01T00:00:00Z",
                        }
                    ]
                },
            }
        ]
    }
    monkeypatch.setattr("sync_service._fetch", lambda _: payload)

    first = client.post("/sync/dividends")
    second = client.post("/sync/dividends")
    assert first.json()["imported"] == 1
    assert second.json()["imported"] == 0
    imported = client.get("/dividends").json()[0]
    assert imported["source"] == "brapi"
    assert imported["total_amount"] == "125.00"
