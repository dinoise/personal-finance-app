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
from finances.parsers.base import ParsedPocketMovement, ParsedTransaction, StatementData
from finances.parsers.detector import detect_bank_and_type
from finances.parsers.factory import get_parser
from finances.repositories.account_repository import AccountRepository
from finances.repositories.savings_pocket_repository import SavingsPocketRepository
from finances.repositories.transaction_repository import TransactionRepository


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


def _store_pdf(src: Path, bank: str, account_type: str, period_start: object) -> Path:
    dest_dir = settings.data_dir / "statements" / bank / account_type
    dest_dir.mkdir(parents=True, exist_ok=True)
    period_str = str(period_start)[:7]  # YYYY-MM
    dest = dest_dir / f"{bank}_{account_type}_{period_str}.pdf"
    if not dest.exists():
        shutil.copy2(src, dest)
    return dest


def _resolve_account(
    repo: AccountRepository,
    bank: str,
    account_type: str,
    alias: str,
    clabe: str | None,
    account_number: str | None,
) -> Account:
    if clabe:
        account = repo.get_by_clabe(clabe)
        if account:
            return account

    if account_number:
        account = repo.get_by_bank_and_number(bank, account_type, account_number)
        if account:
            return account

    return repo.create(
        bank=bank,
        account_type=account_type,
        alias=alias,
        clabe=clabe,
        account_number=account_number,
    )


def _insert_transactions(
    repo: TransactionRepository,
    account_id: int,
    statement_id: int,
    parsed: list[ParsedTransaction],
) -> list:
    result = []
    for p in parsed:
        existing = repo.exists(statement_id, p.bank_reference, p.amount)
        if existing:
            result.append(existing)
            continue
        txn = repo.create(
            account_id=account_id,
            statement_id=statement_id,
            date=p.date,
            description=p.description,
            amount=p.amount,
            amount_mxn=p.amount,
            currency=p.currency,
            transaction_type=p.transaction_type,
            bank_reference=p.bank_reference,
        )
        result.append(txn)
    return result


def _insert_pocket_movements(
    repo: SavingsPocketRepository,
    account_id: int,
    transactions: list,
    movements: list[ParsedPocketMovement],
) -> int:
    count = 0
    for pm in movements:
        txn = transactions[pm.transaction_index]
        pocket = repo.get_or_create(account_id, pm.pocket_name)
        repo.create_movement(
            pocket_id=pocket.id,
            transaction_id=txn.id,
            movement_type=pm.movement_type,
            amount=pm.amount,
        )
        count += 1
    return count


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

    effective_clabe = clabe_override or data.account.clabe

    account_repo = AccountRepository(db)
    txn_repo = TransactionRepository(db)
    pocket_repo = SavingsPocketRepository(db)

    try:
        account = _resolve_account(
            account_repo,
            bank=bank,
            account_type=account_type,
            alias=data.account.alias,
            clabe=effective_clabe,
            account_number=data.account.account_number,
        )

        if account_repo.statement_exists(
            account.id, data.statement.period_start, data.statement.period_end
        ):
            db.rollback()
            return ImportError(
                reason=(
                    f"Statement for {bank} {account_type} "
                    f"{data.statement.period_start} – {data.statement.period_end} "
                    "already exists."
                )
            )

        pdf_path = _store_pdf(path, bank, account_type, data.statement.period_start)

        statement = account_repo.create_statement(
            account_id=account.id,
            period_start=data.statement.period_start,
            period_end=data.statement.period_end,
            file_path=str(pdf_path),
            opening_balance=data.statement.opening_balance,
            closing_balance=data.statement.closing_balance,
            payment_due_date=data.statement.payment_due_date,
            minimum_payment=data.statement.minimum_payment,
        )

        txns = _insert_transactions(txn_repo, account.id, statement.id, data.transactions)
        pocket_count = _insert_pocket_movements(
            pocket_repo, account.id, txns, data.pocket_movements
        )

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
