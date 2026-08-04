"""supervisor reasoning compliance fields

Revision ID: 0006_supervisor_compliance
Revises: 0005_ai_reasoning_engine
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_supervisor_compliance"
down_revision = "0005_ai_reasoning_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_reasoning_revisions", sa.Column("parent_reasoning_revision_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("ai_reasoning_revisions.id"), nullable=True))
    op.add_column("ai_reasoning_revisions", sa.Column("proposal_revision_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("proposal_revisions.id"), nullable=True))
    op.add_column("ai_reasoning_revisions", sa.Column("candidate_before", postgresql.JSONB(), nullable=True))
    op.add_column("ai_reasoning_revisions", sa.Column("candidate_after", postgresql.JSONB(), nullable=True))
    op.add_column("ai_reasoning_revisions", sa.Column("changed_fields", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("ai_reasoning_revisions", sa.Column("watcher_results", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("ai_reasoning_revisions", sa.Column("validation_results", postgresql.JSONB(), nullable=True))
    op.add_column("ai_reasoning_revisions", sa.Column("ai_confidence", sa.Float(), nullable=True))
    op.add_column("ai_reasoning_revisions", sa.Column("calculated_confidence", sa.Float(), nullable=True))
    op.add_column("ai_reasoning_revisions", sa.Column("trust_score", sa.Float(), nullable=True))
    op.add_column("ai_reasoning_revisions", sa.Column("recommendation", sa.String(length=50), nullable=True))
    op.add_column("ai_reasoning_revisions", sa.Column("stopping_decision", sa.String(length=100), nullable=True))
    op.add_column("ai_reasoning_revisions", sa.Column("stopping_reason", sa.String(length=200), nullable=True))
    op.add_column("ai_reasoning_revisions", sa.Column("route_selected", sa.String(length=100), nullable=True))

    op.add_column("cti_consumption_records", sa.Column("requested_misp_event_id", sa.String(length=100), nullable=True))
    op.add_column("cti_consumption_records", sa.Column("resolved_misp_event_id", sa.String(length=100), nullable=True))
    op.add_column("cti_consumption_records", sa.Column("trigger_mode", sa.String(length=50), nullable=True))
    op.add_column("cti_consumption_records", sa.Column("skip_reason", sa.Text(), nullable=True))
    op.add_column("cti_consumption_records", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.add_column("cti_consumption_records", sa.Column("error_code", sa.String(length=100), nullable=True))
    op.add_column("cti_consumption_records", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("cti_consumption_records", sa.Column("requested_at", sa.DateTime(), nullable=True))
    op.add_column("cti_consumption_records", sa.Column("completed_at", sa.DateTime(), nullable=True))
    op.execute("update cti_consumption_records set requested_misp_event_id = misp_event_id, resolved_misp_event_id = misp_event_id, trigger_mode = strategy, requested_at = created_at, completed_at = coalesce(consumed_at, created_at)")
    op.create_index("ix_cti_consumption_idempotency_key", "cti_consumption_records", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_cti_consumption_idempotency_key", table_name="cti_consumption_records")
    for column in ["completed_at", "requested_at", "idempotency_key", "error_code", "failure_reason", "skip_reason", "trigger_mode", "resolved_misp_event_id", "requested_misp_event_id"]:
        op.drop_column("cti_consumption_records", column)
    for column in ["route_selected", "stopping_reason", "stopping_decision", "recommendation", "trust_score", "calculated_confidence", "ai_confidence", "validation_results", "watcher_results", "changed_fields", "candidate_after", "candidate_before", "proposal_revision_id", "parent_reasoning_revision_id"]:
        op.drop_column("ai_reasoning_revisions", column)
