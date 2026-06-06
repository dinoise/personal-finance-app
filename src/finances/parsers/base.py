from abc import ABC, abstractmethod
from pathlib import Path

from finances.schemas.parser_schemas import (
    AccountType,
    BankName,
    ParsedAccount,
    ParsedPocketMovement,
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

    def validate(self, text: str) -> bool:
        """Return True if this PDF's first-page text passes structural checks.

        The default implementation verifies the registry signature — already
        checked by detect_config(), so it always returns True here.
        Override in a subclass to add deeper checks (required sections,
        expected page count, etc.).
        """
        return True

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

    def parse_pocket_movements(
        self, transactions: list[ParsedTransaction]
    ) -> list[ParsedPocketMovement]:
        """Extract savings pocket movements from parsed transactions.

        Returns an empty list by default. Override in debit parsers that
        support named savings pockets (e.g. MercadoPago Apartados, Nu Cajitas).
        """
        return []
