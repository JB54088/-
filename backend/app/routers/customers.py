from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, asc, case, delete, desc, func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from ..consumption import calculate_customer_consumption_summary, calculate_transaction_financials, consumption_count_by_customer_subquery, consumption_value_expression, effective_insurance_expression, effective_revenue_expression, effective_self_pay_expression, order_consumption_value
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import Customer, CustomerAssignmentHistory, CustomerBalanceTransaction, CustomerPoolMatchHistory, CustomerTag, CustomerTagRelation, Department, Order, User
from ..schemas import AssignmentRequest, CustomerBalanceTransactionResponse, CustomerDetailResponse, CustomerListItem, CustomerTagsRequest, CustomerVoidRequest, OrderResponse, ReassignRequest, TimelineEvent
from ..source_categories import SOURCE_CATEGORY_OPTIONS, SOURCE_LEVEL_2_OPTIONS
from ..utils import consumption_key, consumption_key_expression, consumption_order_condition, customer_scope_condition, formal_customer_condition, is_admin, money, period_bounds
from ..timezone import utc_now

router = APIRouter(prefix="/customers", tags=["市场部客户管理"])


def _timeline_sort_key(value: datetime) -> datetime:
    """Compare legacy naive timestamps with the new UTC-aware lifecycle times."""

    if value.tzinfo is None:
        # Existing created/charged timestamps predate the timezone migration;
        # treat their stored values as UTC for ordering without changing them.
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    """Mark legacy server-generated naive timestamps as UTC for the client."""

    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _metrics_subquery():
    consumption_value = consumption_value_expression()
    effective_insurance = effective_insurance_expression()
    effective_revenue = effective_revenue_expression()
    effective_self_pay = effective_self_pay_expression()
    count_metrics = consumption_count_by_customer_subquery(consumption_order_condition())
    return (
        select(
            Order.customer_id.label("customer_id"),
            func.coalesce(func.sum(consumption_value), 0).label("total_spend"),
            func.coalesce(func.sum(effective_insurance), 0).label("insurance_amount"),
            func.coalesce(func.sum(effective_self_pay), 0).label("self_pay_amount"),
            func.coalesce(func.sum(effective_revenue), 0).label("effective_revenue"),
            func.coalesce(count_metrics.c.order_count, 0).label("order_count"),
            func.count(func.distinct(case((and_(consumption_order_condition(), Order.insurance_amount.is_not(None), Order.self_pay_amount.is_not(None)), consumption_key_expression()), else_=None))).label("payment_split_count"),
            func.max(case((and_(consumption_order_condition(), or_(Order.is_refund.is_(False), Order.is_refund.is_(None))), Order.paid_at), else_=None)).label("last_spend_at"),
        )
        .select_from(Order)
        .outerjoin(count_metrics, count_metrics.c.customer_id == Order.customer_id)
        .group_by(Order.customer_id)
        .group_by(count_metrics.c.order_count)
        .subquery()
    )


def _customer_query(metrics=None):
    if metrics is None:
        metrics = _metrics_subquery()
    reporter = aliased(User)
    assignee = aliased(User)
    return (
        select(
            Customer,
            reporter.full_name.label("reported_by_name"),
            assignee.full_name.label("assigned_to_name"),
            Department.name.label("department_name"),
            func.coalesce(metrics.c.total_spend, 0).label("total_spend"),
            func.coalesce(metrics.c.insurance_amount, 0).label("insurance_amount"),
            func.coalesce(metrics.c.self_pay_amount, 0).label("self_pay_amount"),
            func.coalesce(metrics.c.effective_revenue, 0).label("effective_revenue"),
            func.coalesce(metrics.c.order_count, 0).label("order_count"),
            metrics.c.last_spend_at,
            metrics.c.payment_split_count,
        )
        .outerjoin(reporter, Customer.reported_by_id == reporter.id)
        .outerjoin(assignee, Customer.assigned_to_id == assignee.id)
        .outerjoin(Department, Customer.department_id == Department.id)
        .outerjoin(metrics, metrics.c.customer_id == Customer.id)
        .options(selectinload(Customer.tag_relations).selectinload(CustomerTagRelation.tag))
    )


