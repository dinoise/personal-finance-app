from pathlib import Path

import pdfplumber

from finances.parsers.registry import detect_config


def detect_bank_and_type(path: Path) -> tuple[str, str]:
    """Identify bank and account type by matching text signatures on the first PDF page."""
    with pdfplumber.open(path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""

    config = detect_config(first_page_text)
    return config.bank_key, config.account_type
