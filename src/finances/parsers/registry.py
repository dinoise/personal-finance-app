from dataclasses import dataclass, field

from finances.parsers.banamex_credit import BanamexCreditParser
from finances.parsers.base import BankParser
from finances.parsers.bbva_debit import BBVADebitParser
from finances.parsers.mercadopago_debit import MercadoPagoDebitParser
from finances.parsers.nu_credit import NuCreditParser
from finances.parsers.nu_debit import NuDebitParser


@dataclass(frozen=True)
class BankConfig:
    bank_key: str
    account_type: str
    label: str
    signature: str
    parser_class: type[BankParser] = field(hash=False)
    needs_clabe: bool = False


# Order matters — more specific signatures must come before broader ones.
REGISTRY: list[BankConfig] = [
    BankConfig("nu", "credit", "Nu Crédito", "Tarjeta de Credito Nu", NuCreditParser),
    BankConfig("nu", "debit", "Nu Débito", "Cuenta Nu:", NuDebitParser),
    BankConfig("bbva", "debit", "BBVA Débito", "Libreton Basico", BBVADebitParser),
    BankConfig("banamex", "credit", "Banamex Crédito", "JOY BANAMEX", BanamexCreditParser),
    BankConfig(
        "mercadopago",
        "debit",
        "Mercado Pago",
        "ESTADO DE SALDOS",
        MercadoPagoDebitParser,
        needs_clabe=True,
    ),
]


def get_config(bank_key: str, account_type: str) -> BankConfig:
    """Return the BankConfig for the given bank/account_type pair."""
    for config in REGISTRY:
        if config.bank_key == bank_key and config.account_type == account_type:
            return config
    raise ValueError(f"No bank registered for {bank_key!r} / {account_type!r}")


def detect_config(text: str) -> BankConfig:
    """Identify a BankConfig by matching its signature against PDF text."""
    for config in REGISTRY:
        if config.signature in text:
            return config
    raise ValueError("Unrecognized PDF format — no signature matched.")


def all_labels() -> dict[tuple[str, str], str]:
    """Return a mapping of (bank_key, account_type) → label for all registered banks."""
    return {(c.bank_key, c.account_type): c.label for c in REGISTRY}
