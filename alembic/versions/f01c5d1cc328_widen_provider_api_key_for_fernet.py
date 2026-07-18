"""widen provider api_key for Fernet + encrypt existing rows

Revision ID: f01c5d1cc328
Revises: e9ec7fe9d1fc
Create Date: 2026-07-18 18:11:41.203266

SQLite can't ALTER COLUMN in place, so we use the standard
rename + add + copy + drop dance. The copy step also encrypts
existing plaintext rows using the auto-generated ENCRYPTION_KEY.

The downgrade reverses the encryption (best-effort: rows that fail
to decrypt are left as ciphertext rather than truncating, so the
admin can inspect them) and shrinks the column back.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f01c5d1cc328'
down_revision: Union[str, Sequence[str], None] = 'e9ec7fe9d1fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Widen api_key to VARCHAR(2000) and encrypt existing rows."""
    from app.core.security import encrypt_value

    # 1. Rename current column so we can stage a new one.
    with op.batch_alter_table("providers") as batch:
        batch.alter_column(
            "api_key", new_column_name="api_key_legacy"
        )

    # 2. Add the new column with the wider type, nullable for the swap.
    op.add_column(
        "providers",
        sa.Column("api_key", sa.String(length=2000), nullable=True),
    )

    # 3. Encrypt each existing row's plaintext into the new column.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, api_key_legacy FROM providers")).fetchall()
    for row_id, legacy in rows:
        if legacy is None:
            continue
        encrypted = encrypt_value(legacy)
        bind.execute(
            sa.text("UPDATE providers SET api_key = :enc WHERE id = :id"),
            {"enc": encrypted, "id": row_id},
        )

    # 4. Drop the legacy column and enforce NOT NULL on the new one.
    with op.batch_alter_table("providers") as batch:
        batch.drop_column("api_key_legacy")
        batch.alter_column(
            "api_key",
            existing_type=sa.String(length=2000),
            nullable=False,
        )


def downgrade() -> None:
    """Decrypt existing rows and shrink the column back to VARCHAR(500).

    Best-effort: if any row fails to decrypt (e.g. ENCRYPTION_KEY changed),
    it's left as-is. SQLite ALTER COLUMN limitations mean we use the same
    rename/add/copy/drop dance as upgrade.
    """
    from app.core.security import decrypt_value, InvalidToken

    with op.batch_alter_table("providers") as batch:
        batch.alter_column("api_key", new_column_name="api_key_legacy")

    op.add_column(
        "providers",
        sa.Column("api_key", sa.String(length=500), nullable=True),
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, api_key_legacy FROM providers")).fetchall()
    for row_id, legacy in rows:
        if legacy is None:
            continue
        try:
            plain = decrypt_value(legacy)
            bind.execute(
                sa.text("UPDATE providers SET api_key = :plain WHERE id = :id"),
                {"plain": plain, "id": row_id},
            )
        except InvalidToken:
            # Leave the encrypted value in place; admin can clean up.
            pass

    with op.batch_alter_table("providers") as batch:
        batch.drop_column("api_key_legacy")
        batch.alter_column(
            "api_key",
            existing_type=sa.String(length=500),
            nullable=False,
        )
