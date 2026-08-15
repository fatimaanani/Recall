"""add videos.has_embeddings

Revision ID: a4e1c7f92b3d
Revises: 8c5ed0e4b380
Create Date: 2026-08-02 00:00:00.000000

Adds videos.has_embeddings, set once every transcript_segments row for a
video has a populated embedding. Deliberately not a new MediaStatus
value -- a video is already usable for search methods that don't need
embeddings before this flag is set, the same way has_subtitles works.

Uses a transient server_default to satisfy NOT NULL for existing rows,
then drops it so the column's final shape matches has_subtitles and
every other boolean column in this schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4e1c7f92b3d'
down_revision: Union[str, None] = '8c5ed0e4b380'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'videos',
        sa.Column(
            'has_embeddings', sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column('videos', 'has_embeddings', server_default=None)


def downgrade() -> None:
    op.drop_column('videos', 'has_embeddings')
