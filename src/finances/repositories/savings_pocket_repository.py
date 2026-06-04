from decimal import Decimal

from sqlalchemy.orm import Session

from finances.models.savings_pocket import SavingsPocket, SavingsPocketMovement


class SavingsPocketRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_or_create(self, account_id: int, name: str) -> SavingsPocket:
        pocket = self._db.query(SavingsPocket).filter_by(account_id=account_id, name=name).first()
        if pocket is None:
            pocket = SavingsPocket(account_id=account_id, name=name)
            self._db.add(pocket)
            self._db.flush()
        return pocket

    def create_movement(
        self,
        pocket_id: int,
        transaction_id: int,
        movement_type: str,
        amount: Decimal,
        balance_after: Decimal | None = None,
    ) -> SavingsPocketMovement:
        movement = SavingsPocketMovement(
            pocket_id=pocket_id,
            transaction_id=transaction_id,
            movement_type=movement_type,
            amount=amount,
            balance_after=balance_after,
        )
        self._db.add(movement)
        return movement

    def get_by_account(self, account_id: int) -> list[SavingsPocket]:
        return self._db.query(SavingsPocket).filter_by(account_id=account_id).all()
