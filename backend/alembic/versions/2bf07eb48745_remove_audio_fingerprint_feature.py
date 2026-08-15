"""remove audio fingerprint feature

Revision ID: 2bf07eb48745
Revises: 966affa2a5e3
Create Date: 2026-07-28 00:00:00.000000

Audio fingerprint search was removed from project scope. Drops the
audio_fingerprints table, videos.has_fingerprints, and
search_results.fingerprint_score, and rebuilds the search_type enum
without AUDIO_FINGERPRINT (Postgres has no ALTER TYPE ... DROP VALUE, so
the type has to be recreated and both columns using it cast over).

Downgrade restores the schema shape only, not data -- the feature was
never actually populated by any application code.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2bf07eb48745'
down_revision: Union[str, None] = '966affa2a5e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('audio_fingerprints')
    op.drop_column('videos', 'has_fingerprints')
    op.drop_column('search_results', 'fingerprint_score')

    # Both columns using this enum must be converted before the old type
    # is dropped -- Postgres refuses to drop a type still referenced by a column.
    op.execute(
        "CREATE TYPE search_type_new AS ENUM ('EXACT_TEXT', 'SEMANTIC', 'SPEECH_TO_TEXT')"
    )
    op.execute(
        "ALTER TABLE search_queries "
        "ALTER COLUMN query_type TYPE search_type_new "
        "USING query_type::text::search_type_new"
    )
    op.execute(
        "ALTER TABLE evaluation_test_cases "
        "ALTER COLUMN search_type TYPE search_type_new "
        "USING search_type::text::search_type_new"
    )
    op.execute("DROP TYPE search_type")
    op.execute("ALTER TYPE search_type_new RENAME TO search_type")


def downgrade() -> None:
    op.execute(
        "CREATE TYPE search_type_old AS ENUM "
        "('EXACT_TEXT', 'SEMANTIC', 'SPEECH_TO_TEXT', 'AUDIO_FINGERPRINT')"
    )
    op.execute(
        "ALTER TABLE search_queries "
        "ALTER COLUMN query_type TYPE search_type_old "
        "USING query_type::text::search_type_old"
    )
    op.execute(
        "ALTER TABLE evaluation_test_cases "
        "ALTER COLUMN search_type TYPE search_type_old "
        "USING search_type::text::search_type_old"
    )
    op.execute("DROP TYPE search_type")
    op.execute("ALTER TYPE search_type_old RENAME TO search_type")

    op.add_column(
        'search_results',
        sa.Column('fingerprint_score', sa.Float(), nullable=True),
    )

    # Transient server_default satisfies NOT NULL for existing rows, then
    # is dropped so the column's final shape has no server-level default.
    op.add_column(
        'videos',
        sa.Column(
            'has_fingerprints', sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column('videos', 'has_fingerprints', server_default=None)

    # Schema only, no data restored. Matches the original
    # create_remaining_erd_tables shape exactly, including its lack of
    # indexes on this table.
    op.create_table(
        'audio_fingerprints',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=False),
        sa.Column('fingerprint_hash', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
