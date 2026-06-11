"""add_counterpart_fields_to_transactions_drop_from_transfers

Revision ID: ce04c1824c45
Revises: 3da8d576b83f
Create Date: 2026-06-10 23:02:34.126591

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ce04c1824c45"
down_revision: str | Sequence[str] | None = "3da8d576b83f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # ADD COLUMN on transactions — autogenerate handles this cleanly
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("counterpart_identifier", sa.String(length=20), nullable=True)
        )
        batch_op.add_column(
            sa.Column("counterpart_identifier_type", sa.String(length=20), nullable=True)
        )

    # Recreate transfers without counterpart columns and without ck_transfer_identifier_type.
    # batch_alter_table cannot drop the CHECK constraint because it is reflected from the DB
    # and tries to recreate the table with it even after dropping the columns.
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
            currency VARCHAR(3) NOT NULL,
            date DATE NOT NULL,
            transfer_type VARCHAR(10) NOT NULL,
            from_account_id INTEGER,
            to_account_id INTEGER,
            PRIMARY KEY (id),
            CONSTRAINT ck_transfer_type
                CHECK (transfer_type IN ('internal', 'outgoing', 'incoming')),
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
    op.execute(
        """
        INSERT INTO transfers (
            id, source_transaction_id, destination_transaction_id,
            spei_tracking_key, spei_reference, amount, currency, date,
            transfer_type, from_account_id, to_account_id
        )
        SELECT
            id, source_transaction_id, destination_transaction_id,
            spei_tracking_key, spei_reference, amount,
            COALESCE(currency, 'MXN'), date,
            transfer_type, from_account_id, to_account_id
        FROM transfers_old
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
    op.execute(
        """
        INSERT INTO transfers (
            id, source_transaction_id, destination_transaction_id,
            spei_tracking_key, spei_reference, amount, currency, date,
            transfer_type, from_account_id, to_account_id
        )
        SELECT
            id, source_transaction_id, destination_transaction_id,
            spei_tracking_key, spei_reference, amount, currency, date,
            transfer_type, from_account_id, to_account_id
        FROM transfers_new
        """
    )
    op.execute("DROP TABLE transfers_new")
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

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_column("counterpart_identifier_type")
        batch_op.drop_column("counterpart_identifier")
