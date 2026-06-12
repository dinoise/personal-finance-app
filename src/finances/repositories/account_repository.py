from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from finances.models.account import Account, Statement


class AccountRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_clabe(self, clabe: str) -> Account | None:
        return self._db.query(Account).filter_by(clabe=clabe).first()

    def get_all_clabes(self) -> set[str]:
        rows = self._db.query(Account.clabe).filter(Account.clabe.isnot(None)).all()
        return {row[0] for row in rows}

    def get_all_account_ids(self) -> set[int]:
        rows = self._db.query(Account.id).all()
        return {row[0] for row in rows}

    def get_by_bank_and_number(
        self, bank: str, account_type: str, account_number: str
    ) -> Account | None:
        return (
            self._db.query(Account)
            .filter_by(bank=bank, account_type=account_type, account_number=account_number)
            .first()
        )

    def get_by_bank(self, bank: str, account_type: str) -> Account | None:
        return self._db.query(Account).filter_by(bank=bank, account_type=account_type).first()

    def create(
        self,
        bank: str,
        account_type: str,
        alias: str,
        clabe: str | None = None,
        account_number: str | None = None,
    ) -> Account:
        account = Account(
            bank=bank,
            account_type=account_type,
            alias=alias,
            clabe=clabe,
            account_number=account_number,
        )
        self._db.add(account)
        self._db.flush()
        return account

    def statement_exists(self, account_id: int, period_start: date, period_end: date) -> bool:
        return (
            self._db.query(Statement)
            .filter_by(
                account_id=account_id,
                period_start=period_start,
                period_end=period_end,
            )
            .first()
            is not None
        )

    def create_statement(
        self,
        account_id: int,
        period_start: date,
        period_end: date,
        file_path: str,
        opening_balance: Decimal | None = None,
        closing_balance: Decimal | None = None,
        payment_due_date: date | None = None,
        minimum_payment: Decimal | None = None,
    ) -> Statement:
        statement = Statement(
            account_id=account_id,
            period_start=period_start,
            period_end=period_end,
            file_path=file_path,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            payment_due_date=payment_due_date,
            minimum_payment=minimum_payment,
        )
        self._db.add(statement)
        self._db.flush()
        return statement
