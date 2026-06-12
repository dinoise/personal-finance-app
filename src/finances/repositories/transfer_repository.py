from datetime import date

from sqlalchemy.orm import Session, joinedload

from finances.models.transaction import Transaction
from finances.models.transfer import Transfer


class TransferRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        transfer_type: str,
        source_transaction_id: int | None = None,
        destination_transaction_id: int | None = None,
    ) -> Transfer:
        transfer = Transfer(
            source_transaction_id=source_transaction_id,
            destination_transaction_id=destination_transaction_id,
            transfer_type=transfer_type,
        )
        self._db.add(transfer)
        self._db.flush()
        return transfer

    def get_all(self) -> list[Transfer]:
        transfers = (
            self._db.query(Transfer)
            .options(
                joinedload(Transfer.source_transaction).joinedload(Transaction.account),
                joinedload(Transfer.destination_transaction).joinedload(Transaction.account),
            )
            .all()
        )
        return sorted(
            transfers,
            key=lambda t: (
                t.source_transaction.date
                if t.source_transaction
                else t.destination_transaction.date
                if t.destination_transaction
                else date.min
            ),
            reverse=True,
        )

    def get_partial_transfers(self) -> list[Transfer]:
        """Return internal transfers with only one side linked, awaiting the other PDF.

        Only "internal" transfers can be completed by amount+date matching — outgoing
        transfers go to external accounts that will never have an importable PDF.
        """
        return (
            self._db.query(Transfer)
            .options(
                joinedload(Transfer.source_transaction),
                joinedload(Transfer.destination_transaction),
            )
            .filter(
                Transfer.transfer_type == "internal",
                (
                    (Transfer.source_transaction_id.isnot(None))
                    & (Transfer.destination_transaction_id.is_(None))
                )
                | (
                    (Transfer.source_transaction_id.is_(None))
                    & (Transfer.destination_transaction_id.isnot(None))
                ),
            )
            .all()
        )

    def complete_source(self, transfer: Transfer, transaction_id: int) -> None:
        transfer.source_transaction_id = transaction_id
        self._db.flush()

    def complete_destination(self, transfer: Transfer, transaction_id: int) -> None:
        transfer.destination_transaction_id = transaction_id
        self._db.flush()
