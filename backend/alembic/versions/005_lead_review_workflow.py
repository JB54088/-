"""Add lead review notes and make formal source nullable before approval.

Revision ID: 005_lead_review_workflow
Revises: 004_source_category
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "005_lead_review_workflow"
down_revision = "004_source_category"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing("customers", sa.Column("source_note", sa.Text(), nullable=True))
    _add_column_if_missing("customer_assignment_history", sa.Column("change_note", sa.Text(), nullable=True))
    op.alter_column(
        "customers",
        "source_category",
        existing_type=sa.String(length=40),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    # Keep the added audit/note data on downgrade rather than risking data loss.
    op.alter_column(
        "customers",
        "source_category",
        existing_type=sa.String(length=40),
        nullable=False,
        server_default="other",
    )
