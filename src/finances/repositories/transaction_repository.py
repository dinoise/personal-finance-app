from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from finances.models.transaction import Transaction


class TransactionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def exists(
        self,
        statement_id: int,
        bank_reference: str | None,
        amount: Decimal,
        txn_date: date,
        description: str,
        position: int,
    ) -> Transaction | None:
        if bank_reference is not None:
            # SPEI/card transactions: bank_reference is unique within a statement
            return (
                self._db.query(Transaction)
                .filter_by(statement_id=statement_id, bank_reference=bank_reference)
                .first()
            )
        # Transactions without a reference: count how many identical rows already
        # exist. If already-stored count >= position+1, this slot is filled.
        already = (
            self._db.query(Transaction)
            .filter_by(
                statement_id=statement_id,
                bank_reference=None,
                amount=amount,
                date=txn_date,
                description=description,
            )
            .count()
        )
        if already > position:
            return (
                self._db.query(Transaction)
                .filter_by(
                    statement_id=statement_id,
                    bank_reference=None,
                    amount=amount,
                    date=txn_date,
                    description=description,
                )
                .first()
            )
        return None

    def create(
        self,
        account_id: int,
        statement_id: int,
        date: date,
        description: str,
        amount: Decimal,
        amount_mxn: Decimal,
        currency: str,
        transaction_type: str,
        bank_reference: str | None = None,
        spei_tracking_key: str | None = None,
        spei_reference: str | None = None,
        counterpart_identifier: str | None = None,
        counterpart_identifier_type: str | None = None,
    ) -> Transaction:
        txn = Transaction(
            account_id=account_id,
            statement_id=statement_id,
            date=date,
            description=description,
            amount=amount,
            amount_mxn=amount_mxn,
            currency=currency,
            transaction_type=transaction_type,
            bank_reference=bank_reference,
            spei_tracking_key=spei_tracking_key,
            spei_reference=spei_reference,
            counterpart_identifier=counterpart_identifier,
            counterpart_identifier_type=counterpart_identifier_type,
        )
        self._db.add(txn)
        self._db.flush()
        return txn

    def get_by_statement(self, statement_id: int) -> list[Transaction]:
        return (
            self._db.query(Transaction)
            .filter_by(statement_id=statement_id)
            .order_by(Transaction.date)
            .all()
        )

    def get_spei_candidates(self) -> list[Transaction]:
        """Return all transactions that have a spei_tracking_key or a bank_reference."""
        return (
            self._db.query(Transaction)
            .filter(
                (Transaction.spei_tracking_key.isnot(None))
                | (Transaction.bank_reference.isnot(None))
            )
            .all()
        )

    def get_by_account(
        self,
        account_id: int,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[Transaction]:
        q = self._db.query(Transaction).filter_by(account_id=account_id)
        if from_date:
            q = q.filter(Transaction.date >= from_date)
        if to_date:
            q = q.filter(Transaction.date <= to_date)
        return q.order_by(Transaction.date).all()
