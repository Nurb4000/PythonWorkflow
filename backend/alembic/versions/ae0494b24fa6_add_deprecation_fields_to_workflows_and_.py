"""add_deprecation_fields_to_workflows_and_forms

Revision ID: ae0494b24fa6
Revises: 7d66f11b8ee2
Create Date: 2026-08-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'ae0494b24fa6'
down_revision: Union[str, None] = '7d66f11b8ee2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Workflows
    op.add_column('workflows', sa.Column('is_deprecated', sa.Boolean(), server_default='false'))
    op.add_column('workflows', sa.Column('deprecated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('workflows', sa.Column('deprecated_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.add_column('workflows', sa.Column('suggested_replacement_id', sa.Integer(), sa.ForeignKey('workflows.id'), nullable=True))
    
    # Forms
    op.add_column('forms', sa.Column('is_deprecated', sa.Boolean(), server_default='false'))
    op.add_column('forms', sa.Column('deprecated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('forms', sa.Column('deprecated_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.add_column('forms', sa.Column('suggested_replacement_id', sa.Integer(), sa.ForeignKey('forms.id'), nullable=True))


def downgrade() -> None:
    op.drop_column('forms', 'suggested_replacement_id')
    op.drop_column('forms', 'deprecated_by_id')
    op.drop_column('forms', 'deprecated_at')
    op.drop_column('forms', 'is_deprecated')
    op.drop_column('workflows', 'suggested_replacement_id')
    op.drop_column('workflows', 'deprecated_by_id')
    op.drop_column('workflows', 'deprecated_at')
    op.drop_column('workflows', 'is_deprecated')
