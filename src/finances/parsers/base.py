from abc import ABC, abstractmethod
from pathlib import Path

from finances.schemas.parser_schemas import (
    AccountType,
    BankName,
    ParsedAccount,
    ParsedStatement,
    ParsedTransaction,
    StatementData,
)


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
