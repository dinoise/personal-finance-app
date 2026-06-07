"""redesign_transfers_add_spei_to_transactions

Revision ID: 3da8d576b83f
Revises: 31bd6b3c156a
Create Date: 2026-06-07 01:48:27.640543

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3da8d576b83f"
down_revision: str | Sequence[str] | None = "31bd6b3c156a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add SPEI columns to transactions — autogenerate handles this cleanly
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("spei_tracking_key", sa.String(length=30), nullable=True)
        )
        batch_op.add_column(
            sa.Column("spei_reference", sa.String(length=10), nullable=True)
        )

    # Recreate transfers table from scratch using raw SQL.
    # batch_alter_table cannot drop the anonymous FK from the original schema
    # (autogenerate emits drop_constraint(None, ...) which fails at runtime).
    op.execute("PRAGMA foreign_keys=OFF")
    op.execute("ALTER TABLE transfers RENAME TO transfers_old")
    op.execute(
        """
        CREATE TABLE transfers (
            id INTEGER NOT NULL,
            source_transaction_id INTEGER,
            destination_transaction_id INTEGER,
            spei_tracking_key VARCHAR(30),
            spei_reference VARCHAR(10),
            amount NUMERIC(12, 2) NOT NULL,
            currency VARCHAR(3),
            date DATE NOT NULL,
            transfer_type VARCHAR(10) NOT NULL,
            from_account_id INTEGER,
            to_account_id INTEGER,
            counterpart_identifier VARCHAR(20),
            counterpart_identifier_type VARCHAR(20),
            PRIMARY KEY (id),
            CONSTRAINT ck_transfer_type
                CHECK (transfer_type IN ('internal', 'outgoing', 'incoming')),
            CONSTRAINT ck_transfer_identifier_type
                CHECK (counterpart_identifier_type
                       IN ('clabe', 'card', 'account_number', 'unknown')),
            CONSTRAINT fk_transfer_source
                FOREIGN KEY(source_transaction_id) REFERENCES transactions(id),
            CONSTRAINT fk_transfer_dest
                FOREIGN KEY(destination_transaction_id) REFERENCES transactions(id),
            CONSTRAINT fk_transfer_from_account
                FOREIGN KEY(from_account_id) REFERENCES accounts(id),
            CONSTRAINT fk_transfer_to_account
                FOREIGN KEY(to_account_id) REFERENCES accounts(id)
        )
        """
    )
    op.execute("DROP TABLE transfers_old")
    op.execute(
        "CREATE INDEX ix_transfer_source_transaction "
        "ON transfers (source_transaction_id)"
    )
    op.execute(
        "CREATE INDEX ix_transfer_destination_transaction "
        "ON transfers (destination_transaction_id)"
    )
    op.execute("CREATE INDEX ix_transfer_spei_key ON transfers (spei_tracking_key)")
    op.execute("CREATE INDEX ix_transfer_type ON transfers (transfer_type)")
    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("PRAGMA foreign_keys=OFF")
    op.execute("ALTER TABLE transfers RENAME TO transfers_new")
    op.execute(
        """
        CREATE TABLE transfers (
            id INTEGER NOT NULL,
            transaction_id INTEGER NOT NULL,
            spei_tracking_key VARCHAR(30),
            spei_reference VARCHAR(10),
            counterpart_bank_code VARCHAR(3),
            from_account_id INTEGER,
            from_external_name VARCHAR(200),
            to_account_id INTEGER,
            to_external_name VARCHAR(200),
            to_clabe VARCHAR(18),
            transfer_type VARCHAR(10) NOT NULL,
            amount NUMERIC(12, 2) NOT NULL,
            currency VARCHAR(3),
            amount_mxn NUMERIC(12, 2) NOT NULL,
            date DATE NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (spei_tracking_key),
            FOREIGN KEY(transaction_id) REFERENCES transactions(id),
            FOREIGN KEY(from_account_id) REFERENCES accounts(id),
            FOREIGN KEY(to_account_id) REFERENCES accounts(id)
        )
        """
    )
    op.execute("DROP TABLE transfers_new")
    op.execute(
        "CREATE UNIQUE INDEX uq_transfer_spei_tracking_key "
        "ON transfers (spei_tracking_key)"
    )
    op.execute(
        "CREATE INDEX ix_transfer_transaction ON transfers (transaction_id)"
    )
    op.execute("CREATE INDEX ix_transfer_to_clabe ON transfers (to_clabe)")
    op.execute("CREATE INDEX ix_transfer_type ON transfers (transfer_type)")
    op.execute("PRAGMA foreign_keys=ON")

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_column("spei_reference")
        batch_op.drop_column("spei_tracking_key")
