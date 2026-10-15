"""Rebuild customer external consumption snapshots after balance classification."""

from alembic import op
import sqlalchemy as sa


revision = "013_balance_snapshot"
down_revision = "012_balance_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE customers AS c
        SET
            external_total_spend = summary.total_spend,
            external_order_count = summary.order_count,
            external_last_spend_at = summary.last_spend_at,
            last_visit_at = summary.last_spend_at
        FROM (
            SELECT
                c2.id AS customer_id,
                COALESCE(SUM(
                    COALESCE(
                        (SELECT SUM(oi.amount) FROM order_items AS oi WHERE oi.order_id = o.id),
                        o.total_amount,
                        0
                    )
                ), 0) AS total_spend,
                COUNT(DISTINCT CASE
                    WHEN o.visit_no IS NOT NULL
                        THEN 'visit:' || o.visit_no || '|' || (o.paid_at::date)::text
                    WHEN o.external_transaction_id IS NOT NULL
                        THEN 'order:' || o.external_transaction_id
                    WHEN o.transaction_fingerprint IS NOT NULL
                        THEN 'fingerprint:' || o.transaction_fingerprint
                    ELSE NULL
                END) AS order_count,
                MAX(o.paid_at) AS last_spend_at
            FROM customers AS c2
            LEFT JOIN orders AS o
                ON o.customer_id = c2.id
               AND o.has_consumption_record IS TRUE
               AND (o.transaction_kind IS NULL OR o.transaction_kind <> 'balance_transaction')
            GROUP BY c2.id
        ) AS summary
        WHERE c.id = summary.customer_id
    """))


def downgrade() -> None:
    # Snapshot values are derived data.  There is no safe way to reconstruct
    # the pre-classification values without reintroducing balance transactions,
    # so keep the corrected snapshot on downgrade.
    pass
