"""widen byte-count columns to bigint

Revision ID: 17ba62bc0a27
Revises: 9cf9f584de16
Create Date: 2026-07-17 09:30:00.000000

storage_limit_bytes and file_size_bytes could exceed PostgreSQL's plain
INTEGER range (e.g. the 50 GiB default storage limit), so both are
widened to BIGINT. Pure widening -- no data loss either direction.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17ba62bc0a27'
down_revision: Union[str, None] = '9cf9f584de16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'users', 'storage_limit_bytes',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )
    op.alter_column(
        'videos', 'file_size_bytes',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Explicit USING cast so a downgrade against out-of-range data fails loudly instead of truncating.
    op.alter_column(
        'videos', 'file_size_bytes',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using='file_size_bytes::integer',
    )
    op.alter_column(
        'users', 'storage_limit_bytes',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using='storage_limit_bytes::integer',
    )
