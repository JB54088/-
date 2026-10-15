from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from ..consumption import consumption_count_query, consumption_net_keys_subquery, consumption_value_expression, effective_insurance_expression, effective_revenue_expression, effective_self_pay_expression
from ..database import get_db
from ..deps import require_admin
from ..models import Customer, CustomerBalanceTransaction, Order, Report, User
from ..source_categories import SOURCE_CATEGORY_OPTIONS, SOURCE_LEVEL_2_OPTIONS
from ..utils import consumption_key_expression, consumption_order_condition, formal_customer_condition, money

router = APIRouter(prefix="/reports", tags=["经营报告"])

BUSINESS_TZ = ZoneInfo("Asia/Shanghai")


def business_today(reference: datetime | None = None) -> datetime:
    """Return today's midnight in the business timezone as a naive local value.

    Order/Customer business timestamps are stored as local business datetimes
    (ABC charge times are not UTC instants), so report predicates must compare
    against Asia/Shanghai calendar boundaries rather than the container clock.
    """
    if reference is None:
        current = datetime.now(BUSINESS_TZ)
    elif reference.tzinfo is None:
        current = reference.replace(tzinfo=BUSINESS_TZ)
    else:
        current = reference.astimezone(BUSINESS_TZ)
    return current.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def bounds(period: str, reference: datetime | None = None):
    current = business_today(reference)
    if period == "week":
        start = current - timedelta(days=current.weekday())
        return start, start + timedelta(days=7), start - timedelta(days=7)
    start = current.replace(day=1)
    previous_start = (start - timedelta(days=1)).replace(day=1)
    return start, current + timedelta(days=1), previous_start


def display_end(end_exclusive: datetime) -> datetime:
    """Convert an exclusive next-day boundary to the last displayed date."""
    return end_exclusive - timedelta(days=1)


