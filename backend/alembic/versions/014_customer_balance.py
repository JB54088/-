"""Add customer prepaid accounts and backfill existing balance rows."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "014_customer_balance"
down_revision = "013_balance_snapshot"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def upgrade() -> None:
    for name in ("prepaid_balance", "total_recharge_amount", "total_refund_amount", "total_prepaid_spent"):
        _add_column_if_missing(
            "customers",
            sa.Column(name, sa.Numeric(12, 2), nullable=False, server_default="0"),
        )
    for name in ("balance_operation", "balance_payment_amount"):
        column_type = sa.String(20) if name == "balance_operation" else sa.Numeric(12, 2)
        _add_column_if_missing("orders", sa.Column(name, column_type, nullable=True))
    for name in ("prepaid_balance", "total_recharge_amount", "total_refund_amount", "total_prepaid_spent"):
        op.alter_column("customers", name, server_default=None)

    op.create_table(
        "customer_balance_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("external_customer_id", sa.String(length=100), nullable=True),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_before", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("source_transaction_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("charged_at", sa.DateTime(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_transaction_id", name="uq_customer_balance_source_transaction"),
    )
    op.create_index("ix_customer_balance_transactions_customer_id", "customer_balance_transactions", ["customer_id"])
    op.create_index("ix_customer_balance_transactions_external_customer_id", "customer_balance_transactions", ["external_customer_id"])
    op.create_index("ix_customer_balance_transactions_transaction_type", "customer_balance_transactions", ["transaction_type"])
    op.create_index("ix_customer_balance_transactions_source_transaction_id", "customer_balance_transactions", ["source_transaction_id"])
    op.create_index("ix_customer_balance_transactions_charged_at", "customer_balance_transactions", ["charged_at"])

    op.execute(sa.text("""
        UPDATE orders AS o
        SET balance_operation = CASE
            WHEN coalesce(o.raw_json::text, '') ILIKE '%退费%'
                 OR coalesce(o.raw_json::text, '') ILIKE '%退款%'
                 OR coalesce(o.total_amount, 0) < 0
                THEN 'refund'
            ELSE 'recharge'
        END
        WHERE o.transaction_kind = 'balance_transaction'
          AND o.balance_operation IS NULL
    """))

    # Orders imported before this feature already contain the original ABC
    # operation in raw_json and the membership category in item/category.
    # Backfill only balance rows; never delete or rewrite the source order.
    op.execute(sa.text("""
        INSERT INTO customer_balance_transactions
            (customer_id, external_customer_id, transaction_type, amount,
             balance_before, balance_after, source_transaction_id, charged_at, raw_data)
        SELECT
            o.customer_id,
            o.external_customer_id,
            CASE
                WHEN coalesce(o.raw_json::text, '') ILIKE '%退费%'
                     OR coalesce(o.raw_json::text, '') ILIKE '%退款%'
                     OR coalesce(o.total_amount, 0) < 0
                    THEN 'refund'
                ELSE 'recharge'
            END,
            CASE
                WHEN coalesce(o.paid_amount, 0) <> 0 THEN abs(o.paid_amount)
                WHEN coalesce(o.total_amount, 0) <> 0 THEN abs(o.total_amount)
                WHEN coalesce(o.receivable_amount, 0) <> 0 THEN abs(o.receivable_amount)
                WHEN coalesce(o.original_amount, 0) <> 0 THEN abs(o.original_amount)
                ELSE abs(coalesce((SELECT sum(oi.amount) FROM order_items AS oi WHERE oi.order_id = o.id), 0))
            END
            * CASE
                WHEN coalesce(o.raw_json::text, '') ILIKE '%退费%'
                     OR coalesce(o.raw_json::text, '') ILIKE '%退款%'
                     OR coalesce(o.total_amount, 0) < 0
                    THEN -1 ELSE 1
              END,
            0,
            0,
            o.id,
            o.paid_at,
            o.raw_json
        FROM orders AS o
        WHERE o.transaction_kind = 'balance_transaction'
          AND (
              coalesce(o.item_name, '') ILIKE '%会员充值%'
              OR coalesce(o.category, '') ILIKE '%会员充值%'
              OR coalesce(o.category_level_1, '') ILIKE '%会员充值%'
              OR coalesce(o.raw_json::text, '') ILIKE '%会员充值%'
          )
          AND NOT EXISTS (
              SELECT 1 FROM customer_balance_transactions AS b
              WHERE b.source_transaction_id = o.id
          )
    """))

    # Rebuild before/after balances in chronological order for the backfilled
    # rows, then refresh the customer-level derived totals.
    op.execute(sa.text("""
        WITH ordered AS (
            SELECT
                b.id,
                coalesce(sum(b.amount) OVER (
                    PARTITION BY b.customer_id
                    ORDER BY b.charged_at, b.source_transaction_id, b.id
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ), 0) AS balance_before,
                sum(b.amount) OVER (
                    PARTITION BY b.customer_id
                    ORDER BY b.charged_at, b.source_transaction_id, b.id
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS balance_after
            FROM customer_balance_transactions AS b
        )
        UPDATE customer_balance_transactions AS b
        SET balance_before = ordered.balance_before,
            balance_after = ordered.balance_after
        FROM ordered
        WHERE b.id = ordered.id
    """))
    op.execute(sa.text("""
        UPDATE customers AS c
        SET
            prepaid_balance = coalesce(summary.prepaid_balance, 0),
            total_recharge_amount = coalesce(summary.total_recharge_amount, 0),
            total_refund_amount = coalesce(summary.total_refund_amount, 0),
            total_prepaid_spent = coalesce(summary.total_prepaid_spent, 0)
        FROM (
            SELECT
                customer_id,
                sum(amount) AS prepaid_balance,
                sum(CASE WHEN transaction_type = 'recharge' THEN amount ELSE 0 END) AS total_recharge_amount,
                sum(CASE WHEN transaction_type = 'refund' THEN -amount ELSE 0 END) AS total_refund_amount,
                sum(CASE WHEN transaction_type = 'consume' THEN -amount ELSE 0 END) AS total_prepaid_spent
            FROM customer_balance_transactions
            GROUP BY customer_id
        ) AS summary
        WHERE c.id = summary.customer_id
    """))


def downgrade() -> None:
    # Keep this additive migration non-destructive so balance reconciliation
    # records and customer account facts are not lost on rollback.
    pass
