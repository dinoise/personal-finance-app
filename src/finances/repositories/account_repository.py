from sqlalchemy.orm import Session

from finances.models.account import Account, Statement


class AccountRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_clabe(self, clabe: str) -> Account | None:
        return self._db.query(Account).filter_by(clabe=clabe).first()

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

    def statement_exists(self, account_id: int, period_start: object, period_end: object) -> bool:
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
        period_start: object,
        period_end: object,
        file_path: str,
        opening_balance: object = None,
        closing_balance: object = None,
        payment_due_date: object = None,
        minimum_payment: object = None,
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
