from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from finances.models.transaction import Transaction


class TransactionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def exists(
        self, statement_id: int, bank_reference: str | None, amount: Decimal
    ) -> Transaction | None:
        return (
            self._db.query(Transaction)
            .filter_by(
                statement_id=statement_id,
                bank_reference=bank_reference,
                amount=amount,
            )
            .first()
        )

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
