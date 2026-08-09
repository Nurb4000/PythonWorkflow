"""Add form_uploads audit table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-08 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'form_uploads',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('original_name', sa.String(length=255), nullable=False),
        sa.Column('stored_name', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=255), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], name='form_uploads_uploaded_by_fkey'),
    )
    op.create_index('ix_form_uploads_id', 'form_uploads', ['id'])
    op.create_index('ix_form_uploads_stored_name', 'form_uploads', ['stored_name'], unique=True)
    op.create_index('ix_form_uploads_uploaded_by', 'form_uploads', ['uploaded_by'])


def downgrade() -> None:
    op.drop_index('ix_form_uploads_uploaded_by', table_name='form_uploads')
    op.drop_index('ix_form_uploads_stored_name', table_name='form_uploads')
    op.drop_index('ix_form_uploads_id', table_name='form_uploads')
    op.drop_table('form_uploads')
