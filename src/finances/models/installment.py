from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finances.core.database import Base

_PLAN_STATUSES = "active, completed, cancelled"


class InstallmentPlan(Base):
    __tablename__ = "installment_plans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_installment_plan_status",
        ),
        Index("ix_installment_plan_account_status", "account_id", "status"),
        {
            "comment": (
                "MSI (meses sin interés) purchase plans from Nu and Banamex. "
                f"status valid values: {_PLAN_STATUSES}."
            )
        },
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"),
        nullable=False,
        comment="Credit account where the MSI plan was opened.",
    )
    merchant: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Merchant name as extracted from the PDF."
    )
    original_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Total purchase amount before splitting into installments.",
    )
    total_installments: Mapped[int] = mapped_column(
        nullable=False, comment="Total number of monthly installments, e.g. 6, 12, 18."
    )
    interest_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("0.0000"),
        comment="Monthly interest rate. 0.0000 for MSI (sin interés) plans.",
    )
    start_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="Date of the original purchase."
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", comment=f"Plan status. Valid values: {_PLAN_STATUSES}."
    )

    installments: Mapped[list["Installment"]] = relationship(back_populates="plan")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="installment_plan")  # type: ignore[name-defined]


class Installment(Base):
    __tablename__ = "installments"
    __table_args__ = (
        Index("ix_installment_plan_number", "plan_id", "installment_number"),
        {"comment": "Individual monthly payment within an MSI plan. One record per billing cycle."},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("installment_plans.id"),
        nullable=False,
        comment="MSI plan this installment belongs to.",
    )
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"),
        comment="Transaction where this installment charge appeared. NULL for future installments.",
    )
    installment_number: Mapped[int] = mapped_column(
        nullable=False, comment="Sequential number, e.g. 1 of 12."
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="Amount charged in this installment."
    )
    due_date: Mapped[date | None] = mapped_column(
        Date, comment="Expected charge date for this installment."
    )
    is_paid: Mapped[bool] = mapped_column(
        default=False, comment="True when the installment has appeared in a statement."
    )

    plan: Mapped["InstallmentPlan"] = relationship(back_populates="installments")
    transaction: Mapped["Transaction | None"] = relationship()  # type: ignore[name-defined]


from finances.models.transaction import Transaction  # noqa: E402
