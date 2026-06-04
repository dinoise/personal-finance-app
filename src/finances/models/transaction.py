from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finances.core.database import Base

if TYPE_CHECKING:
    from finances.models.account import Account, Statement
    from finances.models.installment import InstallmentPlan

_TRANSACTION_TYPES = "charge, payment, refund, interest"


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        {"comment": "Hierarchical spending categories. parent_id enables sub-categories."},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Category name, e.g. 'Food', 'Transport'."
    )
    color: Mapped[str | None] = mapped_column(
        String(7), comment="Hex color code for UI display, e.g. '#FF5733'."
    )
    icon: Mapped[str | None] = mapped_column(String(50), comment="Icon identifier for UI display.")
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"),
        comment="Parent category ID. NULL means this is a top-level category.",
    )
    budget_mxn: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), comment="Monthly budget in MXN. Used for alerts in the dashboard."
    )

    parent: Mapped[Category | None] = relationship(
        back_populates="children", remote_side="Category.id"
    )
    children: Mapped[list[Category]] = relationship(back_populates="parent")
    labels: Mapped[list[Label]] = relationship(back_populates="category")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="category")


class Label(Base):
    __tablename__ = "labels"
    __table_args__ = (
        Index("ix_label_priority", "priority"),
        {
            "comment": "Regex-based auto-categorization rules. Evaluated in ascending priority order."  # noqa: E501
        },
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern_regex: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Python regex pattern matched against transaction description.",
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"),
        nullable=False,
        comment="Category assigned when the pattern matches.",
    )
    priority: Mapped[int] = mapped_column(
        default=100, comment="Evaluation order. Lower number = higher priority."
    )

    category: Mapped[Category] = relationship(back_populates="labels")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ('charge', 'payment', 'refund', 'interest')",
            name="ck_transaction_type",
        ),
        Index("ix_transaction_account_date", "account_id", "date"),
        Index("ix_transaction_category", "category_id"),
        Index("ix_transaction_statement", "statement_id"),
        Index("ix_transaction_date", "date"),
        Index("ix_transaction_type", "transaction_type"),
        {
            "comment": (
                "Core table — all movements from all banks unified in a single schema. "
                f"transaction_type valid values: {_TRANSACTION_TYPES}."
            )
        },
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"), nullable=False, comment="Account that originated this movement."
    )
    statement_id: Mapped[int] = mapped_column(
        ForeignKey("statements.id"),
        nullable=False,
        comment="Statement where this transaction appeared.",
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), comment="Assigned category. NULL until categorized."
    )
    installment_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("installment_plans.id"),
        comment="Reference to the MSI plan if this transaction is an installment payment.",
    )
    date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="Transaction date as reported by the bank."
    )
    description: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="Raw description exactly as it appears in the PDF."
    )
    merchant: Mapped[str | None] = mapped_column(
        String(200), comment="Normalized merchant name after post-processing."
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="Amount in the original transaction currency."
    )
    amount_mxn: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Amount converted to MXN for cross-account aggregations.",
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="MXN", comment="ISO 4217 currency code of the original transaction."
    )
    transaction_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment=f"Movement type. Valid values: {_TRANSACTION_TYPES}."
    )
    bank_reference: Mapped[str | None] = mapped_column(
        String(100), comment="Bank's own unique identifier for this movement."
    )
    is_internal_transfer: Mapped[bool] = mapped_column(
        default=False,
        comment=(
            "True when the counterpart CLABE matches a known account. "
            "Detected by comparing to_clabe against accounts.clabe — never by name."
        ),
    )

    account: Mapped[Account] = relationship(back_populates="transactions")
    statement: Mapped[Statement] = relationship(back_populates="transactions")
    category: Mapped[Category | None] = relationship(back_populates="transactions")
    installment_plan: Mapped[InstallmentPlan | None] = relationship(back_populates="transactions")
