"""make transcript_segments.search_vector a generated column + GIN index

Revision ID: d0ef68206cdf
Revises: a4e1c7f92b3d
Create Date: 2026-08-03 00:00:00.000000

search_vector was a plain nullable TSVECTOR column that nothing ever
wrote to. This converts it into a database-generated STORED column
(GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED), so Postgres
recomputes it synchronously on every INSERT/UPDATE and it can't drift
out of sync the way an application-side or trigger-based approach could.

'simple' rather than 'english' or 'arabic': transcripts mix English and
Arabic, sometimes within the same segment, and a single to_tsvector()
call can only apply one language's rules to the whole input -- 'simple'
is the only option that behaves predictably for both.

The 2-argument to_tsvector('simple', text) form is used because
generated-column expressions must be immutable, and the 1-argument form
depends on a session-level setting.

The column is dropped and re-added rather than altered in place, since
Postgres has no ALTER TABLE ... ADD GENERATED for an existing column;
safe here because search_vector was never populated, so there's no data
to lose. The ADD COLUMN statement itself backfills every existing row.

Adds a GIN index, the standard index type for tsvector queries, since
search_vector previously had none.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd0ef68206cdf'
down_revision: Union[str, None] = 'a4e1c7f92b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Never written to -- dropping loses nothing.
    op.drop_column('transcript_segments', 'search_vector')
    op.add_column(
        'transcript_segments',
        sa.Column(
            'search_vector',
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', text)", persisted=True),
            nullable=True,
        ),
    )
    # The ADD COLUMN above computes this for every existing row -- that is the backfill.
    op.create_index(
        'ix_transcript_segments_search_vector',
        'transcript_segments',
        ['search_vector'],
        postgresql_using='gin',
    )


def downgrade() -> None:
    op.drop_index('ix_transcript_segments_search_vector', table_name='transcript_segments')
    op.drop_column('transcript_segments', 'search_vector')
    # Restores the original plain nullable TSVECTOR column; nothing is lost
    # since the generated values are always recomputable from text.
    op.add_column(
        'transcript_segments',
        sa.Column('search_vector', postgresql.TSVECTOR(), nullable=True),
    )
