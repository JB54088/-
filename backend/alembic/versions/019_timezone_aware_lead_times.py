"""Store lead submission and approval times as UTC-aware timestamps.

Revision ID: 019_timezone_aware_lead_times
Revises: 018_source_levels
"""

from alembic import op
import sqlalchemy as sa


revision = "019_timezone_aware_lead_times"
down_revision = "018_source_levels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Before this migration the application ran in a UTC Docker container and
    # wrote naive UTC values.  Interpret those historical values as UTC so the
    # instant is preserved rather than inventing a new local time.
    op.alter_column(
        "customers",
        "reported_at",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        postgresql_using="reported_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "customers",
        "reviewed_at",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        postgresql_using="reviewed_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    # Convert UTC instants back to naive UTC values on rollback, preserving
    # the instant and avoiding an accidental Asia/Shanghai reinterpretation.
    op.alter_column(
        "customers",
        "reviewed_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        postgresql_using="reviewed_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "customers",
        "reported_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        postgresql_using="reported_at AT TIME ZONE 'UTC'",
    )
