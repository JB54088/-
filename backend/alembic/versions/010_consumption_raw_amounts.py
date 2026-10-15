"""Keep ABC payment facts and distinguish records from paid revenue.

The import pipeline must keep a fee row even when its actual received amount
is zero (for example a fully deducted service). These columns are additive so
existing orders and all internal customer-management data remain intact.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "010_consumption_raw_amounts"
down_revision = "009_excel_import"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def upgrade() -> None:
    amount_columns = (
        "original_amount",
        "single_negotiation_amount",
        "writeoff_amount",
        "deduction_amount",
        "deduction_amount_raw",
        "discount_amount",
        "negotiation_amount",
        "receivable_amount",
        "paid_amount",
        "arrears_change",
        "non_insurance_amount",
    )
    for name in amount_columns:
        _add_column_if_missing("orders", sa.Column(name, sa.Numeric(12, 2), nullable=True))
    _add_column_if_missing("orders", sa.Column("payment_type_raw", sa.String(80), nullable=True))
    _add_column_if_missing(
        "orders",
        sa.Column("has_consumption_record", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    # Keep the default only for old rows inserted by compatibility code; the
    # ORM and importer explicitly set the value for every new order.
    op.alter_column("orders", "has_consumption_record", server_default=None)


def downgrade() -> None:
    # This migration is intentionally additive. Dropping the raw ABC facts on
    # downgrade would make reconciliation data irrecoverable.
    pass
