"""Repair legacy prepaid projections without deleting source orders."""

from datetime import datetime
from decimal import Decimal
import json

from alembic import op
import sqlalchemy as sa


revision = "016_balance_repair"
down_revision = "015_balance_consume"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("""
        SELECT
            b.id,
            b.customer_id,
            b.transaction_type,
            b.amount,
            b.charged_at,
            b.source_transaction_id,
            o.external_transaction_id,
            o.external_order_id,
            o.paid_amount,
            o.total_amount,
            o.raw_json
        FROM customer_balance_transactions AS b
        LEFT JOIN orders AS o ON o.id = b.source_transaction_id
        ORDER BY b.customer_id, b.charged_at, b.id
    """)).mappings().all()

    current_customer = None
    running = Decimal("0")
    for row in rows:
        if row["customer_id"] != current_customer:
            current_customer = row["customer_id"]
            running = Decimal("0")
        transaction_type = row["transaction_type"]
        amount = Decimal(row["amount"] or 0)

        # A negative ordinary member-card row is a credit/reversal, not a
        # second debit. Keep it in the audit ledger as an adjustment.
        source_signed_amount = row["paid_amount"] if row["paid_amount"] not in (None, 0) else row["total_amount"]
        if transaction_type == "consume" and source_signed_amount is not None and Decimal(source_signed_amount) < 0:
            transaction_type = "adjustment"
            amount = abs(amount)

        if running + amount < 0:
            external_id = row["external_transaction_id"] or row["external_order_id"] or str(row["source_transaction_id"] or row["id"])
            conn.execute(sa.text("""
                INSERT INTO integration_logs
                    (source, event_type, external_id, status, raw_data, error_message,
                     started_at, finished_at, failure_count)
                VALUES
                    ('abc_excel', 'balance_insufficient', :external_id, 'failed', :raw_data,
                     :error_message, :now, :now, 1)
            """), {
                "external_id": str(external_id),
                "raw_data": json.dumps(row["raw_json"] or {}, ensure_ascii=False, default=str),
                "error_message": "历史储值流水余额不足，已保留原始订单但未计入余额",
                "now": datetime.now().replace(microsecond=0),
            })
            conn.execute(sa.text("DELETE FROM customer_balance_transactions WHERE id = :id"), {"id": row["id"]})
            continue

        before = running
        running += amount
        conn.execute(sa.text("""
            UPDATE customer_balance_transactions
            SET transaction_type = :transaction_type,
                amount = :amount,
                balance_before = :balance_before,
                balance_after = :balance_after
            WHERE id = :id
        """), {
            "id": row["id"],
            "transaction_type": transaction_type,
            "amount": amount,
            "balance_before": before,
            "balance_after": running,
        })

    conn.execute(sa.text("""
        UPDATE customers
        SET prepaid_balance = 0,
            total_recharge_amount = 0,
            total_refund_amount = 0,
            total_prepaid_spent = 0
    """))
    conn.execute(sa.text("""
        UPDATE customers AS c
        SET
            prepaid_balance = summary.prepaid_balance,
            total_recharge_amount = summary.total_recharge_amount,
            total_refund_amount = summary.total_refund_amount,
            total_prepaid_spent = summary.total_prepaid_spent
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
