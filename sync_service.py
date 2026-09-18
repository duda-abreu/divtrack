import hashlib
import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from database import DividendRepository
from schemas import SyncResult


BRAPI_URL = "https://brapi.dev/api/v2/stocks/dividends"


class DividendSyncError(RuntimeError):
    pass


def _date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _fetch(tickers: list[str]) -> dict:
    params = urlencode(
        {
            "symbols": ",".join(tickers),
            "startDate": (date.today() - timedelta(days=370)).isoformat(),
            "sortOrder": "desc",
        }
    )
    headers = {"Accept": "application/json", "User-Agent": "DivTrack/0.2"}
    if token := os.getenv("BRAPI_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{BRAPI_URL}?{params}", headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise DividendSyncError(
                "BRAPI_TOKEN ausente ou sem acesso aos dividendos destes ativos"
            ) from exc
        raise DividendSyncError(f"brapi respondeu HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DividendSyncError("não foi possível consultar a brapi") from exc


def _events(payload: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in payload.get("results", []):
        symbol = str(item.get("symbol", "")).upper()
        data = item.get("data") or {}
        grouped[symbol] = data.get("cashDividends") or []
    for item in payload.get("dividends", []):
        symbol = str(item.get("symbol", "")).upper()
        grouped.setdefault(symbol, []).append(item)
    return grouped


def sync_dividends(repository: DividendRepository) -> SyncResult:
    holdings = repository.list_holdings()
    tickers = sorted({holding.ticker for holding in holdings})
    if not tickers:
        return SyncResult(tickers=0, imported=0, skipped=0)

    events: dict[str, list[dict]] = {}
    for start in range(0, len(tickers), 20):
        events.update(_events(_fetch(tickers[start : start + 20])))

    imported = 0
    skipped = 0
    for holding in holdings:
        for event in events.get(holding.ticker, []):
            ex_date = _date(event.get("lastDatePrior") or event.get("exDate"))
            try:
                rate = Decimal(str(event.get("rate")))
            except (InvalidOperation, TypeError):
                skipped += 1
                continue
            if ex_date is None or rate <= 0:
                skipped += 1
                continue
            payment_date = _date(event.get("paymentDate"))
            event_type = str(event.get("label") or "DIVIDENDO").upper()
            raw_key = "|".join(
                [
                    str(holding.portfolio_id),
                    holding.ticker,
                    ex_date.isoformat(),
                    payment_date.isoformat() if payment_date else "",
                    str(rate),
                    event_type,
                ]
            )
            external_key = hashlib.sha256(raw_key.encode()).hexdigest()
            if repository.import_dividend(
                holding,
                ex_date=ex_date,
                payment_date=payment_date,
                amount_per_share=rate,
                event_type=event_type,
                external_key=external_key,
            ):
                imported += 1
            else:
                skipped += 1
    return SyncResult(tickers=len(tickers), imported=imported, skipped=skipped)
