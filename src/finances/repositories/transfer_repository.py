from datetime import date
from decimal import Decimal

from sqlalchemy import case
from sqlalchemy.orm import Session, joinedload

from finances.models.transfer import Transfer


class TransferRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        amount: Decimal,
        currency: str,
        txn_date: date,
        transfer_type: str,
        source_transaction_id: int | None = None,
        destination_transaction_id: int | None = None,
        spei_tracking_key: str | None = None,
        spei_reference: str | None = None,
        from_account_id: int | None = None,
        to_account_id: int | None = None,
        counterpart_identifier: str | None = None,
        counterpart_identifier_type: str | None = None,
    ) -> Transfer:
        transfer = Transfer(
            source_transaction_id=source_transaction_id,
            destination_transaction_id=destination_transaction_id,
            spei_tracking_key=spei_tracking_key,
            spei_reference=spei_reference,
            amount=amount,
            currency=currency,
            date=txn_date,
            transfer_type=transfer_type,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            counterpart_identifier=counterpart_identifier,
            counterpart_identifier_type=counterpart_identifier_type,
        )
        self._db.add(transfer)
        self._db.flush()
        return transfer

    def get_by_spei_key(self, spei_tracking_key: str) -> Transfer | None:
        return self._db.query(Transfer).filter_by(spei_tracking_key=spei_tracking_key).first()

    def get_by_spei_key_match(self, bank_reference: str) -> Transfer | None:
        """Find a Transfer whose spei_tracking_key relates to bank_reference.

        Tries three levels of specificity in a single query, ordered so the
        closest match wins:
          1. exact match          (spei_tracking_key == bank_reference)
          2. suffix match         (spei_tracking_key ends with bank_reference)
          3. contains match       (bank_reference is anywhere in spei_tracking_key)
        """
        specificity = case(
            (Transfer.spei_tracking_key == bank_reference, 1),
            (Transfer.spei_tracking_key.endswith(bank_reference), 2),
            (Transfer.spei_tracking_key.contains(bank_reference), 3),
        )
        return (
            self._db.query(Transfer)
            .filter(
                Transfer.spei_tracking_key.isnot(None),
                Transfer.spei_tracking_key.contains(bank_reference),
            )
            .order_by(specificity)
            .first()
        )

    def exists_for_source(self, transaction_id: int) -> bool:
        return (
            self._db.query(Transfer).filter_by(source_transaction_id=transaction_id).first()
            is not None
        )

    def exists_for_destination(self, transaction_id: int) -> bool:
        return (
            self._db.query(Transfer).filter_by(destination_transaction_id=transaction_id).first()
            is not None
        )

    def get_all(self) -> list[Transfer]:
        return (
            self._db.query(Transfer)
            .options(
                joinedload(Transfer.from_account),
                joinedload(Transfer.to_account),
                joinedload(Transfer.source_transaction),
                joinedload(Transfer.destination_transaction),
            )
            .order_by(Transfer.date.desc())
            .all()
        )

    def complete_source(self, transfer: Transfer, transaction_id: int, account_id: int) -> None:
        transfer.source_transaction_id = transaction_id
        transfer.from_account_id = account_id
        self._db.flush()

    def complete_destination(
        self, transfer: Transfer, transaction_id: int, account_id: int
    ) -> None:
        transfer.destination_transaction_id = transaction_id
        transfer.to_account_id = account_id
        self._db.flush()
