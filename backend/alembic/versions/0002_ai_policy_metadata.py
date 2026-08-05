"""ai policy and interaction metadata

Revision ID: 0002_ai_policy_metadata
Revises: 0001_initial
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_ai_policy_metadata"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    ai_interaction_columns = {
        column["name"] for column in inspector.get_columns("ai_interactions")
    }
    if "latency_ms" not in ai_interaction_columns:
        op.add_column("ai_interactions", sa.Column("latency_ms", sa.Integer(), nullable=True))
    if "response_hash" not in ai_interaction_columns:
        op.add_column("ai_interactions", sa.Column("response_hash", sa.String(length=64), nullable=True))
    if "error_json" not in ai_interaction_columns:
        op.add_column(
            "ai_interactions",
            sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    policy_enum = postgresql.ENUM(
        "already_covered",
        "visibility_gap",
        "insufficient_evidence",
        "generate_candidate",
        name="policydecisionvalue",
        create_type=False,
    )
    policy_enum.create(bind, checkfirst=True)
    if "policy_decisions" not in inspector.get_table_names():
        op.create_table(
            "policy_decisions",
            sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
            sa.Column("workflow_id", postgresql.UUID(as_uuid=False), nullable=False),
            sa.Column("graph_run_id", postgresql.UUID(as_uuid=False), nullable=False),
            sa.Column("behavior_id", postgresql.UUID(as_uuid=False), nullable=False),
            sa.Column("coverage_status", postgresql.ENUM("covered", "partial", "not_covered", name="coveragestatus", create_type=False), nullable=False),
            sa.Column("visibility_status", postgresql.ENUM("visible", "partial", "gap", name="visibilitystatus", create_type=False), nullable=False),
            sa.Column("evidence_sufficient", sa.Boolean(), nullable=False),
            sa.Column("verified_mapping_count", sa.Integer(), nullable=False),
            sa.Column("decision", policy_enum, nullable=False),
            sa.Column("deterministic_rationale", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["behavior_id"], ["behaviors.id"]),
            sa.ForeignKeyConstraint(["graph_run_id"], ["graph_runs.id"]),
            sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    op.drop_table("policy_decisions")
    postgresql.ENUM(name="policydecisionvalue").drop(op.get_bind(), checkfirst=True)
    op.drop_column("ai_interactions", "error_json")
    op.drop_column("ai_interactions", "response_hash")
    op.drop_column("ai_interactions", "latency_ms")
