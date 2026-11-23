from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


Metric = Literal[
    "customer_count",
    "new_customer_count",
    "assigned_customer_count",
    "unassigned_customer_count",
    "effective_revenue",
    "total_consumption",
    "insurance_amount",
    "self_pay_amount",
    "consumption_count",
    "average_order_value",
    "recharge_amount",
    "refund_amount",
    "prepaid_balance",
    "prepaid_spent",
    "balance_overview",
    "payment_mix",
    "balance_mix",
]
GroupBy = Literal["owner", "source_level_1", "source_level_2", "customer", "date"]
TimeRangeType = Literal[
    "all",
    "today",
    "week",
    "month",
    "last_week",
    "last_month",
    "last_7_days",
    "last_30_days",
    "custom",
]


class TimeRange(BaseModel):
    type: TimeRangeType = "month"
    start_date: date | None = None
    end_date: date | None = None


class QueryFilters(BaseModel):
    owner_name: str | None = None
    source_level_1: str | None = None
    source_level_2: str | None = None
    tag_name: str | None = None
    min_consumption: float | None = Field(default=None, ge=0)


class QueryPlan(BaseModel):
    metric: Metric
    time_range: TimeRange = Field(default_factory=TimeRange)
    filters: QueryFilters = Field(default_factory=QueryFilters)
    group_by: GroupBy | None = None
    limit: int = Field(default=10, ge=1, le=50)
    sort: Literal["asc", "desc"] = "desc"


class AgentQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class ChartPoint(BaseModel):
    label: str
    value: float


class ChartPayload(BaseModel):
    type: Literal["bar", "pie", "line"]
    title: str
    data: list[ChartPoint]


class AgentQueryResponse(BaseModel):
    answer: str
    data: dict[str, Any] = Field(default_factory=dict)
    query_plan: QueryPlan
    chart: ChartPayload | None = None
    model_name: str
