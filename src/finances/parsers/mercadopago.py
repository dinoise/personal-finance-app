import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pdfplumber

from finances.parsers.base import BankParser
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

_PERIOD_RE = re.compile(r"Periodo:\s+Del\s+(\d{1,2})\s+al\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})")
_BALANCE_RE = re.compile(
    r"Saldo inicial:\s*\$\s*([\d,]+\.?\d*)\s+Saldo final:\s*\$\s*([\d,]+\.?\d*)"
)
_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_OP_ID_RE = re.compile(r"^\d{9,}$")

# Column x-boundaries derived from word position analysis across all 3 PDFs
_COL_DATE_MAX: float = 92.0  # Fecha
_COL_DESC_MAX: float = 212.0  # Descripción
_COL_ID_MAX: float = 295.0  # ID operación
_COL_VALUE_MAX: float = 365.0  # Valor  (beyond this → Saldo, ignored)

# Max vertical distance (points) between a description word and its row anchor.
# Within a single row, wrapped description lines are at most ~12pt from the anchor.
# Row pitch is ~35pt, so 15pt safely excludes the next row's text.
_ROW_HEIGHT: float = 15.0

# Savings pocket movement patterns
_POCKET_DEPOSIT_RE = re.compile(r"^Monto apartado (.+)$", re.IGNORECASE)
_POCKET_WITHDRAWAL_RE = re.compile(r"^Monto retirado (.+)$", re.IGNORECASE)
_POCKET_INTEREST_RE = re.compile(r"^Ganancia", re.IGNORECASE)

_MONTHS: dict[str, int] = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def _parse_decimal(raw: str) -> Decimal:
    try:
        return Decimal(raw.replace(",", "").replace("$", "").strip())
    except InvalidOperation:
        return Decimal("0")


def _parse_date(raw: str) -> date:
    day, month, year = raw.split("-")
    return date(int(year), int(month), int(day))


def _infer_type(amount: Decimal) -> TransactionType:
    return "payment" if amount > 0 else "charge"


