from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, delete, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, selectinload

from ..consumption import consumption_count_by_customer_subquery, consumption_value_expression
from ..database import get_db
from ..duplicate_leads import find_duplicate_customer
from ..deps import get_current_user, require_admin, require_salesperson
from ..integrations.excel_import.service import link_pending_external_customer
from ..models import Customer, CustomerAssignmentHistory, CustomerTag, CustomerTagRelation, DuplicateLeadReport, Order, User
from ..schemas import LeadCreate, LeadListItem, LeadReviewRequest
from ..source_categories import SOURCE_LEVEL_2_OPTIONS, legacy_source_category, normalize_source_level_1, source_level_2_is_valid
from ..timezone import utc_now
from ..utils import consumption_key_expression, is_admin, normalize_phone

router = APIRouter(prefix="/leads", tags=["客户线索"])


def _lead_query():
    reporter = aliased(User)
    assignee = aliased(User)
    consumption_value = consumption_value_expression()
    count_metrics = consumption_count_by_customer_subquery()
    metrics = (
        select(
            Order.customer_id.label("customer_id"),
            func.coalesce(func.sum(consumption_value), 0).label("total_spend"),
            func.coalesce(count_metrics.c.order_count, 0).label("order_count"),
        )
        .select_from(Order)
        .outerjoin(count_metrics, count_metrics.c.customer_id == Order.customer_id)
        .group_by(Order.customer_id)
        .group_by(count_metrics.c.order_count)
        .subquery()
    )
    return (
        select(Customer, reporter.full_name, assignee.full_name, metrics.c.total_spend, metrics.c.order_count)
        .outerjoin(reporter, Customer.reported_by_id == reporter.id)
        .outerjoin(assignee, Customer.assigned_to_id == assignee.id)
        .outerjoin(metrics, metrics.c.customer_id == Customer.id)
        .options(selectinload(Customer.tag_relations).selectinload(CustomerTagRelation.tag))
        .order_by(desc(Customer.reported_at), desc(Customer.created_at))
    )


def _serialize(row) -> LeadListItem:
    customer, reported_by_name, assigned_to_name, total_spend, order_count = row
    return LeadListItem(
        id=customer.id,
        name=customer.name,
        phone=customer.phone,
        wechat_id=customer.wechat_id,
        gender=customer.gender,
        source_category=customer.source_category,
        source_level_1=customer.source_level_1,
        source_level_2=customer.source_level_2,
        source_custom_name=customer.source_custom_name,
        source_note=customer.source_note,
        notes=customer.notes,
        reported_by_name=reported_by_name,
        reported_at=customer.reported_at,
        assigned_to_name=assigned_to_name,
        lead_status=customer.lead_status,
        tags=[relation.tag.name for relation in customer.tag_relations if relation.tag],
        total_spend=total_spend or Decimal("0"),
        order_count=int(order_count or 0),
    )


