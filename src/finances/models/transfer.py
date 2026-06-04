from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finances.core.database import Base

_TRANSFER_TYPES = "internal, outgoing, incoming"


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        UniqueConstraint("spei_tracking_key", name="uq_transfer_spei_tracking_key"),
        CheckConstraint(
            "transfer_type IN ('internal', 'outgoing', 'incoming')",
            name="ck_transfer_type",
        ),
        Index("ix_transfer_transaction", "transaction_id"),
        Index("ix_transfer_to_clabe", "to_clabe"),
        Index("ix_transfer_type", "transfer_type"),
        {
            "comment": (
                "SPEI bank transfers with identifiable counterpart. "
                "Internal detection: compare to_clabe against accounts.clabe — never by name. "
                f"transfer_type valid values: {_TRANSFER_TYPES}."
            )
        },
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"),
        nullable=False,
        comment="Source transaction this transfer is linked to.",
    )
    spei_tracking_key: Mapped[str | None] = mapped_column(
        String(30),
        unique=True,
        comment=(
            "BANXICO global unique tracking key (up to 30 chars). "
            "Format by bank: BBVA starts with 'MBAN', Nu with 'NU39', Mercado Pago with 'CPO'."
        ),
    )
    spei_reference: Mapped[str | None] = mapped_column(
        String(10),
        comment="Short numeric reference chosen by the sender (up to 10 digits in practice).",
    )
    counterpart_bank_code: Mapped[str | None] = mapped_column(
        String(3),
        comment="First 3 digits of the counterpart CLABE. E.g. 722=MercadoPago, 638=Nu, 012=BBVA.",
    )
    from_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"),
        comment="Sending account if it belongs to the user. NULL if external.",
    )
    from_external_name: Mapped[str | None] = mapped_column(
        String(200), comment="Name of the external sender as reported by BANXICO."
    )
    to_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"),
        comment="Receiving account if it belongs to the user. NULL if external.",
    )
    to_external_name: Mapped[str | None] = mapped_column(
        String(200), comment="Name of the external beneficiary as reported by BANXICO."
    )
    to_clabe: Mapped[str | None] = mapped_column(
        String(18),
        comment=(
            "Destination CLABE — always 18 clean digits. "
            "For BBVA, the parser strips the '00' prefix from the 20-digit raw number."
        ),
    )
    transfer_type: Mapped[str] = mapped_column(
        String(10), nullable=False, comment=f"Transfer direction. Valid values: {_TRANSFER_TYPES}."
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="Amount in the original transaction currency."
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="MXN", comment="ISO 4217 currency code."
    )
    amount_mxn: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="Amount converted to MXN."
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, comment="Transfer date.")

    from_account: Mapped["Account | None"] = relationship(foreign_keys=[from_account_id])
    to_account: Mapped["Account | None"] = relationship(foreign_keys=[to_account_id])


from finances.models.account import Account  # noqa: E402
