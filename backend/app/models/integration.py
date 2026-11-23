from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base_class import Base
from .common import TimestampMixin

if TYPE_CHECKING:
    from .customer import Customer
    from .org import User


class IntegrationLog(Base):
    __tablename__ = "integration_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    new_customers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_customers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_orders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_orders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class ExcelImportBatch(TimestampMixin, Base):
    __tablename__ = "excel_import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column("uploaded_by", ForeignKey("users.id"), index=True, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="preview", nullable=False, index=True)
    sheet_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    preview_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_customers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_customers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unmatched_customers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conflict_customers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_transactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_transactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_transactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    confirmed_by_id: Mapped[int | None] = mapped_column("confirmed_by", ForeignKey("users.id"), index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)

    unmatched_records: Mapped[list["ExcelImportUnmatchedRecord"]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class ExcelImportUnmatchedRecord(TimestampMixin, Base):
    __tablename__ = "excel_import_unmatched_records"
    __table_args__ = (UniqueConstraint("batch_id", "transaction_fingerprint", name="uq_excel_unmatched_batch_fingerprint"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("excel_import_batches.id"), index=True, nullable=False)
    external_customer_id: Mapped[str | None] = mapped_column(String(100), index=True)
    name: Mapped[str | None] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(30), index=True)
    transaction_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    resolved_by_id: Mapped[int | None] = mapped_column("resolved_by", ForeignKey("users.id"), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolution_note: Mapped[str | None] = mapped_column(Text)

    batch: Mapped[ExcelImportBatch] = relationship(back_populates="unmatched_records")
    customer: Mapped["Customer | None"] = relationship()
    resolved_by_user: Mapped["User | None"] = relationship(foreign_keys=[resolved_by_id])
