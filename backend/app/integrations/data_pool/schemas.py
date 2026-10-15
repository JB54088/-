from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class DataPoolCustomerPayload(BaseModel):
    """Normalized external customer shape accepted from the Playwright data pool."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    external_customer_id: str | None = Field(default=None, validation_alias=AliasChoices("external_customer_id", "customer_id", "id"))
    name: str = Field(min_length=1, max_length=80)
    phone: str | None = Field(default=None, min_length=5, max_length=30)
    wechat_id: str | None = Field(default=None, max_length=80, validation_alias=AliasChoices("wechat_id", "wechat_identifier", "wechat"))
    gender: str | None = Field(default=None, max_length=10)
    age: int | None = Field(default=None, ge=0, le=150)
    source: str | None = Field(default=None, max_length=50)
    source_category: str | None = Field(default=None, max_length=40)
    wechat_status: str | None = Field(default=None, max_length=30)
    total_spend: Decimal | None = Field(default=None, ge=0, validation_alias=AliasChoices("total_spend", "cumulative_spend", "total_amount"))
    order_count: int | None = Field(default=None, ge=0, validation_alias=AliasChoices("order_count", "consumption_count", "purchase_count"))
    last_spend_at: datetime | None = Field(default=None, validation_alias=AliasChoices("last_spend_at", "last_consumption_at", "last_order_at"))


class DataPoolOrderPayload(BaseModel):
    """Normalized external order shape accepted from the Playwright data pool."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    external_order_id: str = Field(min_length=1, max_length=100, validation_alias=AliasChoices("external_order_id", "order_id", "id"))
    external_customer_id: str = Field(min_length=1, max_length=100, validation_alias=AliasChoices("external_customer_id", "customer_id"))
    paid_at: datetime = Field(validation_alias=AliasChoices("paid_at", "consumed_at", "consumption_time", "order_time"))
    item_name: str = Field(min_length=1, max_length=120, validation_alias=AliasChoices("item_name", "consumption_item", "product_name"))
    category: str = Field(default="其他", max_length=40, validation_alias=AliasChoices("category", "consumption_category", "item_category"))
    # Both shapes are supported during the transition. ``total_amount`` is
    # canonical; ``amount`` remains accepted for older pool payloads/tests.
    total_amount: Decimal | None = Field(default=None, ge=0, validation_alias=AliasChoices("total_amount", "total_fee"))
    amount: Decimal | None = Field(default=None, ge=0, validation_alias=AliasChoices("amount", "paid_amount"))
    insurance_amount: Decimal | None = Field(default=None, ge=0, validation_alias=AliasChoices("insurance_amount", "insurance_payment_amount", "medical_amount", "医保金额"))
    self_pay_amount: Decimal | None = Field(default=None, ge=0, validation_alias=AliasChoices("self_pay_amount", "self_payment_amount", "out_of_pocket_amount", "自费金额"))
    payment_type: str | None = Field(default=None, max_length=30, validation_alias=AliasChoices("payment_type", "pay_type", "支付类型"))
    order_no: str | None = Field(default=None, max_length=100)
    store_name: str | None = Field(default=None, max_length=100, validation_alias=AliasChoices("store_name", "store"))
    staff_name: str | None = Field(default=None, max_length=80)
    payment_method: str | None = Field(default=None, max_length=40)
    items: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def fill_compatible_total(self):
        if self.total_amount is None and self.amount is not None:
            self.total_amount = self.amount
        if self.amount is None and self.total_amount is not None:
            self.amount = self.total_amount
        if self.total_amount is None and self.insurance_amount is not None and self.self_pay_amount is not None:
            self.total_amount = self.insurance_amount + self.self_pay_amount
            self.amount = self.total_amount
        if self.total_amount is None:
            raise ValueError("消费记录缺少总金额")
        return self


class DataPoolSyncSummary(BaseModel):
    started_at: datetime
    finished_at: datetime
    status: str
    new_customers: int = 0
    updated_customers: int = 0
    new_orders: int = 0
    updated_orders: int = 0
    failure_count: int = 0
    matched_customers: int = 0
    conflict_customers: int = 0
    manual_required_customers: int = 0
    payment_mismatch_count: int = 0
    errors: list[str] = Field(default_factory=list)
