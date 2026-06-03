from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finances.core.database import Base

POCKET_MOVEMENT_TYPES = ("deposit", "withdrawal", "interest")


class SavingsPocket(Base):
    __tablename__ = "savings_pockets"
    __table_args__ = (
        UniqueConstraint("account_id", "name", name="uq_savings_pocket_account_name"),
        Index("ix_savings_pocket_account", "account_id"),
        {
            "comment": (
                "Named savings sub-accounts within a debit account. "
                "MercadoPago calls these 'Apartados'; Nu calls them 'Cajitas'."
            )
        },
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"),
        nullable=False,
        comment="Parent debit account that holds this pocket.",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Pocket name as reported by the bank, e.g. 'Ahorro', 'Renta', 'Cajita Gastos'.",
    )
    is_active: Mapped[bool] = mapped_column(
        default=True,
        comment="False when the pocket has been closed by the user.",
    )

    account: Mapped["Account"] = relationship(back_populates="savings_pockets")  # type: ignore[name-defined]
    movements: Mapped[list["SavingsPocketMovement"]] = relationship(back_populates="pocket")


class SavingsPocketMovement(Base):
    __tablename__ = "savings_pocket_movements"
    __table_args__ = (
        CheckConstraint(
            "movement_type IN ('deposit', 'withdrawal', 'interest')",
            name="ck_pocket_movement_type",
        ),
        Index("ix_pocket_movement_pocket", "pocket_id"),
        Index("ix_pocket_movement_transaction", "transaction_id"),
        {
            "comment": (
                "Each deposit into, withdrawal from, or interest credited to a savings pocket. "
                "Linked to the originating transaction row."
            )
        },
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pocket_id: Mapped[int] = mapped_column(
        ForeignKey("savings_pockets.id"),
        nullable=False,
        comment="Pocket this movement belongs to.",
    )
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"),
        nullable=False,
        comment="Source transaction record for this movement.",
    )
    movement_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="deposit | withdrawal | interest",
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Absolute movement amount (always positive).",
    )
    balance_after: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        comment="Pocket balance after this movement. NULL if not reported by the bank.",
    )

    pocket: Mapped["SavingsPocket"] = relationship(back_populates="movements")
    transaction: Mapped["Transaction"] = relationship()  # type: ignore[name-defined]


from finances.models.account import Account  # noqa: E402
from finances.models.transaction import Transaction  # noqa: E402
