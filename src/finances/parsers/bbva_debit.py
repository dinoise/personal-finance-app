from pathlib import Path

from finances.parsers.base import BankParser
from finances.schemas.parser_schemas import (
    AccountType,
    BankName,
    ParsedAccount,
    ParsedStatement,
    ParsedTransaction,
)


class BBVADebitParser(BankParser):
    @property
    def bank_name(self) -> BankName:
        return "bbva"

    @property
    def account_type(self) -> AccountType:
        return "debit"

    def validate(self, path: Path) -> bool:
        raise NotImplementedError

    def parse_account(self, path: Path) -> ParsedAccount:
        raise NotImplementedError

    def parse_statement(self, path: Path) -> ParsedStatement:
        raise NotImplementedError

    def parse_transactions(self, path: Path) -> list[ParsedTransaction]:
        raise NotImplementedError
