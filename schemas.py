from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DividendBase(BaseModel):
    ticker: str = Field(min_length=1, max_length=15)
    ex_date: date
    payment_date: date | None = None
    amount_per_share: Decimal = Field(gt=0, decimal_places=8)
    shares: Decimal = Field(gt=0, decimal_places=8)
    currency: str = Field(default="BRL", pattern=r"^[A-Za-z]{3}$")

    @field_validator("ticker", "currency")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_dates(self):
        if self.payment_date and self.payment_date < self.ex_date:
            raise ValueError("payment_date must be on or after ex_date")
        return self


class DividendCreate(DividendBase):
    pass


class DividendUpdate(BaseModel):
    ticker: str | None = Field(default=None, min_length=1, max_length=15)
    ex_date: date | None = None
    payment_date: date | None = None
    amount_per_share: Decimal | None = Field(default=None, gt=0, decimal_places=8)
    shares: Decimal | None = Field(default=None, gt=0, decimal_places=8)
    currency: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")

    @field_validator("ticker", "currency")
    @classmethod
    def normalize_uppercase(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class DividendRead(DividendBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    total_amount: Decimal
    created_at: datetime


class CurrencyTotal(BaseModel):
    currency: str
    amount: Decimal


class DividendSummary(BaseModel):
    records: int
    totals: list[CurrencyTotal]
