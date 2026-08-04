"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.base import Base
    from app.models import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from app.db.base import Base
    from app.models import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
