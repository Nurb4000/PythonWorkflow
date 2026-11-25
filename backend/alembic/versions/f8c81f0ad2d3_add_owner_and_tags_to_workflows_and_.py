"""add_owner_and_tags_to_workflows_and_forms

Revision ID: f8c81f0ad2d3
Revises: j0k1l2m3n4o5
Create Date: 2026-08-24 23:12:40.323258

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8c81f0ad2d3'
down_revision: Union[str, None] = 'j0k1l2m3n4o5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add owner_user_id and tags to workflows
    op.add_column('workflows', sa.Column('owner_user_id', sa.Integer(), nullable=True))
    op.add_column('workflows', sa.Column('tags', sa.JSON(), server_default='[]'))
    op.create_index('ix_workflows_owner_user_id', 'workflows', ['owner_user_id'])
    
    # Add owner_user_id and tags to forms
    op.add_column('forms', sa.Column('owner_user_id', sa.Integer(), nullable=True))
    op.add_column('forms', sa.Column('tags', sa.JSON(), server_default='[]'))
    op.create_index('ix_forms_owner_user_id', 'forms', ['owner_user_id'])


def downgrade() -> None:
    op.drop_index('ix_forms_owner_user_id', table_name='forms')
    op.drop_column('forms', 'tags')
    op.drop_column('forms', 'owner_user_id')
    
    op.drop_index('ix_workflows_owner_user_id', table_name='workflows')
    op.drop_column('workflows', 'tags')
    op.drop_column('workflows', 'owner_user_id')
