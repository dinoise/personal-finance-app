## v0.3.0 (2026-06-03)

### Feat

- **parsers**: extract savings pocket movements from MercadoPago statements
- **models**: add savings_pockets and savings_pocket_movements tables

## v0.2.0 (2026-06-03)

### Feat

- **parsers**: add MercadoPago debit statement parser
- **parsers**: add parser factory function
- **parsers**: add bank auto-detection by PDF text signature
- **parsers**: add BankParser ABC and parsed data dataclasses

### Refactor

- **models**: drop fee_transaction_id from cash_withdrawals
- **models**: generalize cash_withdrawals beyond ATM-only
- move __version__ to package __init__.py
