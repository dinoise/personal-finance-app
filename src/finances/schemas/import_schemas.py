from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from finances.schemas.parser_schemas import AccountType, BankName, StatementData

if TYPE_CHECKING:
    from finances.parsers.registry import BankConfig


@dataclass
class ParsedPdfData:
    """Cached parse result for a single PDF. Lives in st.session_state between renders."""

    bank: BankName
    account_type: AccountType
    file_hash: str
    data: StatementData
    config: BankConfig

    @property
    def bank_label(self) -> str:
        return self.config.label

    @property
    def needs_clabe(self) -> bool:
        return self.config.needs_clabe


@dataclass
class ImportResult:
    statement_id: int
    account_alias: str
    bank_label: str
    transactions_inserted: int
    pocket_movements_inserted: int
    pdf_stored_path: Path


@dataclass
class ImportError:
    reason: str


@dataclass
class TransactionRow:
    date: date
    description: str
    amount: Decimal
    transaction_type: str
    bank_reference: str | None
