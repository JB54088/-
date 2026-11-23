from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from .common import PoolMatchStatus, SourceCategory, SourceLevel1, SourceLevel2
from .order import CustomerBalanceTransactionResponse, OrderResponse


class AssignmentRequest(BaseModel):
    assigned_to: int | None = None
    reason: str = Field(default="主管分配客户", max_length=255)
    note: str | None = Field(default=None, max_length=2000)


class BulkAssignmentRequest(AssignmentRequest):
    customer_ids: list[int] = Field(min_length=1, max_length=500)


class ReassignRequest(BaseModel):
    new_salesperson_id: int
    reason: str = Field(min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=2000)


class CustomerVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=2000)


class PoolManualMatchRequest(BaseModel):
    candidate_id: int
    note: str | None = Field(default=None, max_length=2000)


class PoolMatchCandidateResponse(BaseModel):
    id: int
    customer_id: int
    external_customer_id: str
    name: str
    phone: str | None = None
    raw_data: dict
    is_active: bool
    created_at: datetime
    last_seen_at: datetime


class CustomerListItem(BaseModel):
    id: int
    external_customer_id: str | None = None
    pool_match_status: PoolMatchStatus = "pending"
    external_synced_at: datetime | None = None
    name: str
    phone: str | None = None
    wechat_id: str | None = None
    gender: str | None = None
    age: int | None = None
    source_category: SourceCategory | None = None
    source_level_1: SourceLevel1 | None = None
    source_level_2: SourceLevel2 | None = None
    source_custom_name: str | None = None
    source_note: str | None = None
    reported_by_id: int | None = None
    assigned_to_id: int | None = None
    reported_by_name: str | None = None
    assigned_to_name: str | None = None
    department_name: str | None = None
    member_level: str | None = None
    wechat_status: str
    status: str
    lead_status: str
    reported_at: datetime | None = None
    total_spend: Decimal = Decimal("0")
    total_amount: Decimal = Decimal("0")
    # Customer value is based on imported project/detail amounts.  Actual
    # received money remains a separate metric for financial reporting.
    consumption_value: Decimal = Decimal("0")
    actual_paid_amount: Decimal = Decimal("0")
    effective_revenue: Decimal = Decimal("0")
    insurance_amount: Decimal | None = None
    self_pay_amount: Decimal | None = None
    deduction_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    order_count: int = 0
    average_order_value: Decimal = Decimal("0")
    last_spend_at: datetime | None = None
    last_visit_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    prepaid_balance: Decimal = Decimal("0")
    total_recharge_amount: Decimal = Decimal("0")
    total_refund_amount: Decimal = Decimal("0")
    total_prepaid_spent: Decimal = Decimal("0")


class CustomerDetail(CustomerListItem):
    created_at: datetime
    first_visit_at: datetime | None = None
    notes: str | None = None


class TimelineEvent(BaseModel):
    type: str
    title: str
    description: str | None = None
    occurred_at: datetime


class CustomerDetailResponse(BaseModel):
    customer: CustomerDetail
    orders: list[OrderResponse]
    timeline: list[TimelineEvent]
    assignment_history: list[dict]
    pool_match_history: list[dict] = Field(default_factory=list)
    balance_transactions: list[CustomerBalanceTransactionResponse] = Field(default_factory=list)
