"""Safe, read-only execution for the business-analysis query plan.

The planner produces a small, typed vocabulary.  This module is the only
place where that vocabulary is translated into SQLAlchemy expressions; no
model-generated SQL is ever executed.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from ...consumption import (
    consumption_count_query,
    consumption_value_expression,
    effective_insurance_expression,
    effective_revenue_expression,
    effective_self_pay_expression,
)
from ...models import Customer, CustomerBalanceTransaction, CustomerTag, CustomerTagRelation, Order, User
from ...source_categories import SOURCE_LEVEL_1_LABELS, SOURCE_LEVEL_2_OPTIONS
from ...utils import consumption_key_expression, consumption_order_condition, formal_customer_condition, money
from .schemas import QueryPlan, TimeRange

BUSINESS_TZ = ZoneInfo("Asia/Shanghai")

METRIC_LABELS = {
    "customer_count": "客户数",
    "new_customer_count": "新增客户数",
    "assigned_customer_count": "已分配客户数",
    "unassigned_customer_count": "待分配客户数",
    "effective_revenue": "有效经营收入",
    "total_consumption": "消费价值",
    "insurance_amount": "医保支付",
    "self_pay_amount": "自费支付",
    "consumption_count": "消费次数",
    "average_order_value": "平均客单价",
    "recharge_amount": "充值金额",
    "refund_amount": "退款金额",
    "prepaid_balance": "当前储值余额",
    "prepaid_spent": "累计使用储值",
    "balance_overview": "会员储值总览",
    "payment_mix": "支付类型",
    "balance_mix": "充值退款",
}


def _today() -> date:
    return datetime.now(BUSINESS_TZ).date()


def resolve_time_range(time_range: TimeRange) -> tuple[datetime | None, datetime | None, str]:
    """Return naive local datetimes for the existing business tables.

    Orders and balance ledger timestamps are stored as local business-time
    ``timestamp`` values.  The end is exclusive so an entire end date is
    included without relying on 23:59:59 precision.
    """

    today = _today()
    kind = time_range.type
    if kind == "all":
        return None, None, "全部"
    if kind == "today":
        start = today
        label = "今日"
    elif kind == "week":
        start = today - timedelta(days=today.weekday())
        label = "本周"
    elif kind == "month":
        start = today.replace(day=1)
        label = "本月"
    elif kind == "last_week":
        start = today - timedelta(days=today.weekday() + 7)
        return datetime.combine(start, datetime.min.time()), datetime.combine(start + timedelta(days=7), datetime.min.time()), "上周"
    elif kind == "last_month":
        first = today.replace(day=1)
        previous = (first - timedelta(days=1)).replace(day=1)
        return datetime.combine(previous, datetime.min.time()), datetime.combine(first, datetime.min.time()), "上月"
    elif kind == "last_7_days":
        start = today - timedelta(days=6)
        label = "最近7天"
    elif kind == "last_30_days":
        start = today - timedelta(days=29)
        label = "最近30天"
    else:
        start = time_range.start_date or today.replace(day=1)
        requested_end = time_range.end_date or today
        # A natural-language question must never query a future date.
        end_date = min(requested_end, today)
        if start > end_date:
            start = end_date
        return (
            datetime.combine(start, datetime.min.time()),
            datetime.combine(end_date + timedelta(days=1), datetime.min.time()),
            f"{start:%Y/%m/%d} — {end_date:%Y/%m/%d}",
        )
    return datetime.combine(start, datetime.min.time()), datetime.combine(today + timedelta(days=1), datetime.min.time()), label


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return Decimal("0")


def _customer_conditions(plan: QueryPlan) -> list[Any]:
    conditions: list[Any] = [formal_customer_condition()]
    filters = plan.filters
    if filters.owner_name:
        owner_ids = select(User.id).where(
            User.role == "salesperson",
            User.is_active.is_(True),
            or_(User.full_name == filters.owner_name, User.username == filters.owner_name),
        )
        conditions.append(Customer.assigned_to_id.in_(owner_ids))
    if filters.source_level_1:
        conditions.append(Customer.source_level_1 == filters.source_level_1)
    if filters.source_level_2:
        conditions.append(Customer.source_level_2 == filters.source_level_2)
    if filters.tag_name:
        conditions.append(Customer.tag_relations.any(CustomerTagRelation.tag.has(CustomerTag.name == filters.tag_name)))
    return conditions


def _order_conditions(plan: QueryPlan, start: datetime | None, end: datetime | None) -> list[Any]:
    conditions: list[Any] = [
        Order.customer_id.in_(select(Customer.id).where(*_customer_conditions(plan))),
        consumption_order_condition(),
    ]
    if start:
        conditions.append(Order.paid_at >= start)
    if end:
        conditions.append(Order.paid_at < end)
    return conditions


def _balance_conditions(plan: QueryPlan, start: datetime | None, end: datetime | None) -> list[Any]:
    conditions: list[Any] = [
        CustomerBalanceTransaction.customer_id.in_(select(Customer.id).where(*_customer_conditions(plan))),
    ]
    if start:
        conditions.append(CustomerBalanceTransaction.charged_at >= start)
    if end:
        conditions.append(CustomerBalanceTransaction.charged_at < end)
    return conditions


def _group_expression(group_by: str):
    if group_by == "owner":
        return func.coalesce(User.full_name, "待分配")
    if group_by == "source_level_1":
        return func.coalesce(Customer.source_level_1, "other")
    if group_by == "source_level_2":
        return func.coalesce(Customer.source_level_2, "unknown")
    if group_by == "customer":
        return Customer.name
    return func.date(Order.paid_at)


def _group_label(group_by: str, value: Any) -> str:
    if value is None:
        return "待分配" if group_by == "owner" else "未设置"
    raw = str(value)
    if group_by == "source_level_1":
        return SOURCE_LEVEL_1_LABELS.get(raw, raw)
    if group_by == "source_level_2":
        for options in SOURCE_LEVEL_2_OPTIONS.values():
            for option in options:
                if option["code"] == raw:
                    return option["name"]
        return raw
    return raw


def _amount_expression(metric: str):
    return {
        "effective_revenue": effective_revenue_expression(),
        "total_consumption": consumption_value_expression(),
        "insurance_amount": effective_insurance_expression(),
        "self_pay_amount": effective_self_pay_expression(),
    }.get(metric)


def _order_group_rows(db: Session, plan: QueryPlan, start: datetime | None, end: datetime | None, expression):
    group = _group_expression(plan.group_by or "date")
    query = select(group.label("group_key"), func.coalesce(func.sum(expression), 0).label("value"))
    query = query.select_from(Order).join(Customer, Customer.id == Order.customer_id)
    if plan.group_by == "owner":
        query = query.outerjoin(User, User.id == Customer.assigned_to_id)
    conditions = _order_conditions(plan, start, end)
    query = query.where(*conditions).group_by(group).order_by(func.sum(expression).desc()).limit(plan.limit)
    if plan.filters.min_consumption is not None and plan.metric in {"total_consumption", "effective_revenue", "insurance_amount", "self_pay_amount"}:
        query = query.having(func.sum(consumption_value_expression()) >= plan.filters.min_consumption)
    return db.execute(query).all()


def _consumption_count_group_rows(db: Session, plan: QueryPlan, start: datetime | None, end: datetime | None):
    group = _group_expression(plan.group_by or "date")
    key = consumption_key_expression().label("consumption_key")
    net_value = func.coalesce(func.sum(consumption_value_expression()), 0).label("net_value")
    query = select(group.label("group_key"), key, net_value).select_from(Order).join(Customer, Customer.id == Order.customer_id)
    if plan.group_by == "owner":
        query = query.outerjoin(User, User.id == Customer.assigned_to_id)
    rows = db.execute(query.where(*_order_conditions(plan, start, end)).group_by(group, key)).all()
    counts: dict[str, int] = {}
    for row in rows:
        if _decimal(row.net_value) > 0:
            label = _group_label(plan.group_by or "date", row.group_key)
            counts[label] = counts.get(label, 0) + 1
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)[: plan.limit]


def _customer_metric(db: Session, plan: QueryPlan, start: datetime | None, end: datetime | None) -> float:
    conditions = _customer_conditions(plan)
    if plan.metric in {"assigned_customer_count", "unassigned_customer_count"}:
        conditions.append(Customer.assigned_to_id.is_not(None) if plan.metric == "assigned_customer_count" else Customer.assigned_to_id.is_(None))
    if plan.metric == "new_customer_count":
        if start:
            conditions.append(Customer.created_at >= start)
        if end:
            conditions.append(Customer.created_at < end)
    if plan.metric == "customer_count" and plan.filters.min_consumption is not None:
        order_conditions = _order_conditions(plan, start, end)
        totals = select(Order.customer_id).where(*order_conditions).group_by(Order.customer_id).having(func.sum(consumption_value_expression()) >= plan.filters.min_consumption).subquery()
        return float(db.scalar(select(func.count()).select_from(totals)) or 0)
    return float(db.scalar(select(func.count(Customer.id)).where(*conditions)) or 0)


def execute_query_plan(db: Session, plan: QueryPlan) -> dict[str, Any]:
    start, end, range_label = resolve_time_range(plan.time_range)
    metric = plan.metric
    if metric in {"customer_count", "new_customer_count", "assigned_customer_count", "unassigned_customer_count"} and not plan.group_by:
        value = _customer_metric(db, plan, start, end)
        return {"metric": metric, "range_label": range_label, "value": int(value), "rows": []}

    if metric in {"customer_count", "new_customer_count", "assigned_customer_count", "unassigned_customer_count"} and plan.group_by:
        group = _group_expression(plan.group_by)
        conditions = _customer_conditions(plan)
        if metric == "new_customer_count":
            if start:
                conditions.append(Customer.created_at >= start)
            if end:
                conditions.append(Customer.created_at < end)
        elif metric == "assigned_customer_count":
            conditions.append(Customer.assigned_to_id.is_not(None))
        elif metric == "unassigned_customer_count":
            conditions.append(Customer.assigned_to_id.is_(None))
        query = select(group.label("group_key"), func.count(Customer.id).label("value")).select_from(Customer)
        if plan.group_by == "owner":
            query = query.outerjoin(User, User.id == Customer.assigned_to_id)
        grouped = db.execute(query.where(*conditions).group_by(group).order_by(func.count(Customer.id).desc()).limit(plan.limit)).all()
        rows = [{"label": _group_label(plan.group_by, row.group_key), "value": int(row.value or 0)} for row in grouped]
        return {"metric": metric, "range_label": range_label, "value": sum(row["value"] for row in rows), "rows": rows}

    if metric == "prepaid_balance" and not plan.group_by:
        value = db.scalar(select(func.coalesce(func.sum(Customer.prepaid_balance), 0)).where(*_customer_conditions(plan)))
        return {"metric": metric, "range_label": range_label, "value": money(value), "rows": []}

    if metric == "balance_overview" and not plan.group_by:
        current = db.scalar(select(func.coalesce(func.sum(Customer.prepaid_balance), 0)).where(*_customer_conditions(plan)))
        recharge = db.scalar(select(func.coalesce(func.sum(func.abs(CustomerBalanceTransaction.amount)), 0)).where(*_balance_conditions(plan, None, None), CustomerBalanceTransaction.transaction_type == "recharge"))
        refund = db.scalar(select(func.coalesce(func.sum(func.abs(CustomerBalanceTransaction.amount)), 0)).where(*_balance_conditions(plan, None, None), CustomerBalanceTransaction.transaction_type == "refund"))
        rows = [{"label": "当前储值余额", "value": money(current)}, {"label": "累计充值", "value": money(recharge)}, {"label": "累计退款", "value": money(refund)}]
        return {"metric": metric, "range_label": "全部", "value": rows[0]["value"], "rows": rows}

    if metric in {"recharge_amount", "refund_amount", "prepaid_spent"} and not plan.group_by:
        transaction_type = {"recharge_amount": "recharge", "refund_amount": "refund", "prepaid_spent": "consume"}[metric]
        value = db.scalar(select(func.coalesce(func.sum(func.abs(CustomerBalanceTransaction.amount)), 0)).where(*_balance_conditions(plan, start, end), CustomerBalanceTransaction.transaction_type == transaction_type))
        return {"metric": metric, "range_label": range_label, "value": money(value), "rows": []}

    if metric == "balance_mix" and not plan.group_by:
        conditions = _balance_conditions(plan, start, end)
        rows = []
        for transaction_type, label in (("recharge", "充值"), ("refund", "退款")):
            value = db.scalar(select(func.coalesce(func.sum(func.abs(CustomerBalanceTransaction.amount)), 0)).where(*conditions, CustomerBalanceTransaction.transaction_type == transaction_type))
            rows.append({"label": label, "value": money(value)})
        return {"metric": metric, "range_label": range_label, "value": sum(row["value"] for row in rows), "rows": rows}

    if metric == "payment_mix" and plan.group_by:
        group = _group_expression(plan.group_by)
        query = select(
            group.label("group_key"),
            func.coalesce(func.sum(effective_revenue_expression()), 0).label("value"),
            func.coalesce(func.sum(effective_insurance_expression()), 0).label("insurance"),
            func.coalesce(func.sum(effective_self_pay_expression()), 0).label("self_pay"),
        ).select_from(Order).join(Customer, Customer.id == Order.customer_id)
        if plan.group_by == "owner":
            query = query.outerjoin(User, User.id == Customer.assigned_to_id)
        grouped = db.execute(query.where(*_order_conditions(plan, start, end)).group_by(group).order_by(func.sum(effective_revenue_expression()).desc()).limit(plan.limit)).all()
        rows = [{"label": _group_label(plan.group_by, row.group_key), "value": money(row.value), "insurance": money(row.insurance), "self_pay": money(row.self_pay)} for row in grouped]
        return {"metric": metric, "range_label": range_label, "value": sum(row["value"] for row in rows), "rows": rows}

    if metric in {"payment_mix"} and not plan.group_by:
        conditions = _order_conditions(plan, start, end)
        values = [
            ("有效经营收入", effective_revenue_expression()),
            ("医保支付", effective_insurance_expression()),
            ("自费支付", effective_self_pay_expression()),
        ]
        rows = [{"label": label, "value": money(db.scalar(select(func.coalesce(func.sum(expr), 0)).where(*conditions)))} for label, expr in values]
        return {"metric": metric, "range_label": range_label, "value": rows[0]["value"], "rows": rows}

    expression = _amount_expression(metric)
    if expression is None and metric in {"consumption_count", "average_order_value"}:
        conditions = _order_conditions(plan, start, end)
        count = int(db.scalar(consumption_count_query(*conditions)) or 0)
        if metric == "consumption_count":
            return {"metric": metric, "range_label": range_label, "value": count, "rows": []}
        total = db.scalar(select(func.coalesce(func.sum(consumption_value_expression()), 0)).where(*conditions))
        return {"metric": metric, "range_label": range_label, "value": money(_decimal(total) / count if count else 0), "rows": []}

    if plan.group_by and metric == "consumption_count":
        grouped = _consumption_count_group_rows(db, plan, start, end)
        rows = [{"label": label, "value": count} for label, count in grouped]
        return {"metric": metric, "range_label": range_label, "value": sum(row["value"] for row in rows), "rows": rows}

    if plan.group_by and expression is not None:
        grouped = _order_group_rows(db, plan, start, end, expression)
        rows = [{"label": _group_label(plan.group_by, row.group_key), "value": money(row.value)} for row in grouped]
        return {"metric": metric, "range_label": range_label, "value": sum(row["value"] for row in rows), "rows": rows}

    if expression is not None and not plan.group_by:
        value = db.scalar(select(func.coalesce(func.sum(expression), 0)).where(*_order_conditions(plan, start, end)))
        return {"metric": metric, "range_label": range_label, "value": money(value), "rows": []}

    if plan.group_by and metric in {"prepaid_balance", "recharge_amount", "refund_amount", "prepaid_spent"}:
        if metric == "prepaid_balance":
            group = _group_expression(plan.group_by)
            query = select(group.label("group_key"), func.coalesce(func.sum(Customer.prepaid_balance), 0).label("value")).select_from(Customer)
            if plan.group_by == "owner":
                query = query.outerjoin(User, User.id == Customer.assigned_to_id)
            grouped = db.execute(query.where(*_customer_conditions(plan)).group_by(group).order_by(func.sum(Customer.prepaid_balance).desc()).limit(plan.limit)).all()
        else:
            transaction_type = {"recharge_amount": "recharge", "refund_amount": "refund", "prepaid_spent": "consume"}[metric]
            group = _group_expression(plan.group_by)
            query = select(group.label("group_key"), func.coalesce(func.sum(func.abs(CustomerBalanceTransaction.amount)), 0).label("value")).select_from(CustomerBalanceTransaction).join(Customer, Customer.id == CustomerBalanceTransaction.customer_id)
            if plan.group_by == "owner":
                query = query.outerjoin(User, User.id == Customer.assigned_to_id)
            grouped = db.execute(query.where(*_balance_conditions(plan, start, end), CustomerBalanceTransaction.transaction_type == transaction_type).group_by(group).order_by(func.sum(func.abs(CustomerBalanceTransaction.amount)).desc()).limit(plan.limit)).all()
        rows = [{"label": _group_label(plan.group_by, row.group_key), "value": money(row.value)} for row in grouped]
        return {"metric": metric, "range_label": range_label, "value": sum(row["value"] for row in rows), "rows": rows}

    # A future planner extension should fail closed rather than executing an
    # arbitrary expression.
    raise ValueError("当前问题暂不支持该统计方式")
