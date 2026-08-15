"""add admin_messages table and evaluation_results.search_backend

Revision ID: 8c5ed0e4b380
Revises: 2bf07eb48745
Create Date: 2026-07-29 12:00:00.000000

Two independent, additive changes: an admin_messages table for
admin-to-admin messaging, and evaluation_results.search_backend (NOT
NULL enum, default 'postgresql') recording which backend produced a
given evaluation run. Scoped to evaluation_results only, since
search_queries represents real user searches that never touch
Elasticsearch.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8c5ed0e4b380'
down_revision: Union[str, None] = '2bf07eb48745'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Created explicitly (not left to op.add_column) so behavior doesn't
# depend on Alembic/SQLAlchemy version. Member names match SearchBackend's
# own names, not their lowercase .value strings.
search_backend_enum = postgresql.ENUM(
    'POSTGRESQL', 'ELASTICSEARCH', name='search_backend'
)


def upgrade() -> None:
    search_backend_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'evaluation_results',
        sa.Column(
            'search_backend',
            sa.Enum('POSTGRESQL', 'ELASTICSEARCH', name='search_backend', create_type=False),
            nullable=False,
            # Transient default satisfies NOT NULL for existing rows; dropped
            # below so new rows get their default from the ORM instead.
            server_default='POSTGRESQL',
        ),
    )
    op.alter_column('evaluation_results', 'search_backend', server_default=None)

    op.create_index(
        'ix_evaluation_results_test_case_search_backend',
        'evaluation_results',
        ['test_case_id', 'search_backend'],
    )

    op.create_table(
        'admin_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sender_admin_id', sa.Integer(), nullable=False),
        sa.Column('recipient_admin_id', sa.Integer(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sender_admin_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recipient_admin_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # Indexed on both FK columns since the eventual inbox/sent views will each filter on one of these.
    op.create_index('ix_admin_messages_sender_admin_id', 'admin_messages', ['sender_admin_id'])
    op.create_index('ix_admin_messages_recipient_admin_id', 'admin_messages', ['recipient_admin_id'])


def downgrade() -> None:
    op.drop_index('ix_admin_messages_recipient_admin_id', table_name='admin_messages')
    op.drop_index('ix_admin_messages_sender_admin_id', table_name='admin_messages')
    op.drop_table('admin_messages')

    op.drop_index('ix_evaluation_results_test_case_search_backend', table_name='evaluation_results')
    op.drop_column('evaluation_results', 'search_backend')
    search_backend_enum.drop(op.get_bind(), checkfirst=True)
