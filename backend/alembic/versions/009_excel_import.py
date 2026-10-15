"""Add administrator ABC Excel import batches and transaction identity fields."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "009_excel_import"
down_revision = "008_payment_split"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def _add_index_if_missing(table: str, name: str, columns: list[str], unique: bool = False) -> None:
    if name not in {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    _add_column_if_missing("orders", sa.Column("external_customer_id", sa.String(length=100), nullable=True))
    _add_column_if_missing("orders", sa.Column("external_transaction_id", sa.String(length=120), nullable=True))
    _add_column_if_missing("orders", sa.Column("transaction_fingerprint", sa.String(length=64), nullable=True))
    _add_column_if_missing("orders", sa.Column("visit_no", sa.String(length=100), nullable=True))
    _add_column_if_missing("orders", sa.Column("category_level_1", sa.String(length=80), nullable=True))
    _add_column_if_missing("orders", sa.Column("category_level_2", sa.String(length=80), nullable=True))
    _add_column_if_missing("orders", sa.Column("category_level_3", sa.String(length=80), nullable=True))
    _add_column_if_missing("orders", sa.Column("item_code", sa.String(length=100), nullable=True))
    _add_column_if_missing("orders", sa.Column("import_batch_id", sa.Integer(), nullable=True))
    _add_column_if_missing("orders", sa.Column("organization", sa.String(length=120), nullable=True))
    _add_column_if_missing("order_items", sa.Column("category_level_1", sa.String(length=80), nullable=True))
    _add_column_if_missing("order_items", sa.Column("category_level_2", sa.String(length=80), nullable=True))
    _add_column_if_missing("order_items", sa.Column("category_level_3", sa.String(length=80), nullable=True))
    _add_column_if_missing("order_items", sa.Column("item_code", sa.String(length=100), nullable=True))
    _add_column_if_missing("order_items", sa.Column("unit", sa.String(length=30), nullable=True))

    _add_index_if_missing("orders", "ix_orders_external_customer_id", ["external_customer_id"])
    _add_index_if_missing("orders", "ix_orders_external_transaction_id", ["external_transaction_id"], unique=True)
    _add_index_if_missing("orders", "ix_orders_transaction_fingerprint", ["transaction_fingerprint"], unique=True)
    _add_index_if_missing("orders", "ix_orders_import_batch_id", ["import_batch_id"])

    bind = op.get_bind()
    inspector = inspect(bind)
    if "excel_import_batches" not in inspector.get_table_names():
        op.create_table(
            "excel_import_batches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("uploaded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("status", sa.String(length=20), server_default="preview", nullable=False),
            sa.Column("sheet_names", sa.JSON(), nullable=False),
            sa.Column("preview_data", sa.JSON(), nullable=False),
            sa.Column("total_rows", sa.Integer(), server_default="0", nullable=False),
            sa.Column("total_customers", sa.Integer(), server_default="0", nullable=False),
            sa.Column("matched_customers", sa.Integer(), server_default="0", nullable=False),
            sa.Column("unmatched_customers", sa.Integer(), server_default="0", nullable=False),
            sa.Column("conflict_customers", sa.Integer(), server_default="0", nullable=False),
            sa.Column("new_transactions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("updated_transactions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("skipped_transactions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("error_rows", sa.Integer(), server_default="0", nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_excel_import_batches_uploaded_by", "excel_import_batches", ["uploaded_by"])
        op.create_index("ix_excel_import_batches_status", "excel_import_batches", ["status"])
        op.create_index("ix_excel_import_batches_confirmed_by", "excel_import_batches", ["confirmed_by"])

    inspector = inspect(bind)
    if "excel_import_unmatched_records" not in inspector.get_table_names():
        op.create_table(
            "excel_import_unmatched_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_id", sa.Integer(), sa.ForeignKey("excel_import_batches.id"), nullable=False),
            sa.Column("external_customer_id", sa.String(length=100), nullable=True),
            sa.Column("name", sa.String(length=80), nullable=True),
            sa.Column("phone", sa.String(length=30), nullable=True),
            sa.Column("transaction_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("raw_data", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("resolution_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("batch_id", "transaction_fingerprint", name="uq_excel_unmatched_batch_fingerprint"),
        )
        op.create_index("ix_excel_import_unmatched_records_batch_id", "excel_import_unmatched_records", ["batch_id"])
        op.create_index("ix_excel_import_unmatched_records_external_customer_id", "excel_import_unmatched_records", ["external_customer_id"])
        op.create_index("ix_excel_import_unmatched_records_phone", "excel_import_unmatched_records", ["phone"])
        op.create_index("ix_excel_import_unmatched_records_status", "excel_import_unmatched_records", ["status"])
        op.create_index("ix_excel_import_unmatched_records_customer_id", "excel_import_unmatched_records", ["customer_id"])
        op.create_index("ix_excel_import_unmatched_records_resolved_by", "excel_import_unmatched_records", ["resolved_by"])
        op.create_index("ix_excel_import_unmatched_records_transaction_fingerprint", "excel_import_unmatched_records", ["transaction_fingerprint"])

    if not any(set(foreign_key.get("constrained_columns", [])) == {"import_batch_id"} and foreign_key.get("referred_table") == "excel_import_batches" for foreign_key in inspect(bind).get_foreign_keys("orders")):
        op.create_foreign_key("fk_orders_import_batch_id_excel_import_batches", "orders", "excel_import_batches", ["import_batch_id"], ["id"])


def downgrade() -> None:
    # Keep imported records recoverable; this migration is intentionally
    # non-destructive on downgrade in the same spirit as the payment split
    # migration.
    pass
