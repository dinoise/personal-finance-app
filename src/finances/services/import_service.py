"""
Import pipeline: PDF → parse → persist.

Flow:
    1. Detect bank and account type from the PDF.
    2. Resolve or create the Account record (prompts caller for CLABE when missing).
    3. Guard against duplicate statements (same account + period).
    4. Copy the PDF to data/statements/<bank>/<type>/ for local archiving.
    5. Persist Statement, Transactions, SavingsPocketMovements atomically.
"""

import hashlib
import shutil
from pathlib import Path

import pdfplumber
from sqlalchemy.exc import IntegrityError

from finances.core.config import settings
from finances.core.database import SessionLocal
from finances.models.account import Account
from finances.models.transaction import Transaction
from finances.parsers.registry import detect_config
from finances.repositories.account_repository import AccountRepository
from finances.repositories.savings_pocket_repository import SavingsPocketRepository
from finances.repositories.transaction_repository import TransactionRepository
from finances.schemas.import_schemas import ImportError, ImportResult, ParsedPdfData
from finances.schemas.parser_schemas import ParsedPocketMovement, ParsedTransaction, StatementData

# ---------------------------------------------------------------------------
# Module-level helper (stateless — no DB required)
# ---------------------------------------------------------------------------


def parse_pdf(path: Path) -> ParsedPdfData | ImportError:
    """Open and fully parse a PDF. Returns a ParsedPdfData to cache in session state."""
    try:
        with pdfplumber.open(path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""
        config = detect_config(first_page_text)
    except ValueError as e:
        return ImportError(reason=str(e))

    parser = config.parser_class()
    file_hash = hashlib.md5(path.read_bytes()).hexdigest()
    data = parser.parse(path)

    return ParsedPdfData(
        bank=config.bank_key,
        account_type=config.account_type,
        file_hash=file_hash,
        data=data,
        config=config,
    )


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class ImportService:
    def __init__(self) -> None:
        self._db = SessionLocal()
        self._account_repo = AccountRepository(self._db)
        self._txn_repo = TransactionRepository(self._db)
        self._pocket_repo = SavingsPocketRepository(self._db)

    def __enter__(self) -> "ImportService":
        return self

    def __exit__(self, *_: object) -> None:
        self._db.close()

    # ── Public API ────────────────────────────────────────────────────────────

    def import_parsed(
        self,
        parsed: ParsedPdfData,
        source_path: Path,
        clabe_override: str | None = None,
    ) -> ImportResult | ImportError:
        """
        Persist an already-parsed PDF into the database.

        Args:
            parsed: Result of a previous parse_pdf() call (held in session state).
            source_path: Original PDF path, used to archive the file.
            clabe_override: CLABE provided by the user when the bank doesn't print it.

        Returns:
            ImportResult on success, ImportError on failure.
        """
        data: StatementData = parsed.data
        effective_clabe = clabe_override or data.account.clabe

        try:
            account = self._resolve_account(
                bank=parsed.bank,
                account_type=parsed.account_type,
                alias=data.account.alias,
                clabe=effective_clabe,
                account_number=data.account.account_number,
            )

            if self._account_repo.statement_exists(
                account.id, data.statement.period_start, data.statement.period_end
            ):
                self._db.rollback()
                return ImportError(
                    reason=(
                        f"Statement for {parsed.bank} {parsed.account_type} "
                        f"{data.statement.period_start} – {data.statement.period_end} "
                        "already exists."
                    )
                )

            pdf_path = self._store_pdf(
                source_path, parsed.bank, parsed.account_type, data.statement.period_start
            )

            statement = self._account_repo.create_statement(
                account_id=account.id,
                period_start=data.statement.period_start,
                period_end=data.statement.period_end,
                file_path=str(pdf_path),
                opening_balance=data.statement.opening_balance,
                closing_balance=data.statement.closing_balance,
                payment_due_date=data.statement.payment_due_date,
                minimum_payment=data.statement.minimum_payment,
            )

            txns = self._insert_transactions(account.id, statement.id, data.transactions)
            pocket_count = self._insert_pocket_movements(account.id, txns, data.pocket_movements)

            self._db.commit()

            return ImportResult(
                statement_id=statement.id,
                account_alias=account.alias,
                bank_label=parsed.config.label,
                transactions_inserted=len(txns),
                pocket_movements_inserted=pocket_count,
                pdf_stored_path=pdf_path,
            )

        except IntegrityError as e:
            self._db.rollback()
            return ImportError(reason=f"Database integrity error: {e.orig}")
        except Exception as e:
            self._db.rollback()
            return ImportError(reason=str(e))

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_account(
        self,
        bank: str,
        account_type: str,
        alias: str,
        clabe: str | None,
        account_number: str | None,
    ) -> Account:
        if clabe:
            account = self._account_repo.get_by_clabe(clabe)
            if account:
                return account

        if account_number:
            account = self._account_repo.get_by_bank_and_number(bank, account_type, account_number)
            if account:
                return account

        return self._account_repo.create(
            bank=bank,
            account_type=account_type,
            alias=alias,
            clabe=clabe,
            account_number=account_number,
        )

    def _insert_transactions(
        self,
        account_id: int,
        statement_id: int,
        parsed: list[ParsedTransaction],
    ) -> list[Transaction]:
        result = []
        seen: dict[tuple[object, ...], int] = {}
        for p in parsed:
            key = (p.date, p.description, p.amount)
            position = seen.get(key, 0)
            seen[key] = position + 1
            existing = self._txn_repo.exists(
                statement_id, p.bank_reference, p.amount, p.date, p.description, position
            )
            if existing:
                result.append(existing)
                continue
            txn = self._txn_repo.create(
                account_id=account_id,
                statement_id=statement_id,
                date=p.date,
                description=p.description,
                amount=p.amount,
                amount_mxn=p.amount,
                currency=p.currency,
                transaction_type=p.transaction_type,
                bank_reference=p.bank_reference,
                spei_tracking_key=p.spei_tracking_key,
                spei_reference=p.spei_reference,
                counterpart_identifier=p.counterpart_identifier,
                counterpart_identifier_type=p.counterpart_identifier_type,
            )
            result.append(txn)
        return result

    def _insert_pocket_movements(
        self,
        account_id: int,
        transactions: list[Transaction],
        movements: list[ParsedPocketMovement],
    ) -> int:
        count = 0
        for pm in movements:
            txn = transactions[pm.transaction_index]
            pocket = self._pocket_repo.get_or_create(account_id, pm.pocket_name)
            self._pocket_repo.create_movement(
                pocket_id=pocket.id,
                transaction_id=txn.id,
                movement_type=pm.movement_type,
                amount=pm.amount,
            )
            count += 1
        return count

    @staticmethod
    def _store_pdf(src: Path, bank: str, account_type: str, period_start: object) -> Path:
        dest_dir = settings.data_dir / "statements" / bank / account_type
        dest_dir.mkdir(parents=True, exist_ok=True)
        period_str = str(period_start)[:7]
        dest = dest_dir / f"{bank}_{account_type}_{period_str}.pdf"
        if not dest.exists():
            shutil.copy2(src, dest)
        return dest


# ---------------------------------------------------------------------------
# Convenience wrapper (keeps the view call simple)
# ---------------------------------------------------------------------------


def import_parsed(
    parsed: ParsedPdfData,
    source_path: Path,
    clabe_override: str | None = None,
) -> ImportResult | ImportError:
    """Thin wrapper so the view doesn't need to manage the DB session."""
    with ImportService() as svc:
        return svc.import_parsed(parsed, source_path, clabe_override)
