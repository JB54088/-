from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base_class import Base
from .common import TimestampMixin

if TYPE_CHECKING:
    from .customer import Customer
    from .org import Store


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    external_order_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    external_customer_id: Mapped[str | None] = mapped_column(String(100), index=True)
    external_transaction_id: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    transaction_fingerprint: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    visit_no: Mapped[str | None] = mapped_column(String(100), index=True)
    item_name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    category_level_1: Mapped[str | None] = mapped_column(String(80))
    category_level_2: Mapped[str | None] = mapped_column(String(80))
    category_level_3: Mapped[str | None] = mapped_column(String(80))
    item_code: Mapped[str | None] = mapped_column(String(100))
    # amount is retained as a legacy compatibility column; total_amount is
    # the canonical total used by all new API and reporting calculations.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # ABC raw payment facts. ``total_amount`` is retained for the imported
    # order-level amount; shared reporting resolves project value, actual paid,
    # payment split and effective revenue separately.
    original_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    single_negotiation_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    writeoff_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    deduction_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    deduction_amount_raw: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    negotiation_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    receivable_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    arrears_change: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    insurance_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    self_pay_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    non_insurance_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    payment_type: Mapped[str | None] = mapped_column(String(30))
    payment_type_raw: Mapped[str | None] = mapped_column(String(80))
    # Member recharge/refund rows are retained for balance reconciliation but
    # are excluded from all consumption and operating-revenue statistics.
    transaction_kind: Mapped[str] = mapped_column(String(30), default="consumption", nullable=False, index=True)
    # Preserve ABC's original charge/refund business type. ``is_refund`` is
    # the normalized direction used by net consumption and revenue metrics.
    transaction_operation: Mapped[str | None] = mapped_column(String(30), index=True)
    is_refund: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    balance_operation: Mapped[str | None] = mapped_column(String(20), index=True)
    # Positive amount actually deducted from prepaid balance for a consumption
    # row; the ledger stores the signed negative effect.
    balance_payment_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # A zero paid amount can still represent a real service/fee record (for
    # example, a fully deducted item). This flag is deliberately independent
    # from all monetary columns.
    has_consumption_record: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    # verified, mismatch, or unknown when the external source does not expose
    # enough information to validate the split.
    payment_split_status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False, index=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("excel_import_batches.id"), index=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    organization: Mapped[str | None] = mapped_column(String(120))
    # Historical snapshot only. Permission checks always follow Customer.assigned_to.
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    staff_name: Mapped[str | None] = mapped_column(String(80))
    payment_method: Mapped[str | None] = mapped_column(String(40))
    raw_json: Mapped[dict | None] = mapped_column(JSON)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    customer: Mapped["Customer"] = relationship(back_populates="orders")
    store: Mapped["Store | None"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    balance_transactions: Mapped[list["CustomerBalanceTransaction"]] = relationship(back_populates="source_order")


class CustomerBalanceTransaction(TimestampMixin, Base):
    """Immutable audit row for a customer's prepaid balance movement."""

    __tablename__ = "customer_balance_transactions"
    __table_args__ = (
        UniqueConstraint("source_transaction_id", name="uq_customer_balance_source_transaction"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True, nullable=False)
    external_customer_id: Mapped[str | None] = mapped_column(String(100), index=True)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    source_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    charged_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    raw_data: Mapped[dict | None] = mapped_column(JSON)

    customer: Mapped["Customer"] = relationship(back_populates="balance_transactions")
    source_order: Mapped[Order | None] = relationship(back_populates="balance_transactions")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    item_name: Mapped[str] = mapped_column(String(120), nullable=False)
    category_level_1: Mapped[str | None] = mapped_column(String(80))
    category_level_2: Mapped[str | None] = mapped_column(String(80))
    category_level_3: Mapped[str | None] = mapped_column(String(80))
    item_code: Mapped[str | None] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit: Mapped[str | None] = mapped_column(String(30))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    order: Mapped[Order] = relationship(back_populates="items")
