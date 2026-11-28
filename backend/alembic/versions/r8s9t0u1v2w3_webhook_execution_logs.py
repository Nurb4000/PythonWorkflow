"""Add webhook execution log table (M4)

Stores one row per inbound webhook invocation or outbound delivery attempt so
operators can inspect responses, retries and idempotency keys from the admin
dashboard instead of digging through run logs / raw DB tables.

This revision also merges the two pre-existing Alembic heads
(``p6q7r8s9t0u1`` and ``q7r8s9t0u1v2``) into a single head.

Revision ID: r8s9t0u1v2w3
Revises: p6q7r8s9t0u1, q7r8s9t0u1v2
Create Date: 2026-11-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "r8s9t0u1v2w3"
down_revision: Union[str, tuple, None] = ("p6q7r8s9t0u1", "q7r8s9t0u1v2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'webhook_logs')"
        )
    ).scalar()
    if exists:
        return

    op.create_table(
        "webhook_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("workflow_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("endpoint", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("method", sa.String(length=10), nullable=False, server_default="POST"),
        sa.Column("source_ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("will_retry", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("response_snippet", sa.Text(), nullable=False, server_default=""),
        sa.Column("request_payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
    )
    for name, columns in (
        ("ix_webhook_logs_id", ["id"]),
        ("ix_webhook_logs_direction", ["direction"]),
        ("ix_webhook_logs_event_type", ["event_type"]),
        ("ix_webhook_logs_status", ["status"]),
        ("ix_webhook_logs_success", ["success"]),
        ("ix_webhook_logs_workflow_id", ["workflow_id"]),
        ("ix_webhook_logs_run_id", ["run_id"]),
        ("ix_webhook_logs_tenant_id", ["tenant_id"]),
        ("ix_webhook_logs_idempotency_key", ["idempotency_key"]),
        ("ix_webhook_logs_created_at", ["created_at"]),
        ("ix_webhook_logs_created_direction", ["created_at", "direction"]),
        ("ix_webhook_logs_workflow_created", ["workflow_id", "created_at"]),
        ("ix_webhook_logs_event_created", ["event_type", "created_at"]),
    ):
        op.create_index(name, "webhook_logs", columns, unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'webhook_logs')"
        )
    ).scalar()
    if not exists:
        return

    for name in (
        "ix_webhook_logs_event_created",
        "ix_webhook_logs_workflow_created",
        "ix_webhook_logs_created_direction",
        "ix_webhook_logs_created_at",
        "ix_webhook_logs_idempotency_key",
        "ix_webhook_logs_tenant_id",
        "ix_webhook_logs_run_id",
        "ix_webhook_logs_workflow_id",
        "ix_webhook_logs_success",
        "ix_webhook_logs_status",
        "ix_webhook_logs_event_type",
        "ix_webhook_logs_direction",
        "ix_webhook_logs_id",
    ):
        op.drop_index(name, table_name="webhook_logs")
    op.drop_table("webhook_logs")