@router.get("/pending")
def list_pending_leads(
    search: str | None = None,
    reported_by_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """The admin review queue is intentionally limited to pending leads."""
    return _list_leads(search, "pending", reported_by_id, page, page_size, db, user)


@router.get("")
def list_leads(
    search: str | None = None,
    status: str | None = None,
    reported_by_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _list_leads(search, status, reported_by_id, page, page_size, db, user)


@router.get("/mine")
def list_my_leads(
    search: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_salesperson),
):
    return _list_leads(search, status, None, page, page_size, db, user)


def _list_leads(search, status, reported_by_id, page, page_size, db: Session, user: User):
    query = _lead_query()
    conditions = [Customer.is_deleted.is_(False)]
    if not is_admin(user):
        conditions.append(Customer.reported_by_id == user.id)
    elif reported_by_id:
        conditions.append(Customer.reported_by_id == reported_by_id)
    if search:
        conditions.append(
            or_(
                Customer.name.ilike(f"%{search}%"),
                Customer.phone.ilike(f"%{search}%"),
                Customer.wechat_id.ilike(f"%{search}%"),
            )
        )
    if status:
        conditions.append(Customer.lead_status == status)
    if conditions:
        query = query.where(and_(*conditions))
    rows = db.execute(query).unique().all()
    total = len(rows)
    page_rows = rows[(page - 1) * page_size : page * page_size]
    return {
        "items": [_serialize(row) for row in page_rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.post("")
def create_lead(payload: LeadCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    is_admin_creator = is_admin(user)
    if not is_admin_creator and (
        payload.source_level_1
        or payload.source_level_2
        or payload.source_custom_name
        or payload.tag_ids
        or payload.assigned_to is not None
    ):
        raise HTTPException(status_code=403, detail="业务员只能提交基础客户线索")

    admin_source_level_1 = payload.source_level_1
    admin_source_level_2 = payload.source_level_2
    admin_source_custom_name = payload.source_custom_name.strip() if payload.source_custom_name else None
    admin_assignee = None
    admin_tag_ids: list[int] = []
    if is_admin_creator:
        if not admin_source_level_1 or not admin_source_level_2:
            raise HTTPException(status_code=400, detail="管理员创建客户时必须选择完整的来源归档分类")
        if not source_level_2_is_valid(admin_source_level_1, admin_source_level_2):
            raise HTTPException(status_code=400, detail="一级来源与二级来源不匹配")
        if admin_source_level_1 == "other" and admin_source_level_2 == "custom" and not admin_source_custom_name:
            raise HTTPException(status_code=400, detail="选择自定义来源时必须填写来源名称")
        admin_tag_ids = _validate_review_tags(db, payload.tag_ids)
        if payload.assigned_to is not None:
            admin_assignee = _validate_assignee(db, payload.assigned_to)

    submission_id = payload.submission_id or uuid4().hex
    existing_submission = db.scalar(select(Customer).where(Customer.submission_id == submission_id, Customer.is_deleted.is_(False)))
    if existing_submission:
        if existing_submission.reported_by_id == user.id:
            message = "客户已创建并进入市场部客户管理" if is_admin_creator else "客户线索已提交，等待主管审核"
            return {"message": message, "lead_id": existing_submission.id, "status": existing_submission.lead_status}
        # A key supplied by another account must never become a customer lookup.
        raise HTTPException(status_code=409, detail="该提交请求已处理，请勿重复提交")

    existing_duplicate_report = db.scalar(select(DuplicateLeadReport).where(DuplicateLeadReport.submission_id == submission_id))
    if existing_duplicate_report:
        raise HTTPException(status_code=409, detail="该客户已存在，已提交管理员确认。")

    normalized_phone = normalize_phone(payload.phone)
    if not normalized_phone:
        raise HTTPException(status_code=400, detail="请输入有效手机号")
    normalized_wechat = payload.wechat_id.strip() if payload.wechat_id and payload.wechat_id.strip() else None
    duplicate = find_duplicate_customer(db, normalized_phone, normalized_wechat)
    if duplicate:
        db.add(
            DuplicateLeadReport(
                existing_customer_id=duplicate.customer.id,
                reported_name=payload.name.strip(),
                reported_phone=normalized_phone,
                reported_wechat=normalized_wechat,
                new_reported_by_id=user.id,
                duplicate_reason=duplicate.reason,
                status="pending",
                submission_id=submission_id,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        raise HTTPException(status_code=409, detail="该客户已存在，已提交管理员确认。")

    # The server, not the browser, owns the business submission timestamp.
    now = utc_now()
    customer = Customer(
        name=payload.name.strip(),
        phone=normalized_phone,
        wechat_id=normalized_wechat,
        gender=payload.gender,
        source=payload.source_note,
        source_note=payload.source_note,
        source_category=legacy_source_category(admin_source_level_1) if is_admin_creator else None,
        source_level_1=admin_source_level_1 if is_admin_creator else None,
        source_level_2=admin_source_level_2 if is_admin_creator else None,
        source_custom_name=admin_source_custom_name if is_admin_creator else None,
        notes=payload.notes,
        reported_by_id=user.id,
        reported_at=now,
        assigned_to_id=admin_assignee.id if admin_assignee else None,
        department_id=admin_assignee.department_id if admin_assignee else None,
        lead_status="approved" if is_admin_creator and admin_assignee else ("unassigned" if is_admin_creator else "pending"),
        reviewed_by_id=user.id if is_admin_creator else None,
        reviewed_at=now if is_admin_creator else None,
        status="active",
        member_level="普通",
        submission_id=submission_id,
    )
    db.add(customer)
    try:
        db.flush()
        if is_admin_creator:
            for tag_id in admin_tag_ids:
                db.add(CustomerTagRelation(customer_id=customer.id, tag_id=tag_id))
            if admin_assignee:
                db.add(
                    CustomerAssignmentHistory(
                        customer_id=customer.id,
                        previous_salesperson_id=None,
                        new_salesperson_id=admin_assignee.id,
                        changed_by_id=user.id,
                        change_reason="管理员创建时首次分配",
                        change_note="管理员创建客户线索时直接分配业务员",
                    )
                )
        link_pending_external_customer(db, customer)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_submission = db.scalar(select(Customer).where(Customer.submission_id == submission_id, Customer.is_deleted.is_(False)))
        if existing_submission and existing_submission.reported_by_id == user.id:
            return {"message": "客户线索已提交，等待主管审核", "lead_id": existing_submission.id, "status": existing_submission.lead_status}
        raise HTTPException(status_code=409, detail="该提交请求已处理，请勿重复提交")
    db.refresh(customer)
    if is_admin_creator:
        message = "客户已创建并进入市场部客户管理" if admin_assignee else "客户已创建，当前待分配业务员"
    else:
        message = "客户线索已提交，等待主管审核"
    return {"message": message, "lead_id": customer.id, "status": customer.lead_status}


def _validate_review_tags(db: Session, tag_ids: list[int]) -> list[int]:
    normalized_ids = list(dict.fromkeys(tag_ids))
    tags = db.scalars(select(CustomerTag).where(CustomerTag.id.in_(normalized_ids))).all() if normalized_ids else []
    if len(tags) != len(normalized_ids):
        raise HTTPException(status_code=400, detail="存在无效客户标签")
    return normalized_ids


def _validate_assignee(db: Session, assigned_to: int | None) -> User:
    if assigned_to is None:
        raise HTTPException(status_code=400, detail="审核通过前必须选择当前归属业务员")
    assignee = db.get(User, assigned_to)
    if not assignee or not assignee.is_active or assignee.role != "salesperson":
        raise HTTPException(status_code=400, detail="归属对象必须是启用中的业务员")
    return assignee


def _resolve_review_source(payload: LeadReviewRequest) -> tuple[str | None, str | None, str | None]:
    """Resolve the new linked source fields while accepting old clients temporarily."""
    level_1 = payload.source_level_1
    level_2 = payload.source_level_2
    custom_name = payload.source_custom_name.strip() if payload.source_custom_name else None
    if not level_1 and payload.source_category:
        level_1 = normalize_source_level_1(payload.source_category)
        fallback_options = SOURCE_LEVEL_2_OPTIONS.get(level_1, ())
        level_2 = fallback_options[0]["code"] if fallback_options else None
    return level_1, level_2, custom_name


@router.post("/{customer_id}/review")
def review_lead(
    customer_id: int,
    payload: LeadReviewRequest,
    db: Session = Depends(get_db),
    reviewer: User = Depends(require_admin),
):
    """Approve/reject one pending lead as a single database transaction."""
    customer = db.scalar(
        select(Customer)
        .options(selectinload(Customer.tag_relations))
        .where(Customer.id == customer_id, Customer.is_deleted.is_(False))
    )
    if not customer:
        raise HTTPException(status_code=404, detail="线索不存在")
    if customer.lead_status != "pending":
        raise HTTPException(status_code=409, detail="只有待审核线索可以审核")

    tag_ids = _validate_review_tags(db, payload.tag_ids)
    assignee = None
    source_level_1, source_level_2, source_custom_name = _resolve_review_source(payload)
    if payload.action == "approve":
        if not source_level_1 or not source_level_2:
            raise HTTPException(status_code=400, detail="审核通过前必须选择完整的来源归档分类")
        if not source_level_2_is_valid(source_level_1, source_level_2):
            raise HTTPException(status_code=400, detail="一级来源与二级来源不匹配")
        if source_level_1 == "other" and source_level_2 == "custom" and not source_custom_name:
            raise HTTPException(status_code=400, detail="选择自定义来源时必须填写来源名称")
        assignee = _validate_assignee(db, payload.assigned_to)

    try:
        if payload.action == "approve":
            # Formal source, tags, assignment, status and first assignment history commit together.
            customer.source_level_1 = source_level_1
            customer.source_level_2 = source_level_2
            customer.source_custom_name = source_custom_name
            # Keep the legacy field synchronized for old reports/clients.
            customer.source_category = legacy_source_category(source_level_1)
            customer.assigned_to_id = assignee.id
            customer.lead_status = "approved"
            db.execute(delete(CustomerTagRelation).where(CustomerTagRelation.customer_id == customer.id))
            for tag_id in tag_ids:
                db.add(CustomerTagRelation(customer_id=customer.id, tag_id=tag_id))
            db.add(
                CustomerAssignmentHistory(
                    customer_id=customer.id,
                    previous_salesperson_id=None,
                    new_salesperson_id=assignee.id,
                    changed_by_id=reviewer.id,
                    change_reason="首次分配",
                    change_note="线索审核通过时首次分配",
                )
            )
        else:
            customer.lead_status = "rejected"
        customer.reviewed_by_id = reviewer.id
        # Only a successfully committed approval receives an approval time.
        if payload.action == "approve":
            customer.reviewed_at = utc_now()
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "message": "线索已审核通过并进入市场部客户管理" if payload.action == "approve" else "线索已驳回",
        "lead_id": customer.id,
        "status": customer.lead_status,
        "source_category": customer.source_category,
        "source_level_1": customer.source_level_1,
        "source_level_2": customer.source_level_2,
        "source_custom_name": customer.source_custom_name,
        "assigned_to": customer.assigned_to_id,
    }
