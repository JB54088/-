"""Backfill prepaid-consumption rows already imported before the ledger existed."""

from alembic import op
import sqlalchemy as sa


revision = "015_balance_consume"
down_revision = "014_customer_balance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE orders AS o
        SET balance_operation = NULL
        WHERE o.transaction_kind <> 'balance_transaction'
    """))
    bind.execute(sa.text("""
        WITH candidates AS (
            SELECT
                o.id,
                o.customer_id,
                o.paid_at,
                abs(coalesce(
                    nullif(o.paid_amount, 0),
                    nullif(o.total_amount, 0),
                    (SELECT sum(oi.amount) FROM order_items AS oi WHERE oi.order_id = o.id),
                    0
                )) AS amount
            FROM orders AS o
            WHERE o.transaction_kind <> 'balance_transaction'
              AND o.balance_payment_amount IS NULL
              AND (
                  lower(coalesce(o.payment_type_raw, '') || ' ' || coalesce(o.payment_method, '')) LIKE '%会员卡%'
                  OR lower(coalesce(o.payment_type_raw, '') || ' ' || coalesce(o.payment_method, '')) LIKE '%会员余额%'
                  OR lower(coalesce(o.payment_type_raw, '') || ' ' || coalesce(o.payment_method, '')) LIKE '%储值%'
                  OR lower(coalesce(o.payment_type_raw, '') || ' ' || coalesce(o.payment_method, '')) LIKE '%余额支付%'
                  OR lower(coalesce(o.payment_type_raw, '') || ' ' || coalesce(o.payment_method, '')) LIKE '%prepaid%'
                  OR lower(coalesce(o.payment_type_raw, '') || ' ' || coalesce(o.payment_method, '')) LIKE '%balance%'
              )
        )
        UPDATE orders AS o
        SET balance_payment_amount = candidates.amount
        FROM candidates
        WHERE o.id = candidates.id
          AND candidates.amount > 0
    """))
    bind.execute(sa.text("""
        INSERT INTO customer_balance_transactions
            (customer_id, external_customer_id, transaction_type, amount,
             balance_before, balance_after, source_transaction_id, charged_at, raw_data)
        SELECT
            o.customer_id,
            o.external_customer_id,
            'consume',
            -o.balance_payment_amount,
            0,
            0,
            o.id,
            o.paid_at,
            o.raw_json
        FROM orders AS o
        WHERE o.transaction_kind <> 'balance_transaction'
          AND o.balance_payment_amount > 0
          AND NOT EXISTS (
              SELECT 1 FROM customer_balance_transactions AS b
              WHERE b.source_transaction_id = o.id
          )
    """))
    bind.execute(sa.text("""
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
    bind.execute(sa.text("""
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
    pass
