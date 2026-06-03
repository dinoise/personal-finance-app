from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finances.core.database import Base

# Allowed withdrawal point types
WITHDRAWAL_TYPES = ("atm", "convenience_store", "bank_branch", "other")


class CashWithdrawal(Base):
    __tablename__ = "cash_withdrawals"
    __table_args__ = (
        Index("ix_cash_withdrawal_account", "account_id"),
        CheckConstraint(
            "withdrawal_type IN ('atm', 'convenience_store', 'bank_branch', 'other')",
            name="ck_cash_withdrawal_type",
        ),
        {
            "comment": (
                "Cash withdrawals from any point: ATM, OXXO, bank branch, etc. "
                "Modeled separately from transfers — money leaves the trackable banking system."
            )
        },
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"),
        nullable=False,
        comment="Debit account from which cash was withdrawn.",
    )
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"),
        nullable=False,
        comment="Transaction record for the withdrawal amount.",
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"),
        comment="Category assigned to this withdrawal, e.g. 'Cash expenses'.",
    )
    fee_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"),
        comment="Separate transaction for the withdrawal fee. NULL if no fee was applied.",
    )
    withdrawal_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="atm",
        comment="Point type: atm | convenience_store | bank_branch | other.",
    )
    withdrawal_point: Mapped[str | None] = mapped_column(
        String(200),
        comment="Name of the withdrawal point as reported by the bank, e.g. 'OXXO ZARCO MEX'.",
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="Amount withdrawn in the original currency."
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="MXN", comment="ISO 4217 currency code."
    )
    amount_mxn: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="Amount converted to MXN."
    )
    fee_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        comment="Fee charged for the withdrawal. 0.00 if none.",
    )

    account: Mapped["Account"] = relationship()  # type: ignore[name-defined]
    category: Mapped["Category | None"] = relationship()  # type: ignore[name-defined]


from finances.models.account import Account  # noqa: E402
from finances.models.transaction import Category  # noqa: E402
