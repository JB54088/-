from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base_class import Base
from .common import TimestampMixin

if TYPE_CHECKING:
    from .order import CustomerBalanceTransaction, Order
    from .org import Department, User


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_customer_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    # Browser retries reuse this key; the unique nullable column makes lead
    # creation idempotent without changing the customer business identity.
    submission_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # Internal leads normally provide a phone. External pool rows may not, so
    # a missing phone is kept as NULL and can be resolved manually later.
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    wechat_id: Mapped[str | None] = mapped_column(String(80))
    gender: Mapped[str | None] = mapped_column(String(10))
    age: Mapped[int | None] = mapped_column(Integer)
    # Retain the raw/legacy value for history; business filters use source_category.
    source: Mapped[str | None] = mapped_column(String(50), index=True)
    # source is retained as the raw/legacy value; source_category is formal classification metadata.
    source_category: Mapped[str | None] = mapped_column(String(40), default=None, nullable=True, index=True)
    # New two-level source archive. source_category remains as a legacy
    # compatibility value while these fields are authoritative.
    source_level_1: Mapped[str | None] = mapped_column(String(40), default=None, nullable=True, index=True)
    source_level_2: Mapped[str | None] = mapped_column(String(60), default=None, nullable=True, index=True)
    source_custom_name: Mapped[str | None] = mapped_column(String(120), default=None, nullable=True)
    source_note: Mapped[str | None] = mapped_column(Text)
    external_total_spend: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    external_order_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    external_last_spend_at: Mapped[datetime | None] = mapped_column(DateTime)
    external_synced_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    external_raw_data: Mapped[dict | None] = mapped_column(JSON)
    # Customer-level prepaid account, derived from the balance ledger.
    prepaid_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    total_recharge_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    total_refund_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    total_prepaid_spent: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    pool_match_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)

    # reported_by is immutable after the lead is created; assigned_to is the current owner.
    reported_by_id: Mapped[int | None] = mapped_column("reported_by", ForeignKey("users.id"), index=True)
    assigned_to_id: Mapped[int | None] = mapped_column("assigned_to", ForeignKey("users.id"), index=True)
    # Lead lifecycle timestamps are stored as UTC instants.  The UI converts
    # them to Asia/Shanghai for display.
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    lead_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    reviewed_by_id: Mapped[int | None] = mapped_column("reviewed_by", ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    member_level: Mapped[str | None] = mapped_column(String(30))
    wechat_status: Mapped[str] = mapped_column(String(30), default="unbound")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    # Soft-delete lifecycle.  Archived customers remain queryable by their
    # primary key for audit purposes, but are excluded from all active
    # customer/order/report scopes.
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_id: Mapped[int | None] = mapped_column("deleted_by", ForeignKey("users.id"), index=True)
    deleted_reason: Mapped[str | None] = mapped_column(String(255))
    deleted_note: Mapped[str | None] = mapped_column(Text)
    first_visit_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_visit_at: Mapped[datetime | None] = mapped_column(DateTime)

    department: Mapped["Department | None"] = relationship(back_populates="customers")
    reported_by_user: Mapped["User | None"] = relationship(back_populates="reported_customers", foreign_keys=[reported_by_id])
    assigned_to_user: Mapped["User | None"] = relationship(back_populates="assigned_customers", foreign_keys=[assigned_to_id])
    reviewed_by_user: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_id])
    deleted_by_user: Mapped["User | None"] = relationship(foreign_keys=[deleted_by_id])
    orders: Mapped[list["Order"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    assignment_history: Mapped[list["CustomerAssignmentHistory"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    tag_relations: Mapped[list["CustomerTagRelation"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    pool_match_history: Mapped[list["CustomerPoolMatchHistory"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    pool_match_candidates: Mapped[list["CustomerPoolMatchCandidate"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    balance_transactions: Mapped[list["CustomerBalanceTransaction"]] = relationship(back_populates="customer", cascade="all, delete-orphan")


class CustomerAssignmentHistory(Base):
    __tablename__ = "customer_assignment_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    previous_salesperson_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    new_salesperson_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    changed_by_id: Mapped[int | None] = mapped_column("changed_by", ForeignKey("users.id"))
    change_reason: Mapped[str | None] = mapped_column("change_reason", String(255))
    change_note: Mapped[str | None] = mapped_column("change_note", Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="assignment_history")
    previous_salesperson: Mapped["User | None"] = relationship(foreign_keys=[previous_salesperson_id])
    new_salesperson: Mapped["User | None"] = relationship(foreign_keys=[new_salesperson_id])
    changed_by_user: Mapped["User | None"] = relationship(back_populates="assignment_changes", foreign_keys=[changed_by_id])


class CustomerPoolMatchHistory(Base):
    __tablename__ = "customer_pool_match_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    external_customer_id: Mapped[str | None] = mapped_column(String(100), index=True)
    match_type: Mapped[str] = mapped_column(String(20), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    matched_by_id: Mapped[int | None] = mapped_column("matched_by", ForeignKey("users.id"), index=True)
    matched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer] = relationship(back_populates="pool_match_history")
    matched_by_user: Mapped["User | None"] = relationship(foreign_keys=[matched_by_id])


class CustomerPoolMatchCandidate(TimestampMixin, Base):
    __tablename__ = "customer_pool_match_candidates"
    __table_args__ = (UniqueConstraint("customer_id", "external_customer_id", name="uq_pool_candidate_customer_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    external_customer_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30))
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer] = relationship(back_populates="pool_match_candidates")
    resolved_by_user: Mapped["User | None"] = relationship(foreign_keys=[resolved_by_id])


class CustomerTag(Base):
    __tablename__ = "customer_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="blue")
    relations: Mapped[list["CustomerTagRelation"]] = relationship(back_populates="tag", cascade="all, delete-orphan")


class CustomerTagRelation(Base):
    __tablename__ = "customer_tag_relations"
    __table_args__ = (UniqueConstraint("customer_id", "tag_id", name="uq_customer_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("customer_tags.id"), index=True)
    customer: Mapped[Customer] = relationship(back_populates="tag_relations")
    tag: Mapped[CustomerTag] = relationship(back_populates="relations")


class DuplicateLeadReport(TimestampMixin, Base):
    """A salesperson submission that matched an existing customer identity."""

    __tablename__ = "duplicate_lead_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    existing_customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True, nullable=False)
    reported_name: Mapped[str] = mapped_column(String(80), nullable=False)
    reported_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    reported_wechat: Mapped[str | None] = mapped_column(String(80))
    new_reported_by_id: Mapped[int] = mapped_column("new_reported_by", ForeignKey("users.id"), index=True, nullable=False)
    duplicate_reason: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    reviewed_by_id: Mapped[int | None] = mapped_column("reviewed_by", ForeignKey("users.id"), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_note: Mapped[str | None] = mapped_column(Text)
    submission_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
