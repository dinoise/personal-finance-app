from datetime import date
from decimal import Decimal

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
        )
        self._db.add(transfer)
        self._db.flush()
        return transfer

    def get_indexed_by_spei_key(self) -> dict[str, Transfer]:
        """Return all transfers that have a spei_tracking_key, indexed by it."""
        rows = self._db.query(Transfer).filter(Transfer.spei_tracking_key.isnot(None)).all()
        return {t.spei_tracking_key: t for t in rows if t.spei_tracking_key is not None}

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
