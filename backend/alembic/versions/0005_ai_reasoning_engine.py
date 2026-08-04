"""ai reasoning engine telemetry

Revision ID: 0005_ai_reasoning_engine
Revises: 0004_database_idempotency
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_ai_reasoning_engine"
down_revision = "0004_database_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_reasoning_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("workflows.id"), nullable=False),
        sa.Column("graph_run_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("graph_runs.id"), nullable=False, unique=True),
        sa.Column("cti_event_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("cti_events.id"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="running"),
        sa.Column("current_node", sa.String(length=100), nullable=True),
        sa.Column("current_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trust_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("approval_recommendation", sa.String(length=50), nullable=False, server_default="needs_review"),
        sa.Column("termination_reason", sa.String(length=200), nullable=True),
        sa.Column("session_summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "ai_reasoning_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("ai_reasoning_sessions.id"), nullable=False),
        sa.Column("graph_run_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("graph_runs.id"), nullable=False),
        sa.Column("behavior_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("behaviors.id"), nullable=True),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("proposals.id"), nullable=True),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("improvements", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("confidence_before", sa.Float(), nullable=True),
        sa.Column("confidence_after", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence_delta", sa.Float(), nullable=False, server_default="0"),
        sa.Column("validation_before", postgresql.JSONB(), nullable=True),
        sa.Column("validation_after", postgresql.JSONB(), nullable=True),
        sa.Column("validation_delta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("termination_reason", sa.String(length=200), nullable=True),
        sa.Column("candidate_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "ai_watcher_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("ai_reasoning_sessions.id"), nullable=False),
        sa.Column("graph_run_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("graph_runs.id"), nullable=False),
        sa.Column("node_name", sa.String(length=100), nullable=False),
        sa.Column("watcher_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "ai_confidence_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("ai_reasoning_sessions.id"), nullable=False),
        sa.Column("graph_run_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("graph_runs.id"), nullable=False),
        sa.Column("node_name", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("confidence_type", sa.String(length=100), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("factors", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "cti_consumption_records",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("misp_event_id", sa.String(length=100), nullable=True),
        sa.Column("cti_event_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("cti_events.id"), nullable=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("workflows.id"), nullable=True),
        sa.Column("trigger_source", sa.String(length=100), nullable=False),
        sa.Column("strategy", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ai_reasoning_revisions_session_created", "ai_reasoning_revisions", ["session_id", "created_at"])
    op.create_index("ix_ai_watcher_results_session_created", "ai_watcher_results", ["session_id", "created_at"])
    op.create_index("ix_ai_confidence_events_session_created", "ai_confidence_events", ["session_id", "created_at"])
    op.create_index("ix_cti_consumption_records_created", "cti_consumption_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_cti_consumption_records_created", table_name="cti_consumption_records")
    op.drop_index("ix_ai_confidence_events_session_created", table_name="ai_confidence_events")
    op.drop_index("ix_ai_watcher_results_session_created", table_name="ai_watcher_results")
    op.drop_index("ix_ai_reasoning_revisions_session_created", table_name="ai_reasoning_revisions")
    op.drop_table("cti_consumption_records")
    op.drop_table("ai_confidence_events")
    op.drop_table("ai_watcher_results")
    op.drop_table("ai_reasoning_revisions")
    op.drop_table("ai_reasoning_sessions")
