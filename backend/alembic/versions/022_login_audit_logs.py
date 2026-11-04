"""Record login account and outcome for administrator review."""

from alembic import op
import sqlalchemy as sa


revision = "022_login_audit_logs"
down_revision = "021_customer_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("full_name", sa.String(length=80), nullable=True),
        sa.Column("role", sa.String(length=30), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_login_audit_logs_user_id", "login_audit_logs", ["user_id"])
    op.create_index("ix_login_audit_logs_username", "login_audit_logs", ["username"])
    op.create_index("ix_login_audit_logs_success", "login_audit_logs", ["success"])
    op.create_index("ix_login_audit_logs_created_at", "login_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_login_audit_logs_created_at", table_name="login_audit_logs")
    op.drop_index("ix_login_audit_logs_success", table_name="login_audit_logs")
    op.drop_index("ix_login_audit_logs_username", table_name="login_audit_logs")
    op.drop_index("ix_login_audit_logs_user_id", table_name="login_audit_logs")
    op.drop_table("login_audit_logs")
