from finances.parsers.base import BankParser
from finances.schemas.parser_schemas import (
    AccountType,
    BankName,
    ParsedAccount,
    ParsedStatement,
    ParsedTransaction,
)


class NuCreditParser(BankParser):
    @property
    def bank_name(self) -> BankName:
        return "nu"

    @property
    def account_type(self) -> AccountType:
        return "credit"

    def validate(self, text: str) -> bool:
        raise NotImplementedError

    def _account_from_text(self, text: str) -> ParsedAccount:
        raise NotImplementedError

    def _statement_from_text(self, text: str, filename: str) -> ParsedStatement:
        raise NotImplementedError

    def _parse_page(self, page: object) -> list[ParsedTransaction]:
        raise NotImplementedError
