import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

from finances.parsers.base import (
    AccountType,
    BankName,
    BankParser,
    ParsedAccount,
    ParsedPocketMovement,
    ParsedStatement,
    ParsedTransaction,
    StatementData,
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


def _infer_type(amount: Decimal) -> str:
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

    def _parse_page(self, page: object) -> list[ParsedTransaction]:  # type: ignore[override]
        """
        Extract transactions from one page using word (x, y) coordinates.

        openhtmltopdf renders each table row with 5 thin horizontal rects
        (one per column) sharing the same y0 — these are the row bottom borders.
        We derive row bands from those y0 values, then bucket each word into its
        band and column based on position, reconstructing rows even when
        descriptions wrap across multiple visual lines within the same cell.
        """
        rects: list[dict] = getattr(page, "rects", [])
        words: list[dict] = page.extract_words(x_tolerance=3, y_tolerance=3)  # type: ignore[union-attr]
        page_height: float = getattr(page, "height", 800.0)

        bands = self._row_bands(rects, page_height)
        bucketed = self._bucket_words(words, bands)
        return self._build_transactions(bucketed)

    def _row_bands(self, rects: list[dict], page_height: float) -> list[tuple[float, float]]:
        """
        Derive (y_top, y_bottom) bands from horizontal rect separators.
        Each thin rect marks the bottom edge of a row.
        """
        separator_ys = sorted(
            set(
                round(r["y0"], 1)
                for r in rects
                if r.get("height", 0) < 2 and r.get("width", 0) > 50
            )
        )

        if not separator_ys:
            return [(0.0, page_height)]

        boundaries = [0.0, *separator_ys, page_height]
        return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]

    def _bucket_words(
        self,
        words: list[dict],
        bands: list[tuple[float, float]],
    ) -> list[dict[str, str]]:
        """
        Assign each word to its row band and column.
        Returns a list of row dicts: {date, description, op_id, value}.

        Description words are allowed to span across adjacent bands because
        long descriptions wrap visually (the cell is taller than the other
        columns).  All other columns are strictly bucketed to their band.
        """
        rows: list[dict[str, list[tuple[float, str]]]] = [
            {"date": [], "description": [], "op_id": [], "value": []} for _ in bands
        ]

        for word in words:
            top: float = word["top"]
            x0: float = word["x0"]
            text: str = word["text"]

            idx = self._band_index(top, bands)
            if idx is None:
                continue

            row = rows[idx]
            if x0 < _COL_DATE_MAX:
                row["date"].append((top, text))
            elif x0 < _COL_DESC_MAX:
                row["description"].append((top, text))
            elif x0 < _COL_ID_MAX:
                row["op_id"].append((top, text))
            elif x0 < _COL_VALUE_MAX:
                row["value"].append((top, text))

        # For each band determine the anchor top from valid date/op_id tokens only,
        # then filter description words to those within _ROW_HEIGHT of that anchor.
        result: list[dict[str, str]] = []
        for row in rows:
            # Anchor: top of the first valid date token or valid op_id token
            valid_date_tops = [t for t, txt in row["date"] if _DATE_RE.match(txt)]
            valid_id_tops = [t for t, txt in row["op_id"] if _OP_ID_RE.match(txt)]
            anchor_tops = valid_date_tops + valid_id_tops
            anchor = min(anchor_tops) if anchor_tops else None

            def _join(
                items: list[tuple[float, str]],
                strict: bool,
                row_anchor: float | None,
            ) -> str:
                if not strict or row_anchor is None:
                    return " ".join(txt for _, txt in items).strip()
                return " ".join(
                    txt for t, txt in items if abs(t - row_anchor) <= _ROW_HEIGHT
                ).strip()

            result.append(
                {
                    "date": _join(row["date"], strict=False, row_anchor=anchor),
                    "description": _join(row["description"], strict=True, row_anchor=anchor),
                    "op_id": _join(row["op_id"], strict=False, row_anchor=anchor),
                    "value": _join(row["value"], strict=False, row_anchor=anchor),
                }
            )

        return result

    @staticmethod
    def _band_index(top: float, bands: list[tuple[float, float]]) -> int | None:
        for i, (y_top, y_bottom) in enumerate(bands):
            if y_top <= top < y_bottom:
                return i
        return None

    def _build_transactions(self, rows: list[dict[str, str]]) -> list[ParsedTransaction]:
        transactions: list[ParsedTransaction] = []

        for i, row in enumerate(rows):
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

            # If description is empty, look ahead one band — the description
            # words may have landed in the next band due to row height differences
            if not description and i + 1 < len(rows):
                next_row = rows[i + 1]
                next_date = next((t for t in next_row["date"].split() if _DATE_RE.match(t)), "")
                next_op = next((t for t in next_row["op_id"].split() if _OP_ID_RE.match(t)), "")
                # Borrow description only if the next band is not its own transaction
                if not next_date and not next_op:
                    description = next_row["description"].strip()

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
                    transaction_type=_infer_type(amount),  # type: ignore[arg-type]
                    bank_reference=op_id,
                )
            )

        return transactions
