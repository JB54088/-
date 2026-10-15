"""Add lead reporting, current assignment and new history fields."""

from alembic import op
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, inspect, text

revision = "002_salesperson_permissions"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def _ensure_fk(table: str, columns: list[str], referred_table: str, name: str) -> None:
    existing = inspect(op.get_bind()).get_foreign_keys(table)
    if not any(set(item.get("constrained_columns", [])) == set(columns) and item.get("referred_table") == referred_table for item in existing):
        op.create_foreign_key(name, table, referred_table, columns, ["id"])


def upgrade() -> None:
    _add_column_if_missing("customers", Column("wechat_id", String(80), nullable=True))
    _add_column_if_missing("customers", Column("notes", Text(), nullable=True))
    _add_column_if_missing("customers", Column("reported_by", Integer(), nullable=True))
    _add_column_if_missing("customers", Column("assigned_to", Integer(), nullable=True))
    _add_column_if_missing("customers", Column("reported_at", DateTime(), nullable=True))
    _add_column_if_missing("customers", Column("lead_status", String(20), nullable=True, server_default="pending"))
    _add_column_if_missing("customers", Column("reviewed_by", Integer(), nullable=True))
    _add_column_if_missing("customers", Column("reviewed_at", DateTime(), nullable=True))
    _ensure_fk("customers", ["reported_by"], "users", "fk_customers_reported_by")
    _ensure_fk("customers", ["assigned_to"], "users", "fk_customers_assigned_to")
    _ensure_fk("customers", ["reviewed_by"], "users", "fk_customers_reviewed_by")
    op.execute(text("UPDATE customers SET reported_by = owner_id WHERE reported_by IS NULL AND owner_id IS NOT NULL"))
    op.execute(text("UPDATE customers SET assigned_to = owner_id WHERE assigned_to IS NULL AND owner_id IS NOT NULL"))
    op.execute(text("UPDATE customers SET reported_at = created_at WHERE reported_at IS NULL"))
    op.execute(text("UPDATE customers SET lead_status = CASE WHEN assigned_to IS NULL THEN 'unassigned' ELSE 'converted' END WHERE lead_status IS NULL OR lead_status = 'pending'"))

    _add_column_if_missing("customer_assignment_history", Column("previous_salesperson_id", Integer(), nullable=True))
    _add_column_if_missing("customer_assignment_history", Column("new_salesperson_id", Integer(), nullable=True))
    _add_column_if_missing("customer_assignment_history", Column("changed_by", Integer(), nullable=True))
    _add_column_if_missing("customer_assignment_history", Column("change_reason", String(255), nullable=True))
    _ensure_fk("customer_assignment_history", ["previous_salesperson_id"], "users", "fk_assignment_previous_salesperson")
    _ensure_fk("customer_assignment_history", ["new_salesperson_id"], "users", "fk_assignment_new_salesperson")
    _ensure_fk("customer_assignment_history", ["changed_by"], "users", "fk_assignment_changed_by")
    op.execute(text("UPDATE customer_assignment_history SET previous_salesperson_id = old_owner_id WHERE previous_salesperson_id IS NULL"))
    op.execute(text("UPDATE customer_assignment_history SET new_salesperson_id = new_owner_id WHERE new_salesperson_id IS NULL"))
    op.execute(text("UPDATE customer_assignment_history SET changed_by = operator_id WHERE changed_by IS NULL"))
    op.execute(text("UPDATE customer_assignment_history SET change_reason = reason WHERE change_reason IS NULL"))


def downgrade() -> None:
    # Legacy columns are intentionally retained so a rollback does not destroy audit data.
    pass
