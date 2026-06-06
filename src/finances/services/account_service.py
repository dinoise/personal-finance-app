from finances.core.database import SessionLocal
from finances.repositories.account_repository import AccountRepository


class AccountService:
    def __init__(self) -> None:
        self._db = SessionLocal()

    def __enter__(self) -> "AccountService":
        return self

    def __exit__(self, *_: object) -> None:
        self._db.close()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_existing_account(self, bank: str, account_type: str) -> tuple[str, str] | None:
        """Return (clabe, alias) for an existing account of the given bank/type, or None."""
        account = AccountRepository(self._db).get_by_bank(bank, account_type)
        if account and account.clabe:
            return account.clabe, account.alias
        return None


# ---------------------------------------------------------------------------
# Module-level convenience wrappers
# ---------------------------------------------------------------------------


def get_existing_account(bank: str, account_type: str) -> tuple[str, str] | None:
    with AccountService() as svc:
        return svc.get_existing_account(bank, account_type)
