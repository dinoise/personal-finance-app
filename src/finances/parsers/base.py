from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

BankName = Literal["nu", "bbva", "banamex", "mercadopago"]
AccountType = Literal["credit", "debit"]
TransactionType = Literal["charge", "payment", "refund", "interest"]


@dataclass
class ParsedAccount:
    bank: BankName
    account_type: AccountType
    alias: str
    clabe: str | None = None
    account_number: str | None = None
    last4: str | None = None
    credit_limit: Decimal | None = None


@dataclass
class ParsedStatement:
    period_start: date
    period_end: date
    payment_due_date: date | None = None
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    minimum_payment: Decimal | None = None


@dataclass
class ParsedTransaction:
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


@dataclass
class StatementData:
    account: ParsedAccount
    statement: ParsedStatement
    transactions: list[ParsedTransaction] = field(default_factory=list)


class BankParser(ABC):
    @property
    @abstractmethod
    def bank_name(self) -> BankName: ...

    @property
    @abstractmethod
    def account_type(self) -> AccountType: ...

    @abstractmethod
    def validate(self, path: Path) -> bool:
        """Return True if this PDF belongs to this parser before processing."""

    @abstractmethod
    def parse_account(self, path: Path) -> ParsedAccount:
        """Extract account metadata from the PDF header."""

    @abstractmethod
    def parse_statement(self, path: Path) -> ParsedStatement:
        """Extract period summary: balances, dates, minimum payment."""

    @abstractmethod
    def parse_transactions(self, path: Path) -> list[ParsedTransaction]:
        """Extract all movements from the statement."""

    def parse(self, path: Path) -> StatementData:
        """Run the full parse pipeline and return a single result object."""
        return StatementData(
            account=self.parse_account(path),
            statement=self.parse_statement(path),
            transactions=self.parse_transactions(path),
        )
