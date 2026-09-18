from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status

from database import DividendRepository, get_repository
from schemas import DividendCreate, DividendRead, DividendSummary, DividendUpdate


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_repository().initialize()
    yield


app = FastAPI(
    title="DivTrack API",
    description="API para registrar e acompanhar dividendos.",
    version="0.1.0",
    lifespan=lifespan,
)

Repository = Annotated[DividendRepository, Depends(get_repository)]


@app.get("/", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/dividends",
    response_model=DividendRead,
    status_code=status.HTTP_201_CREATED,
    tags=["dividends"],
)
def create_dividend(payload: DividendCreate, repository: Repository) -> DividendRead:
    return repository.create(payload)


@app.get("/dividends", response_model=list[DividendRead], tags=["dividends"])
def list_dividends(
    repository: Repository,
    ticker: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DividendRead]:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before date_to")
    return repository.list(ticker, date_from, date_to, limit, offset)


@app.get("/dividends/summary", response_model=DividendSummary, tags=["dividends"])
def summarize_dividends(
    repository: Repository,
    ticker: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> DividendSummary:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before date_to")
    return repository.summary(ticker, date_from, date_to)


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
