"""database idempotency constraints

Revision ID: 0004_database_idempotency
Revises: 0003_attack_mapping_audit
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_database_idempotency"
down_revision = "0003_attack_mapping_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_interactions", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.execute(
        """
        delete from review_actions
        where id in (
            select id from (
                select id, row_number() over (
                    partition by proposal_revision_id, action
                    order by created_at asc, id asc
                ) as rn
                from review_actions
            ) ranked
            where ranked.rn > 1
        )
        """
    )
    op.execute(
        """
        delete from deployment_artifacts
        where id in (
            select id from (
                select id, row_number() over (
                    partition by proposal_revision_id, artifact_type
                    order by created_at asc, id asc
                ) as rn
                from deployment_artifacts
            ) ranked
            where ranked.rn > 1
        )
        """
    )
    op.create_unique_constraint("uq_ai_interaction_idempotency_key", "ai_interactions", ["idempotency_key"])
    op.create_unique_constraint("uq_review_action_revision_action", "review_actions", ["proposal_revision_id", "action"])
    op.create_unique_constraint("uq_deployment_artifact_revision_type", "deployment_artifacts", ["proposal_revision_id", "artifact_type"])
    op.create_index(
        "uq_running_graph_operation",
        "graph_runs",
        ["workflow_id", sa.text("coalesce(resume_from_node, 'initial')")],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "uq_active_generated_detection_revision",
        "detection_catalog",
        [sa.text("(normalized_logic->>'proposal_revision_id')")],
        unique=True,
        postgresql_where=sa.text("source = 'generated' and status = 'active' and normalized_logic ? 'proposal_revision_id'"),
    )


def downgrade() -> None:
    op.drop_index("uq_active_generated_detection_revision", table_name="detection_catalog")
    op.drop_index("uq_running_graph_operation", table_name="graph_runs")
    op.drop_constraint("uq_deployment_artifact_revision_type", "deployment_artifacts", type_="unique")
    op.drop_constraint("uq_review_action_revision_action", "review_actions", type_="unique")
    op.drop_constraint("uq_ai_interaction_idempotency_key", "ai_interactions", type_="unique")
    op.drop_column("ai_interactions", "idempotency_key")
