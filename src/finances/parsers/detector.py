from pathlib import Path

import pdfplumber

from finances.parsers.base import AccountType, BankName

# (signature, bank, account_type) — order matters: more specific signatures first
_SIGNATURES: list[tuple[str, BankName, AccountType]] = [
    ("Tarjeta de Credito Nu", "nu", "credit"),
    ("Cuenta Nu:", "nu", "debit"),
    ("Libreton Basico", "bbva", "debit"),
    ("JOY BANAMEX", "banamex", "credit"),
    ("ESTADO DE SALDOS", "mercadopago", "debit"),
]


def detect_bank_and_type(path: Path) -> tuple[BankName, AccountType]:
    """Identify bank and account type by matching text signatures on the first PDF page."""
    with pdfplumber.open(path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""

    for signature, bank, account_type in _SIGNATURES:
        if signature in first_page_text:
            return bank, account_type

    raise ValueError(f"Unrecognized PDF format: {path.name}")
