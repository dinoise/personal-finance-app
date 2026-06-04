from pathlib import Path

import pdfplumber

from finances.parsers.registry import detect_config
from finances.schemas.parser_schemas import AccountType, BankName


def detect_bank_and_type(path: Path) -> tuple[BankName, AccountType]:
    """Identify bank and account type by matching text signatures on the first PDF page."""
    with pdfplumber.open(path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""

    config = detect_config(first_page_text)
    return config.bank_key, config.account_type  # type: ignore[return-value]
