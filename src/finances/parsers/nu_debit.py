from pathlib import Path

from finances.parsers.base import (
    AccountType,
    BankName,
    BankParser,
    ParsedAccount,
    ParsedStatement,
    ParsedTransaction,
)


class NuDebitParser(BankParser):
    @property
    def bank_name(self) -> BankName:
        return "nu"  # type: ignore[return-value]

    @property
    def account_type(self) -> AccountType:
        return "debit"  # type: ignore[return-value]

    def validate(self, path: Path) -> bool:
        raise NotImplementedError

    def parse_account(self, path: Path) -> ParsedAccount:
        raise NotImplementedError

    def parse_statement(self, path: Path) -> ParsedStatement:
        raise NotImplementedError

    def parse_transactions(self, path: Path) -> list[ParsedTransaction]:
        raise NotImplementedError
