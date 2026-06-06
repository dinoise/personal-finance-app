from datetime import date
from decimal import Decimal, InvalidOperation

MONTHS: dict[str, int] = {
    "enero": 1,
    "ene": 1,
    "febrero": 2,
    "feb": 2,
    "marzo": 3,
    "mar": 3,
    "abril": 4,
    "abr": 4,
    "mayo": 5,
    "may": 5,
    "junio": 6,
    "jun": 6,
    "julio": 7,
    "jul": 7,
    "agosto": 8,
    "ago": 8,
    "septiembre": 9,
    "sep": 9,
    "octubre": 10,
    "oct": 10,
    "noviembre": 11,
    "nov": 11,
    "diciembre": 12,
    "dic": 12,
}


def parse_decimal(raw: str) -> Decimal:
    """Parse a Mexican bank amount string into Decimal. Returns 0 on failure."""
    try:
        return Decimal(raw.replace(",", "").replace("$", "").strip())
    except InvalidOperation:
        return Decimal("0")


def parse_date_dmy(raw: str) -> date:
    """Parse a DD-MM-YYYY date string (standard format in Mexican bank PDFs)."""
    day, month, year = raw.split("-")
    return date(int(year), int(month), int(day))
