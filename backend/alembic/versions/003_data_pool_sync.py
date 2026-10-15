"""Add data-pool snapshots and sync audit fields."""

from alembic import op
from sqlalchemy import Column, DateTime, Integer, JSON, Numeric, String, inspect, text


revision = "003_data_pool_sync"
down_revision = "002_salesperson_permissions"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def _add_index_if_missing(table: str, name: str, columns: list[str]) -> None:
    existing = {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns)


def upgrade() -> None:
    _add_column_if_missing("customers", Column("external_total_spend", Numeric(12, 2), nullable=False, server_default="0"))
    _add_column_if_missing("customers", Column("external_order_count", Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("customers", Column("external_last_spend_at", DateTime(), nullable=True))
    _add_column_if_missing("customers", Column("external_synced_at", DateTime(), nullable=True))
    _add_column_if_missing("customers", Column("external_raw_data", JSON(), nullable=True))
    _add_index_if_missing("customers", "ix_customers_external_synced_at", ["external_synced_at"])
    op.execute(text("UPDATE customers SET external_total_spend = 0 WHERE external_total_spend IS NULL"))
    op.execute(text("UPDATE customers SET external_order_count = 0 WHERE external_order_count IS NULL"))

    _add_column_if_missing("orders", Column("synced_at", DateTime(), nullable=True))
    op.execute(text("UPDATE orders SET synced_at = created_at WHERE synced_at IS NULL"))
    _add_index_if_missing("orders", "ix_orders_synced_at", ["synced_at"])

    _add_column_if_missing("integration_logs", Column("started_at", DateTime(), nullable=True))
    _add_column_if_missing("integration_logs", Column("finished_at", DateTime(), nullable=True))
    _add_column_if_missing("integration_logs", Column("new_customers", Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("integration_logs", Column("updated_customers", Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("integration_logs", Column("new_orders", Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("integration_logs", Column("updated_orders", Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("integration_logs", Column("failure_count", Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    # Keep the snapshot and audit columns on downgrade so externally sourced data is not lost.
    pass
