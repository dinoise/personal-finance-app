from __future__ import annotations

from decimal import Decimal

from finances.core.database import SessionLocal
from finances.models.transaction import Transaction
from finances.models.transfer import Transfer
from finances.repositories.account_repository import AccountRepository
from finances.repositories.transaction_repository import TransactionRepository
from finances.repositories.transfer_repository import TransferRepository


class TransferService:
    def __init__(self) -> None:
        self._db = SessionLocal()
        self._txn_repo = TransactionRepository(self._db)
        self._transfer_repo = TransferRepository(self._db)
        self._account_repo = AccountRepository(self._db)

    def __enter__(self) -> TransferService:
        return self

    def __exit__(self, *_: object) -> None:
        self._db.close()

    def get_all(self) -> list[Transfer]:
        return self._transfer_repo.get_all()

    def detect_transfers(self) -> int:
        """Link transactions into Transfer records.

        Pass 1: transactions with spei_tracking_key → create or complete a Transfer.
        Pass 2: transactions without spei_tracking_key but with bank_reference →
                look for an existing Transfer whose spei_tracking_key relates to
                that bank_reference (exact → suffix → contains).

        Returns the number of Transfer records created or updated.
        """
        known_clabes = self._account_repo.get_all_clabes()

        touched = 0
        touched += self._pass_spei_key(known_clabes)
        touched += self._pass_bank_reference(known_clabes)
        self._db.commit()
        return touched

    # ------------------------------------------------------------------
    # Internal passes
    # ------------------------------------------------------------------

    def _pass_spei_key(self, known_clabes: set[str]) -> int:
        touched = 0
        for txn in self._txn_repo.get_with_spei_key():
            assert txn.spei_tracking_key is not None
            existing = self._transfer_repo.get_by_spei_key(txn.spei_tracking_key)
            if existing is not None:
                touched += self._complete_transfer(existing, txn)
            else:
                self._create_transfer(txn, txn.spei_tracking_key, known_clabes)
                touched += 1
        return touched

    def _pass_bank_reference(self, known_clabes: set[str]) -> int:
        touched = 0
        for txn in self._txn_repo.get_without_spei_key_with_bank_reference():
            assert txn.bank_reference is not None

            if txn.amount < 0 and self._transfer_repo.exists_for_source(txn.id):
                continue
            if txn.amount >= 0 and self._transfer_repo.exists_for_destination(txn.id):
                continue

            match = self._transfer_repo.get_by_spei_key_match(txn.bank_reference)
            if match is not None:
                touched += self._complete_transfer(match, txn)
        return touched

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_transfer(
        self,
        txn: Transaction,
        spei_tracking_key: str,
        known_clabes: set[str],
    ) -> None:
        is_outgoing = txn.amount < Decimal("0")
        counterpart_id, counterpart_type = self._resolve_counterpart(txn, known_clabes)
        transfer_type = self._transfer_type(counterpart_id, known_clabes)

        self._transfer_repo.create(
            amount=abs(txn.amount),
            currency=txn.currency,
            txn_date=txn.date,
            transfer_type=transfer_type,
            source_transaction_id=txn.id if is_outgoing else None,
            destination_transaction_id=None if is_outgoing else txn.id,
            spei_tracking_key=spei_tracking_key,
            spei_reference=txn.spei_reference,
            from_account_id=txn.account_id if is_outgoing else None,
            to_account_id=None if is_outgoing else txn.account_id,
            counterpart_identifier=counterpart_id,
            counterpart_identifier_type=counterpart_type,
        )

    def _complete_transfer(self, transfer: Transfer, txn: Transaction) -> int:
        is_outgoing = txn.amount < Decimal("0")
        if is_outgoing and transfer.source_transaction_id is None:
            self._transfer_repo.complete_source(transfer, txn.id, txn.account_id)
            return 1
        if not is_outgoing and transfer.destination_transaction_id is None:
            self._transfer_repo.complete_destination(transfer, txn.id, txn.account_id)
            return 1
        return 0

    def _resolve_counterpart(
        self, txn: Transaction, known_clabes: set[str]
    ) -> tuple[str | None, str | None]:
        return None, None

    def _transfer_type(self, counterpart_id: str | None, known_clabes: set[str]) -> str:
        if counterpart_id is not None and counterpart_id in known_clabes:
            return "internal"
        return "outgoing"


# ---------------------------------------------------------------------------
# Convenience wrappers (keeps views free of DB and service class details)
# ---------------------------------------------------------------------------


def detect_transfers() -> int:
    with TransferService() as svc:
        return svc.detect_transfers()


def get_all_transfers() -> list[Transfer]:
    with TransferService() as svc:
        return svc.get_all()
