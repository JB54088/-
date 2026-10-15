"""Add insurance/self-pay amounts to orders."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "008_payment_split"
down_revision = "007_duplicate_lead_reports"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def _add_index_if_missing(table: str, name: str, columns: list[str]) -> None:
    if name not in {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade() -> None:
    _add_column_if_missing("orders", sa.Column("total_amount", sa.Numeric(12, 2), nullable=True))
    _add_column_if_missing("orders", sa.Column("insurance_amount", sa.Numeric(12, 2), nullable=True))
    _add_column_if_missing("orders", sa.Column("self_pay_amount", sa.Numeric(12, 2), nullable=True))
    _add_column_if_missing("orders", sa.Column("payment_type", sa.String(length=30), nullable=True))
    _add_column_if_missing("orders", sa.Column("payment_split_status", sa.String(length=20), nullable=False, server_default="unknown"))
    _add_index_if_missing("orders", "ix_orders_payment_split_status", ["payment_split_status"])

    # Existing orders predate the split fields. Keep their known total exactly
    # and leave both components NULL to communicate that the source did not
    # provide a breakdown; do not invent an insurance/self-pay allocation.
    op.execute(text("UPDATE orders SET total_amount = amount WHERE total_amount IS NULL"))
    op.execute(text("UPDATE orders SET payment_split_status = 'unknown' WHERE payment_split_status IS NULL"))
    op.alter_column("orders", "total_amount", existing_type=sa.Numeric(12, 2), nullable=False)


def downgrade() -> None:
    # Preserve payment facts and data-quality state on downgrade.
    pass
