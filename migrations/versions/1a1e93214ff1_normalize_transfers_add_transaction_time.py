"""normalize_transfers_add_transaction_time

Revision ID: 1a1e93214ff1
Revises: ce04c1824c45
Create Date: 2026-06-12 00:35:13.987315

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1a1e93214ff1"
down_revision: str | Sequence[str] | None = "ce04c1824c45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Both tables are rebuilt with raw SQL under PRAGMA foreign_keys=OFF.
    # batch_alter_table cannot be used here: it internally DROPs and recreates
    # the table, which fails when another table holds a named FK pointing to it
    # (transfers → transactions), even if foreign_keys was set OFF beforehand
    # via op.execute() — Alembic opens its own sub-connection for the batch.
    op.execute("PRAGMA foreign_keys=OFF")

    # ── transactions ──────────────────────────────────────────────────────────
    # Add: time (nullable TIME, UTC)
    # Drop: is_internal_transfer (never used — info lives in transfers.transfer_type)
    op.execute("ALTER TABLE transactions RENAME TO transactions_old")
    op.execute("""
        CREATE TABLE transactions (
            id                       INTEGER NOT NULL,
            account_id               INTEGER NOT NULL,
            statement_id             INTEGER NOT NULL,
            category_id              INTEGER,
            installment_plan_id      INTEGER,
            date                     DATE NOT NULL,
            description              VARCHAR(500) NOT NULL,
            merchant                 VARCHAR(200),
            amount                   NUMERIC(12, 2) NOT NULL,
            amount_mxn               NUMERIC(12, 2) NOT NULL,
            currency                 VARCHAR(3) NOT NULL,
            transaction_type         VARCHAR(20) NOT NULL,
            bank_reference           VARCHAR(100),
            counterpart_identifier   VARCHAR(20),
            counterpart_identifier_type VARCHAR(20),
            spei_tracking_key        VARCHAR(30),
            spei_reference           VARCHAR(10),
            time                     TIME,
            PRIMARY KEY (id),
            CONSTRAINT ck_transaction_type
                CHECK (transaction_type IN ('charge', 'payment', 'refund', 'interest')),
            FOREIGN KEY (account_id)          REFERENCES accounts (id),
            FOREIGN KEY (statement_id)        REFERENCES statements (id),
            FOREIGN KEY (category_id)         REFERENCES categories (id),
            FOREIGN KEY (installment_plan_id) REFERENCES installment_plans (id)
        )
    """)
    op.execute("""
        INSERT INTO transactions (
            id, account_id, statement_id, category_id, installment_plan_id,
            date, description, merchant, amount, amount_mxn, currency,
            transaction_type, bank_reference, counterpart_identifier,
            counterpart_identifier_type, spei_tracking_key, spei_reference,
            time
        )
        SELECT
            id, account_id, statement_id, category_id, installment_plan_id,
            date, description, merchant, amount, amount_mxn, currency,
            transaction_type, bank_reference, counterpart_identifier,
            counterpart_identifier_type, spei_tracking_key, spei_reference,
            NULL
        FROM transactions_old
    """)
    op.execute("DROP TABLE transactions_old")
    op.execute(
        "CREATE INDEX ix_transaction_account_date ON transactions (account_id, date)"
    )
    op.execute("CREATE INDEX ix_transaction_category  ON transactions (category_id)")
    op.execute("CREATE INDEX ix_transaction_statement  ON transactions (statement_id)")
    op.execute("CREATE INDEX ix_transaction_date       ON transactions (date)")
    op.execute("CREATE INDEX ix_transaction_type       ON transactions (transaction_type)")

    # ── transfers ─────────────────────────────────────────────────────────────
    # Drop: amount, currency, date, spei_tracking_key, spei_reference,
    #       from_account_id, to_account_id  (all derivable from linked transactions)
    op.execute("ALTER TABLE transfers RENAME TO transfers_old")
    op.execute("""
        CREATE TABLE transfers (
            id                         INTEGER NOT NULL,
            source_transaction_id      INTEGER,
            destination_transaction_id INTEGER,
            transfer_type              VARCHAR NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT fk_transfer_source
                FOREIGN KEY (source_transaction_id) REFERENCES transactions (id),
            CONSTRAINT fk_transfer_dest
                FOREIGN KEY (destination_transaction_id) REFERENCES transactions (id),
            CONSTRAINT ck_transfer_type
                CHECK (transfer_type IN ('internal', 'outgoing', 'incoming'))
        )
    """)
    op.execute("""
        INSERT INTO transfers (id, source_transaction_id, destination_transaction_id, transfer_type)
        SELECT id, source_transaction_id, destination_transaction_id, transfer_type
        FROM transfers_old
    """)
    op.execute("DROP TABLE transfers_old")
    op.execute(
        "CREATE INDEX ix_transfer_source_transaction"
        " ON transfers (source_transaction_id)"
    )
    op.execute(
        "CREATE INDEX ix_transfer_destination_transaction"
        " ON transfers (destination_transaction_id)"
    )
    op.execute("CREATE INDEX ix_transfer_type ON transfers (transfer_type)")

    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")

    # ── transfers: restore removed columns ────────────────────────────────────
    op.execute("ALTER TABLE transfers RENAME TO transfers_old")
    op.execute("""
        CREATE TABLE transfers (
            id                         INTEGER NOT NULL,
            source_transaction_id      INTEGER,
            destination_transaction_id INTEGER,
            spei_tracking_key          VARCHAR(30),
            spei_reference             VARCHAR(10),
            amount                     NUMERIC(12, 2) NOT NULL DEFAULT 0,
            currency                   VARCHAR(3) NOT NULL DEFAULT 'MXN',
            date                       DATE NOT NULL DEFAULT '1970-01-01',
            transfer_type              VARCHAR NOT NULL,
            from_account_id            INTEGER,
            to_account_id              INTEGER,
            PRIMARY KEY (id),
            CONSTRAINT fk_transfer_source
                FOREIGN KEY (source_transaction_id) REFERENCES transactions (id),
            CONSTRAINT fk_transfer_dest
                FOREIGN KEY (destination_transaction_id) REFERENCES transactions (id),
            CONSTRAINT fk_transfer_from_account
                FOREIGN KEY (from_account_id) REFERENCES accounts (id),
            CONSTRAINT fk_transfer_to_account
                FOREIGN KEY (to_account_id) REFERENCES accounts (id),
            CONSTRAINT ck_transfer_type
                CHECK (transfer_type IN ('internal', 'outgoing', 'incoming'))
        )
    """)
    op.execute("""
        INSERT INTO transfers (
            id, source_transaction_id, destination_transaction_id, transfer_type
        )
        SELECT id, source_transaction_id, destination_transaction_id, transfer_type
        FROM transfers_old
    """)
    op.execute("DROP TABLE transfers_old")
    op.execute(
        "CREATE INDEX ix_transfer_source_transaction ON transfers (source_transaction_id)"
    )
    op.execute(
        "CREATE INDEX ix_transfer_destination_transaction"
        " ON transfers (destination_transaction_id)"
    )
    op.execute("CREATE INDEX ix_transfer_spei_key ON transfers (spei_tracking_key)")
    op.execute("CREATE INDEX ix_transfer_type ON transfers (transfer_type)")

    # ── transactions: restore is_internal_transfer, drop time ────────────────
    op.execute("ALTER TABLE transactions RENAME TO transactions_old")
    op.execute("""
        CREATE TABLE transactions (
            id                       INTEGER NOT NULL,
            account_id               INTEGER NOT NULL,
            statement_id             INTEGER NOT NULL,
            category_id              INTEGER,
            installment_plan_id      INTEGER,
            date                     DATE NOT NULL,
            description              VARCHAR(500) NOT NULL,
            merchant                 VARCHAR(200),
            amount                   NUMERIC(12, 2) NOT NULL,
            amount_mxn               NUMERIC(12, 2) NOT NULL,
            currency                 VARCHAR(3) NOT NULL,
            transaction_type         VARCHAR(20) NOT NULL,
            bank_reference           VARCHAR(100),
            counterpart_identifier   VARCHAR(20),
            counterpart_identifier_type VARCHAR(20),
            spei_tracking_key        VARCHAR(30),
            spei_reference           VARCHAR(10),
            is_internal_transfer     BOOLEAN NOT NULL DEFAULT 0,
            PRIMARY KEY (id),
            CONSTRAINT ck_transaction_type
                CHECK (transaction_type IN ('charge', 'payment', 'refund', 'interest')),
            FOREIGN KEY (account_id)          REFERENCES accounts (id),
            FOREIGN KEY (statement_id)        REFERENCES statements (id),
            FOREIGN KEY (category_id)         REFERENCES categories (id),
            FOREIGN KEY (installment_plan_id) REFERENCES installment_plans (id)
        )
    """)
    op.execute("""
        INSERT INTO transactions (
            id, account_id, statement_id, category_id, installment_plan_id,
            date, description, merchant, amount, amount_mxn, currency,
            transaction_type, bank_reference, counterpart_identifier,
            counterpart_identifier_type, spei_tracking_key, spei_reference,
            is_internal_transfer
        )
        SELECT
            id, account_id, statement_id, category_id, installment_plan_id,
            date, description, merchant, amount, amount_mxn, currency,
            transaction_type, bank_reference, counterpart_identifier,
            counterpart_identifier_type, spei_tracking_key, spei_reference,
            0
        FROM transactions_old
    """)
    op.execute("DROP TABLE transactions_old")
    op.execute(
        "CREATE INDEX ix_transaction_account_date ON transactions (account_id, date)"
    )
    op.execute("CREATE INDEX ix_transaction_category  ON transactions (category_id)")
    op.execute("CREATE INDEX ix_transaction_statement  ON transactions (statement_id)")
    op.execute("CREATE INDEX ix_transaction_date       ON transactions (date)")
    op.execute("CREATE INDEX ix_transaction_type       ON transactions (transaction_type)")

    op.execute("PRAGMA foreign_keys=ON")
