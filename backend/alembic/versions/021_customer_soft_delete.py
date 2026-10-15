"""Add soft-delete audit fields for customers."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "021_customer_soft_delete"
down_revision = "020_agent_query_logs"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def _add_index_if_missing(table: str, name: str, columns: list[str]) -> None:
    if name not in {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade() -> None:
    _add_column_if_missing("customers", sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing("customers", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("customers", sa.Column("deleted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    _add_column_if_missing("customers", sa.Column("deleted_reason", sa.String(length=255), nullable=True))
    _add_column_if_missing("customers", sa.Column("deleted_note", sa.Text(), nullable=True))
    _add_index_if_missing("customers", "ix_customers_is_deleted", ["is_deleted"])
    _add_index_if_missing("customers", "ix_customers_deleted_by", ["deleted_by"])
    op.alter_column("customers", "is_deleted", server_default=None)


def downgrade() -> None:
    # Keep this migration reversible for schema tooling.  The application
    # never physically deletes customer rows as part of the feature.
    bind = op.get_bind()
    indexes = {item["name"] for item in inspect(bind).get_indexes("customers")}
    if "ix_customers_deleted_by" in indexes:
        op.drop_index("ix_customers_deleted_by", table_name="customers")
    if "ix_customers_is_deleted" in indexes:
        op.drop_index("ix_customers_is_deleted", table_name="customers")
    columns = {item["name"] for item in inspect(bind).get_columns("customers")}
    for name in ("deleted_note", "deleted_reason", "deleted_by", "deleted_at", "is_deleted"):
        if name in columns:
            op.drop_column("customers", name)
