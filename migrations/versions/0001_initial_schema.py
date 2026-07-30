"""Initial production schema.

Revision ID: 0001
Revises:
"""

from alembic import op

from app.db.base import Base
from app.db.models import *  # noqa: F403

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
