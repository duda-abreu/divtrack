import asyncio
import os
from contextlib import asynccontextmanager, suppress
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import DividendRepository, get_repository
from schemas import (
    DividendCreate,
    DividendRead,
    DividendSummary,
    DividendUpdate,
    HoldingCreate,
    HoldingRead,
    HoldingUpdate,
    PortfolioCreate,
    PortfolioRead,
    PortfolioUpdate,
    SyncResult,
)
from sync_service import DividendSyncError, sync_dividends


BASE_DIR = Path(__file__).resolve().parent


async def auto_sync(stop: asyncio.Event) -> None:
    interval = max(int(os.getenv("DIVTRACK_SYNC_INTERVAL", "21600")), 300)
    while not stop.is_set():
        try:
            await asyncio.to_thread(sync_dividends, get_repository())
        except DividendSyncError:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            continue


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_repository().initialize()
    stop = asyncio.Event()
    task = asyncio.create_task(auto_sync(stop))
    yield
    stop.set()
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(
    title="DivTrack API",
    description="API para registrar e acompanhar dividendos.",
    version="0.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

Repository = Annotated[DividendRepository, Depends(get_repository)]


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/dividends",
    response_model=DividendRead,
    status_code=status.HTTP_201_CREATED,
    tags=["dividends"],
)
def create_dividend(payload: DividendCreate, repository: Repository) -> DividendRead:
    if payload.portfolio_id and repository.get_portfolio(payload.portfolio_id) is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return repository.create(payload)


@app.get("/dividends", response_model=list[DividendRead], tags=["dividends"])
def list_dividends(
    repository: Repository,
    ticker: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    portfolio_id: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DividendRead]:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before date_to")
    return repository.list(ticker, date_from, date_to, limit, offset, portfolio_id)


@app.get("/dividends/summary", response_model=DividendSummary, tags=["dividends"])
def summarize_dividends(
    repository: Repository,
    ticker: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    portfolio_id: Annotated[int | None, Query(gt=0)] = None,
) -> DividendSummary:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before date_to")
    return repository.summary(ticker, date_from, date_to, portfolio_id)


@app.get("/dividends/{dividend_id}", response_model=DividendRead, tags=["dividends"])
def get_dividend(dividend_id: int, repository: Repository) -> DividendRead:
    dividend = repository.get(dividend_id)
    if dividend is None:
        raise HTTPException(status_code=404, detail="Dividend not found")
    return dividend


@app.patch("/dividends/{dividend_id}", response_model=DividendRead, tags=["dividends"])
def update_dividend(
    dividend_id: int, payload: DividendUpdate, repository: Repository
) -> DividendRead:
    if (
        payload.portfolio_id is not None
        and repository.get_portfolio(payload.portfolio_id) is None
    ):
        raise HTTPException(status_code=404, detail="Portfolio not found")
    dividend = repository.update(dividend_id, payload)
    if dividend is None:
        raise HTTPException(status_code=404, detail="Dividend not found")
    return dividend


@app.delete(
    "/dividends/{dividend_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["dividends"],
)
def delete_dividend(dividend_id: int, repository: Repository) -> Response:
    if not repository.delete(dividend_id):
        raise HTTPException(status_code=404, detail="Dividend not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/portfolios",
    response_model=PortfolioRead,
    status_code=status.HTTP_201_CREATED,
    tags=["portfolios"],
)
def create_portfolio(payload: PortfolioCreate, repository: Repository) -> PortfolioRead:
    return repository.create_portfolio(payload)


@app.get("/portfolios", response_model=list[PortfolioRead], tags=["portfolios"])
def list_portfolios(repository: Repository) -> list[PortfolioRead]:
    return repository.list_portfolios()


@app.get("/portfolios/{portfolio_id}", response_model=PortfolioRead, tags=["portfolios"])
def get_portfolio(portfolio_id: int, repository: Repository) -> PortfolioRead:
    portfolio = repository.get_portfolio(portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


@app.patch("/portfolios/{portfolio_id}", response_model=PortfolioRead, tags=["portfolios"])
def update_portfolio(
    portfolio_id: int, payload: PortfolioUpdate, repository: Repository
) -> PortfolioRead:
    portfolio = repository.update_portfolio(portfolio_id, payload)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


@app.delete(
    "/portfolios/{portfolio_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["portfolios"],
)
def delete_portfolio(portfolio_id: int, repository: Repository) -> Response:
    if not repository.delete_portfolio(portfolio_id):
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/holdings",
    response_model=HoldingRead,
    status_code=status.HTTP_201_CREATED,
    tags=["holdings"],
)
def create_holding(payload: HoldingCreate, repository: Repository) -> HoldingRead:
    if repository.get_portfolio(payload.portfolio_id) is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return repository.create_holding(payload)


@app.get("/holdings", response_model=list[HoldingRead], tags=["holdings"])
def list_holdings(
    repository: Repository,
    portfolio_id: Annotated[int | None, Query(gt=0)] = None,
) -> list[HoldingRead]:
    return repository.list_holdings(portfolio_id)


@app.patch("/holdings/{holding_id}", response_model=HoldingRead, tags=["holdings"])
def update_holding(
    holding_id: int, payload: HoldingUpdate, repository: Repository
) -> HoldingRead:
    holding = repository.update_holding(holding_id, payload)
    if holding is None:
        raise HTTPException(status_code=404, detail="Holding not found")
    return holding


@app.delete(
    "/holdings/{holding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["holdings"],
)
def delete_holding(holding_id: int, repository: Repository) -> Response:
    if not repository.delete_holding(holding_id):
        raise HTTPException(status_code=404, detail="Holding not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/sync/dividends", response_model=SyncResult, tags=["sync"])
async def run_dividend_sync(repository: Repository) -> SyncResult:
    try:
        return await asyncio.to_thread(sync_dividends, repository)
    except DividendSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
