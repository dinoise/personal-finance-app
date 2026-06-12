from __future__ import annotations

import re
from datetime import date
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

        Three passes, all in memory after two initial queries:
          Pass 1: transactions with spei_tracking_key → O(1) dict lookup
          Pass 2: transactions with only bank_reference → suffix index O(1) lookup
          Pass 3: unlinked outgoing on own accounts, matched by (amount, date) against
                  unlinked incoming on own accounts — links only when exactly one match
                  exists on each side (no ambiguity).

        Returns the number of Transfer records created or updated.
        """
        known_clabes = self._account_repo.get_all_clabes()
        known_account_ids = self._account_repo.get_all_account_ids()

        transfers_by_key = self._txn_repo.get_transfers_indexed_by_spei_key()
        suffix_index = self._build_suffix_index(transfers_by_key)
        candidates = self._txn_repo.get_spei_candidates()

        touched = 0
        for txn in candidates:
            if txn.spei_tracking_key is not None:
                touched += self._handle_spei_key(txn, transfers_by_key, suffix_index, known_clabes)
            elif txn.bank_reference is not None:
                touched += self._handle_bank_reference(txn, suffix_index)

        touched += self._handle_amount_date_pass(known_account_ids)

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

        transfer = self._create_transfer(txn, known_clabes)
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

    def _handle_amount_date_pass(
        self,
        known_account_ids: set[int],
    ) -> int:
        """Complete partial transfers by matching (amount, date) against unlinked own transactions.

        Operates on transfers that already have one side linked but not the other — these
        were created by passes 1/2 from SPEI keys. Links only when exactly one unambiguous
        match exists on each side. Generic — no bank-specific logic.
        """
        partial = self._transfer_repo.get_partial_transfers()
        if not partial:
            return 0

        unlinked_incoming = self._txn_repo.get_unlinked_own_incoming(known_account_ids)

        # Build index: (abs_amount, date) → list of incoming transactions
        incoming_index: dict[tuple[Decimal, date], list[Transaction]] = {}
        for txn in unlinked_incoming:
            key = (txn.amount, txn.date)
            incoming_index.setdefault(key, []).append(txn)

        touched = 0
        consumed_incoming: set[int] = set()

        for transfer in partial:
            if (
                transfer.source_transaction_id is not None
                and transfer.destination_transaction_id is None
            ):
                src = transfer.source_transaction
                if src is None:
                    continue
                key = (abs(src.amount), src.date)
                matches = [
                    t
                    for t in incoming_index.get(key, [])
                    if t.id not in consumed_incoming and t.account_id != src.account_id
                ]
                if len(matches) != 1:
                    continue
                self._transfer_repo.complete_destination(transfer, matches[0].id)
                consumed_incoming.add(matches[0].id)
                touched += 1

        return touched

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_transfer(self, txn: Transaction, known_clabes: set[str]) -> Transfer:
        is_outgoing = txn.amount < Decimal("0")
        transfer_type = self._transfer_type(txn, known_clabes)

        return self._transfer_repo.create(
            transfer_type=transfer_type,
            source_transaction_id=txn.id if is_outgoing else None,
            destination_transaction_id=None if is_outgoing else txn.id,
        )

    def _complete_transfer(self, transfer: Transfer, txn: Transaction) -> int:
        is_outgoing = txn.amount < Decimal("0")
        if is_outgoing and transfer.source_transaction_id is None:
            self._transfer_repo.complete_source(transfer, txn.id)
            return 1
        if not is_outgoing and transfer.destination_transaction_id is None:
            self._transfer_repo.complete_destination(transfer, txn.id)
            return 1
        return 0

    def _transfer_type(self, txn: Transaction, known_clabes: set[str]) -> str:
        if txn.counterpart_identifier is not None and txn.counterpart_identifier in known_clabes:
            return "internal"
        return "outgoing"

    def _build_suffix_index(self, transfers_by_key: dict[str, Transfer]) -> dict[str, Transfer]:
        """Build a numeric-suffix index: trailing digits of each spei_tracking_key → Transfer.

        "CPO147653673997"          → "147653673997"
        "MBAN01002602160076127075" → "01002602160076127075"
        "NU38MIUCDO289F0BF5FKAT58DEAS" → no trailing digits, skipped

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
