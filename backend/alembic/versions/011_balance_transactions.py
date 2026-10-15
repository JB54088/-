"""Mark member balance recharge/refund rows separately from consumption."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "011_balance_transactions"
down_revision = "010_consumption_raw_amounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns("orders")}
    if "transaction_kind" not in columns:
        op.add_column(
            "orders",
            sa.Column("transaction_kind", sa.String(length=30), nullable=False, server_default="consumption"),
        )
    indexes = {item["name"] for item in inspect(op.get_bind()).get_indexes("orders")}
    if "ix_orders_transaction_kind" not in indexes:
        op.create_index("ix_orders_transaction_kind", "orders", ["transaction_kind"], unique=False)
    op.alter_column("orders", "transaction_kind", server_default=None)


def downgrade() -> None:
    # Keep this additive migration non-destructive so balance classification is
    # not lost during a rollback.
    pass
