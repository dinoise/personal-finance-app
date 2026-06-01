from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finances.core.database import Base

_BANKS = "nu, bbva, banamex, mercadopago"
_ACCOUNT_TYPES = "credit, debit"


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("bank IN ('nu', 'bbva', 'banamex', 'mercadopago')", name="ck_account_bank"),
        CheckConstraint("account_type IN ('credit', 'debit')", name="ck_account_type"),
        {"comment": "Catalog of all bank accounts. CLABE is the natural unique identifier."},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bank: Mapped[str] = mapped_column(
        String(20), nullable=False, comment=f"Bank identifier. Valid values: {_BANKS}"
    )
    account_type: Mapped[str] = mapped_column(
        String(10), nullable=False, comment=f"Account type. Valid values: {_ACCOUNT_TYPES}"
    )
    clabe: Mapped[str | None] = mapped_column(
        String(18),
        unique=True,
        comment="18-digit CLABE — natural unique key. NULL for cards without CLABE.",
    )
    account_number: Mapped[str | None] = mapped_column(
        String(30), comment="Internal account number assigned by the bank."
    )
    last4: Mapped[str | None] = mapped_column(
        String(4), comment="Last 4 digits of the card. Only populated for credit accounts."
    )
    alias: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Human-readable label, e.g. 'Nu Debit CDMX'."
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="MXN", comment="ISO 4217 currency code. Defaults to MXN."
    )
    credit_limit: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), comment="Credit limit in MXN. NULL for debit accounts."
    )
    is_active: Mapped[bool] = mapped_column(
        default=True, comment="Set to False to archive the account without deleting its data."
    )

    statements: Mapped[list["Statement"]] = relationship(back_populates="account")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")  # type: ignore[name-defined]  # noqa: F821


class Statement(Base):
    __tablename__ = "statements"
    __table_args__ = (
        UniqueConstraint("account_id", "period_start", "period_end", name="uq_statement_period"),
        Index("ix_statement_account_period", "account_id", "period_start", "period_end"),
        {"comment": "One record per imported PDF. Prevents importing the same period twice."},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"), nullable=False, comment="Account this statement belongs to."
    )
    period_start: Mapped[date] = mapped_column(
        Date, nullable=False, comment="Start of the billing period."
    )
    period_end: Mapped[date] = mapped_column(
        Date, nullable=False, comment="End of the billing period / cutoff date."
    )
    payment_due_date: Mapped[date | None] = mapped_column(
        Date, comment="Payment due date. Only populated for credit accounts."
    )
    opening_balance: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), comment="Balance at the start of the period."
    )
    closing_balance: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        comment="Balance at the end of the period / amount to avoid interest charges.",
    )
    minimum_payment: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), comment="Minimum payment required. Only populated for credit accounts."
    )
    file_path: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="Absolute path to the original PDF on disk."
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), comment="Timestamp when this statement was imported."
    )

    account: Mapped["Account"] = relationship(back_populates="statements")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="statement")  # type: ignore[name-defined]  # noqa: F821
