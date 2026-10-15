from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


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


class Store(TimestampMixin, Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    address: Mapped[str | None] = mapped_column(String(255))
    orders: Mapped[list["Order"]] = relationship(back_populates="store")


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
    # source is retained as the raw/legacy value; source_category is selected by an admin during review.
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

    department: Mapped[Department | None] = relationship(back_populates="customers")
    reported_by_user: Mapped[User | None] = relationship(back_populates="reported_customers", foreign_keys=[reported_by_id])
    assigned_to_user: Mapped[User | None] = relationship(back_populates="assigned_customers", foreign_keys=[assigned_to_id])
    reviewed_by_user: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id])
    deleted_by_user: Mapped[User | None] = relationship(foreign_keys=[deleted_by_id])
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
    previous_salesperson: Mapped[User | None] = relationship(foreign_keys=[previous_salesperson_id])
    new_salesperson: Mapped[User | None] = relationship(foreign_keys=[new_salesperson_id])
    changed_by_user: Mapped[User | None] = relationship(back_populates="assignment_changes", foreign_keys=[changed_by_id])


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
    matched_by_user: Mapped[User | None] = relationship(foreign_keys=[matched_by_id])


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
    resolved_by_user: Mapped[User | None] = relationship(foreign_keys=[resolved_by_id])


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
    customer: Mapped[Customer] = relationship(back_populates="orders")
    store: Mapped[Store | None] = relationship(back_populates="orders")
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

    customer: Mapped[Customer] = relationship(back_populates="balance_transactions")
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
    customer: Mapped[Customer | None] = relationship()
    resolved_by_user: Mapped[User | None] = relationship(foreign_keys=[resolved_by_id])


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


class Report(TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("period_type", "period_start", name="uq_report_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ai_summary: Mapped[str | None] = mapped_column(Text)


class AgentQueryLog(TimestampMixin, Base):
    """Audit trail for read-only business assistant queries."""

    __tablename__ = "agent_query_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    query_plan_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_summary: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(String(120))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
