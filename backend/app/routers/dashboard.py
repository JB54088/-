from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from ..consumption import consumption_count_query, consumption_net_keys_subquery, consumption_value_expression, effective_insurance_expression, effective_revenue_expression, effective_self_pay_expression
from ..database import get_db
from ..deps import get_current_user
from ..models import Customer, CustomerBalanceTransaction, CustomerTag, CustomerTagRelation, Order, User
from ..source_categories import SOURCE_CATEGORY_OPTIONS, SOURCE_LEVEL_2_OPTIONS
from ..utils import consumption_key_expression, consumption_order_condition, customer_scope_condition, formal_customer_condition, is_admin, money, order_scope_condition, period_bounds

router = APIRouter(prefix="/dashboard", tags=["经营看板"])


def _conditions(user: User, customer: bool = False) -> list:
    formal_customers = formal_customer_condition()
    condition = customer_scope_condition(user) if customer else order_scope_condition(user)
    if customer:
        return [formal_customers] if condition is True else [condition, formal_customers]
    formal_order_scope = Order.customer_id.in_(select(Customer.id).where(formal_customers))
    base = [formal_order_scope, consumption_order_condition()]
    return base if condition is True else [condition, *base]


def _count(db: Session, model, conditions: list) -> int:
    return int(db.scalar(select(func.count(model.id)).where(*conditions)) or 0)


def _sum_orders(db: Session, user: User, start: datetime | None = None, end: datetime | None = None) -> float:
    conditions = _conditions(user)
    if start:
        conditions.append(Order.paid_at >= start)
    if end:
        conditions.append(Order.paid_at <= end)
    return money(db.scalar(select(func.coalesce(func.sum(effective_revenue_expression()), 0)).where(*conditions)))


def _sum_consumption(db: Session, user: User, start: datetime | None = None, end: datetime | None = None) -> float:
    """Sum imported project value, independent of actual payment received."""
    conditions = _conditions(user)
    if start:
        conditions.append(Order.paid_at >= start)
    if end:
        conditions.append(Order.paid_at <= end)
    return money(db.scalar(select(func.coalesce(func.sum(consumption_value_expression()), 0)).where(*conditions)))


def _sum_payment(db: Session, user: User, field, start: datetime | None = None, end: datetime | None = None) -> float:
    conditions = _conditions(user)
    if start:
        conditions.append(Order.paid_at >= start)
    if end:
        conditions.append(Order.paid_at <= end)
    return money(db.scalar(select(func.coalesce(func.sum(field), 0)).where(*conditions)))


def _count_unknown_payment_splits(db: Session, user: User, start: datetime | None = None, end: datetime | None = None) -> int:
    conditions = _conditions(user)
    if start:
        conditions.append(Order.paid_at >= start)
    if end:
        conditions.append(Order.paid_at <= end)
    conditions.append(or_(Order.insurance_amount.is_(None), Order.self_pay_amount.is_(None)))
    return int(db.scalar(select(func.count(Order.id)).where(*conditions)) or 0)


def _sum_balance_ledger(db: Session, user: User, transaction_type: str, start: datetime | None = None, end: datetime | None = None) -> float:
    """Sum one customer-scoped prepaid ledger category as a positive amount."""

    conditions = [*_conditions(user, customer=True), CustomerBalanceTransaction.transaction_type == transaction_type]
    if start:
        conditions.append(CustomerBalanceTransaction.charged_at >= start)
    if end:
        conditions.append(CustomerBalanceTransaction.charged_at <= end)
    value = func.abs(CustomerBalanceTransaction.amount)
    query = select(func.coalesce(func.sum(value), 0)).join(
        Customer, Customer.id == CustomerBalanceTransaction.customer_id
    ).where(*conditions)
    return money(db.scalar(query))


def _current_prepaid_balance(db: Session, user: User) -> float:
    conditions = _conditions(user, customer=True)
    return money(db.scalar(select(func.coalesce(func.sum(Customer.prepaid_balance), 0)).where(*conditions)))


