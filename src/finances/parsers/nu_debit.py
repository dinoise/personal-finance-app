import re
from datetime import date
from decimal import Decimal
from re import Match
from typing import ClassVar

from finances.parsers.base import BankParser
from finances.parsers.utils import MONTHS, parse_date_dmy_text, parse_decimal
from finances.schemas.parser_schemas import (
    AccountType,
    BankName,
    ParsedAccount,
    ParsedPocketMovement,
    ParsedStatement,
    ParsedTransaction,
)


class NuDebitParser(BankParser):
    # ── Class-level patterns ──────────────────────────────────────────────────

    # Header (page 1)
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

    # Section boundary — pages from here on are a mirror with inverted signs
    _CAJITAS_SECTION: ClassVar = "Detalle de movimientos de tus cajitas"

    # Transaction line: "DD MMM YYYY  <description>  +/-$amount"
    _TXN_RE: ClassVar = re.compile(
        r"^(\d{2}\s+[A-ZÁÉÍÓÚÜÑ]{3}\s+\d{4})\s+(.+?)\s+([+-]\$[\d,]+\.\d{2})\s*$",
        re.MULTILINE,
    )

    # Split-date: "DD MMM\n<description> +/-$amount\nYYYY"
    # pdfplumber breaks the date across lines on dense pages
    _SPLIT_DATE_RE: ClassVar = re.compile(
        r"^(\d{2}\s+[A-ZÁÉÍÓÚÜÑ]{3})\n(.+?)\s+([+-]\$[\d,]+\.\d{2})\n(\d{4})$",
        re.MULTILINE,
    )

    # Inverted: description wraps above the date line, concept wraps below
    # "desc_part1\nDD MMM YYYY +/-$amount\nconcept_part2"
    _INVERTED_DATE_RE: ClassVar = re.compile(
        r"^([^\n]+)\n(\d{2}\s+[A-ZÁÉÍÓÚÜÑ]{3}\s+\d{4})\s+([+-]\$[\d,]+\.\d{2})\n([^\n]+)$",
        re.MULTILINE,
    )

    # Cajitas movement descriptions
    _POCKET_DEPOSIT_RE: ClassVar = re.compile(r"^Depósito en Cajita:\s+(.+)$")
    _POCKET_WITHDRAWAL_RE: ClassVar = re.compile(r"^Retiro de Cajita:\s+(.+)$")

    # SPEI detail block (text after each transaction line)
    # Matches 16-digit card numbers (debit-card/credit-card) or 18-digit CLABEs
    _DETAIL_CLABE_RE: ClassVar = re.compile(r"(\d{16,18})\s+(clabe|debit-card|credit-card)")
    _TRACKING_RE: ClassVar = re.compile(r"Clave de rastreo\s+(\S+?)(?:,|\s)")
    _REFERENCE_RE: ClassVar = re.compile(r"Clave de referencia\s+(\S+)")

    # ── Identity ──────────────────────────────────────────────────────────────

    @property
    def bank_name(self) -> BankName:
        return "nu"

    @property
    def account_type(self) -> AccountType:
        return "debit"

    # ── Hooks ─────────────────────────────────────────────────────────────────

    def _should_stop(self, page: object) -> bool:
        text = page.extract_text() or ""  # type: ignore[attr-defined]
        return self._CAJITAS_SECTION in text

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

    # ── Abstract implementation ───────────────────────────────────────────────

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

    def _parse_page(self, page: object) -> list[ParsedTransaction]:
        text = self._normalize_split_dates(page.extract_text() or "")  # type: ignore[attr-defined]
        matches = list(self._TXN_RE.finditer(text))
        return self._build_transactions(text, matches)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _normalize_split_dates(self, text: str) -> str:
        # Format 1: "DD MMM\ndesc +/-$amt\nYYYY"
        text = self._SPLIT_DATE_RE.sub(
            lambda m: f"{m.group(1)} {m.group(4)} {m.group(2)} {m.group(3)}",
            text,
        )
        # Format 2: "desc_part1\nDD MMM YYYY +/-$amt\nconcept_part2"
        text = self._INVERTED_DATE_RE.sub(
            lambda m: f"{m.group(2)} {m.group(1)} {m.group(4)} {m.group(3)}",
            text,
        )
        return text

    _IDENTIFIER_TYPE_MAP: ClassVar[dict[str, str]] = {
        "clabe": "clabe",
        "debit-card": "card",
        "credit-card": "card",
    }

    def _extract_spei_detail(
        self, detail: str
    ) -> tuple[str | None, str | None, str | None, str | None]:
        counterpart_identifier: str | None = None
        counterpart_identifier_type: str | None = None
        spei_tracking_key: str | None = None
        spei_reference: str | None = None

        m = self._DETAIL_CLABE_RE.search(detail)
        if m:
            counterpart_identifier = m.group(1)
            counterpart_identifier_type = self._IDENTIFIER_TYPE_MAP[m.group(2)]

        m = self._TRACKING_RE.search(detail)
        if m:
            spei_tracking_key = m.group(1).rstrip(",")

        m = self._REFERENCE_RE.search(detail)
        if m:
            spei_reference = m.group(1)

        return (
            counterpart_identifier,
            counterpart_identifier_type,
            spei_tracking_key,
            spei_reference,
        )

    def _build_transactions(self, text: str, matches: list[Match[str]]) -> list[ParsedTransaction]:
        transactions: list[ParsedTransaction] = []
        for i, m in enumerate(matches):
            amount = parse_decimal(m.group(3).replace("$", "").replace("+", ""))

            detail_start = m.end()
            detail_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            counterpart_id, counterpart_type, spei_tracking_key, spei_reference = (
                self._extract_spei_detail(text[detail_start:detail_end])
            )

            transactions.append(
                ParsedTransaction(
                    date=parse_date_dmy_text(m.group(1)),
                    description=m.group(2).strip(),
                    amount=amount,
                    transaction_type=self._infer_type(amount),
                    spei_tracking_key=spei_tracking_key,
                    spei_reference=spei_reference,
                    counterpart_identifier=counterpart_id,
                    counterpart_identifier_type=counterpart_type,
                )
            )
        return transactions
