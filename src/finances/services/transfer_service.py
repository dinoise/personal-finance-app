from __future__ import annotations

import re
from decimal import Decimal
from typing import ClassVar

from finances.core.database import SessionLocal
from finances.models.transaction import Transaction
from finances.models.transfer import Transfer
from finances.repositories.account_repository import AccountRepository
from finances.repositories.transaction_repository import TransactionRepository
from finances.repositories.transfer_repository import TransferRepository


class TransferService:
    _TRAILING_DIGITS: ClassVar[re.Pattern[str]] = re.compile(r"\d+$")

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

        Reads exactly two queries up front, then does all matching in memory:
          - Query 1: all transfers with spei_tracking_key → dict[key, Transfer]
          - Query 2: all transactions with spei_tracking_key OR bank_reference

        For each transaction:
          - Has spei_tracking_key → O(1) dict lookup (pass 1)
          - Has only bank_reference → scored match against dict keys (pass 2)

        Returns the number of Transfer records created or updated.
        """
        known_clabes = self._account_repo.get_all_clabes()
        transfers_by_key = self._transfer_repo.get_indexed_by_spei_key()
        suffix_index = self._build_suffix_index(transfers_by_key)
        candidates = self._txn_repo.get_spei_candidates()

        touched = 0
        for txn in candidates:
            if txn.spei_tracking_key is not None:
                touched += self._handle_spei_key(txn, transfers_by_key, suffix_index, known_clabes)
            elif txn.bank_reference is not None:
                touched += self._handle_bank_reference(txn, suffix_index)

        self._db.commit()
        return touched

    # ------------------------------------------------------------------
    # Per-transaction handlers
    # ------------------------------------------------------------------

    def _handle_spei_key(
        self,
        txn: Transaction,
        transfers_by_key: dict[str, Transfer],
        suffix_index: dict[str, Transfer],
        known_clabes: set[str],
    ) -> int:
        assert txn.spei_tracking_key is not None
        existing = transfers_by_key.get(txn.spei_tracking_key)
        if existing is not None:
            return self._complete_transfer(existing, txn)

        transfer = self._create_transfer(txn, txn.spei_tracking_key, known_clabes)
        transfers_by_key[txn.spei_tracking_key] = transfer
        m = self._TRAILING_DIGITS.search(txn.spei_tracking_key)
        if m:
            suffix_index[m.group()] = transfer
        return 1

    def _handle_bank_reference(
        self,
        txn: Transaction,
        suffix_index: dict[str, Transfer],
    ) -> int:
        assert txn.bank_reference is not None

        match = suffix_index.get(txn.bank_reference)
        if match is None:
            return 0

        is_outgoing = txn.amount < Decimal("0")
        if is_outgoing and match.source_transaction_id is not None:
            return 0
        if not is_outgoing and match.destination_transaction_id is not None:
            return 0

        return self._complete_transfer(match, txn)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_transfer(
        self,
        txn: Transaction,
        spei_tracking_key: str,
        known_clabes: set[str],
    ) -> Transfer:
        is_outgoing = txn.amount < Decimal("0")
        counterpart_id, counterpart_type = self._resolve_counterpart(txn, known_clabes)
        transfer_type = self._transfer_type(counterpart_id, known_clabes)

        return self._transfer_repo.create(
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

    def _build_suffix_index(self, transfers_by_key: dict[str, Transfer]) -> dict[str, Transfer]:
        """Build a numeric-suffix index: trailing digits of each spei_tracking_key → Transfer.

        "CPO147653673997"          → "147653673997"
        "MBAN01002602160076127075" → "01002602160076127075"
        "NU39KT5HHAG58GLQ2T6PF3JQRLT5" → no trailing digits, skipped

        O(K) build, O(1) lookup. bank_reference is always the trailing numeric part
        of the spei_tracking_key regardless of bank prefix.
        """
        index: dict[str, Transfer] = {}
        for key, transfer in transfers_by_key.items():
            m = self._TRAILING_DIGITS.search(key)
            if m:
                index[m.group()] = transfer
        return index


# ---------------------------------------------------------------------------
# Convenience wrappers (keeps views free of DB and service class details)
# ---------------------------------------------------------------------------


def detect_transfers() -> int:
    with TransferService() as svc:
        return svc.detect_transfers()


def get_all_transfers() -> list[Transfer]:
    with TransferService() as svc:
        return svc.get_all()
