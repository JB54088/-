"""Normalize customer source categories while retaining raw source values.

Revision ID: 004_source_category
Revises: 003_data_pool_sync
"""

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa


revision = "004_source_category"
down_revision = "003_data_pool_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {item["name"] for item in inspect(connection).get_columns("customers")}
    if "source_category" not in columns:
        op.add_column("customers", sa.Column("source_category", sa.String(length=40), nullable=True))
    indexes = {item["name"] for item in inspect(connection).get_indexes("customers")}
    if "ix_customers_source_category" not in indexes:
        op.create_index("ix_customers_source_category", "customers", ["source_category"], unique=False)
    op.execute(
        """
        UPDATE customers
        SET source_category = CASE lower(trim(coalesce(source, '')))
            WHEN '地推' THEN 'field_sales'
            WHEN 'field_sales' THEN 'field_sales'
            WHEN '线上' THEN 'online'
            WHEN 'online' THEN 'online'
            WHEN '小红书' THEN 'online'
            WHEN '抖音' THEN 'online'
            WHEN '公众号' THEN 'online'
            WHEN '企业微信' THEN 'online'
            WHEN '线下' THEN 'offline'
            WHEN 'offline' THEN 'offline'
            WHEN '自然到店' THEN 'offline'
            WHEN '到店' THEN 'offline'
            WHEN '线下到店' THEN 'offline'
            WHEN '活动' THEN 'event'
            WHEN 'event' THEN 'event'
            WHEN '第三方转介绍' THEN 'third_party_referral'
            WHEN 'third_party_referral' THEN 'third_party_referral'
            WHEN '老客转介绍' THEN 'third_party_referral'
            WHEN '转介绍' THEN 'third_party_referral'
            WHEN '外部来源' THEN 'external'
            WHEN 'external' THEN 'external'
            WHEN '其它' THEN 'other'
            WHEN '其他' THEN 'other'
            WHEN 'other' THEN 'other'
            ELSE 'other'
        END
        """
    )
    op.alter_column("customers", "source_category", nullable=False, server_default="other")
    constraints = {item["name"] for item in inspect(connection).get_check_constraints("customers")}
    if "ck_customers_source_category" not in constraints:
        op.create_check_constraint(
            "ck_customers_source_category",
            "customers",
            "source_category IN ('field_sales', 'online', 'offline', 'event', 'third_party_referral', 'external', 'other')",
        )


def downgrade() -> None:
    connection = op.get_bind()
    constraints = {item["name"] for item in inspect(connection).get_check_constraints("customers")}
    if "ck_customers_source_category" in constraints:
        op.drop_constraint("ck_customers_source_category", "customers", type_="check")
    indexes = {item["name"] for item in inspect(connection).get_indexes("customers")}
    if "ix_customers_source_category" in indexes:
        op.drop_index("ix_customers_source_category", table_name="customers")
    if "source_category" in {item["name"] for item in inspect(connection).get_columns("customers")}:
        op.drop_column("customers", "source_category")