class MercadoPagoParser(BankParser):
    @property
    def bank_name(self) -> BankName:
        return "mercadopago"

    @property
    def account_type(self) -> AccountType:
        return "debit"

    def validate(self, path: Path) -> bool:
        with pdfplumber.open(path) as pdf:
            text = pdf.pages[0].extract_text() or ""
        return "ESTADO DE SALDOS" in text

    def parse_account(self, path: Path) -> ParsedAccount:
        with pdfplumber.open(path) as pdf:
            text = pdf.pages[0].extract_text() or ""

        account_number: str | None = None
        m = re.search(r"Cust id:\s*(\d+)", text)
        if m:
            account_number = m.group(1)

        return ParsedAccount(
            bank="mercadopago",
            account_type="debit",
            alias="Mercado Pago Débito",
            # CLABE is not printed in MP statements — user must provide it on first import
            clabe=None,
            account_number=account_number,
        )

    def parse_statement(self, path: Path) -> ParsedStatement:
        with pdfplumber.open(path) as pdf:
            text = pdf.pages[0].extract_text() or ""

        m = _PERIOD_RE.search(text)
        if not m:
            raise ValueError(f"Cannot parse period from {path.name}")

        day_start, day_end, month_str, year_str = m.groups()
        month = _MONTHS[month_str.lower()]
        year = int(year_str)

        opening_balance: Decimal | None = None
        closing_balance: Decimal | None = None
        bm = _BALANCE_RE.search(text)
        if bm:
            opening_balance = _parse_decimal(bm.group(1))
            closing_balance = _parse_decimal(bm.group(2))

        return ParsedStatement(
            period_start=date(year, month, int(day_start)),
            period_end=date(year, month, int(day_end)),
            opening_balance=opening_balance,
            closing_balance=closing_balance,
        )

    def parse_transactions(self, path: Path) -> list[ParsedTransaction]:
        transactions: list[ParsedTransaction] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                transactions.extend(self._parse_page(page))
        return transactions

    def parse_pocket_movements(
        self, transactions: list[ParsedTransaction]
    ) -> list[ParsedPocketMovement]:
        movements: list[ParsedPocketMovement] = []
        for i, txn in enumerate(transactions):
            desc = txn.description

            m = _POCKET_DEPOSIT_RE.match(desc)
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

            m = _POCKET_WITHDRAWAL_RE.match(desc)
            if m:
                movements.append(
                    ParsedPocketMovement(
                        pocket_name=m.group(1).strip(),
                        movement_type="withdrawal",
                        amount=abs(txn.amount),
                        transaction_index=i,
                    )
                )
                continue

            if _POCKET_INTEREST_RE.match(desc):
                movements.append(
                    ParsedPocketMovement(
                        pocket_name="general",
                        movement_type="interest",
                        amount=abs(txn.amount),
                        transaction_index=i,
                    )
                )

        return movements

    def parse(self, path: Path) -> StatementData:
        transactions = self.parse_transactions(path)
        return StatementData(
            account=self.parse_account(path),
            statement=self.parse_statement(path),
            transactions=transactions,
            pocket_movements=self.parse_pocket_movements(transactions),
        )

    def _parse_page(self, page: object) -> list[ParsedTransaction]:
        """
        Extract transactions from one page using word (x, y) coordinates.

        Strategy: identify row anchors (the top-y of each date/op_id pair),
        then assign every word to the nearest anchor within _ROW_HEIGHT.
        This is more robust than band-based bucketing because openhtmltopdf
        sometimes places multiple transactions in the same rect band and
        renders op_id a few points above the corresponding date.
        """
        words: list[dict[str, Any]] = page.extract_words(x_tolerance=3, y_tolerance=3)  # type: ignore[attr-defined]
        bucketed = self._bucket_words(words)
        return self._build_transactions(bucketed)

    def _bucket_words(self, words: list[dict[str, Any]]) -> list[dict[str, str]]:
        """
        Two-pass bucketing:
        Pass 1 — collect all date and op_id tops to build the anchor list.
                 Each unique top (rounded to 2pt) that has either a valid date
                 or a valid op_id becomes a row anchor.
        Pass 2 — assign every word to the nearest anchor within _ROW_HEIGHT.

        Anchors are derived independently per column so that a 3-4pt vertical
        drift between the date cell and the op_id cell does not split a row.
        """
        RowWords = list[tuple[float, float, str]]

        # Pass 1: collect candidate anchor tops from date and op_id columns
        date_tops: list[float] = []
        op_id_tops: list[float] = []
        for word in words:
            top: float = word["top"]
            x0: float = word["x0"]
            text: str = word["text"]
            if x0 < _COL_DATE_MAX and _DATE_RE.match(text):
                date_tops.append(top)
            elif _COL_DESC_MAX <= x0 < _COL_ID_MAX and _OP_ID_RE.match(text):
                op_id_tops.append(top)

        # Merge date and op_id tops: group within 5pt, take the mean as anchor
        raw_tops = sorted(set(date_tops + op_id_tops))
        anchors: list[float] = []
        for t in raw_tops:
            if anchors and abs(t - anchors[-1]) <= 5.0:
                # Merge into the existing anchor (running mean)
                anchors[-1] = (anchors[-1] + t) / 2
            else:
                anchors.append(t)

        if not anchors:
            return []

        rows: list[dict[str, RowWords]] = [
            {"date": [], "description": [], "op_id": [], "value": []} for _ in anchors
        ]

        # Pass 2: assign every word to the nearest anchor within _ROW_HEIGHT
        for word in words:
            top = word["top"]
            x0 = word["x0"]
            text = word["text"]

            best_idx: int | None = None
            best_dist = float("inf")
            for i, anchor in enumerate(anchors):
                dist = abs(top - anchor)
                if dist <= _ROW_HEIGHT and dist < best_dist:
                    best_dist = dist
                    best_idx = i

            if best_idx is None:
                continue

            row = rows[best_idx]
            if x0 < _COL_DATE_MAX:
                row["date"].append((top, x0, text))
            elif x0 < _COL_DESC_MAX:
                row["description"].append((top, x0, text))
            elif x0 < _COL_ID_MAX:
                row["op_id"].append((top, x0, text))
            elif x0 < _COL_VALUE_MAX:
                row["value"].append((top, x0, text))

        def _join(items: RowWords) -> str:
            ordered = sorted(items, key=lambda w: (round(w[0]), w[1]))
            return " ".join(txt for _, _, txt in ordered).strip()

        return [
            {
                "date": _join(row["date"]),
                "description": _join(row["description"]),
                "op_id": _join(row["op_id"]),
                "value": _join(row["value"]),
            }
            for row in rows
        ]

    def _build_transactions(self, rows: list[dict[str, str]]) -> list[ParsedTransaction]:
        transactions: list[ParsedTransaction] = []

        for row in rows:
            # Pick the first DD-MM-YYYY token — header words may share the band
            date_str = next((t for t in row["date"].split() if _DATE_RE.match(t)), "")
            # Pick the first 9+-digit token — stray single digits may follow
            op_id = next((t for t in row["op_id"].split() if _OP_ID_RE.match(t)), "")

            if not date_str or not op_id:
                continue

            value_str = row["value"].replace("$", "").strip()

            # Strip header words that may have leaked into the description cell
            description = re.sub(
                r"\b(Descripción|Descripcion|Fecha|Valor|Saldo)\b\s*",
                "",
                row["description"],
            ).strip()

            amount = _parse_decimal(value_str)

            # Some MP rows have no description in the PDF (e.g. micro interest credits).
            # Fall back to a label derived from the sign so the record is never blank.
            if not description:
                description = "Ganancia" if amount > 0 else "Movimiento"
            transactions.append(
                ParsedTransaction(
                    date=_parse_date(date_str),
                    description=description,
                    amount=amount,
                    transaction_type=_infer_type(amount),
                    bank_reference=op_id,
                )
            )

        return transactions
