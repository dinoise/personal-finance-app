from finances.parsers.base import BankParser
from finances.schemas.parser_schemas import AccountType, BankName


def get_parser(bank: BankName, account_type: AccountType) -> BankParser:
    """Return the correct parser instance for the given bank and account type."""
    from finances.parsers.banamex_credit import BanamexCreditParser
    from finances.parsers.bbva_debit import BBVADebitParser
    from finances.parsers.mercadopago import MercadoPagoParser
    from finances.parsers.nu_credit import NuCreditParser
    from finances.parsers.nu_debit import NuDebitParser

    _registry: dict[tuple[BankName, AccountType], type[BankParser]] = {
        ("nu", "credit"): NuCreditParser,
        ("nu", "debit"): NuDebitParser,
        ("bbva", "debit"): BBVADebitParser,
        ("banamex", "credit"): BanamexCreditParser,
        ("mercadopago", "debit"): MercadoPagoParser,
    }

    key = (bank, account_type)
    if key not in _registry:
        raise ValueError(f"No parser registered for {bank!r} / {account_type!r}")

    return _registry[key]()