def _row_to_customer(row, include_external: bool = True) -> CustomerListItem:
    customer, reported_by_name, assigned_to_name, department_name, total_spend, insurance_amount, self_pay_amount, effective_revenue, order_count, last_spend_at, payment_split_count = row
    # Customer value is always derived from local orders.  The legacy snapshot
    # columns remain for backward compatibility, but are not a reporting source.
    resolved_total_spend = total_spend or Decimal("0")
    resolved_order_count = int(order_count or 0)
    resolved_last_spend_at = last_spend_at
    return CustomerListItem(
        id=customer.id,
        external_customer_id=customer.external_customer_id if include_external else None,
        pool_match_status=customer.pool_match_status,
        external_synced_at=customer.external_synced_at if include_external else None,
        name=customer.name,
        phone=customer.phone,
        wechat_id=customer.wechat_id,
        gender=customer.gender,
        age=customer.age,
        source_category=customer.source_category,
        source_level_1=customer.source_level_1,
        source_level_2=customer.source_level_2,
        source_custom_name=customer.source_custom_name,
        source_note=customer.source_note,
        reported_by_id=customer.reported_by_id,
        assigned_to_id=customer.assigned_to_id,
        reported_by_name=reported_by_name,
        assigned_to_name=assigned_to_name,
        department_name=department_name,
        member_level=customer.member_level,
        wechat_status=customer.wechat_status,
        status=customer.status,
        lead_status=customer.lead_status,
        reported_at=customer.reported_at,
        total_spend=resolved_total_spend or Decimal("0"),
        total_amount=resolved_total_spend or Decimal("0"),
        consumption_value=resolved_total_spend or Decimal("0"),
        effective_revenue=effective_revenue or Decimal("0"),
        insurance_amount=(insurance_amount or Decimal("0")) if not order_count or payment_split_count == order_count else None,
        self_pay_amount=(self_pay_amount or Decimal("0")) if not order_count or payment_split_count == order_count else None,
        order_count=resolved_order_count,
        last_spend_at=resolved_last_spend_at,
        last_visit_at=customer.last_visit_at,
        tags=[relation.tag.name for relation in customer.tag_relations if relation.tag],
        prepaid_balance=customer.prepaid_balance or Decimal("0"),
        total_recharge_amount=customer.total_recharge_amount or Decimal("0"),
        total_refund_amount=customer.total_refund_amount or Decimal("0"),
        total_prepaid_spent=customer.total_prepaid_spent or Decimal("0"),
    )


