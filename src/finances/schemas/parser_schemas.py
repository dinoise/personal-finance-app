from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

# Valid values defined in parsers/registry.py — add a BankConfig there to support a new bank.
BankName = str
AccountType = Literal["credit", "debit"]
TransactionType = Literal["charge", "payment", "refund", "interest"]
PocketMovementType = Literal["deposit", "withdrawal", "interest"]


class ParsedAccount(BaseModel):
    model_config = ConfigDict(frozen=True)

    bank: BankName
    account_type: AccountType
    alias: str
    clabe: str | None = None
    account_number: str | None = None
    last4: str | None = None
    credit_limit: Decimal | None = None


class ParsedStatement(BaseModel):
    model_config = ConfigDict(frozen=True)

    period_start: date
    period_end: date
    payment_due_date: date | None = None
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    minimum_payment: Decimal | None = None

    @model_validator(mode="after")
    def period_end_after_start(self) -> "ParsedStatement":
        if self.period_end < self.period_start:
            raise ValueError(
                f"period_end ({self.period_end}) must be >= period_start ({self.period_start})"
            )
        return self


class ParsedTransaction(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    description: str
    amount: Decimal
    transaction_type: TransactionType
    bank_reference: str | None = None
    spei_tracking_key: str | None = None
    spei_reference: str | None = None
    counterpart_clabe: str | None = None
    counterpart_name: str | None = None
    currency: str = "MXN"


class ParsedPocketMovement(BaseModel):
    model_config = ConfigDict(frozen=True)

    pocket_name: str
    movement_type: PocketMovementType
    amount: Decimal
    transaction_index: int


class StatementData(BaseModel):
    model_config = ConfigDict(frozen=True)

    account: ParsedAccount
    statement: ParsedStatement
    transactions: list[ParsedTransaction] = []
    pocket_movements: list[ParsedPocketMovement] = []
