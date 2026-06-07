from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finances.core.database import Base

if TYPE_CHECKING:
    from finances.models.account import Account
    from finances.models.transaction import Transaction

_TRANSFER_TYPES = "internal, outgoing, incoming"
_IDENTIFIER_TYPES = "clabe, card, account_number, unknown"


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint(
            "transfer_type IN ('internal', 'outgoing', 'incoming')",
            name="ck_transfer_type",
        ),
        CheckConstraint(
            "counterpart_identifier_type IN ('clabe', 'card', 'account_number', 'unknown')",
            name="ck_transfer_identifier_type",
        ),
        Index("ix_transfer_source_transaction", "source_transaction_id"),
        Index("ix_transfer_destination_transaction", "destination_transaction_id"),
        Index("ix_transfer_spei_key", "spei_tracking_key"),
        Index("ix_transfer_type", "transfer_type"),
        {
            "comment": (
                "One record per logical movement (not per transaction). "
                "source_transaction_id = outgoing side, "
                "destination_transaction_id = incoming side. "
                "Either side can be NULL if only one PDF has been imported. "
                f"transfer_type valid values: {_TRANSFER_TYPES}. "
                f"counterpart_identifier_type valid values: {_IDENTIFIER_TYPES}."
            )
        },
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", name="fk_transfer_source"),
        comment="Transaction on the outgoing side (amount < 0). NULL if not yet imported.",
    )
    destination_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", name="fk_transfer_dest"),
        comment="Transaction on the incoming side (amount > 0). NULL if not yet imported.",
    )
    spei_tracking_key: Mapped[str | None] = mapped_column(
        String(30),
        comment=(
            "BANXICO global unique tracking key (up to 30 chars). "
            "Nu sends with prefix 'NU39', MercadoPago with 'CPO'. "
            "Nu↔MP matching: Nu.spei_tracking_key == 'CPO' + MP.bank_reference."
        ),
    )
    spei_reference: Mapped[str | None] = mapped_column(
        String(10),
        comment="Short numeric reference chosen by the sender (up to 10 digits).",
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="Absolute transfer amount in original currency."
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="MXN", comment="ISO 4217 currency code."
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, comment="Transfer date.")
    transfer_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment=f"Direction. Valid values: {_TRANSFER_TYPES}.",
    )
    from_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", name="fk_transfer_from_account"),
        comment="Sending account if it belongs to the user. NULL if external.",
    )
    to_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", name="fk_transfer_to_account"),
        comment="Receiving account if it belongs to the user. NULL if external.",
    )
    counterpart_identifier: Mapped[str | None] = mapped_column(
        String(20),
        comment="CLABE, card number, or account number of the external counterpart.",
    )
    counterpart_identifier_type: Mapped[str | None] = mapped_column(
        String(20),
        comment=f"Type of counterpart_identifier. Valid values: {_IDENTIFIER_TYPES}.",
    )

    source_transaction: Mapped[Transaction | None] = relationship(
        foreign_keys=[source_transaction_id]
    )
    destination_transaction: Mapped[Transaction | None] = relationship(
        foreign_keys=[destination_transaction_id]
    )
    from_account: Mapped[Account | None] = relationship(foreign_keys=[from_account_id])
    to_account: Mapped[Account | None] = relationship(foreign_keys=[to_account_id])