@router.get("/meta")
def customer_meta(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    departments = db.scalars(select(Department).order_by(Department.id)).all()
    users_query = select(User).where(User.role == "salesperson", User.is_active.is_(True)).order_by(User.full_name)
    if not is_admin(user):
        users_query = users_query.where(User.id == user.id)
    users = db.scalars(users_query).all()
    tags = db.scalars(select(CustomerTag).order_by(CustomerTag.name)).all()
    return {
        "departments": [{"id": d.id, "name": d.name} for d in departments],
        "users": [{"id": u.id, "name": u.full_name, "role": u.role} for u in users],
        # New linked source options. Keep source_categories as a compatibility alias.
        "source_level_1_options": SOURCE_CATEGORY_OPTIONS,
        "source_level_2_options": SOURCE_LEVEL_2_OPTIONS,
        "source_categories": SOURCE_CATEGORY_OPTIONS,
        "statuses": ["active", "inactive"],
        "lead_statuses": ["pending", "reviewed", "unassigned", "assigned", "approved", "converted", "rejected"],
        "pool_match_statuses": [
            {"code": "matched", "name": "已匹配"},
            {"code": "pending", "name": "待匹配"},
            {"code": "conflict", "name": "匹配冲突"},
            {"code": "manual_required", "name": "待人工处理"},
        ],
        "tags": [{"id": tag.id, "name": tag.name, "color": tag.color} for tag in tags],
    }


def _owner_asset_summary(db: Session, owner_id: int | None, period_start: datetime, period_end: datetime, metrics):
    """Aggregate the existing customer/order metrics by current assignment.

    ``assigned_to_id`` is the only ownership dimension used here.  The
    reporter remains an audit field and never affects customer-pool totals.
    Period figures use Order.paid_at, while new-customer figures use the
    formal-customer approval timestamp reviewed_at.
    """
    formal = formal_customer_condition()
    owner = Customer.assigned_to_id == owner_id if owner_id is not None else Customer.assigned_to_id.is_(None)
    customer_conditions = [formal, owner]

    customer_count = int(db.scalar(select(func.count(Customer.id)).select_from(Customer).where(*customer_conditions)) or 0)
    month_new_customers = int(db.scalar(select(func.count(Customer.id)).select_from(Customer).where(*customer_conditions, Customer.reviewed_at >= period_start, Customer.reviewed_at <= period_end)) or 0)
    total_consumption = money(db.scalar(select(func.coalesce(func.sum(metrics.c.total_spend), 0)).select_from(Customer).outerjoin(metrics, metrics.c.customer_id == Customer.id).where(*customer_conditions)))
    total_revenue = money(db.scalar(select(func.coalesce(func.sum(metrics.c.effective_revenue), 0)).select_from(Customer).outerjoin(metrics, metrics.c.customer_id == Customer.id).where(*customer_conditions)))
    high_value_customers = int(db.scalar(select(func.count(Customer.id)).select_from(Customer).outerjoin(metrics, metrics.c.customer_id == Customer.id).where(*customer_conditions, metrics.c.total_spend >= 1000)) or 0)
    recent_new_customer_at = db.scalar(select(func.max(Customer.reviewed_at)).where(*customer_conditions))

    order_scope = [formal, owner, Order.paid_at >= period_start, Order.paid_at <= period_end]
    month_consumption = money(db.scalar(select(func.coalesce(func.sum(consumption_value_expression()), 0)).select_from(Order).join(Customer, Customer.id == Order.customer_id).where(*order_scope)))
    month_revenue = money(db.scalar(select(func.coalesce(func.sum(effective_revenue_expression()), 0)).select_from(Order).join(Customer, Customer.id == Order.customer_id).where(*order_scope)))
    return {
        "assigned_to_id": owner_id,
        "customer_count": customer_count,
        "month_new_customers": month_new_customers,
        "total_consumption": total_consumption,
        "month_consumption": month_consumption,
        "total_revenue": total_revenue,
        "month_revenue": month_revenue,
        "high_value_customers": high_value_customers,
        "recent_new_customer_at": _as_utc(recent_new_customer_at) if recent_new_customer_at else None,
    }


@router.get("/owner-summary")
def owner_summary(
    period: str = Query("month", pattern="^(today|week|month|custom)$"),
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Return the admin's salesperson-first customer asset directory."""
    period_start, period_end = period_bounds(period, start, end)
    metrics = _metrics_subquery()
    salespeople = db.scalars(select(User).where(User.role == "salesperson", User.is_active.is_(True)).order_by(User.full_name)).all()
    owners = []
    for salesperson in salespeople:
        summary = _owner_asset_summary(db, salesperson.id, period_start, period_end, metrics)
        owners.append({"id": salesperson.id, "name": salesperson.full_name, **summary})
    unassigned = _owner_asset_summary(db, None, period_start, period_end, metrics)
    return {"period": period, "period_start": _as_utc(period_start), "period_end": _as_utc(period_end), "owners": owners, "unassigned": {"name": "待分配客户", **unassigned}}


@router.get("")
def list_customers(
    search: str | None = None,
    assigned_to_id: int | None = None,
    unassigned: bool = False,
    reported_by_id: int | None = None,
    source_category: str | None = Query(None, pattern="^(field_sales|online|offline|event|third_party_referral|external|other)$"),
    source_level_1: str | None = Query(None, pattern="^(field_sales|online|offline|event|referral|other)$"),
    source_level_2: str | None = Query(None, pattern="^(field_sales_group_1|field_sales_group_2|field_sales_other|wechat|xiaohongshu|douyin|online_other|store_visit|community_promotion|offline_other|free_clinic|health_lecture|event_other|patient_referral|doctor_referral|partner_referral|unknown|custom)$"),
    tag_id: int | None = None,
    lead_status: str | None = None,
    customer_status: str | None = Query(None, alias="status"),
    pool_match_status: str | None = Query(None, pattern="^(pending|matched|conflict|manual_required)$"),
    min_spend: Decimal | None = None,
    max_spend: Decimal | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("reviewed_at", pattern="^(reviewed_at|created_at|name|total_spend|order_count|last_spend_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    metrics = _metrics_subquery()
    conditions = []
    visibility = customer_scope_condition(user)
    if visibility is not True:
        conditions.append(visibility)
    # Pending/rejected submissions belong to the lead workflow, not the formal customer pool.
    conditions.append(formal_customer_condition())
    if search:
        conditions.append(or_(Customer.name.ilike(f"%{search}%"), Customer.phone.ilike(f"%{search}%"), Customer.wechat_id.ilike(f"%{search}%")))
    if unassigned:
        conditions.append(Customer.assigned_to_id.is_(None))
    elif assigned_to_id is not None:
        conditions.append(Customer.assigned_to_id == assigned_to_id)
    if reported_by_id:
        conditions.append(Customer.reported_by_id == reported_by_id)
    if source_level_1:
        conditions.append(Customer.source_level_1 == source_level_1)
    if source_level_2:
        conditions.append(Customer.source_level_2 == source_level_2)
    if source_category:
        conditions.append(Customer.source_category == source_category)
    if tag_id:
        conditions.append(Customer.tag_relations.any(CustomerTagRelation.tag_id == tag_id))
    if lead_status:
        conditions.append(Customer.lead_status == lead_status)
    if customer_status:
        conditions.append(Customer.status == customer_status)
    if pool_match_status:
        conditions.append(Customer.pool_match_status == pool_match_status)
    if start:
        conditions.append(Customer.created_at >= start)
    if end:
        conditions.append(Customer.created_at <= end)
    if min_spend is not None:
        conditions.append(func.coalesce(metrics.c.total_spend, 0) >= min_spend)
    if max_spend is not None:
        conditions.append(func.coalesce(metrics.c.total_spend, 0) <= max_spend)

    query = _customer_query(metrics)
    if conditions:
        query = query.where(and_(*conditions))
    sort_expr = {
        "reviewed_at": Customer.reviewed_at,
        "created_at": Customer.created_at,
        "name": Customer.name,
        "total_spend": func.coalesce(metrics.c.total_spend, 0),
        "order_count": func.coalesce(metrics.c.order_count, 0),
        "last_spend_at": metrics.c.last_spend_at,
    }[sort_by]
    if sort_order == "desc":
        ordering = [desc(sort_expr).nullslast(), desc(Customer.id)]
    else:
        ordering = [asc(sort_expr).nullslast(), asc(Customer.id)]
    query = query.order_by(*ordering)
    count_query = select(func.count(Customer.id)).select_from(Customer).outerjoin(metrics, metrics.c.customer_id == Customer.id)
    if conditions:
        count_query = count_query.where(and_(*conditions))
    total = int(db.scalar(count_query) or 0)
    page_rows = db.execute(query.offset((page - 1) * page_size).limit(page_size)).unique().all()
    return {"items": [_row_to_customer(row, include_external=is_admin(user)) for row in page_rows], "total": total, "page": page, "page_size": page_size, "total_pages": (total + page_size - 1) // page_size}


def _get_visible_customer(customer_id: int, db: Session, user: User) -> Customer:
    customer = db.scalar(
        select(Customer)
        .options(
            selectinload(Customer.orders).selectinload(Order.store),
            selectinload(Customer.orders).selectinload(Order.items),
            selectinload(Customer.tag_relations).selectinload(CustomerTagRelation.tag),
            selectinload(Customer.assignment_history),
        )
        .where(Customer.id == customer_id, Customer.is_deleted.is_(False))
    )
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")
    if not is_admin(user) and customer.assigned_to_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看该客户")
    return customer


@router.get("/assignment-history")
def assignment_history(
    search: str | None = None,
    salesperson_id: int | None = None,
    changed_by_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    previous = aliased(User)
    new = aliased(User)
    changer = aliased(User)
    query = (
        select(CustomerAssignmentHistory, Customer.name, previous.full_name, new.full_name, changer.full_name)
        .join(Customer, Customer.id == CustomerAssignmentHistory.customer_id)
        .outerjoin(previous, previous.id == CustomerAssignmentHistory.previous_salesperson_id)
        .outerjoin(new, new.id == CustomerAssignmentHistory.new_salesperson_id)
        .outerjoin(changer, changer.id == CustomerAssignmentHistory.changed_by_id)
    )
    conditions = []
    if search:
        conditions.append(or_(Customer.name.ilike(f"%{search}%"), Customer.phone.ilike(f"%{search}%")))
    if salesperson_id:
        conditions.append(or_(CustomerAssignmentHistory.previous_salesperson_id == salesperson_id, CustomerAssignmentHistory.new_salesperson_id == salesperson_id))
    if changed_by_id:
        conditions.append(CustomerAssignmentHistory.changed_by_id == changed_by_id)
    if start:
        conditions.append(CustomerAssignmentHistory.changed_at >= start)
    if end:
        conditions.append(CustomerAssignmentHistory.changed_at <= end)
    if conditions:
        query = query.where(and_(*conditions))
    rows = db.execute(query.order_by(CustomerAssignmentHistory.changed_at.desc()).limit(limit)).all()
    return [
        {
            "id": item.id,
            "customer_id": item.customer_id,
            "customer_name": customer_name,
            "previous_salesperson_id": item.previous_salesperson_id,
            "previous_salesperson_name": previous_name or "待分配",
            "new_salesperson_id": item.new_salesperson_id,
            "new_salesperson_name": new_name or "待分配",
            "changed_by_id": item.changed_by_id,
            "changed_by": changer_name or "—",
            "change_reason": item.change_reason,
            "change_note": item.change_note,
            "changed_at": _as_utc(item.changed_at),
        }
        for item, customer_name, previous_name, new_name, changer_name in rows
    ]


@router.put("/{customer_id}/tags")
def replace_customer_tags(customer_id: int, payload: CustomerTagsRequest, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    customer = db.scalar(select(Customer).where(Customer.id == customer_id, Customer.is_deleted.is_(False)))
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")
    tag_ids = list(dict.fromkeys(payload.tag_ids))
    tags = db.scalars(select(CustomerTag).where(CustomerTag.id.in_(tag_ids))).all() if tag_ids else []
    if len(tags) != len(tag_ids):
        raise HTTPException(status_code=400, detail="存在无效客户标签")
    db.execute(delete(CustomerTagRelation).where(CustomerTagRelation.customer_id == customer_id))
    for tag_id in tag_ids:
        db.add(CustomerTagRelation(customer_id=customer_id, tag_id=tag_id))
    db.commit()
    return {"message": "客户标签已更新", "tags": [tag.name for tag in tags]}


@router.get("/{customer_id}", response_model=CustomerDetailResponse)
def get_customer(customer_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    customer = _get_visible_customer(customer_id, db, user)
    summary = calculate_customer_consumption_summary(customer.orders)
    department = customer.department
    assignee = customer.assigned_to_user
    reporter = customer.reported_by_user
    detail = CustomerListItem(
        id=customer.id,
        external_customer_id=customer.external_customer_id if is_admin(user) else None,
        pool_match_status=customer.pool_match_status,
        external_synced_at=customer.external_synced_at if is_admin(user) else None,
        name=customer.name,
        phone=customer.phone,
        wechat_id=customer.wechat_id,
        gender=customer.gender,
        age=customer.age,
        source_category=customer.source_category,
        source_level_1=customer.source_level_1,
        source_level_2=customer.source_level_2,
        source_custom_name=customer.source_custom_name,
        source_note=customer.source_note,
        reported_by_id=customer.reported_by_id,
        assigned_to_id=customer.assigned_to_id,
        reported_by_name=reporter.full_name if reporter else None,
        assigned_to_name=assignee.full_name if assignee else None,
        department_name=department.name if department else None,
        member_level=customer.member_level,
        wechat_status=customer.wechat_status,
        status=customer.status,
        lead_status=customer.lead_status,
        reported_at=customer.reported_at,
        total_spend=summary.total_consumption,
        total_amount=summary.total_consumption,
        consumption_value=summary.total_consumption,
        actual_paid_amount=summary.actual_paid_amount,
        effective_revenue=summary.effective_revenue,
        insurance_amount=summary.insurance_amount,
        self_pay_amount=summary.self_pay_amount,
        deduction_amount=summary.deduction_amount,
        discount_amount=summary.discount_amount,
        order_count=summary.consumption_count,
        average_order_value=summary.average_order_value,
        last_spend_at=summary.last_consumption_at,
        last_visit_at=customer.last_visit_at,
        tags=[relation.tag.name for relation in customer.tag_relations if relation.tag],
        prepaid_balance=customer.prepaid_balance or Decimal("0"),
        total_recharge_amount=customer.total_recharge_amount or Decimal("0"),
        total_refund_amount=customer.total_refund_amount or Decimal("0"),
        total_prepaid_spent=customer.total_prepaid_spent or Decimal("0"),
    )
    detail_dict = detail.model_dump()
    detail_dict.update({"created_at": customer.created_at, "first_visit_at": customer.first_visit_at, "notes": customer.notes})
    orders = [
        OrderResponse(
            id=order.id,
            order_no=order.order_no,
            customer_id=customer.id,
            customer_name=customer.name,
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
            store_name=order.store.name if order.store else None,
            department_name=department.name if department else None,
            owner_name=assignee.full_name if assignee else None,
            staff_name=order.staff_name,
            payment_method=order.payment_method,
            items=order.items,
        )
        for order, financials in ((order, calculate_transaction_financials(order)) for order in sorted(customer.orders, key=lambda item: item.paid_at, reverse=True))
    ]
    timeline = [TimelineEvent(type="created", title="线索报备", description=reporter.full_name if reporter else None, occurred_at=customer.reported_at or customer.created_at)]
    if customer.reviewed_at:
        reviewer = customer.reviewed_by_user.full_name if customer.reviewed_by_user else "主管"
        timeline.append(TimelineEvent(type="reviewed", title="主管审核线索", description=reviewer, occurred_at=customer.reviewed_at))
    for assignment in customer.assignment_history:
        previous = db.get(User, assignment.previous_salesperson_id) if assignment.previous_salesperson_id else None
        new = db.get(User, assignment.new_salesperson_id) if assignment.new_salesperson_id else None
        operator = db.get(User, assignment.changed_by_id) if assignment.changed_by_id else None
        title = "首次分配" if assignment.previous_salesperson_id is None else "调整客户归属"
        previous_name = previous.full_name if previous else "待分配"
        new_name = new.full_name if new else "待分配"
        description = f"{previous_name} → {new_name}"
        if operator:
            description += f" · 操作人：{operator.full_name}"
        timeline.append(TimelineEvent(type="assignment", title=title, description=description, occurred_at=assignment.changed_at))
    if customer.first_visit_at:
        timeline.append(TimelineEvent(type="visit", title="首次到店", occurred_at=customer.first_visit_at))
    for index, order in enumerate(sorted(customer.orders, key=lambda item: item.paid_at)):
        timeline.append(TimelineEvent(type="purchase", title="再次消费" if index else "消费", description=f"{order.item_name} · 消费价值 ¥{order_consumption_value(order)}", occurred_at=order.paid_at))
    history = []
    if is_admin(user):
        for item in sorted(customer.assignment_history, key=lambda item: item.changed_at, reverse=True):
            previous = db.get(User, item.previous_salesperson_id) if item.previous_salesperson_id else None
            new = db.get(User, item.new_salesperson_id) if item.new_salesperson_id else None
            changed_by = db.get(User, item.changed_by_id) if item.changed_by_id else None
            history.append({"id": item.id, "previous_salesperson_id": item.previous_salesperson_id, "previous_salesperson_name": previous.full_name if previous else "待分配", "new_salesperson_id": item.new_salesperson_id, "new_salesperson_name": new.full_name if new else "待分配", "changed_by_id": item.changed_by_id, "changed_by": changed_by.full_name if changed_by else "—", "change_reason": item.change_reason, "change_note": item.change_note, "changed_at": _as_utc(item.changed_at)})
    pool_history = []
    if is_admin(user):
        match_rows = db.execute(
            select(CustomerPoolMatchHistory, User.full_name)
            .outerjoin(User, CustomerPoolMatchHistory.matched_by_id == User.id)
            .where(CustomerPoolMatchHistory.customer_id == customer.id)
            .order_by(CustomerPoolMatchHistory.matched_at.desc())
        ).all()
        pool_history = [
            {
                "id": item.id,
                "external_customer_id": item.external_customer_id,
                "match_type": item.match_type,
                "previous_status": item.previous_status,
                "new_status": item.new_status,
                "matched_by": operator_name or "系统",
                "matched_at": item.matched_at,
                "note": item.note,
            }
            for item, operator_name in match_rows
        ]
    balance_rows = db.scalars(
        select(CustomerBalanceTransaction)
        .where(CustomerBalanceTransaction.customer_id == customer.id)
        .order_by(CustomerBalanceTransaction.charged_at.desc(), CustomerBalanceTransaction.id.desc())
    ).all()
    balance_transactions = [
        CustomerBalanceTransactionResponse(
            id=item.id,
            customer_id=item.customer_id,
            external_customer_id=item.external_customer_id if is_admin(user) else None,
            transaction_type=item.transaction_type,
            amount=item.amount,
            balance_before=item.balance_before,
            balance_after=item.balance_after,
            source_transaction_id=item.source_transaction_id,
            charged_at=item.charged_at,
            created_at=item.created_at,
        )
        for item in balance_rows
    ]
    return {"customer": detail_dict, "orders": orders, "timeline": sorted(timeline, key=lambda item: _timeline_sort_key(item.occurred_at), reverse=True), "assignment_history": history, "pool_match_history": pool_history, "balance_transactions": balance_transactions}


def _apply_customer_void(db: Session, customer: Customer, operator: User, payload: CustomerVoidRequest) -> dict:
    """Apply the reversible customer archive inside the caller's transaction."""
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="作废原因不能为空")

    now = utc_now()
    external_id = customer.external_customer_id
    raw_data = dict(customer.external_raw_data or {})
    retired_ids = list(raw_data.get("retired_external_customer_ids") or [])
    if external_id and external_id not in retired_ids:
        retired_ids.append(external_id)
    raw_data.update({
        "active_external_customer_id": None,
        "retired_external_customer_ids": retired_ids,
        "voided_at": now.isoformat(),
        "voided_by": operator.id,
        "voided_reason": reason,
        "voided_note": payload.note,
    })

    # Release the active mapping so a future correct lead can reuse the same
    # ABC patient ID.  The former ID remains in raw audit data and in the
    # immutable imported orders/history.
    customer.external_customer_id = None
    customer.pool_match_status = "pending"
    customer.is_deleted = True
    customer.deleted_at = now
    customer.deleted_by_id = operator.id
    customer.deleted_reason = reason
    customer.deleted_note = payload.note
    customer.external_raw_data = raw_data
    db.add(
        CustomerPoolMatchHistory(
            customer_id=customer.id,
            external_customer_id=external_id,
            match_type="customer_voided",
            previous_status="matched" if external_id else "pending",
            new_status="archived",
            matched_by_id=operator.id,
            note=f"客户作废：{reason}" + (f"；{payload.note}" if payload.note else ""),
        )
    )
    db.flush()
    return {
        "message": "客户已作废，历史数据已保留，后续可以重新报备",
        "customer_id": customer.id,
        "is_deleted": True,
        "deleted_at": customer.deleted_at,
        "deleted_by": operator.id,
        "deleted_reason": customer.deleted_reason,
        "released_external_customer_id": external_id,
    }


@router.post("/{customer_id}/void")
def void_customer(
    customer_id: int,
    payload: CustomerVoidRequest,
    db: Session = Depends(get_db),
    operator: User = Depends(require_admin),
):
    """Archive a customer without deleting any history or imported facts."""
    customer = db.scalar(select(Customer).where(Customer.id == customer_id, Customer.is_deleted.is_(False)))
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在或已经作废")
    try:
        result = _apply_customer_void(db, customer, operator, payload)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


@router.post("/{customer_id}/reassign")
def reassign_customer(
    customer_id: int,
    payload: ReassignRequest,
    db: Session = Depends(get_db),
    operator: User = Depends(require_admin),
):
    """Change only the current owner and append an immutable audit record."""
    customer = db.scalar(select(Customer).where(Customer.id == customer_id, Customer.is_deleted.is_(False)))
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")
    if customer.lead_status in {"pending", "rejected"}:
        raise HTTPException(status_code=409, detail="待审核/已驳回线索不能在市场部客户管理中变更归属")
    new_user = db.get(User, payload.new_salesperson_id)
    if not new_user or not new_user.is_active or new_user.role != "salesperson":
        raise HTTPException(status_code=400, detail="归属对象必须是启用中的业务员")
    if customer.assigned_to_id == new_user.id:
        raise HTTPException(status_code=400, detail="新归属业务员与当前归属相同")

    previous_id = customer.assigned_to_id
    try:
        customer.assigned_to_id = new_user.id
        db.add(
            CustomerAssignmentHistory(
                customer_id=customer.id,
                previous_salesperson_id=previous_id,
                new_salesperson_id=new_user.id,
                changed_by_id=operator.id,
                change_reason=payload.reason,
                change_note=payload.note,
            )
        )
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "message": "客户归属已变更，历史记录已保存",
        "customer_id": customer.id,
        "reported_by": customer.reported_by_id,
        "assigned_to": customer.assigned_to_id,
        "assigned_to_name": new_user.full_name,
    }


@router.patch("/{customer_id}/assignment")
def update_assignment(customer_id: int, payload: AssignmentRequest, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    customer = db.scalar(select(Customer).where(Customer.id == customer_id, Customer.is_deleted.is_(False)))
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")
    new_user = None
    if payload.assigned_to is not None:
        new_user = db.get(User, payload.assigned_to)
        if not new_user or not new_user.is_active or new_user.role != "salesperson":
            raise HTTPException(status_code=400, detail="归属对象必须是启用中的业务员")
    if customer.assigned_to_id == payload.assigned_to:
        return {"message": "客户归属未变化", "customer_id": customer.id, "assigned_to": customer.assigned_to_id}
    previous_id = customer.assigned_to_id
    customer.assigned_to_id = payload.assigned_to
    customer.lead_status = "unassigned" if new_user is None else ("assigned" if customer.lead_status != "converted" else "converted")
    db.add(CustomerAssignmentHistory(customer_id=customer.id, previous_salesperson_id=previous_id, new_salesperson_id=payload.assigned_to, changed_by_id=operator.id, change_reason=payload.reason, change_note=payload.note))
    db.commit()
    return {"message": "客户归属已更新", "customer_id": customer.id, "assigned_to": customer.assigned_to_id}


@router.post("/bulk-assignment")
def bulk_assignment(payload: dict, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    assignment = AssignmentRequest.model_validate(payload)
    customer_ids = payload.get("customer_ids", [])
    if not isinstance(customer_ids, list) or not customer_ids or len(customer_ids) > 500:
        raise HTTPException(status_code=400, detail="请选择 1-500 个客户")
    target = db.get(User, assignment.assigned_to) if assignment.assigned_to is not None else None
    if assignment.assigned_to is not None and (not target or target.role != "salesperson" or not target.is_active):
        raise HTTPException(status_code=400, detail="归属对象必须是启用中的业务员")
    customers = db.scalars(select(Customer).where(Customer.id.in_(customer_ids), Customer.is_deleted.is_(False))).all()
    updated = 0
    for customer in customers:
        if customer.assigned_to_id == assignment.assigned_to:
            continue
        previous_id = customer.assigned_to_id
        customer.assigned_to_id = assignment.assigned_to
        customer.lead_status = "unassigned" if target is None else ("assigned" if customer.lead_status != "converted" else "converted")
        db.add(CustomerAssignmentHistory(customer_id=customer.id, previous_salesperson_id=previous_id, new_salesperson_id=assignment.assigned_to, changed_by_id=operator.id, change_reason=assignment.reason, change_note=assignment.note))
        updated += 1
    db.commit()
    return {"message": f"已更新 {updated} 个客户", "updated": updated}
