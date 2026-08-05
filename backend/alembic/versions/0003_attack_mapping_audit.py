"""attack mapping audit metadata

Revision ID: 0003_attack_mapping_audit
Revises: 0002_ai_policy_metadata
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_attack_mapping_audit"
down_revision = "0002_ai_policy_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("attack_mappings")
    }
    if "attack_version" not in columns:
        op.add_column(
            "attack_mappings", sa.Column("attack_version", sa.String(length=50), nullable=True)
        )
    if "verification_details" not in columns:
        op.add_column(
            "attack_mappings",
            sa.Column("verification_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("attack_mappings", "verification_details")
    op.drop_column("attack_mappings", "attack_version")
