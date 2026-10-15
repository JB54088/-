"""Add read-only business assistant audit logs."""

from alembic import op
import sqlalchemy as sa


revision = "020_agent_query_logs"
down_revision = "019_timezone_aware_lead_times"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_query_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("query_plan_json", sa.JSON(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_query_logs_user_id", "agent_query_logs", ["user_id"])
    op.create_index("ix_agent_query_logs_status", "agent_query_logs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_agent_query_logs_status", table_name="agent_query_logs")
    op.drop_index("ix_agent_query_logs_user_id", table_name="agent_query_logs")
    op.drop_table("agent_query_logs")
