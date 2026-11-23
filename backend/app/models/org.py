from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base_class import Base
from .common import TimestampMixin

if TYPE_CHECKING:
    from .customer import Customer, CustomerAssignmentHistory
    from .order import Order


class Department(TimestampMixin, Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    users: Mapped[list["User"]] = relationship(back_populates="department")
    customers: Mapped[list["Customer"]] = relationship(back_populates="department")


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    department: Mapped[Department | None] = relationship(back_populates="users")
    reported_customers: Mapped[list["Customer"]] = relationship(back_populates="reported_by_user", foreign_keys="Customer.reported_by_id")
    assigned_customers: Mapped[list["Customer"]] = relationship(back_populates="assigned_to_user", foreign_keys="Customer.assigned_to_id")
    assignment_changes: Mapped[list["CustomerAssignmentHistory"]] = relationship(back_populates="changed_by_user", foreign_keys="CustomerAssignmentHistory.changed_by_id")


class LoginAuditLog(Base):
    """One row per submitted login attempt; password material is never retained."""

    __tablename__ = "login_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(80))
    role: Mapped[str | None] = mapped_column(String(30))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class Store(TimestampMixin, Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    address: Mapped[str | None] = mapped_column(String(255))
    orders: Mapped[list["Order"]] = relationship(back_populates="store")
