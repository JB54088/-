from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


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
