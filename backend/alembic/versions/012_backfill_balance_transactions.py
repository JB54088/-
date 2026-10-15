"""Backfill member recharge/refund rows imported before balance classification."""

from alembic import op
import sqlalchemy as sa


revision = "012_balance_backfill"
down_revision = "011_balance_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE orders
        SET transaction_kind = 'balance_transaction'
        WHERE transaction_kind <> 'balance_transaction'
          AND (
              coalesce(item_name, '') ILIKE '%会员充值%'
              OR coalesce(category, '') ILIKE '%会员充值%'
              OR coalesce(category_level_1, '') ILIKE '%会员充值%'
              OR coalesce(raw_json::text, '') ILIKE '%会员充值%'
          )
    """))


def downgrade() -> None:
    # This migration only classifies rows that were already imported.  The
    # original facts remain in raw_json; reverting the classification restores
    # the pre-migration default without deleting any order data.
    op.execute(sa.text("""
        UPDATE orders
        SET transaction_kind = 'consumption'
        WHERE transaction_kind = 'balance_transaction'
          AND (
              coalesce(item_name, '') ILIKE '%会员充值%'
              OR coalesce(category, '') ILIKE '%会员充值%'
              OR coalesce(category_level_1, '') ILIKE '%会员充值%'
              OR coalesce(raw_json::text, '') ILIKE '%会员充值%'
          )
    """))