@router.get("")
def dashboard(
    period: str = Query("month", pattern="^(today|week|month|custom)$"),
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    period_start, period_end = period_bounds(period, start, end)
    week_start, week_end = period_bounds("week")
    month_start, month_end = period_bounds("month")
    today_start, today_end = period_bounds("today")
    customer_conditions = _conditions(user, customer=True)
    order_conditions = _conditions(user)
    consumption_value = consumption_value_expression()
    effective_revenue = effective_revenue_expression()
    effective_self_pay = effective_self_pay_expression()
    business_insurance = effective_insurance_expression()

    def count_customers_since(from_date: datetime, to_date: datetime | None = None) -> int:
        conditions = [*customer_conditions, Customer.created_at >= from_date]
        if to_date:
            conditions.append(Customer.created_at <= to_date)
        return _count(db, Customer, conditions)

    def count_leads_since(from_date: datetime, to_date: datetime | None = None) -> int:
        conditions = [*customer_conditions, Customer.reported_at >= from_date]
        if to_date:
            conditions.append(Customer.reported_at <= to_date)
        return _count(db, Customer, conditions)

    period_revenue = _sum_orders(db, user, period_start, period_end)
    week_revenue = _sum_orders(db, user, week_start, week_end)
    month_revenue = _sum_orders(db, user, month_start, month_end)
    total_revenue = _sum_orders(db, user)
    period_consumption = _sum_consumption(db, user, period_start, period_end)
    week_consumption = _sum_consumption(db, user, week_start, week_end)
    month_consumption = _sum_consumption(db, user, month_start, month_end)
    total_consumption = _sum_consumption(db, user)
    period_insurance = _sum_payment(db, user, business_insurance, period_start, period_end)
    period_self_pay = _sum_payment(db, user, effective_self_pay, period_start, period_end)
    week_insurance = _sum_payment(db, user, business_insurance, week_start, week_end)
    week_self_pay = _sum_payment(db, user, effective_self_pay, week_start, week_end)
    month_insurance = _sum_payment(db, user, business_insurance, month_start, month_end)
    month_self_pay = _sum_payment(db, user, effective_self_pay, month_start, month_end)
    total_insurance = _sum_payment(db, user, business_insurance)
    total_self_pay = _sum_payment(db, user, effective_self_pay)
    period_deduction = _sum_payment(db, user, Order.deduction_amount, period_start, period_end)
    period_discount = _sum_payment(db, user, Order.discount_amount, period_start, period_end)
    week_deduction = _sum_payment(db, user, Order.deduction_amount, week_start, week_end)
    week_discount = _sum_payment(db, user, Order.discount_amount, week_start, week_end)
    month_deduction = _sum_payment(db, user, Order.deduction_amount, month_start, month_end)
    month_discount = _sum_payment(db, user, Order.discount_amount, month_start, month_end)
    total_deduction = _sum_payment(db, user, Order.deduction_amount)
    total_discount = _sum_payment(db, user, Order.discount_amount)
    period_recharge = _sum_balance_ledger(db, user, "recharge", period_start, period_end)
    week_recharge = _sum_balance_ledger(db, user, "recharge", week_start, week_end)
    month_recharge = _sum_balance_ledger(db, user, "recharge", month_start, month_end)
    total_recharge = _sum_balance_ledger(db, user, "recharge")
    period_refund = _sum_balance_ledger(db, user, "refund", period_start, period_end)
    week_refund = _sum_balance_ledger(db, user, "refund", week_start, week_end)
    month_refund = _sum_balance_ledger(db, user, "refund", month_start, month_end)
    total_refund = _sum_balance_ledger(db, user, "refund")
    current_prepaid_balance = _current_prepaid_balance(db, user)
    period_unknown_splits = _count_unknown_payment_splits(db, user, period_start, period_end)
    week_unknown_splits = _count_unknown_payment_splits(db, user, week_start, week_end)
    month_unknown_splits = _count_unknown_payment_splits(db, user, month_start, month_end)
    total_unknown_splits = _count_unknown_payment_splits(db, user)
    month_order_conditions = [*order_conditions, Order.paid_at >= month_start, Order.paid_at <= month_end]
    month_orders = int(db.scalar(consumption_count_query(*month_order_conditions)) or 0)
    net_order_keys = consumption_net_keys_subquery(*order_conditions)
    paid_customer_subquery = select(net_order_keys.c.customer_id).where(net_order_keys.c.net_value > 0).group_by(net_order_keys.c.customer_id).subquery()
    repeat_subquery = select(net_order_keys.c.customer_id).where(net_order_keys.c.net_value > 0).group_by(net_order_keys.c.customer_id).having(func.count() >= 2).subquery()
    paid_count = int(db.scalar(select(func.count()).select_from(paid_customer_subquery)) or 0)
    repeat_count = int(db.scalar(select(func.count()).select_from(repeat_subquery)) or 0)
    tag_customer_conditions = [*customer_conditions]

    trend_rows = db.execute(
        select(func.date(Order.paid_at).label("day"), func.coalesce(func.sum(effective_revenue), 0).label("revenue"))
        .where(*order_conditions, Order.paid_at >= datetime.now() - timedelta(days=29), Order.paid_at <= period_end)
        .group_by(func.date(Order.paid_at))
        .order_by(func.date(Order.paid_at))
    ).all()
    trend_map = {str(row.day): money(row.revenue) for row in trend_rows}
    revenue_trend = [{"date": (datetime.now() - timedelta(days=29 - i)).strftime("%m/%d"), "revenue": trend_map.get(str((datetime.now() - timedelta(days=29 - i)).date()), 0)} for i in range(30)]

    new_rows = db.execute(
        select(func.date(Customer.created_at).label("day"), func.count(Customer.id).label("count"))
        .where(*customer_conditions, Customer.created_at >= datetime.now() - timedelta(days=29))
        .group_by(func.date(Customer.created_at))
        .order_by(func.date(Customer.created_at))
    ).all()
    new_map = {str(row.day): int(row.count) for row in new_rows}
    new_customer_trend = [{"date": (datetime.now() - timedelta(days=29 - i)).strftime("%m/%d"), "count": new_map.get(str((datetime.now() - timedelta(days=29 - i)).date()), 0)} for i in range(30)]

    source_count_rows = db.execute(
        select(Customer.source_level_1, func.count(Customer.id))
        .where(*tag_customer_conditions)
        .group_by(Customer.source_level_1)
    ).all()
    source_revenue_rows = db.execute(
        select(
            Customer.source_level_1,
            func.coalesce(func.sum(effective_revenue), 0),
            func.coalesce(func.sum(consumption_value), 0),
            func.coalesce(func.sum(case((and_(Order.paid_at >= week_start, Order.paid_at <= week_end), effective_revenue), else_=0)), 0),
            func.coalesce(func.sum(case((and_(Order.paid_at >= week_start, Order.paid_at <= week_end), consumption_value_expression()), else_=0)), 0),
            func.coalesce(func.sum(case((and_(Order.paid_at >= month_start, Order.paid_at <= month_end), effective_revenue), else_=0)), 0),
            func.coalesce(func.sum(case((and_(Order.paid_at >= month_start, Order.paid_at <= month_end), consumption_value_expression()), else_=0)), 0),
        )
        .join(Order, Order.customer_id == Customer.id)
        .where(*order_conditions)
        .group_by(Customer.source_level_1)
    ).all()
    source_count_map = {row[0] or "other": int(row[1] or 0) for row in source_count_rows}
    source_revenue_map = {
        row[0] or "other": {"total": money(row[1]), "total_consumption": money(row[2]), "week": money(row[3]), "week_consumption": money(row[4]), "month": money(row[5]), "month_consumption": money(row[6])}
        for row in source_revenue_rows
    }
    source_total_customers = sum(source_count_map.values())
    source_analysis = []
    for option in SOURCE_CATEGORY_OPTIONS:
        code = option["code"]
        revenue = source_revenue_map.get(code, {"total": 0, "total_consumption": 0, "week": 0, "week_consumption": 0, "month": 0, "month_consumption": 0})
        count = source_count_map.get(code, 0)
        source_analysis.append({
            "code": code,
            "name": option["name"],
            "customer_count": count,
            "customer_percentage": round(count / source_total_customers * 100, 1) if source_total_customers else 0,
            "total_revenue": revenue["total"],
            "week_revenue": revenue["week"],
            "month_revenue": revenue["month"],
            "total_consumption": revenue["total_consumption"],
            "week_consumption": revenue["week_consumption"],
            "month_consumption": revenue["month_consumption"],
        })
    source_level_2_count_rows = db.execute(
        select(Customer.source_level_1, Customer.source_level_2, func.count(Customer.id))
        .where(*tag_customer_conditions)
        .group_by(Customer.source_level_1, Customer.source_level_2)
    ).all()
    source_level_2_revenue_rows = db.execute(
        select(
            Customer.source_level_1,
            Customer.source_level_2,
            func.coalesce(func.sum(effective_revenue), 0),
            func.coalesce(func.sum(consumption_value), 0),
        )
        .join(Order, Order.customer_id == Customer.id)
        .where(*order_conditions)
        .group_by(Customer.source_level_1, Customer.source_level_2)
    ).all()
    source_level_2_counts = {(row[0], row[1]): int(row[2] or 0) for row in source_level_2_count_rows}
    source_level_2_revenue = {(row[0], row[1]): {"revenue": money(row[2]), "consumption": money(row[3])} for row in source_level_2_revenue_rows}
    source_level_2_analysis = []
    for level_1 in SOURCE_CATEGORY_OPTIONS:
        for level_2 in SOURCE_LEVEL_2_OPTIONS.get(level_1["code"], ()):
            key = (level_1["code"], level_2["code"])
            values = source_level_2_revenue.get(key, {"revenue": 0, "consumption": 0})
            source_level_2_analysis.append({
                "level_1_code": level_1["code"],
                "level_1_name": level_1["name"],
                "code": level_2["code"],
                "name": level_2["name"],
                "customer_count": source_level_2_counts.get(key, 0),
                "total_revenue": values["revenue"],
                "total_consumption": values["consumption"],
            })
    tag_rows = db.execute(
        select(CustomerTag.name, func.count(CustomerTagRelation.customer_id))
        .join(CustomerTagRelation, CustomerTagRelation.tag_id == CustomerTag.id)
        .join(Customer, Customer.id == CustomerTagRelation.customer_id)
        .where(*customer_conditions)
        .group_by(CustomerTag.name)
        .order_by(func.count(CustomerTagRelation.customer_id).desc())
        .limit(8)
    ).all()

    high_value_rows = db.execute(
        select(Customer.id, Customer.name, User.full_name, func.coalesce(func.sum(consumption_value_expression()), 0))
        .outerjoin(Order, Order.customer_id == Customer.id)
        .outerjoin(User, Customer.assigned_to_id == User.id)
        .where(*customer_conditions)
        .group_by(Customer.id, Customer.name, User.full_name)
        .order_by(func.coalesce(func.sum(consumption_value), 0).desc())
        .limit(10)
    ).all()
    high_value_customers = [{"id": row[0], "name": row[1], "assigned_to_name": row[2], "total_spend": money(row[3])} for row in high_value_rows]

    sales_performance = []
    if is_admin(user):
        sales_rows = db.execute(
            select(
                User.id,
                User.full_name,
                func.count(func.distinct(Customer.id)),
                func.coalesce(func.sum(effective_revenue), 0),
                func.coalesce(func.sum(consumption_value), 0),
                func.coalesce(func.sum(business_insurance), 0),
                func.coalesce(func.sum(effective_self_pay), 0),
                func.coalesce(func.sum(case((Order.paid_at >= week_start, effective_revenue), else_=0)), 0),
                func.coalesce(func.sum(case((Order.paid_at >= week_start, consumption_value), else_=0)), 0),
                func.coalesce(func.sum(case((Order.paid_at >= week_start, business_insurance), else_=0)), 0),
                func.coalesce(func.sum(case((Order.paid_at >= week_start, effective_self_pay), else_=0)), 0),
                func.coalesce(func.sum(case((Order.paid_at >= month_start, effective_revenue), else_=0)), 0),
                func.coalesce(func.sum(case((Order.paid_at >= month_start, consumption_value), else_=0)), 0),
                func.coalesce(func.sum(case((Order.paid_at >= month_start, business_insurance), else_=0)), 0),
                func.coalesce(func.sum(case((Order.paid_at >= month_start, effective_self_pay), else_=0)), 0),
                func.coalesce(func.sum(case((and_(Order.paid_at >= period_start, Order.paid_at <= period_end), effective_revenue), else_=0)), 0),
                func.coalesce(func.sum(case((and_(Order.paid_at >= period_start, Order.paid_at <= period_end), consumption_value), else_=0)), 0),
                func.coalesce(func.sum(case((and_(Order.paid_at >= period_start, Order.paid_at <= period_end), business_insurance), else_=0)), 0),
                func.coalesce(func.sum(case((and_(Order.paid_at >= period_start, Order.paid_at <= period_end), effective_self_pay), else_=0)), 0),
            )
            .select_from(User)
            .outerjoin(Customer, Customer.assigned_to_id == User.id)
            .outerjoin(Order, Order.customer_id == Customer.id)
            .where(User.role == "salesperson", User.is_active.is_(True), formal_customer_condition())
            .group_by(User.id, User.full_name)
            .order_by(func.sum(consumption_value).desc().nullslast())
        ).all()
        sales_performance = [{
            "id": row[0],
            "name": row[1],
            "customer_count": int(row[2] or 0),
            "revenue": money(row[15]),
            "total_revenue": money(row[3]),
            "total_consumption": money(row[4]),
            "total_insurance": money(row[5]),
            "total_self_pay": money(row[6]),
            "week_revenue": money(row[7]),
            "week_consumption": money(row[8]),
            "week_insurance": money(row[9]),
            "week_self_pay": money(row[10]),
            "month_revenue": money(row[11]),
            "month_consumption": money(row[12]),
            "month_insurance": money(row[13]),
            "month_self_pay": money(row[14]),
            "period_consumption": money(row[16]),
            "period_insurance": money(row[17]),
            "period_self_pay": money(row[18]),
        } for row in sales_rows]

    recent_rows = db.execute(
        select(Order.id, Order.item_name, consumption_value, Order.paid_at, Customer.id, Customer.name)
        .join(Customer, Customer.id == Order.customer_id)
        .where(*order_conditions)
        .order_by(Order.paid_at.desc())
        .limit(8)
    ).all()
    recent_activity = [{"id": row[0], "title": f"{row[5]} 完成消费", "description": f"{row[1]} · 消费价值 ¥{money(row[2]):,.2f}", "occurred_at": row[3]} for row in recent_rows]
    follow_up_conditions = [*customer_conditions, Customer.tag_relations.any(CustomerTagRelation.tag.has(CustomerTag.name == "待跟进"))]
    follow_up_count = _count(db, Customer, follow_up_conditions)
    unassigned_count = _count(db, Customer, [formal_customer_condition(), Customer.assigned_to_id.is_(None)]) if is_admin(user) else 0
    converted_count = _count(db, Customer, [*customer_conditions, Customer.lead_status == "converted"])

    return {
        "role_view": "admin" if is_admin(user) else "salesperson",
        "period": {"start": period_start, "end": period_end},
        "kpis": {
            "total_customers": _count(db, Customer, customer_conditions),
            "today_new_leads": count_leads_since(today_start, today_end) if is_admin(user) else count_customers_since(today_start, today_end),
            "week_new_leads": count_leads_since(week_start, week_end) if is_admin(user) else count_customers_since(week_start, week_end),
            "unassigned_customers": unassigned_count,
            "converted_customers": converted_count,
            "assigned_customers": _count(db, Customer, [*customer_conditions, Customer.assigned_to_id.is_not(None)]),
            "week_revenue": week_revenue,
            "month_revenue": month_revenue,
            "total_revenue": total_revenue,
            "period_revenue": period_revenue,
            "week_consumption": week_consumption,
            "month_consumption": month_consumption,
            "total_consumption": total_consumption,
            "period_consumption": period_consumption,
            "period_insurance": period_insurance,
            "period_self_pay": period_self_pay,
            "week_insurance": week_insurance,
            "week_self_pay": week_self_pay,
            "month_insurance": month_insurance,
            "month_self_pay": month_self_pay,
            "total_insurance": total_insurance,
            "total_self_pay": total_self_pay,
            "period_deduction": period_deduction,
            "period_discount": period_discount,
            "week_deduction": week_deduction,
            "week_discount": week_discount,
            "month_deduction": month_deduction,
            "month_discount": month_discount,
            "total_deduction": total_deduction,
            "total_discount": total_discount,
            "period_recharge": period_recharge,
            "week_recharge": week_recharge,
            "month_recharge": month_recharge,
            "total_recharge": total_recharge,
            "period_refund": period_refund,
            "week_refund": week_refund,
            "month_refund": month_refund,
            "total_refund": total_refund,
            "current_prepaid_balance": current_prepaid_balance,
            "period_payment_split_unknown_orders": period_unknown_splits,
            "week_payment_split_unknown_orders": week_unknown_splits,
            "month_payment_split_unknown_orders": month_unknown_splits,
            "total_payment_split_unknown_orders": total_unknown_splits,
            "week_insurance_amount": week_insurance,
            "week_self_pay_amount": week_self_pay,
            "month_insurance_amount": month_insurance,
            "month_self_pay_amount": month_self_pay,
            "insurance_ratio": round(period_insurance / period_revenue * 100, 1) if period_revenue else 0,
            "self_pay_ratio": round(period_self_pay / period_revenue * 100, 1) if period_revenue else 0,
            "avg_order_value": round(month_consumption / month_orders, 2) if month_orders else 0,
            "repurchase_rate": round(repeat_count / paid_count * 100, 1) if paid_count else 0,
            "my_customers": _count(db, Customer, customer_conditions),
            "week_new_customers": count_customers_since(week_start, week_end),
            "month_new_customers": count_customers_since(month_start, month_end),
            "my_total_spend": total_consumption,
            "month_my_spend": month_consumption,
            "my_order_count": int(db.scalar(consumption_count_query(*order_conditions)) or 0),
            "follow_up_customers": follow_up_count,
        },
        "revenue_trend": revenue_trend,
        "new_customer_trend": new_customer_trend,
        "source_breakdown": [{"name": item["name"], "value": item["customer_count"]} for item in source_analysis],
        "source_revenue_breakdown": [{"name": item["name"], "value": item["total_revenue"]} for item in source_analysis],
        "source_consumption_breakdown": [{"name": item["name"], "value": item["total_consumption"]} for item in source_analysis],
        "source_analysis": source_analysis,
        "source_level_2_analysis": source_level_2_analysis,
        "tag_breakdown": [{"name": row[0], "value": int(row[1])} for row in tag_rows],
        "high_value_customers": high_value_customers,
        "sales_performance": sales_performance,
        "sales_ranking": [{"name": row["name"], "value": row["revenue"]} for row in sales_performance],
        "customer_mix": [{"name": "本期新增", "value": count_customers_since(period_start, period_end)}, {"name": "历史客户", "value": max(paid_count - count_customers_since(period_start, period_end), 0)}],
        "recent_activity": recent_activity,
    }
