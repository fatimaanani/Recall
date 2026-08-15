"""add videos.file_checksum

Revision ID: 966affa2a5e3
Revises: 17ba62bc0a27
Create Date: 2026-07-22 10:00:00.000000

Adds a nullable videos.file_checksum (SHA-256 hex, 64 chars) for
content-based duplicate-upload detection. Not backfilled -- there's no
reliable way to compute a checksum for files uploaded before this column
existed, so those rows are simply excluded from duplicate comparisons.

A plain index, not a unique constraint: duplicate-detection scope
differs by role (own uploads for regular users vs. the whole shared
dataset for admins), so uniqueness is enforced at the application layer
instead (video_service.save_upload); this index just keeps that lookup fast.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '966affa2a5e3'
down_revision: Union[str, None] = '17ba62bc0a27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'videos',
        sa.Column('file_checksum', sa.String(length=64), nullable=True),
    )
    op.create_index(
        'ix_videos_file_checksum', 'videos', ['file_checksum'],
    )


def downgrade() -> None:
    op.drop_index('ix_videos_file_checksum', table_name='videos')
    op.drop_column('videos', 'file_checksum')
