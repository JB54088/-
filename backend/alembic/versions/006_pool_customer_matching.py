"""Add deferred data-pool customer matching and audit candidates."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "006_pool_customer_matching"
down_revision = "005_lead_review_workflow"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def _add_index_if_missing(table: str, name: str, columns: list[str]) -> None:
    if name not in {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade() -> None:
    _add_column_if_missing(
        "customers",
        sa.Column("pool_match_status", sa.String(length=30), nullable=False, server_default="pending"),
    )
    _add_index_if_missing("customers", "ix_customers_pool_match_status", ["pool_match_status"])
    # Existing external snapshots are already mapped; newly reported internal
    # leads remain pending until a later pool sync finds them.
    op.execute(text("UPDATE customers SET pool_match_status = CASE WHEN external_customer_id IS NULL THEN 'pending' ELSE 'matched' END WHERE pool_match_status IS NULL OR pool_match_status = 'pending'"))
    op.alter_column("customers", "phone", existing_type=sa.String(length=30), nullable=True)

    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "customer_pool_match_history" not in tables:
        op.create_table(
            "customer_pool_match_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("external_customer_id", sa.String(length=100), nullable=True),
            sa.Column("match_type", sa.String(length=20), nullable=False),
            sa.Column("previous_status", sa.String(length=30), nullable=True),
            sa.Column("new_status", sa.String(length=30), nullable=False),
            sa.Column("matched_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("matched_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
        )
    _add_index_if_missing("customer_pool_match_history", "ix_customer_pool_match_history_customer_id", ["customer_id"])
    _add_index_if_missing("customer_pool_match_history", "ix_customer_pool_match_history_external_customer_id", ["external_customer_id"])
    _add_index_if_missing("customer_pool_match_history", "ix_customer_pool_match_history_matched_by", ["matched_by"])

    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "customer_pool_match_candidates" not in tables:
        op.create_table(
            "customer_pool_match_candidates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("external_customer_id", sa.String(length=100), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("phone", sa.String(length=30), nullable=True),
            sa.Column("raw_data", sa.JSON(), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("resolved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("resolution_note", sa.Text(), nullable=True),
            sa.UniqueConstraint("customer_id", "external_customer_id", name="uq_pool_candidate_customer_external"),
        )
    _add_index_if_missing("customer_pool_match_candidates", "ix_customer_pool_match_candidates_customer_id", ["customer_id"])
    _add_index_if_missing("customer_pool_match_candidates", "ix_customer_pool_match_candidates_external_customer_id", ["external_customer_id"])
    _add_index_if_missing("customer_pool_match_candidates", "ix_customer_pool_match_candidates_is_active", ["is_active"])


def downgrade() -> None:
    # Preserve matching audit data on downgrade; it is safer than destructive
    # removal and keeps external linkage history available for investigation.
    pass
