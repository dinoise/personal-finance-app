## v0.5.0 (2026-06-04)

### Feat

- **registry**: centralize bank metadata in BankConfig registry
- **schemas**: add parser_schemas and import_schemas modules

### Fix

- **views**: resolve DetachedInstanceError and Account object type mismatch in import view

### Refactor

- **services,views**: move all business logic and queries out of import view

## v0.4.0 (2026-06-04)

### Feat

- **views**: add import statement view with CLABE prompt and transaction table
- **repositories**: add AccountRepository, TransactionRepository, SavingsPocketRepository
- **services**: implement PDF import pipeline with statement archiving
- **parsers**: add stub parsers for remaining banks

### Fix

- **models**: move Installment.transaction relationship inside class definition

### Refactor

- **import_view**: changing position on info about the clabe after the existing account validation
- **services**: use repositories in import_service instead of direct queries

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
