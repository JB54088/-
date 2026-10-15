import csv
import io
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from ..consumption import actual_paid_expression, calculate_transaction_financials, consumption_count_by_customer_subquery, consumption_value_expression, effective_insurance_expression, effective_revenue_expression, effective_self_pay_expression, order_consumption_value
from ..database import get_db
from ..deps import get_current_user
from ..models import Customer, CustomerTagRelation, Department, Order, Store, User
from ..schemas import OrderResponse
from ..utils import consumption_key, consumption_key_expression, consumption_order_condition, formal_customer_condition, is_admin, is_consumption_order, order_scope_condition

router = APIRouter(prefix="/orders", tags=["消费管理"])


def _query(user: User):
    assignee = aliased(User)
    query = (
        select(Order, Customer.name, Store.name, Department.name, assignee.full_name)
        .join(Customer, Order.customer_id == Customer.id)
        .outerjoin(Store, Order.store_id == Store.id)
        .outerjoin(Department, Order.department_id == Department.id)
        .outerjoin(assignee, Customer.assigned_to_id == assignee.id)
        .where(formal_customer_condition())
        .options(selectinload(Order.items))
    )
    visibility = order_scope_condition(user)
    return query if visibility is True else query.where(visibility)


def serialize(row):
    order, customer_name, store_name, department_name, owner_name = row
    financials = calculate_transaction_financials(order)
    return OrderResponse(
        id=order.id,
        order_no=order.order_no,
        customer_id=order.customer_id,
        customer_name=customer_name,
        paid_at=order.paid_at,
        visit_no=order.visit_no,
        item_name=order.item_name,
        category=order.category,
        amount=order.total_amount,
        total_amount=order.total_amount,
        consumption_amount=financials.total_consumption,
        effective_revenue=financials.effective_revenue,
        actual_paid_amount=financials.actual_paid_amount,
        original_amount=order.original_amount,
        single_negotiation_amount=order.single_negotiation_amount,
        writeoff_amount=order.writeoff_amount,
        deduction_amount=order.deduction_amount,
        deduction_amount_raw=order.deduction_amount_raw,
        discount_amount=order.discount_amount,
        negotiation_amount=order.negotiation_amount,
        receivable_amount=order.receivable_amount,
        paid_amount=order.paid_amount,
        arrears_change=order.arrears_change,
        insurance_amount=financials.insurance_amount,
        self_pay_amount=financials.self_pay_amount,
        non_insurance_amount=order.non_insurance_amount,
        payment_type=order.payment_type,
        payment_type_raw=order.payment_type_raw,
        transaction_kind=order.transaction_kind,
        transaction_operation=order.transaction_operation,
        is_refund=order.is_refund,
        balance_operation=order.balance_operation,
        balance_payment_amount=order.balance_payment_amount,
        has_consumption_record=order.has_consumption_record,
        payment_split_status=order.payment_split_status,
        store_name=store_name,
        department_name=department_name,
        owner_name=owner_name,
        staff_name=order.staff_name,
        payment_method=order.payment_method,
        items=order.items,
    )