def build_report(db: Session, period: str, start: datetime, end: datetime, previous_start: datetime):
    week_start, week_end, _ = bounds("week")
    month_start, month_end, _ = bounds("month")
    formal_customers = formal_customer_condition()
    formal_order = and_(Order.customer_id.in_(select(Customer.id).where(formal_customers)), consumption_order_condition())
    current_orders = [formal_order, Order.paid_at >= start, Order.paid_at < end]
    previous_orders = [formal_order, Order.paid_at >= previous_start, Order.paid_at < start]
    current_customers = [formal_customers, Customer.created_at >= start, Customer.created_at < end]
    consumption_value = consumption_value_expression()
    effective_revenue = effective_revenue_expression()
    effective_self_pay = effective_self_pay_expression()
    business_insurance = effective_insurance_expression()

    def balance_total(transaction_type: str, from_date: datetime | None = None, to_date: datetime | None = None) -> float:
        conditions = [formal_customers, CustomerBalanceTransaction.transaction_type == transaction_type]
        if from_date:
            conditions.append(CustomerBalanceTransaction.charged_at >= from_date)
        if to_date:
            conditions.append(CustomerBalanceTransaction.charged_at < to_date)
        return money(db.scalar(
            select(func.coalesce(func.sum(func.abs(CustomerBalanceTransaction.amount)), 0))
            .join(Customer, Customer.id == CustomerBalanceTransaction.customer_id)
            .where(*conditions)
        ))

    current_recharge = balance_total("recharge", start, end)
    current_refund = balance_total("refund", start, end)
    total_recharge = balance_total("recharge")
    total_refund = balance_total("refund")
    current_prepaid_balance = money(db.scalar(select(func.coalesce(func.sum(Customer.prepaid_balance), 0)).where(formal_customers)))
    revenue = money(db.scalar(select(func.coalesce(func.sum(effective_revenue), 0)).where(*current_orders)))
    previous_revenue = money(db.scalar(select(func.coalesce(func.sum(effective_revenue), 0)).where(*previous_orders)))
    week_revenue = money(db.scalar(select(func.coalesce(func.sum(effective_revenue), 0)).where(formal_order, Order.paid_at >= week_start, Order.paid_at < week_end)))
    month_revenue = money(db.scalar(select(func.coalesce(func.sum(effective_revenue), 0)).where(formal_order, Order.paid_at >= month_start, Order.paid_at < month_end)))
    total_revenue = money(db.scalar(select(func.coalesce(func.sum(effective_revenue), 0)).where(formal_order)))
    consumption = money(db.scalar(select(func.coalesce(func.sum(consumption_value), 0)).where(*current_orders)))
    previous_consumption = money(db.scalar(select(func.coalesce(func.sum(consumption_value), 0)).where(*previous_orders)))
    week_consumption = money(db.scalar(select(func.coalesce(func.sum(consumption_value), 0)).where(formal_order, Order.paid_at >= week_start, Order.paid_at < week_end)))
    month_consumption = money(db.scalar(select(func.coalesce(func.sum(consumption_value), 0)).where(formal_order, Order.paid_at >= month_start, Order.paid_at < month_end)))
    total_consumption = money(db.scalar(select(func.coalesce(func.sum(consumption_value), 0)).where(formal_order)))
    period_insurance = money(db.scalar(select(func.coalesce(func.sum(business_insurance), 0)).where(*current_orders)))
    period_self_pay = money(db.scalar(select(func.coalesce(func.sum(effective_self_pay), 0)).where(*current_orders)))
    week_insurance = money(db.scalar(select(func.coalesce(func.sum(business_insurance), 0)).where(formal_order, Order.paid_at >= week_start, Order.paid_at < week_end)))
    week_self_pay = money(db.scalar(select(func.coalesce(func.sum(effective_self_pay), 0)).where(formal_order, Order.paid_at >= week_start, Order.paid_at < week_end)))
    month_insurance = money(db.scalar(select(func.coalesce(func.sum(business_insurance), 0)).where(formal_order, Order.paid_at >= month_start, Order.paid_at < month_end)))
    month_self_pay = money(db.scalar(select(func.coalesce(func.sum(effective_self_pay), 0)).where(formal_order, Order.paid_at >= month_start, Order.paid_at < month_end)))
    total_insurance = money(db.scalar(select(func.coalesce(func.sum(business_insurance), 0)).where(formal_order)))
    total_self_pay = money(db.scalar(select(func.coalesce(func.sum(effective_self_pay), 0)).where(formal_order)))
    period_deduction = money(db.scalar(select(func.coalesce(func.sum(Order.deduction_amount), 0)).where(*current_orders)))
    period_discount = money(db.scalar(select(func.coalesce(func.sum(Order.discount_amount), 0)).where(*current_orders)))
    week_deduction = money(db.scalar(select(func.coalesce(func.sum(Order.deduction_amount), 0)).where(formal_order, Order.paid_at >= week_start, Order.paid_at < week_end)))
    week_discount = money(db.scalar(select(func.coalesce(func.sum(Order.discount_amount), 0)).where(formal_order, Order.paid_at >= week_start, Order.paid_at < week_end)))
    month_deduction = money(db.scalar(select(func.coalesce(func.sum(Order.deduction_amount), 0)).where(formal_order, Order.paid_at >= month_start, Order.paid_at < month_end)))
    month_discount = money(db.scalar(select(func.coalesce(func.sum(Order.discount_amount), 0)).where(formal_order, Order.paid_at >= month_start, Order.paid_at < month_end)))
    total_deduction = money(db.scalar(select(func.coalesce(func.sum(Order.deduction_amount), 0)).where(formal_order)))
    total_discount = money(db.scalar(select(func.coalesce(func.sum(Order.discount_amount), 0)).where(formal_order)))
    def unknown_split_count(*conditions) -> int:
        return int(db.scalar(select(func.count(Order.id)).where(*conditions, or_(Order.insurance_amount.is_(None), Order.self_pay_amount.is_(None)))) or 0)

    period_unknown_splits = unknown_split_count(*current_orders)
    week_unknown_splits = unknown_split_count(formal_order, Order.paid_at >= week_start, Order.paid_at < week_end)
    month_unknown_splits = unknown_split_count(formal_order, Order.paid_at >= month_start, Order.paid_at < month_end)
    total_unknown_splits = unknown_split_count(formal_order)
    order_count = int(db.scalar(consumption_count_query(*current_orders)) or 0)
    new_count = int(db.scalar(select(func.count(Customer.id)).where(*current_customers)) or 0)
    visit_count = int(db.scalar(select(func.count(func.distinct(Order.customer_id))).where(*current_orders)) or 0)
    net_order_keys = consumption_net_keys_subquery(*current_orders)
    repeat_subquery = select(net_order_keys.c.customer_id).where(net_order_keys.c.net_value > 0).group_by(net_order_keys.c.customer_id).having(func.count() >= 2).subquery()
    repeat_count = int(db.scalar(select(func.count()).select_from(repeat_subquery)) or 0)
    customer_subquery = select(Order.customer_id).where(*current_orders).group_by(Order.customer_id).subquery()
    paid_customer_count = int(db.scalar(select(func.count()).select_from(customer_subquery)) or 0)
    total_customer_count = int(db.scalar(select(func.count(Customer.id)).where(formal_customers)) or 0)
    unassigned_customer_count = int(db.scalar(select(func.count(Customer.id)).where(formal_customers, Customer.assigned_to_id.is_(None))) or 0)

    period_revenue_case = func.coalesce(func.sum(case((and_(Order.paid_at >= start, Order.paid_at < end), effective_revenue), else_=0)), 0)
    period_consumption_case = func.coalesce(func.sum(case((and_(Order.paid_at >= start, Order.paid_at < end), consumption_value), else_=0)), 0)
    period_insurance_case = func.coalesce(func.sum(case((and_(Order.paid_at >= start, Order.paid_at < end), business_insurance), else_=0)), 0)
    period_self_pay_case = func.coalesce(func.sum(case((and_(Order.paid_at >= start, Order.paid_at < end), effective_self_pay), else_=0)), 0)
    week_revenue_case = func.coalesce(func.sum(case((and_(Order.paid_at >= week_start, Order.paid_at < week_end), effective_revenue), else_=0)), 0)
    week_consumption_case = func.coalesce(func.sum(case((and_(Order.paid_at >= week_start, Order.paid_at < week_end), consumption_value), else_=0)), 0)
    week_insurance_case = func.coalesce(func.sum(case((and_(Order.paid_at >= week_start, Order.paid_at < week_end), business_insurance), else_=0)), 0)
    week_self_pay_case = func.coalesce(func.sum(case((and_(Order.paid_at >= week_start, Order.paid_at < week_end), effective_self_pay), else_=0)), 0)
    month_revenue_case = func.coalesce(func.sum(case((and_(Order.paid_at >= month_start, Order.paid_at < month_end), effective_revenue), else_=0)), 0)
    month_consumption_case = func.coalesce(func.sum(case((and_(Order.paid_at >= month_start, Order.paid_at < month_end), consumption_value), else_=0)), 0)
    month_insurance_case = func.coalesce(func.sum(case((and_(Order.paid_at >= month_start, Order.paid_at < month_end), business_insurance), else_=0)), 0)
    month_self_pay_case = func.coalesce(func.sum(case((and_(Order.paid_at >= month_start, Order.paid_at < month_end), effective_self_pay), else_=0)), 0)
    total_revenue_case = func.coalesce(func.sum(effective_revenue), 0)
    total_consumption_case = func.coalesce(func.sum(consumption_value), 0)
    total_insurance_case = func.coalesce(func.sum(business_insurance), 0)
    total_self_pay_case = func.coalesce(func.sum(effective_self_pay), 0)
    new_customer_case = func.count(func.distinct(case((and_(Customer.created_at >= start, Customer.created_at < end), Customer.id), else_=None)))
    sales_rows = db.execute(
        select(User.id, User.full_name, func.count(func.distinct(Customer.id)), period_revenue_case, period_consumption_case, period_insurance_case, period_self_pay_case, week_revenue_case, week_consumption_case, week_insurance_case, week_self_pay_case, month_revenue_case, month_consumption_case, month_insurance_case, month_self_pay_case, total_revenue_case, total_consumption_case, total_insurance_case, total_self_pay_case, new_customer_case)
        .select_from(User)
        .outerjoin(Customer, Customer.assigned_to_id == User.id)
        .outerjoin(Order, Order.customer_id == Customer.id)
        .where(User.role == "salesperson", User.is_active.is_(True), formal_customer_condition())
        .group_by(User.id, User.full_name)
        .order_by(period_revenue_case.desc())
    ).all()

    value_rows = db.execute(
        select(Customer.id, Customer.name, Customer.assigned_to_id, func.coalesce(func.sum(consumption_value), 0))
        .outerjoin(Order, Order.customer_id == Customer.id)
        .where(formal_customers)
        .group_by(Customer.id, Customer.name, Customer.assigned_to_id)
        .order_by(func.coalesce(func.sum(consumption_value), 0).desc())
    ).all()
    high_value_by_assignee: dict[int, int] = {}
    for row in value_rows:
        if row[2] and row[3] is not None and row[3] >= 1000:
            high_value_by_assignee[row[2]] = high_value_by_assignee.get(row[2], 0) + 1
    top_customers = [{"id": row[0], "name": row[1], "assigned_to_id": row[2], "total_spend": money(row[3])} for row in value_rows[:10]]
    salesperson_performance = [
        {
            "id": row[0],
            "name": row[1],
            "customer_count": int(row[2] or 0),
            "period_revenue": money(row[3]),
            "period_consumption": money(row[4]),
            "period_insurance": money(row[5]),
            "period_self_pay": money(row[6]),
            "week_revenue": money(row[7]),
            "week_consumption": money(row[8]),
            "week_insurance": money(row[9]),
            "week_self_pay": money(row[10]),
            "month_revenue": money(row[11]),
            "month_consumption": money(row[12]),
            "month_insurance": money(row[13]),
            "month_self_pay": money(row[14]),
            "total_revenue": money(row[15]),
            "total_consumption": money(row[16]),
            "total_insurance": money(row[17]),
            "total_self_pay": money(row[18]),
            "new_customers": int(row[19] or 0),
            "high_value_customers": high_value_by_assignee.get(row[0], 0),
        }
        for row in sales_rows
    ]
    sales_ranking = [{"name": row["name"], "value": row["period_revenue"]} for row in salesperson_performance]
    source_count_rows = db.execute(
        select(
            Customer.source_level_1,
            func.count(Customer.id),
            func.count(case((and_(Customer.created_at >= start, Customer.created_at < end), Customer.id), else_=None)),
        )
        .where(formal_customers)
        .group_by(Customer.source_level_1)
    ).all()
    source_revenue_rows = db.execute(
        select(
            Customer.source_level_1,
            func.coalesce(func.sum(effective_revenue), 0),
            func.coalesce(func.sum(consumption_value), 0),
            func.coalesce(func.sum(case((and_(Order.paid_at >= week_start, Order.paid_at < week_end), effective_revenue), else_=0)), 0),
            func.coalesce(func.sum(case((and_(Order.paid_at >= week_start, Order.paid_at < week_end), consumption_value), else_=0)), 0),
            func.coalesce(func.sum(case((and_(Order.paid_at >= month_start, Order.paid_at < month_end), effective_revenue), else_=0)), 0),
            func.coalesce(func.sum(case((and_(Order.paid_at >= month_start, Order.paid_at < month_end), consumption_value), else_=0)), 0),
        )
        .join(Order, Order.customer_id == Customer.id)
        .where(formal_customers)
        .group_by(Customer.source_level_1)
    ).all()
    source_count_map = {row[0] or "other": {"customers": int(row[1] or 0), "new": int(row[2] or 0)} for row in source_count_rows}
    source_revenue_map = {
        row[0] or "other": {"total": money(row[1]), "total_consumption": money(row[2]), "week": money(row[3]), "week_consumption": money(row[4]), "month": money(row[5]), "month_consumption": money(row[6])}
        for row in source_revenue_rows
    }
    source_analysis = []
    for option in SOURCE_CATEGORY_OPTIONS:
        code = option["code"]
        counts = source_count_map.get(code, {"customers": 0, "new": 0})
        revenues = source_revenue_map.get(code, {"total": 0, "total_consumption": 0, "week": 0, "week_consumption": 0, "month": 0, "month_consumption": 0})
        source_analysis.append({
            "code": code,
            "name": option["name"],
            "customer_count": counts["customers"],
            "new_customers": counts["new"],
            "customer_percentage": round(counts["customers"] / total_customer_count * 100, 1) if total_customer_count else 0,
            "total_revenue": revenues["total"],
            "period_revenue": money(db.scalar(select(func.coalesce(func.sum(effective_revenue), 0)).join(Customer, Customer.id == Order.customer_id).where(Customer.source_level_1 == code, formal_customers, *current_orders))),
            "total_consumption": revenues["total_consumption"],
            "period_consumption": money(db.scalar(select(func.coalesce(func.sum(consumption_value), 0)).join(Customer, Customer.id == Order.customer_id).where(Customer.source_level_1 == code, formal_customers, *current_orders))),
            "week_revenue": revenues["week"],
            "week_consumption": revenues["week_consumption"],
            "month_revenue": revenues["month"],
            "month_consumption": revenues["month_consumption"],
        })
    source_level_2_count_rows = db.execute(
        select(
            Customer.source_level_1,
            Customer.source_level_2,
            func.count(Customer.id),
            func.count(case((and_(Customer.created_at >= start, Customer.created_at < end), Customer.id), else_=None)),
        )
        .where(formal_customers)
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
        .where(formal_customers)
        .group_by(Customer.source_level_1, Customer.source_level_2)
    ).all()
    source_level_2_counts = {(row[0], row[1]): {"customers": int(row[2] or 0), "new": int(row[3] or 0)} for row in source_level_2_count_rows}
    source_level_2_revenue = {(row[0], row[1]): {"revenue": money(row[2]), "consumption": money(row[3])} for row in source_level_2_revenue_rows}
    source_level_2_analysis = []
    for level_1 in SOURCE_CATEGORY_OPTIONS:
        for level_2 in SOURCE_LEVEL_2_OPTIONS.get(level_1["code"], ()):
            key = (level_1["code"], level_2["code"])
            counts = source_level_2_counts.get(key, {"customers": 0, "new": 0})
            values = source_level_2_revenue.get(key, {"revenue": 0, "consumption": 0})
            source_level_2_analysis.append({
                "level_1_code": level_1["code"],
                "level_1_name": level_1["name"],
                "code": level_2["code"],
                "name": level_2["name"],
                "customer_count": counts["customers"],
                "new_customers": counts["new"],
                "total_revenue": values["revenue"],
                "total_consumption": values["consumption"],
            })
    item_rows = db.execute(select(Order.item_name, func.coalesce(func.sum(consumption_value), 0), func.count(func.distinct(consumption_key_expression()))).where(*current_orders).group_by(Order.item_name).order_by(func.sum(consumption_value).desc()).limit(10)).all()
    growth = round((revenue - previous_revenue) / previous_revenue * 100, 1) if previous_revenue else (100 if revenue else 0)
    metrics = {
        "total_customers": total_customer_count,
        "assigned_customers": total_customer_count - unassigned_customer_count,
        "unassigned_customers": unassigned_customer_count,
        "total_revenue": total_revenue,
        "week_revenue": week_revenue,
        "month_revenue": month_revenue,
        "total_consumption": total_consumption,
        "week_consumption": week_consumption,
        "month_consumption": month_consumption,
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
        "recharge": current_recharge,
        "refund": current_refund,
        "total_recharge": total_recharge,
        "total_refund": total_refund,
        "current_prepaid_balance": current_prepaid_balance,
        "period_payment_split_unknown_orders": period_unknown_splits,
        "week_payment_split_unknown_orders": week_unknown_splits,
        "month_payment_split_unknown_orders": month_unknown_splits,
        "total_payment_split_unknown_orders": total_unknown_splits,
        "insurance_ratio": round(period_insurance / revenue * 100, 1) if revenue else 0,
        "self_pay_ratio": round(period_self_pay / revenue * 100, 1) if revenue else 0,
        "new_customers": new_count,
        "visit_customers": visit_count,
        "paying_customers": paid_customer_count,
        "revenue": revenue,
        "previous_revenue": previous_revenue,
        "consumption": consumption,
        "previous_consumption": previous_consumption,
        "growth_rate": growth,
        "avg_order_value": round(consumption / order_count, 2) if order_count else 0,
        "repurchase_rate": round(repeat_count / paid_customer_count * 100, 1) if paid_customer_count else 0,
        "revisit_rate": round(repeat_count / max(visit_count, 1) * 100, 1),
        "new_customers_count": new_count,
        "old_customers_count": max(paid_customer_count - new_count, 0),
        "sales_ranking": sales_ranking,
        "source_performance": [{"name": item["name"], "value": item["period_revenue"]} for item in source_analysis],
        "source_analysis": source_analysis,
        "source_level_2_analysis": source_level_2_analysis,
        "top_items": [{"name": row[0], "value": money(row[1]), "orders": int(row[2])} for row in item_rows],
        "salesperson_performance": salesperson_performance,
        "top_customers": top_customers,
        "top_salesperson": salesperson_performance[0]["name"] if salesperson_performance else None,
    }
    period_label = "周" if period == "week" else "月"
    direction = "增长" if growth >= 0 else "下降"
    summary = f"本{period_label}有效经营收入为 ¥{revenue:,.0f}，较上期{direction} {abs(growth):.1f}%；当前累计消费价值 ¥{total_consumption:,.0f}，TOP业务员为 {metrics['top_salesperson'] or '暂无'}。"
    return metrics, summary


@router.get("")
def get_report(period: str = Query("week", pattern="^(week|month)$"), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    start, end, previous_start = bounds(period)
    metrics, summary = build_report(db, period, start, end, previous_start)
    report_end = display_end(end)
    stored = db.scalar(select(Report).where(Report.period_type == period, Report.period_start == start))
    if stored:
        stored.period_end = report_end
        stored.metrics = metrics
        stored.ai_summary = summary
    else:
        db.add(Report(period_type=period, period_start=start, period_end=report_end, metrics=metrics, ai_summary=summary))
    db.commit()
    return {"period_type": period, "period_start": start, "period_end": report_end, "metrics": metrics, "ai_summary": summary}
