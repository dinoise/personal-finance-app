from finances.core.database import SessionLocal
from finances.repositories.transaction_repository import TransactionRepository
from finances.schemas.import_schemas import TransactionRow


class TransactionService:
    def __init__(self) -> None:
        self._db = SessionLocal()

    def __enter__(self) -> "TransactionService":
        return self

    def __exit__(self, *_: object) -> None:
        self._db.close()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_statement_transactions(self, statement_id: int) -> list[TransactionRow]:
        """Return all transactions for a statement as plain dataclass rows."""
        txns = TransactionRepository(self._db).get_by_statement(statement_id)
        return [
            TransactionRow(
                date=t.date,
                description=t.description,
                amount=t.amount,
                transaction_type=t.transaction_type,
                bank_reference=t.bank_reference,
            )
            for t in txns
        ]


# ---------------------------------------------------------------------------
# Module-level convenience wrappers
# ---------------------------------------------------------------------------


def get_statement_transactions(statement_id: int) -> list[TransactionRow]:
    with TransactionService() as svc:
        return svc.get_statement_transactions(statement_id)
