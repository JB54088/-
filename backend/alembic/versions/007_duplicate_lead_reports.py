"""Add duplicate lead reports and idempotent salesperson submissions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "007_duplicate_lead_reports"
down_revision = "006_pool_customer_matching"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def _add_index_if_missing(table: str, name: str, columns: list[str], unique: bool = False) -> None:
    if name not in {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    _add_column_if_missing("customers", sa.Column("submission_id", sa.String(length=100), nullable=True))
    _add_index_if_missing("customers", "ix_customers_submission_id", ["submission_id"], unique=True)

    # Normalize historical phone formatting before new lead matching starts.
    # The original source field is not overwritten anywhere else, and NULL is
    # retained for data-pool customers that have no phone.
    op.execute(text("""
        WITH normalized_phones AS (
            SELECT
                id,
                NULLIF(
                    CASE
                        WHEN digits LIKE '0086%' AND length(digits) = 15 THEN substring(digits FROM 5)
                        WHEN digits LIKE '86%' AND length(digits) = 13 THEN substring(digits FROM 3)
                        ELSE digits
                    END,
                    ''
                ) AS normalized_phone
            FROM (
                SELECT id, regexp_replace(phone, '[^0-9]', '', 'g') AS digits
                FROM customers
                WHERE phone IS NOT NULL
            ) AS phone_values
        )
        UPDATE customers AS customers_row
        SET phone = normalized_phones.normalized_phone
        FROM normalized_phones
        WHERE customers_row.id = normalized_phones.id
    """))

    tables = set(inspect(op.get_bind()).get_table_names())
    if "duplicate_lead_reports" not in tables:
        op.create_table(
            "duplicate_lead_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("existing_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("reported_name", sa.String(length=80), nullable=False),
            sa.Column("reported_phone", sa.String(length=30), nullable=False),
            sa.Column("reported_wechat", sa.String(length=80), nullable=True),
            sa.Column("new_reported_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("duplicate_reason", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("submission_id", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
    _add_index_if_missing("duplicate_lead_reports", "ix_duplicate_lead_reports_existing_customer_id", ["existing_customer_id"])
    _add_index_if_missing("duplicate_lead_reports", "ix_duplicate_lead_reports_new_reported_by", ["new_reported_by"])
    _add_index_if_missing("duplicate_lead_reports", "ix_duplicate_lead_reports_status", ["status"])
    _add_index_if_missing("duplicate_lead_reports", "ix_duplicate_lead_reports_reviewed_by", ["reviewed_by"])
    _add_index_if_missing("duplicate_lead_reports", "ix_duplicate_lead_reports_submission_id", ["submission_id"], unique=True)


def downgrade() -> None:
    # Keep duplicate-report and idempotency history on downgrade. This data is
    # operational audit information and should not be removed accidentally.
    pass
