"""Create all V1 tables.

Revision ID: 001_initial
Revises:
"""
from alembic import op

from app.db.base import Base

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
