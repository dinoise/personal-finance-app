from finances.parsers.base import BankParser
from finances.parsers.registry import get_config


def get_parser(bank: str, account_type: str) -> BankParser:
    """Return the correct parser instance for the given bank and account type."""
    return get_config(bank, account_type).parser_class()
