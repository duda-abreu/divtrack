import os
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from schemas import CurrencyTotal, DividendCreate, DividendRead, DividendSummary, DividendUpdate


def _default_database_path() -> Path:
    return Path(os.getenv("DIVTRACK_DB_PATH", Path(__file__).with_name("divtrack.db")))


class DividendRepository:
    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dividends (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    ex_date TEXT NOT NULL,
                    payment_date TEXT,
                    amount_per_share TEXT NOT NULL,
                    shares TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
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
            ticker=row["ticker"],
            ex_date=row["ex_date"],
            payment_date=row["payment_date"],
            amount_per_share=amount,
            shares=shares,
            currency=row["currency"],
            total_amount=amount * shares,
            created_at=row["created_at"],
        )

    def create(self, dividend: DividendCreate) -> DividendRead:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO dividends
                    (ticker, ex_date, payment_date, amount_per_share, shares, currency)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    dividend.ticker,
                    dividend.ex_date.isoformat(),
                    dividend.payment_date.isoformat() if dividend.payment_date else None,
                    str(dividend.amount_per_share),
                    str(dividend.shares),
                    dividend.currency,
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
        ticker: str | None, date_from: date | None, date_to: date | None
    ) -> tuple[str, list[str]]:
        clauses: list[str] = []
        values: list[str] = []
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
    ) -> list[DividendRead]:
        where, values = self._filters(ticker, date_from, date_to)
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
            include={"ticker", "ex_date", "payment_date", "amount_per_share", "shares", "currency"}
        )
        data.update(changes.model_dump(exclude_unset=True))
        validated = DividendCreate.model_validate(data)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE dividends SET ticker = ?, ex_date = ?, payment_date = ?,
                    amount_per_share = ?, shares = ?, currency = ? WHERE id = ?
                """,
                (
                    validated.ticker,
                    validated.ex_date.isoformat(),
                    validated.payment_date.isoformat() if validated.payment_date else None,
                    str(validated.amount_per_share),
                    str(validated.shares),
                    validated.currency,
                    dividend_id,
                ),
            )
        return self.get(dividend_id)

    def delete(self, dividend_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM dividends WHERE id = ?", (dividend_id,))
        return cursor.rowcount > 0

    def summary(
        self, ticker: str | None, date_from: date | None, date_to: date | None
    ) -> DividendSummary:
        where, values = self._filters(ticker, date_from, date_to)
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


_repository: DividendRepository | None = None


def get_repository() -> DividendRepository:
    global _repository
    database_path = _default_database_path()
    if _repository is None or _repository.database_path != str(database_path):
        _repository = DividendRepository(database_path)
    return _repository