@router.get("")
def list_orders(
    search: str | None = None,
    category: str | None = None,
    assigned_to_id: int | None = None,
    owner_id: int | None = Query(None, description="兼容旧参数，始终叠加当前用户权限范围"),
    start: datetime | None = None,
    end: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = _query(user)
    conditions = []
    effective_assignee = assigned_to_id or owner_id
    if effective_assignee:
        conditions.append(Customer.assigned_to_id == effective_assignee)
    if search:
        conditions.append(or_(Order.order_no.ilike(f"%{search}%"), Customer.name.ilike(f"%{search}%"), Order.item_name.ilike(f"%{search}%")))
    if category:
        conditions.append(Order.category == category)
    if start:
        conditions.append(Order.paid_at >= start)
    if end:
        conditions.append(Order.paid_at <= end)
    if conditions:
        query = query.where(and_(*conditions))
    rows = db.execute(query.order_by(desc(Order.paid_at))).all()
    total = len(rows)
    page_rows = rows[(page - 1) * page_size : page * page_size]
    financials = [calculate_transaction_financials(row[0]) for row in rows]
    business_financials = [item for row, item in zip(rows, financials) if is_consumption_order(row[0])]
    total_amount = sum((item.total_consumption for item in business_financials), Decimal("0"))
    effective_revenue = sum((item.effective_revenue for item in business_financials), Decimal("0"))
    actual_paid_amount = sum((item.actual_paid_amount for item in business_financials), Decimal("0"))
    split_complete = not business_financials or all(item.insurance_amount is not None and item.self_pay_amount is not None for item in business_financials)
    insurance_amount = sum((item.insurance_amount or Decimal("0") for item in business_financials), Decimal("0"))
    self_pay_amount = sum((item.self_pay_amount or Decimal("0") for item in business_financials), Decimal("0"))
    net_by_key: dict[str, Decimal] = {}
    for row, financial in zip(rows, financials):
        if is_consumption_order(row[0]):
            key = consumption_key(row[0])
            net_by_key[key] = net_by_key.get(key, Decimal("0")) + financial.total_consumption
    consumption_count = sum(1 for value in net_by_key.values() if value > 0)
    return {"items": [serialize(row) for row in page_rows], "total": total, "page": page, "page_size": page_size, "total_pages": (total + page_size - 1) // page_size, "summary": {"total_amount": round(float(total_amount), 2), "consumption_amount": round(float(total_amount), 2), "effective_revenue": round(float(effective_revenue), 2), "actual_paid_amount": round(float(actual_paid_amount), 2), "insurance_amount": round(float(insurance_amount), 2) if split_complete else None, "self_pay_amount": round(float(self_pay_amount), 2) if split_complete else None, "payment_split_status": "verified" if split_complete else "unknown", "order_count": consumption_count}}


@router.get("/customer-summary")
def list_customer_consumption_summary(
    search: str | None = None,
    assigned_to_id: int | None = None,
    source_category: str | None = Query(None, pattern="^(field_sales|online|offline|event|third_party_referral|external|other)$"),
    source_level_1: str | None = Query(None, pattern="^(field_sales|online|offline|event|referral|other)$"),
    source_level_2: str | None = Query(None, pattern="^(field_sales_group_1|field_sales_group_2|field_sales_other|wechat|xiaohongshu|douyin|online_other|store_visit|community_promotion|offline_other|free_clinic|health_lecture|event_other|patient_referral|doctor_referral|partner_referral|unknown|custom)$"),
    payment_type: str | None = Query(None, pattern="^(insurance|self_pay)$"),
    start: datetime | None = None,
    end: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return one row per visible customer, with consumption aggregated once per order.

    The customer dimension remains the authorization boundary.  The outer join
    intentionally keeps customers with no orders visible to admins (and to a
    salesperson for their assigned pool), while date/payment filters only keep
    customers that have a qualifying order.
    """
    reporter = aliased(User)
    assignee = aliased(User)
    effective_self_pay = effective_self_pay_expression()
    order_join_conditions = [Order.customer_id == Customer.id, consumption_order_condition()]
    if start:
        order_join_conditions.append(Order.paid_at >= start)
    if end:
        order_join_conditions.append(Order.paid_at <= end)
    effective_insurance = effective_insurance_expression()
    if payment_type == "insurance":
        order_join_conditions.append(effective_insurance > 0)
    elif payment_type == "self_pay":
        order_join_conditions.append(effective_self_pay > 0)

    conditions = [formal_customer_condition()]
    if not is_admin(user):
        conditions.append(Customer.assigned_to_id == user.id)
    if assigned_to_id:
        conditions.append(Customer.assigned_to_id == assigned_to_id)
    if search:
        term = f"%{search}%"
        conditions.append(or_(Customer.name.ilike(term), Customer.phone.ilike(term), Customer.external_customer_id.ilike(term)))
    if source_category:
        conditions.append(Customer.source_category == source_category)
    if source_level_1:
        conditions.append(Customer.source_level_1 == source_level_1)
    if source_level_2:
        conditions.append(Customer.source_level_2 == source_level_2)

    consumption_value = consumption_value_expression()
    actual_paid = actual_paid_expression()
    effective_revenue = effective_revenue_expression()
    count_conditions = [consumption_order_condition()]
    if start:
        count_conditions.append(Order.paid_at >= start)
    if end:
        count_conditions.append(Order.paid_at <= end)
    if payment_type == "insurance":
        count_conditions.append(effective_insurance > 0)
    elif payment_type == "self_pay":
        count_conditions.append(effective_self_pay > 0)
    count_metrics = consumption_count_by_customer_subquery(*count_conditions)
    query = (
        select(
            Customer,
            reporter.full_name.label("reported_by_name"),
            assignee.full_name.label("assigned_to_name"),
            func.coalesce(func.sum(consumption_value), 0).label("total_amount"),
            func.coalesce(func.sum(actual_paid), 0).label("actual_paid_amount"),
            func.coalesce(func.sum(effective_revenue), 0).label("effective_revenue"),
            func.coalesce(func.sum(effective_insurance), 0).label("insurance_amount"),
            func.coalesce(func.sum(effective_self_pay), 0).label("self_pay_amount"),
            func.coalesce(count_metrics.c.order_count, 0).label("order_count"),
            func.max(case((or_(Order.is_refund.is_(False), Order.is_refund.is_(None)), Order.paid_at), else_=None)).label("last_spend_at"),
            func.count(func.distinct(case((and_(Order.insurance_amount.is_not(None), Order.self_pay_amount.is_not(None)), consumption_key_expression()), else_=None))).label("payment_split_count"),
        )
        .outerjoin(reporter, Customer.reported_by_id == reporter.id)
        .outerjoin(assignee, Customer.assigned_to_id == assignee.id)
        .outerjoin(Order, and_(*order_join_conditions))
        .outerjoin(count_metrics, count_metrics.c.customer_id == Customer.id)
        .where(and_(*conditions))
        .group_by(Customer.id, reporter.full_name, assignee.full_name, count_metrics.c.order_count)
        .options(selectinload(Customer.tag_relations).selectinload(CustomerTagRelation.tag))
        .order_by(desc(func.max(Order.paid_at)), Customer.name)
    )
    if start or end or payment_type:
        query = query.having(func.count(Order.id) > 0)

    rows = db.execute(query).unique().all()
    total = len(rows)
    page_rows = rows[(page - 1) * page_size : page * page_size]
    items = []
    total_orders = 0
    total_amount = Decimal("0")
    total_insurance = Decimal("0")
    total_self_pay = Decimal("0")
    all_rows_split = True
    for row in rows:
        customer, reported_by_name, assigned_to_name, amount, actual_paid_amount, effective_revenue, insurance, self_pay, order_count, last_spend_at, split_count = row
        order_count = int(order_count or 0)
        split_complete = order_count == 0 or int(split_count or 0) == order_count
        total_orders += order_count
        total_amount += amount or Decimal("0")
        total_insurance += insurance or Decimal("0")
        total_self_pay += self_pay or Decimal("0")
        all_rows_split = all_rows_split and split_complete
        if row in page_rows:
            items.append({
                "id": customer.id,
                "external_customer_id": customer.external_customer_id,
                "name": customer.name,
                "phone": customer.phone,
                "source_category": customer.source_category,
                "source_level_1": customer.source_level_1,
                "source_level_2": customer.source_level_2,
                "source_custom_name": customer.source_custom_name,
                "reported_by_name": reported_by_name,
                "assigned_to_id": customer.assigned_to_id,
                "assigned_to_name": assigned_to_name,
                "tags": [relation.tag.name for relation in customer.tag_relations if relation.tag],
                "status": customer.status,
                "lead_status": customer.lead_status,
                "total_amount": round(float(amount or 0), 2),
                "consumption_amount": round(float(amount or 0), 2),
                "actual_paid_amount": round(float(actual_paid_amount or 0), 2),
                "effective_revenue": round(float(effective_revenue or 0), 2),
                "insurance_amount": round(float(insurance or 0), 2) if split_complete else None,
                "self_pay_amount": round(float(self_pay or 0), 2) if split_complete else None,
                "order_count": order_count,
                "last_spend_at": last_spend_at,
            })
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "summary": {
            "customer_count": total,
            "order_count": total_orders,
            "total_amount": round(float(total_amount), 2),
            "consumption_amount": round(float(total_amount), 2),
            "actual_paid_amount": round(float(sum((row[4] or Decimal("0") for row in rows), Decimal("0"))), 2),
            "effective_revenue": round(float(sum((row[5] or Decimal("0") for row in rows), Decimal("0"))), 2),
            "insurance_amount": round(float(total_insurance), 2) if all_rows_split else None,
            "self_pay_amount": round(float(total_self_pay), 2) if all_rows_split else None,
            "payment_split_status": "verified" if all_rows_split else "unknown",
        },
    }


@router.get("/export")
def export_orders(start: datetime | None = None, end: datetime | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = _query(user).order_by(desc(Order.paid_at))
    conditions = []
    if start:
        conditions.append(Order.paid_at >= start)
    if end:
        conditions.append(Order.paid_at <= end)
    if conditions:
        query = query.where(and_(*conditions))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["订单号", "客户", "消费时间", "消费项目", "类型", "原价", "应收", "实收", "总金额", "医保金额", "自费金额", "抵扣金额", "核销金额", "优惠金额", "支付方式", "订单拆分状态", "门店", "部门", "业务员", "服务人员"])
    for row in db.execute(query).all():
        order, customer_name, store_name, department_name, owner_name = row
        writer.writerow([order.order_no, customer_name, order.paid_at.isoformat(), order.item_name, order.category, order.original_amount if order.original_amount is not None else "", order.receivable_amount if order.receivable_amount is not None else "", order.paid_amount if order.paid_amount is not None else order.total_amount, order.total_amount, order.insurance_amount if order.insurance_amount is not None else "", order.self_pay_amount if order.self_pay_amount is not None else "", order.deduction_amount if order.deduction_amount is not None else "", order.writeoff_amount if order.writeoff_amount is not None else "", order.discount_amount if order.discount_amount is not None else "", order.payment_type_raw or order.payment_method or "", order.payment_split_status, store_name or "", department_name or "", owner_name or "", order.staff_name or ""])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue().encode("utf-8-sig")]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=orders.csv"})
