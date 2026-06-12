from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finances.core.database import Base

if TYPE_CHECKING:
    from finances.models.transaction import Transaction

_TRANSFER_TYPES = "internal, outgoing, incoming"


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint(
            "transfer_type IN ('internal', 'outgoing', 'incoming')",
            name="ck_transfer_type",
        ),
        Index("ix_transfer_source_transaction", "source_transaction_id"),
        Index("ix_transfer_destination_transaction", "destination_transaction_id"),
        Index("ix_transfer_type", "transfer_type"),
        {
            "comment": (
                "One record per logical movement (not per transaction). "
                "source_transaction_id = outgoing side, "
                "destination_transaction_id = incoming side. "
                "Either side can be NULL if only one PDF has been imported. "
                f"transfer_type valid values: {_TRANSFER_TYPES}."
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
    transfer_type: Mapped[str] = mapped_column(
        comment=f"Direction. Valid values: {_TRANSFER_TYPES}.",
    )

    source_transaction: Mapped[Transaction | None] = relationship(
        foreign_keys=[source_transaction_id]
    )
    destination_transaction: Mapped[Transaction | None] = relationship(
        foreign_keys=[destination_transaction_id]
    )
