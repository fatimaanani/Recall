"""create remaining erd tables

Revision ID: 9cf9f584de16
Revises: 3ffee117a0ad
Create Date: 2026-07-16 12:00:00.000000

Adds the twelve remaining ERD tables in foreign-key dependency order.

Postgres ENUM types are named, shared objects, not scoped to one table:
subtitle_source already exists (from the previous migration) and is
reused here with create_type=False; search_type and search_scope are
each created once and reused the same way for their second table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9cf9f584de16'
down_revision: Union[str, None] = '3ffee117a0ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # transcript_segments.embedding is a pgvector column; the extension
    # must exist before that table is created.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table('password_reset_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=255), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )

    op.create_table('categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'name', name='uq_categories_user_id_name')
    )

    op.create_table('video_categories',
    sa.Column('video_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('assigned_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('video_id', 'category_id')
    )

    op.create_table('transcript_segments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('video_id', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.Float(), nullable=False),
    sa.Column('end_time', sa.Float(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('embedding', Vector(384), nullable=True),
    sa.Column('search_vector', postgresql.TSVECTOR(), nullable=True),
    sa.Column('source', postgresql.ENUM('UPLOADED', 'EMBEDDED', 'WHISPER', 'NONE', name='subtitle_source', create_type=False), nullable=False),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('audio_fingerprints',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('video_id', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.Float(), nullable=False),
    sa.Column('end_time', sa.Float(), nullable=False),
    sa.Column('fingerprint_hash', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('search_queries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('query_text', sa.Text(), nullable=True),
    sa.Column('original_audio_filename', sa.String(length=255), nullable=True),
    sa.Column('audio_query_path', sa.String(length=1000), nullable=True),
    sa.Column('transcribed_text', sa.Text(), nullable=True),
    sa.Column('query_type', sa.Enum('EXACT_TEXT', 'SEMANTIC', 'SPEECH_TO_TEXT', 'AUDIO_FINGERPRINT', name='search_type'), nullable=False),
    sa.Column('search_scope', sa.Enum('MY_LIBRARY', 'SHARED_LIBRARY', 'BOTH', name='search_scope'), nullable=False),
    sa.Column('results_found', sa.Integer(), nullable=False),
    sa.Column('response_time_ms', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('search_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('query_id', sa.Integer(), nullable=False),
    sa.Column('video_id', sa.Integer(), nullable=False),
    sa.Column('transcript_segment_id', sa.Integer(), nullable=True),
    sa.Column('matched_start_time', sa.Float(), nullable=True),
    sa.Column('matched_end_time', sa.Float(), nullable=True),
    sa.Column('matched_text', sa.Text(), nullable=True),
    sa.Column('confidence_score', sa.Float(), nullable=False),
    sa.Column('keyword_score', sa.Float(), nullable=True),
    sa.Column('semantic_score', sa.Float(), nullable=True),
    sa.Column('fingerprint_score', sa.Float(), nullable=True),
    sa.Column('rank_position', sa.Integer(), nullable=False),
    sa.Column('selected_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['query_id'], ['search_queries.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['transcript_segment_id'], ['transcript_segments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('query_id', 'rank_position', name='uq_search_results_query_rank')
    )

    op.create_table('generated_clips',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('result_id', sa.Integer(), nullable=False),
    sa.Column('video_id', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.Float(), nullable=False),
    sa.Column('end_time', sa.Float(), nullable=False),
    sa.Column('clip_path', sa.String(length=1000), nullable=False),
    sa.Column('clip_url', sa.String(length=1000), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['result_id'], ['search_results.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('result_id')
    )

    op.create_table('processing_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('video_id', sa.Integer(), nullable=False),
    sa.Column('process_type', sa.String(length=100), nullable=False),
    sa.Column('status', sa.Enum('STARTED', 'COMPLETED', 'FAILED', name='processing_status'), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('error_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('search_query_id', sa.Integer(), nullable=True),
    sa.Column('search_result_id', sa.Integer(), nullable=True),
    sa.Column('video_id', sa.Integer(), nullable=True),
    sa.Column('error_source', sa.String(length=100), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['search_query_id'], ['search_queries.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['search_result_id'], ['search_results.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('evaluation_test_cases',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_by_admin_id', sa.Integer(), nullable=True),
    sa.Column('test_name', sa.String(length=255), nullable=False),
    sa.Column('query_text', sa.Text(), nullable=True),
    sa.Column('audio_query_path', sa.String(length=1000), nullable=True),
    sa.Column('search_type', postgresql.ENUM('EXACT_TEXT', 'SEMANTIC', 'SPEECH_TO_TEXT', 'AUDIO_FINGERPRINT', name='search_type', create_type=False), nullable=False),
    sa.Column('search_scope', postgresql.ENUM('MY_LIBRARY', 'SHARED_LIBRARY', 'BOTH', name='search_scope', create_type=False), nullable=False),
    sa.Column('expected_video_id', sa.Integer(), nullable=False),
    sa.Column('expected_start_time', sa.Float(), nullable=False),
    sa.Column('expected_end_time', sa.Float(), nullable=False),
    sa.Column('timestamp_tolerance_seconds', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_admin_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['expected_video_id'], ['videos.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('evaluation_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('test_case_id', sa.Integer(), nullable=False),
    sa.Column('search_query_id', sa.Integer(), nullable=True),
    sa.Column('top_result_id', sa.Integer(), nullable=True),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.Column('accuracy_score', sa.Float(), nullable=True),
    sa.Column('precision_at_k', sa.Float(), nullable=True),
    sa.Column('recall_at_k', sa.Float(), nullable=True),
    sa.Column('reciprocal_rank', sa.Float(), nullable=True),
    sa.Column('response_time_ms', sa.Float(), nullable=True),
    sa.Column('evaluated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['search_query_id'], ['search_queries.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['test_case_id'], ['evaluation_test_cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['top_result_id'], ['search_results.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('evaluation_results')
    op.drop_table('evaluation_test_cases')
    op.drop_table('error_logs')
    op.drop_table('processing_logs')
    op.drop_table('generated_clips')
    op.drop_table('search_results')
    op.drop_table('search_queries')
    op.drop_table('audio_fingerprints')
    op.drop_table('transcript_segments')
    op.drop_table('video_categories')
    op.drop_table('categories')
    op.drop_table('password_reset_tokens')

    # search_type/search_scope were created by this migration; subtitle_source
    # already existed and must NOT be dropped here.
    postgresql.ENUM(name='search_scope').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='search_type').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='processing_status').drop(op.get_bind(), checkfirst=True)
