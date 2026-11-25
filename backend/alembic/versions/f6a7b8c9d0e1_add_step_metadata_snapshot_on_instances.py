"""Add step metadata snapshot to step_instances

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('step_instances', sa.Column('step_title', sa.String(length=255), nullable=False, server_default=''))
    op.add_column('step_instances', sa.Column('step_type', sa.String(length=50), nullable=False, server_default=''))
    op.add_column('step_instances', sa.Column('step_description', sa.Text(), nullable=False, server_default=''))
    op.add_column('step_instances', sa.Column('step_definition', sa.JSON(), nullable=True))

    # Backfill existing instances from their (still-linked) workflow steps.
    op.execute(
        """
        UPDATE step_instances AS si
        SET step_title = COALESCE(ws.title, ws.step_type, ''),
            step_type = COALESCE(ws.step_type, ''),
            step_description = COALESCE(ws.description, ''),
            step_definition = ws.definition
        FROM workflow_steps AS ws
        WHERE si.step_id = ws.id
        """
    )


def downgrade() -> None:
    op.drop_column('step_instances', 'step_definition')
    op.drop_column('step_instances', 'step_description')
    op.drop_column('step_instances', 'step_type')
    op.drop_column('step_instances', 'step_title')
