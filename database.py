from __future__ import annotations

import os
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from schemas import (
    CurrencyTotal,
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
)


def _default_database_path() -> Path:
    return Path(os.getenv("DIVTRACK_DB_PATH", Path(__file__).with_name("divtrack.db")))


class DividendRepository:
    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS portfolios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS holdings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                    ticker TEXT NOT NULL,
                    shares TEXT NOT NULL,
                    average_price TEXT,
                    acquired_on TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (portfolio_id, ticker)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dividends (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE SET NULL,
                    ticker TEXT NOT NULL,
                    ex_date TEXT NOT NULL,
                    payment_date TEXT,
                    amount_per_share TEXT NOT NULL,
                    shares TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    event_type TEXT NOT NULL DEFAULT 'DIVIDENDO',
                    source TEXT NOT NULL DEFAULT 'manual',
                    external_key TEXT UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(dividends)")
            }
            if "portfolio_id" not in columns:
                connection.execute(
                    "ALTER TABLE dividends ADD COLUMN portfolio_id INTEGER "
                    "REFERENCES portfolios(id) ON DELETE SET NULL"
                )
            migrations = {
                "event_type": "TEXT NOT NULL DEFAULT 'DIVIDENDO'",
                "source": "TEXT NOT NULL DEFAULT 'manual'",
                "external_key": "TEXT",
            }
            for column, definition in migrations.items():
                if column not in columns:
                    connection.execute(
                        f"ALTER TABLE dividends ADD COLUMN {column} {definition}"
                    )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_dividends_external_key "
                "ON dividends (external_key) WHERE external_key IS NOT NULL"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_dividends_ticker_date "
                "ON dividends (ticker, ex_date)"
            )

    @staticmethod
    def _to_model(row: sqlite3.Row) -> DividendRead:
        amount = Decimal(row["amount_per_share"])
        shares = Decimal(row["shares"])
        return DividendRead(
            id=row["id"],
            portfolio_id=row["portfolio_id"],
            ticker=row["ticker"],
            ex_date=row["ex_date"],
            payment_date=row["payment_date"],
            amount_per_share=amount,
            shares=shares,
            currency=row["currency"],
            event_type=row["event_type"],
            source=row["source"],
            total_amount=amount * shares,
            created_at=row["created_at"],
        )

    def create(self, dividend: DividendCreate) -> DividendRead:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO dividends
                    (portfolio_id, ticker, ex_date, payment_date, amount_per_share, shares,
                     currency, event_type, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dividend.portfolio_id,
                    dividend.ticker,
                    dividend.ex_date.isoformat(),
                    dividend.payment_date.isoformat() if dividend.payment_date else None,
                    str(dividend.amount_per_share),
                    str(dividend.shares),
                    dividend.currency,
                    dividend.event_type,
                    dividend.source,
                ),
            )
            row = connection.execute(
                "SELECT * FROM dividends WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return self._to_model(row)

    def get(self, dividend_id: int) -> DividendRead | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM dividends WHERE id = ?", (dividend_id,)
            ).fetchone()
        return self._to_model(row) if row else None

    @staticmethod
    def _filters(
        ticker: str | None,
        date_from: date | None,
        date_to: date | None,
        portfolio_id: int | None = None,
    ) -> tuple[str, list[str | int]]:
        clauses: list[str] = []
        values: list[str | int] = []
        if portfolio_id:
            clauses.append("portfolio_id = ?")
            values.append(portfolio_id)
        if ticker:
            clauses.append("ticker = ?")
            values.append(ticker.strip().upper())
        if date_from:
            clauses.append("ex_date >= ?")
            values.append(date_from.isoformat())
        if date_to:
            clauses.append("ex_date <= ?")
            values.append(date_to.isoformat())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return where, values

    def list(
        self,
        ticker: str | None,
        date_from: date | None,
        date_to: date | None,
        limit: int,
        offset: int,
        portfolio_id: int | None = None,
    ) -> list[DividendRead]:
        where, values = self._filters(ticker, date_from, date_to, portfolio_id)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM dividends{where} ORDER BY ex_date DESC, id DESC LIMIT ? OFFSET ?",
                [*values, limit, offset],
            ).fetchall()
        return [self._to_model(row) for row in rows]

    def update(self, dividend_id: int, changes: DividendUpdate) -> DividendRead | None:
        current = self.get(dividend_id)
        if current is None:
            return None
        data = current.model_dump(
            include={
                "portfolio_id",
                "ticker",
                "ex_date",
                "payment_date",
                "amount_per_share",
                "shares",
                "currency",
                "event_type",
                "source",
            }
        )
        data.update(changes.model_dump(exclude_unset=True))
        validated = DividendCreate.model_validate(data)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE dividends SET portfolio_id = ?, ticker = ?, ex_date = ?, payment_date = ?,
                    amount_per_share = ?, shares = ?, currency = ?, event_type = ?, source = ?
                WHERE id = ?
                """,
                (
                    validated.portfolio_id,
                    validated.ticker,
                    validated.ex_date.isoformat(),
                    validated.payment_date.isoformat() if validated.payment_date else None,
                    str(validated.amount_per_share),
                    str(validated.shares),
                    validated.currency,
                    validated.event_type,
                    validated.source,
                    dividend_id,
                ),
            )
        return self.get(dividend_id)

    def delete(self, dividend_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM dividends WHERE id = ?", (dividend_id,))
        return cursor.rowcount > 0

    def summary(
        self,
        ticker: str | None,
        date_from: date | None,
        date_to: date | None,
        portfolio_id: int | None = None,
    ) -> DividendSummary:
        where, values = self._filters(ticker, date_from, date_to, portfolio_id)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT amount_per_share, shares, currency FROM dividends{where}", values
            ).fetchall()
        totals: dict[str, Decimal] = {}
        for row in rows:
            totals.setdefault(row["currency"], Decimal("0"))
            totals[row["currency"]] += Decimal(row["amount_per_share"]) * Decimal(row["shares"])
        return DividendSummary(
            records=len(rows),
            totals=[CurrencyTotal(currency=currency, amount=amount) for currency, amount in sorted(totals.items())],
        )

    @staticmethod
    def _portfolio_model(row: sqlite3.Row) -> PortfolioRead:
        return PortfolioRead(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
        )

    def create_portfolio(self, portfolio: PortfolioCreate) -> PortfolioRead:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO portfolios (name, description) VALUES (?, ?)",
                (portfolio.name, portfolio.description),
            )
            row = connection.execute(
                "SELECT * FROM portfolios WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return self._portfolio_model(row)

    def list_portfolios(self) -> list[PortfolioRead]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM portfolios ORDER BY name, id"
            ).fetchall()
        return [self._portfolio_model(row) for row in rows]

    def get_portfolio(self, portfolio_id: int) -> PortfolioRead | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM portfolios WHERE id = ?", (portfolio_id,)
            ).fetchone()
        return self._portfolio_model(row) if row else None

    def update_portfolio(
        self, portfolio_id: int, changes: PortfolioUpdate
    ) -> PortfolioRead | None:
        current = self.get_portfolio(portfolio_id)
        if current is None:
            return None
        data = current.model_dump(include={"name", "description"})
        data.update(changes.model_dump(exclude_unset=True))
        validated = PortfolioCreate.model_validate(data)
        with self._connect() as connection:
            connection.execute(
                "UPDATE portfolios SET name = ?, description = ? WHERE id = ?",
                (validated.name, validated.description, portfolio_id),
            )
        return self.get_portfolio(portfolio_id)

    def delete_portfolio(self, portfolio_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM portfolios WHERE id = ?", (portfolio_id,)
            )
        return cursor.rowcount > 0

    @staticmethod
    def _holding_model(row: sqlite3.Row) -> HoldingRead:
        return HoldingRead(
            id=row["id"],
            portfolio_id=row["portfolio_id"],
            ticker=row["ticker"],
            shares=row["shares"],
            average_price=row["average_price"],
            acquired_on=row["acquired_on"],
            created_at=row["created_at"],
        )

    def create_holding(self, holding: HoldingCreate) -> HoldingRead:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO holdings
                    (portfolio_id, ticker, shares, average_price, acquired_on)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (portfolio_id, ticker) DO UPDATE SET
                    shares = excluded.shares,
                    average_price = excluded.average_price,
                    acquired_on = excluded.acquired_on
                """,
                (
                    holding.portfolio_id,
                    holding.ticker,
                    str(holding.shares),
                    str(holding.average_price) if holding.average_price is not None else None,
                    holding.acquired_on.isoformat() if holding.acquired_on else None,
                ),
            )
            row = connection.execute(
                "SELECT * FROM holdings WHERE portfolio_id = ? AND ticker = ?",
                (holding.portfolio_id, holding.ticker),
            ).fetchone()
        return self._holding_model(row)

    def list_holdings(self, portfolio_id: int | None = None) -> list[HoldingRead]:
        query = "SELECT * FROM holdings"
        values: tuple[int, ...] = ()
        if portfolio_id is not None:
            query += " WHERE portfolio_id = ?"
            values = (portfolio_id,)
        query += " ORDER BY ticker, id"
        with self._connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._holding_model(row) for row in rows]

    def get_holding(self, holding_id: int) -> HoldingRead | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM holdings WHERE id = ?", (holding_id,)
            ).fetchone()
        return self._holding_model(row) if row else None

    def update_holding(
        self, holding_id: int, changes: HoldingUpdate
    ) -> HoldingRead | None:
        current = self.get_holding(holding_id)
        if current is None:
            return None
        data = current.model_dump(
            include={"portfolio_id", "ticker", "shares", "average_price", "acquired_on"}
        )
        data.update(changes.model_dump(exclude_unset=True))
        validated = HoldingCreate.model_validate(data)
        with self._connect() as connection:
            connection.execute(
                "UPDATE holdings SET shares = ?, average_price = ?, acquired_on = ? WHERE id = ?",
                (
                    str(validated.shares),
                    str(validated.average_price) if validated.average_price is not None else None,
                    validated.acquired_on.isoformat() if validated.acquired_on else None,
                    holding_id,
                ),
            )
        return self.get_holding(holding_id)

    def delete_holding(self, holding_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM holdings WHERE id = ?", (holding_id,))
        return cursor.rowcount > 0

    def import_dividend(
        self,
        holding: HoldingRead,
        *,
        ex_date: date,
        payment_date: date | None,
        amount_per_share: Decimal,
        event_type: str,
        external_key: str,
    ) -> bool:
        if holding.acquired_on and ex_date < holding.acquired_on:
            return False
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO dividends
                    (portfolio_id, ticker, ex_date, payment_date, amount_per_share,
                     shares, currency, event_type, source, external_key)
                VALUES (?, ?, ?, ?, ?, ?, 'BRL', ?, 'brapi', ?)
                """,
                (
                    holding.portfolio_id,
                    holding.ticker,
                    ex_date.isoformat(),
                    payment_date.isoformat() if payment_date else None,
                    str(amount_per_share),
                    str(holding.shares),
                    event_type,
                    external_key,
                ),
            )
        return cursor.rowcount > 0


_repository: DividendRepository | None = None


def get_repository() -> DividendRepository:
    global _repository
    database_path = _default_database_path()
    if _repository is None or _repository.database_path != str(database_path):
        _repository = DividendRepository(database_path)
    return _repository
