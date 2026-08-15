"""add admin_audit_logs table

Revision ID: b1a2e4c88f01
Revises: f3a9c1d4b7e2
Create Date: 2026-08-08 00:00:00.000000

Adds a minimal admin audit log recording four action types: suspend,
reactivate, delete, promote.

actor_admin_id and target_user_id use ON DELETE SET NULL, not CASCADE,
since an audit row must survive the account deletions it's often
recording. actor_username/target_username are plain-text snapshots taken
at write time so the row stays meaningful once either FK goes null, and
are never updated afterward.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a2e4c88f01'
down_revision: Union[str, None] = 'f3a9c1d4b7e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'admin_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_admin_id', sa.Integer(), nullable=True),
        sa.Column('actor_username', sa.String(length=80), nullable=False),
        sa.Column('target_user_id', sa.Integer(), nullable=True),
        sa.Column('target_username', sa.String(length=80), nullable=False),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['actor_admin_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['target_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_admin_audit_logs_created_at', 'admin_audit_logs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_admin_audit_logs_created_at', table_name='admin_audit_logs')
    op.drop_table('admin_audit_logs')
