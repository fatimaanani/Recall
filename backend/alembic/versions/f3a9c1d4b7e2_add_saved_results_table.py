"""add saved_results table

Revision ID: f3a9c1d4b7e2
Revises: d0ef68206cdf
Create Date: 2026-08-05 00:00:00.000000

Adds saved_results for bookmarking a search result. Deliberately doesn't
duplicate video_id or generated_clip_id onto this table -- a saved
scene's video and clip are always reachable via search_results (one
join each).

Both FKs are ON DELETE CASCADE: deleting a user deletes their saved
rows, and deleting a search_result deletes any saved rows pointing at
it, matching how generated_clips already cascades from search_results.
No FK to generated_clips -- the requirement that a result already have a
clip before it can be saved is enforced at the service layer instead.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a9c1d4b7e2'
down_revision: Union[str, None] = 'd0ef68206cdf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'saved_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('search_result_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['search_result_id'], ['search_results.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'search_result_id', name='uq_saved_results_user_result'),
    )


def downgrade() -> None:
    op.drop_table('saved_results')
