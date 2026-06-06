from abc import ABC, abstractmethod
from decimal import Decimal
from pathlib import Path
from typing import Any

import pdfplumber

from finances.schemas.parser_schemas import (
    AccountType,
    BankName,
    ParsedAccount,
    ParsedPocketMovement,
    ParsedStatement,
    ParsedTransaction,
    StatementData,
    TransactionType,
)


class BankParser(ABC):
    # ── Identity ─────────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def bank_name(self) -> BankName: ...

    @property
    @abstractmethod
    def account_type(self) -> AccountType: ...

    # ── Abstract (must implement) ─────────────────────────────────────────────

    @abstractmethod
    def _account_from_text(self, text: str) -> ParsedAccount:
        """Build a ParsedAccount from the first-page text."""

    @abstractmethod
    def _statement_from_text(self, text: str, filename: str) -> ParsedStatement:
        """Build a ParsedStatement from the first-page text."""

    @abstractmethod
    def _parse_page(self, page: Any) -> list[ParsedTransaction]:
        """Extract transactions from a single pdfplumber page object."""

    # ── Hooks (override when needed) ─────────────────────────────────────────

    def validate(self, text: str) -> bool:
        """Return True if this PDF's first-page text passes structural checks.

        The default implementation verifies the registry signature — already
        checked by detect_config(), so it always returns True here.
        Override in a subclass to add deeper checks (required sections,
        expected page count, etc.).
        """
        return True

    def _should_stop(self, page: Any) -> bool:
        """Return True to stop page iteration before processing this page.

        Default: never stop. Override when a section boundary marks the end
        of relevant content (e.g. Nu Débito cajitas mirror section).
        """
        return False

    def parse_pocket_movements(
        self, transactions: list[ParsedTransaction]
    ) -> list[ParsedPocketMovement]:
        """Extract savings pocket movements from parsed transactions.

        Returns an empty list by default. Override in debit parsers that
        support named savings pockets (e.g. MercadoPago Apartados, Nu Cajitas).
        """
        return []

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _infer_type(amount: Decimal) -> TransactionType:
        return "payment" if amount > 0 else "charge"

    # ── Public API ────────────────────────────────────────────────────────────

    def parse_account(self, path: Path) -> ParsedAccount:
        with pdfplumber.open(path) as pdf:
            text = pdf.pages[0].extract_text() or ""
        return self._account_from_text(text)

    def parse_statement(self, path: Path) -> ParsedStatement:
        with pdfplumber.open(path) as pdf:
            text = pdf.pages[0].extract_text() or ""
        return self._statement_from_text(text, path.name)

    def parse_transactions(self, path: Path) -> list[ParsedTransaction]:
        transactions: list[ParsedTransaction] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                if self._should_stop(page):
                    break
                transactions.extend(self._parse_page(page))
        return transactions

    def parse(self, path: Path) -> StatementData:
        with pdfplumber.open(path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""
            transactions: list[ParsedTransaction] = []
            for page in pdf.pages:
                if self._should_stop(page):
                    break
                transactions.extend(self._parse_page(page))
        return StatementData(
            account=self._account_from_text(first_page_text),
            statement=self._statement_from_text(first_page_text, path.name),
            transactions=transactions,
            pocket_movements=self.parse_pocket_movements(transactions),
        )
