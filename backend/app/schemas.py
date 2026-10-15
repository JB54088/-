from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


LeadStatus = Literal["pending", "reviewed", "unassigned", "assigned", "approved", "converted", "rejected"]
SourceCategory = Literal["field_sales", "online", "offline", "event", "third_party_referral", "external", "other"]
SourceLevel1 = Literal["field_sales", "online", "offline", "event", "referral", "other"]
SourceLevel2 = Literal[
    "field_sales_group_1", "field_sales_group_2", "field_sales_other",
    "wechat", "xiaohongshu", "douyin", "online_other",
    "store_visit", "community_promotion", "offline_other",
    "free_clinic", "health_lecture", "event_other",
    "patient_referral", "doctor_referral", "partner_referral",
    "unknown", "custom",
]
PoolMatchStatus = Literal["pending", "matched", "conflict", "manual_required"]


class LoginRequest(BaseModel):
    username: str
    password: str


class UserBrief(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    department_id: int | None = None
    department_name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserBrief


class AssignmentRequest(BaseModel):
    assigned_to: int | None = None
    reason: str = Field(default="主管分配客户", max_length=255)
    note: str | None = Field(default=None, max_length=2000)


class BulkAssignmentRequest(AssignmentRequest):
    customer_ids: list[int] = Field(min_length=1, max_length=500)


class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=5, max_length=30)
    wechat_id: str | None = Field(default=None, max_length=80)
    gender: str | None = Field(default=None, max_length=10)
    source_note: str | None = Field(default=None, max_length=500, validation_alias=AliasChoices("source_note", "source"))
    notes: str | None = Field(default=None, max_length=2000)
    # These fields are accepted by the shared lead endpoint for administrator
    # creation.  The router enforces that only admins may use them.
    source_level_1: SourceLevel1 | None = None
    source_level_2: SourceLevel2 | None = None
    source_custom_name: str | None = Field(default=None, max_length=120)
    tag_ids: list[int] = Field(default_factory=list, max_length=20)
    assigned_to: int | None = None
    submission_id: str | None = Field(default=None, max_length=100, validation_alias=AliasChoices("submission_id", "idempotency_key"))


class LeadReviewRequest(BaseModel):
    action: Literal["approve", "reject"] = "approve"
    source_category: SourceCategory | None = None
    source_level_1: SourceLevel1 | None = None
    source_level_2: SourceLevel2 | None = None
    source_custom_name: str | None = Field(default=None, max_length=120)
    tag_ids: list[int] = Field(default_factory=list, max_length=20)
    assigned_to: int | None = None
    review_note: str | None = Field(default=None, max_length=2000)


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


class ExcelImportBindRequest(BaseModel):
    customer_id: int
    note: str | None = Field(default=None, max_length=2000)


class ExcelImportIgnoreRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class DuplicateLeadReviewRequest(BaseModel):
    action: Literal["confirm_duplicate", "not_duplicate", "reject"]
    review_note: str | None = Field(default=None, max_length=2000)


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str = Field(default="blue", max_length=20)


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    color: str | None = Field(default=None, max_length=20)


class CustomerTagsRequest(BaseModel):
    tag_ids: list[int] = Field(default_factory=list, max_length=20)


class DepartmentBrief(BaseModel):
    id: int
    name: str


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


class LeadListItem(BaseModel):
    id: int
    name: str
    phone: str
    wechat_id: str | None = None
    gender: str | None = None
    source_category: SourceCategory | None = None
    source_level_1: SourceLevel1 | None = None
    source_level_2: SourceLevel2 | None = None
    source_custom_name: str | None = None
    source_note: str | None = None
    notes: str | None = None
    reported_by_name: str | None = None
    reported_at: datetime | None = None
    assigned_to_name: str | None = None
    lead_status: str
    tags: list[str] = Field(default_factory=list)
    total_spend: Decimal = Decimal("0")
    order_count: int = 0


class TagResponse(BaseModel):
    id: int
    name: str
    color: str
    customer_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class OrderItemResponse(BaseModel):
    id: int
    item_name: str
    category_level_1: str | None = None
    category_level_2: str | None = None
    category_level_3: str | None = None
    item_code: str | None = None
    quantity: int
    unit: str | None = None
    unit_price: Decimal
    amount: Decimal

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    id: int
    order_no: str
    customer_id: int
    customer_name: str
    paid_at: datetime
    visit_no: str | None = None
    item_name: str
    category: str
    amount: Decimal
    total_amount: Decimal
    consumption_amount: Decimal | None = None
    effective_revenue: Decimal | None = None
    actual_paid_amount: Decimal | None = None
    original_amount: Decimal | None = None
    single_negotiation_amount: Decimal | None = None
    writeoff_amount: Decimal | None = None
    deduction_amount: Decimal | None = None
    deduction_amount_raw: Decimal | None = None
    discount_amount: Decimal | None = None
    negotiation_amount: Decimal | None = None
    receivable_amount: Decimal | None = None
    paid_amount: Decimal | None = None
    arrears_change: Decimal | None = None
    insurance_amount: Decimal | None = None
    self_pay_amount: Decimal | None = None
    non_insurance_amount: Decimal | None = None
    payment_type: str | None = None
    payment_type_raw: str | None = None
    transaction_kind: str = "consumption"
    transaction_operation: str | None = None
    is_refund: bool = False
    balance_operation: str | None = None
    balance_payment_amount: Decimal | None = None
    has_consumption_record: bool = True
    payment_split_status: str = "unknown"
    store_name: str | None = None
    department_name: str | None = None
    owner_name: str | None = None
    staff_name: str | None = None
    payment_method: str | None = None
    items: list[OrderItemResponse] = Field(default_factory=list)


class CustomerBalanceTransactionResponse(BaseModel):
    id: int
    customer_id: int
    external_customer_id: str | None = None
    transaction_type: str
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal
    source_transaction_id: int | None = None
    charged_at: datetime
    created_at: datetime


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


class ReportResponse(BaseModel):
    period_type: str
    period_start: datetime
    period_end: datetime
    metrics: dict
    ai_summary: str
