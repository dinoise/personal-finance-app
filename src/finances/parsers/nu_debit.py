import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import ClassVar

import pdfplumber

from finances.parsers.base import BankParser
from finances.parsers.utils import MONTHS, parse_decimal
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

_MONTH_ABBR: dict[str, int] = {
    "ENE": 1,
    "FEB": 2,
    "MAR": 3,
    "ABR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DIC": 12,
}


class NuDebitParser(BankParser):
    # Header patterns (page 1)
    _ACCOUNT_RE: ClassVar = re.compile(r"Cuenta Nu:\s*(\d+)")
    _CLABE_RE: ClassVar = re.compile(r"CLABE:\s*(\d{18})")
    _PERIOD_RE: ClassVar = re.compile(
        r"Periodo: del (\d{1,2}) al (\d{1,2}) (\w+) (\d{4})", re.IGNORECASE
    )
    _BALANCE_RE: ClassVar = re.compile(
        r"Saldo inicial \$([\d,]+\.\d{2}).*?"
        r"Saldo al generar este estado de cuenta \$([\d,]+\.\d{2})",
        re.DOTALL,
    )

    # Marks the start of the cajitas mirror section — stop parsing here
    _CAJITAS_SECTION: ClassVar = "Detalle de movimientos de tus cajitas"

    # Transaction line: "DD MMM YYYY  <description>  +/-$amount"
    _TXN_RE: ClassVar = re.compile(
        r"^(\d{2}\s+[A-ZÁÉÍÓÚÜÑ]{3}\s+\d{4})\s+(.+?)\s+([+-]\$[\d,]+\.\d{2})\s*$",
        re.MULTILINE,
    )

    # Split-date format: "DD MMM\n<description> +/-$amount\nYYYY"
    # pdfplumber breaks the date across lines on dense pages
    _SPLIT_DATE_RE: ClassVar = re.compile(
        r"^(\d{2}\s+[A-ZÁÉÍÓÚÜÑ]{3})\n(.+?)\s+([+-]\$[\d,]+\.\d{2})\n(\d{4})$",
        re.MULTILINE,
    )

    # Inverted format: description wraps above the date line, concept below
    # "desc_part1\nDD MMM YYYY +/-$amount\nconcept_part2"
    _INVERTED_DATE_RE: ClassVar = re.compile(
        r"^([^\n]+)\n(\d{2}\s+[A-ZÁÉÍÓÚÜÑ]{3}\s+\d{4})\s+([+-]\$[\d,]+\.\d{2})\n([^\n]+)$",
        re.MULTILINE,
    )

    # Cajitas (savings pockets) movement patterns
    _POCKET_DEPOSIT_RE: ClassVar = re.compile(r"^Depósito en Cajita:\s+(.+)$")
    _POCKET_WITHDRAWAL_RE: ClassVar = re.compile(r"^Retiro de Cajita:\s+(.+)$")

    # SPEI detail patterns (text block after each transaction line)
    # Matches 16-digit card numbers (debit-card/credit-card) or 18-digit CLABEs
    _DETAIL_CLABE_RE: ClassVar = re.compile(r"(\d{16,18})\s+(?:clabe|debit-card|credit-card)")
    _TRACKING_RE: ClassVar = re.compile(r"Clave de rastreo\s+(\S+?)(?:,|\s)")
    _REFERENCE_RE: ClassVar = re.compile(r"Clave de referencia\s+(\S+)")

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def bank_name(self) -> BankName:
        return "nu"

    @property
    def account_type(self) -> AccountType:
        return "debit"

    # ── Public API (ABC) ────────────────────────────────────────────────────

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
                text = page.extract_text() or ""
                if self._CAJITAS_SECTION in text:
                    break
                transactions.extend(self._parse_page(text))
        return transactions

    def parse(self, path: Path) -> StatementData:
        with pdfplumber.open(path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""
            transactions: list[ParsedTransaction] = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                if self._CAJITAS_SECTION in text:
                    break
                transactions.extend(self._parse_page(text))
        return StatementData(
            account=self._account_from_text(first_page_text),
            statement=self._statement_from_text(first_page_text, path.name),
            transactions=transactions,
            pocket_movements=self.parse_pocket_movements(transactions),
        )

    # ── Public extensions ───────────────────────────────────────────────────

    def parse_pocket_movements(
        self, transactions: list[ParsedTransaction]
    ) -> list[ParsedPocketMovement]:
        movements: list[ParsedPocketMovement] = []
        for i, txn in enumerate(transactions):
            m = self._POCKET_DEPOSIT_RE.match(txn.description)
            if m:
                movements.append(
                    ParsedPocketMovement(
                        pocket_name=m.group(1).strip(),
                        movement_type="deposit",
                        amount=abs(txn.amount),
                        transaction_index=i,
                    )
                )
                continue

            m = self._POCKET_WITHDRAWAL_RE.match(txn.description)
            if m:
                movements.append(
                    ParsedPocketMovement(
                        pocket_name=m.group(1).strip(),
                        movement_type="withdrawal",
                        amount=abs(txn.amount),
                        transaction_index=i,
                    )
                )

        return movements

    # ── Private helpers ─────────────────────────────────────────────────────

    def _account_from_text(self, text: str) -> ParsedAccount:
        clabe: str | None = None
        account_number: str | None = None
        m = self._CLABE_RE.search(text)
        if m:
            clabe = m.group(1)
        m = self._ACCOUNT_RE.search(text)
        if m:
            account_number = m.group(1)
        return ParsedAccount(
            bank="nu",
            account_type="debit",
            alias="Nu Débito",
            clabe=clabe,
            account_number=account_number,
        )

    def _statement_from_text(self, text: str, filename: str) -> ParsedStatement:
        m = self._PERIOD_RE.search(text)
        if not m:
            raise ValueError(f"Cannot parse period from {filename}")
        day_start, day_end, month_str, year_str = m.groups()
        month = MONTHS[month_str.lower()]
        year = int(year_str)

        opening_balance: Decimal | None = None
        closing_balance: Decimal | None = None
        bm = self._BALANCE_RE.search(text)
        if bm:
            opening_balance = parse_decimal(bm.group(1))
            closing_balance = parse_decimal(bm.group(2))

        return ParsedStatement(
            period_start=date(year, month, int(day_start)),
            period_end=date(year, month, int(day_end)),
            opening_balance=opening_balance,
            closing_balance=closing_balance,
        )

    # ── Private parsing pipeline ────────────────────────────────────────────

    @staticmethod
    def _parse_date(raw: str) -> date:
        parts = raw.split()
        return date(int(parts[2]), _MONTH_ABBR[parts[1]], int(parts[0]))

    @staticmethod
    def _infer_type(amount: Decimal) -> TransactionType:
        return "payment" if amount > 0 else "charge"

    def _normalize_split_dates(self, text: str) -> str:
        """Normalize non-standard date/description layouts to 'DD MMM YYYY desc +/-$amt'."""
        # Format 1: "DD MMM\ndesc +/-$amt\nYYYY"
        text = self._SPLIT_DATE_RE.sub(
            lambda m: f"{m.group(1)} {m.group(4)} {m.group(2)} {m.group(3)}",
            text,
        )
        # Format 2: "desc_part1\nDD MMM YYYY +/-$amt\nconcept_part2"
        # Join desc_part1 and concept_part2 as full description
        text = self._INVERTED_DATE_RE.sub(
            lambda m: f"{m.group(2)} {m.group(1)} {m.group(4)} {m.group(3)}",
            text,
        )
        return text

    def _parse_page(self, text: str) -> list[ParsedTransaction]:
        text = self._normalize_split_dates(text)
        matches = list(self._TXN_RE.finditer(text))
        if not matches:
            return []

        transactions: list[ParsedTransaction] = []
        for i, m in enumerate(matches):
            amount_str = m.group(3).replace("$", "").replace("+", "")
            amount = parse_decimal(amount_str)

            # Text between this match and the next is the SPEI detail block
            detail_start = m.end()
            detail_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            detail = text[detail_start:detail_end]

            counterpart_clabe: str | None = None
            spei_tracking_key: str | None = None
            spei_reference: str | None = None

            cm = self._DETAIL_CLABE_RE.search(detail)
            if cm:
                counterpart_clabe = cm.group(1)

            tm = self._TRACKING_RE.search(detail)
            if tm:
                spei_tracking_key = tm.group(1).rstrip(",")

            rm = self._REFERENCE_RE.search(detail)
            if rm:
                spei_reference = rm.group(1)

            transactions.append(
                ParsedTransaction(
                    date=self._parse_date(m.group(1)),
                    description=m.group(2).strip(),
                    amount=amount,
                    transaction_type=self._infer_type(amount),
                    spei_tracking_key=spei_tracking_key,
                    spei_reference=spei_reference,
                    counterpart_clabe=counterpart_clabe,
                )
            )

        return transactions
