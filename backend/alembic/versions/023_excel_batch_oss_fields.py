"""Add Aliyun OSS archive metadata fields to excel_import_batches."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "023_excel_batch_oss_fields"
down_revision = "022_login_audit_logs"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def _add_index_if_missing(table: str, name: str, columns: list[str]) -> None:
    if name not in {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade() -> None:
    _add_column_if_missing("excel_import_batches", sa.Column("oss_bucket", sa.String(length=120), nullable=True))
    _add_column_if_missing("excel_import_batches", sa.Column("oss_object_key", sa.String(length=500), nullable=True))
    _add_column_if_missing("excel_import_batches", sa.Column("file_sha256", sa.String(length=64), nullable=True))
    _add_column_if_missing("excel_import_batches", sa.Column("file_size_bytes", sa.Integer(), nullable=True))
    _add_index_if_missing("excel_import_batches", "ix_excel_import_batches_file_sha256", ["file_sha256"])


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {item["name"] for item in inspect(bind).get_indexes("excel_import_batches")}
    if "ix_excel_import_batches_file_sha256" in indexes:
        op.drop_index("ix_excel_import_batches_file_sha256", table_name="excel_import_batches")
    columns = {item["name"] for item in inspect(bind).get_columns("excel_import_batches")}
    for name in ("file_size_bytes", "file_sha256", "oss_object_key", "oss_bucket"):
        if name in columns:
            op.drop_column("excel_import_batches", name)
