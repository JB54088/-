"""Add first- and second-level customer source archive fields.

Revision ID: 018_source_levels
Revises: 017_refund_direction
"""

from alembic import op
import sqlalchemy as sa


revision = "018_source_levels"
down_revision = "017_refund_direction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("source_level_1", sa.String(length=40), nullable=True))
    op.add_column("customers", sa.Column("source_level_2", sa.String(length=60), nullable=True))
    op.add_column("customers", sa.Column("source_custom_name", sa.String(length=120), nullable=True))
    op.create_index("ix_customers_source_level_1", "customers", ["source_level_1"], unique=False)
    op.create_index("ix_customers_source_level_2", "customers", ["source_level_2"], unique=False)
    op.create_check_constraint(
        "ck_customers_source_level_1",
        "customers",
        "source_level_1 IS NULL OR source_level_1 IN ('field_sales', 'online', 'offline', 'event', 'referral', 'other')",
    )
    op.create_check_constraint(
        "ck_customers_source_level_2",
        "customers",
        "source_level_2 IS NULL OR source_level_2 IN ("
        "'field_sales_group_1', 'field_sales_group_2', 'field_sales_other', "
        "'wechat', 'xiaohongshu', 'douyin', 'online_other', "
        "'store_visit', 'community_promotion', 'offline_other', "
        "'free_clinic', 'health_lecture', 'event_other', "
        "'patient_referral', 'doctor_referral', 'partner_referral', "
        "'unknown', 'custom')",
    )

    # Preserve source as-is and infer only the new first-level value from the
    # existing normalized category. Old detailed text is used where it is
    # unambiguous; otherwise the second level is an explicit fallback.
    op.execute(
        """
        UPDATE customers
        SET source_level_1 = CASE source_category
            WHEN 'field_sales' THEN 'field_sales'
            WHEN 'online' THEN 'online'
            WHEN 'offline' THEN 'offline'
            WHEN 'event' THEN 'event'
            WHEN 'third_party_referral' THEN 'referral'
            WHEN 'external' THEN 'other'
            WHEN 'other' THEN 'other'
            ELSE CASE lower(trim(coalesce(source, '')))
                WHEN '地推' THEN 'field_sales'
                WHEN '线上' THEN 'online'
                WHEN '线下' THEN 'offline'
                WHEN '活动' THEN 'event'
                WHEN '第三方转介绍' THEN 'referral'
                WHEN '转介绍' THEN 'referral'
                ELSE 'other'
            END
        END,
        source_level_2 = CASE lower(trim(coalesce(source, '')))
            WHEN '小红书' THEN 'xiaohongshu'
            WHEN '抖音' THEN 'douyin'
            WHEN '公众号' THEN 'online_other'
            WHEN '企业微信' THEN 'wechat'
            WHEN '自然到店' THEN 'store_visit'
            WHEN '到店' THEN 'store_visit'
            WHEN '线下到店' THEN 'store_visit'
            WHEN '老客转介绍' THEN 'patient_referral'
            WHEN '转介绍' THEN 'patient_referral'
            ELSE CASE source_category
                WHEN 'field_sales' THEN 'field_sales_other'
                WHEN 'online' THEN 'online_other'
                WHEN 'offline' THEN 'offline_other'
                WHEN 'event' THEN 'event_other'
                WHEN 'third_party_referral' THEN 'patient_referral'
                ELSE 'unknown'
            END
        END
        WHERE source_level_1 IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("ck_customers_source_level_2", "customers", type_="check")
    op.drop_constraint("ck_customers_source_level_1", "customers", type_="check")
    op.drop_index("ix_customers_source_level_2", table_name="customers")
    op.drop_index("ix_customers_source_level_1", table_name="customers")
    op.drop_column("customers", "source_custom_name")
    op.drop_column("customers", "source_level_2")
    op.drop_column("customers", "source_level_1")
