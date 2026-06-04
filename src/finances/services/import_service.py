"""
Import pipeline: PDF → parse → persist.

Flow:
    1. Detect bank and account type from the PDF.
    2. Resolve or create the Account record (prompts caller for CLABE when missing).
    3. Guard against duplicate statements (same account + period).
    4. Copy the PDF to data/statements/<bank>/<type>/ for local archiving.
    5. Persist Statement, Transactions, SavingsPocketMovements atomically.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from finances.core.config import settings
from finances.models.account import Account, Statement
from finances.models.savings_pocket import SavingsPocket, SavingsPocketMovement
from finances.models.transaction import Transaction
from finances.parsers.base import ParsedPocketMovement, ParsedTransaction, StatementData
from finances.parsers.detector import detect_bank_and_type
from finances.parsers.factory import get_parser

# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------


@dataclass
class ImportResult:
    account: Account
    statement: Statement
    transactions_inserted: int
    pocket_movements_inserted: int
    pdf_stored_path: Path


@dataclass
class ImportError:
    reason: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _statements_dir(bank: str, account_type: str) -> Path:
    path = settings.data_dir / "statements" / bank / account_type
    path.mkdir(parents=True, exist_ok=True)
    return path


def _store_pdf(src: Path, bank: str, account_type: str, period_start: object) -> Path:
    """Copy PDF to data/statements/<bank>/<type>/ with a normalized filename."""
    dest_dir = _statements_dir(bank, account_type)
    period_str = str(period_start)[:7]  # YYYY-MM
    dest = dest_dir / f"{bank}_{account_type}_{period_str}.pdf"
    if not dest.exists():
        shutil.copy2(src, dest)
    return dest


def _resolve_account(
    db: Session,
    bank: str,
    account_type: str,
    account_number: str | None,
    alias: str,
    clabe: str | None,
) -> Account:
    """Return existing Account or create a new one."""
    account: Account | None = None

    if clabe:
        account = db.query(Account).filter_by(clabe=clabe).first()

    if account is None and account_number:
        account = (
            db.query(Account)
            .filter_by(bank=bank, account_type=account_type, account_number=account_number)
            .first()
        )

    if account is None:
        account = Account(
            bank=bank,
            account_type=account_type,
            alias=alias,
            clabe=clabe,
            account_number=account_number,
        )
        db.add(account)
        db.flush()

    return account


def _is_duplicate_statement(db: Session, account_id: int, data: StatementData) -> bool:
    return (
        db.query(Statement)
        .filter_by(
            account_id=account_id,
            period_start=data.statement.period_start,
            period_end=data.statement.period_end,
        )
        .first()
        is not None
    )


def _insert_transactions(
    db: Session,
    account_id: int,
    statement_id: int,
    parsed: list[ParsedTransaction],
) -> tuple[list[Transaction], int]:
    """Insert transactions, skipping duplicates by (statement_id, bank_reference, amount)."""
    inserted: list[Transaction] = []
    skipped = 0

    for p in parsed:
        exists = (
            db.query(Transaction)
            .filter_by(
                statement_id=statement_id,
                bank_reference=p.bank_reference,
                amount=p.amount,
            )
            .first()
        )
        if exists:
            inserted.append(exists)
            skipped += 1
            continue

        txn = Transaction(
            account_id=account_id,
            statement_id=statement_id,
            date=p.date,
            description=p.description,
            amount=p.amount,
            amount_mxn=p.amount,  # all MercadoPago transactions are MXN
            currency=p.currency,
            transaction_type=p.transaction_type,
            bank_reference=p.bank_reference,
        )
        db.add(txn)
        db.flush()
        inserted.append(txn)

    return inserted, skipped


def _insert_pocket_movements(
    db: Session,
    account_id: int,
    transactions: list[Transaction],
    movements: list[ParsedPocketMovement],
) -> int:
    inserted = 0

    for pm in movements:
        txn = transactions[pm.transaction_index]

        # Resolve or create the pocket
        pocket = (
            db.query(SavingsPocket).filter_by(account_id=account_id, name=pm.pocket_name).first()
        )
        if pocket is None:
            pocket = SavingsPocket(account_id=account_id, name=pm.pocket_name)
            db.add(pocket)
            db.flush()

        movement = SavingsPocketMovement(
            pocket_id=pocket.id,
            transaction_id=txn.id,
            movement_type=pm.movement_type,
            amount=pm.amount,
        )
        db.add(movement)
        inserted += 1

    return inserted


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_pdf(
    db: Session,
    path: Path,
    clabe_override: str | None = None,
) -> ImportResult | ImportError:
    """
    Import a bank statement PDF into the database.

    Args:
        db: Active SQLAlchemy session.
        path: Path to the PDF file to import.
        clabe_override: CLABE provided by the user when the parser cannot extract it
                        (e.g. MercadoPago statements do not print the CLABE).

    Returns:
        ImportResult on success, ImportError on failure.
    """
    try:
        bank, account_type = detect_bank_and_type(path)
    except ValueError as e:
        return ImportError(reason=str(e))

    parser = get_parser(bank, account_type)

    if not parser.validate(path):
        return ImportError(reason=f"PDF failed validation for {bank}/{account_type}.")

    data: StatementData = parser.parse(path)

    # Use caller-supplied CLABE when the parser cannot extract one
    effective_clabe = clabe_override or data.account.clabe

    try:
        account = _resolve_account(
            db,
            bank=bank,
            account_type=account_type,
            account_number=data.account.account_number,
            alias=data.account.alias,
            clabe=effective_clabe,
        )

        if _is_duplicate_statement(db, account.id, data):
            db.rollback()
            return ImportError(
                reason=(
                    f"Statement for {bank} {account_type} "
                    f"{data.statement.period_start} – {data.statement.period_end} "
                    "already exists."
                )
            )

        pdf_path = _store_pdf(path, bank, account_type, data.statement.period_start)

        statement = Statement(
            account_id=account.id,
            period_start=data.statement.period_start,
            period_end=data.statement.period_end,
            opening_balance=data.statement.opening_balance,
            closing_balance=data.statement.closing_balance,
            payment_due_date=data.statement.payment_due_date,
            minimum_payment=data.statement.minimum_payment,
            file_path=str(pdf_path),
        )
        db.add(statement)
        db.flush()

        txns, _ = _insert_transactions(db, account.id, statement.id, data.transactions)
        pocket_count = _insert_pocket_movements(db, account.id, txns, data.pocket_movements)

        db.commit()

        return ImportResult(
            account=account,
            statement=statement,
            transactions_inserted=len(txns),
            pocket_movements_inserted=pocket_count,
            pdf_stored_path=pdf_path,
        )

    except IntegrityError as e:
        db.rollback()
        return ImportError(reason=f"Database integrity error: {e.orig}")
    except Exception as e:
        db.rollback()
        return ImportError(reason=str(e))
