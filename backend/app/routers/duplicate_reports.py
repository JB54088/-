from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.orm import Session, aliased

from ..database import get_db
from ..deps import require_admin
from ..models import Customer, DuplicateLeadReport, User
from ..schemas import DuplicateLeadReviewRequest

router = APIRouter(prefix="/duplicate-reports", tags=["重复报备"])


def _serialize(row) -> dict:
    report, existing, original_reporter, current_assignee, new_reporter, reviewer = row
    return {
        "id": report.id,
        "existing_customer_id": existing.id,
        "existing_customer_name": existing.name,
        "existing_customer_phone": existing.phone,
        "existing_reported_by_id": existing.reported_by_id,
        "existing_reported_by_name": original_reporter,
        "existing_assigned_to_id": existing.assigned_to_id,
        "existing_assigned_to_name": current_assignee,
        "reported_name": report.reported_name,
        "reported_phone": report.reported_phone,
        "reported_wechat": report.reported_wechat,
        "new_reported_by_id": report.new_reported_by_id,
        "new_reported_by_name": new_reporter,
        "duplicate_reason": report.duplicate_reason,
        "status": report.status,
        "reviewed_by_id": report.reviewed_by_id,
        "reviewed_by_name": reviewer,
        "reviewed_at": report.reviewed_at,
        "review_note": report.review_note,
        "submission_id": report.submission_id,
        "created_at": report.created_at,
    }


def _query():
    original_reporter = aliased(User)
    current_assignee = aliased(User)
    new_reporter = aliased(User)
    reviewer = aliased(User)
    return (
        select(
            DuplicateLeadReport,
            Customer,
            original_reporter.full_name,
            current_assignee.full_name,
            new_reporter.full_name,
            reviewer.full_name,
        )
        .join(Customer, DuplicateLeadReport.existing_customer_id == Customer.id)
        .outerjoin(original_reporter, Customer.reported_by_id == original_reporter.id)
        .outerjoin(current_assignee, Customer.assigned_to_id == current_assignee.id)
        .outerjoin(new_reporter, DuplicateLeadReport.new_reported_by_id == new_reporter.id)
        .outerjoin(reviewer, DuplicateLeadReport.reviewed_by_id == reviewer.id)
        .order_by(desc(DuplicateLeadReport.created_at), desc(DuplicateLeadReport.id))
    )


@router.get("")
def list_duplicate_reports(
    status: str | None = Query(None, pattern="^(pending|confirmed_duplicate|not_duplicate|rejected)$"),
    search: str | None = None,
    new_reported_by_id: int | None = None,
    assigned_to_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = _query()
    conditions = []
    if status:
        conditions.append(DuplicateLeadReport.status == status)
    if new_reported_by_id:
        conditions.append(DuplicateLeadReport.new_reported_by_id == new_reported_by_id)
    if assigned_to_id:
        conditions.append(Customer.assigned_to_id == assigned_to_id)
    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                DuplicateLeadReport.reported_name.ilike(search_pattern),
                DuplicateLeadReport.reported_phone.ilike(search_pattern),
                Customer.name.ilike(search_pattern),
                Customer.phone.ilike(search_pattern),
            )
        )
    if conditions:
        query = query.where(and_(*conditions))
    rows = db.execute(query).all()
    total = len(rows)
    page_rows = rows[(page - 1) * page_size : page * page_size]
    return {
        "items": [_serialize(row) for row in page_rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.post("/{report_id}/review")
def review_duplicate_report(
    report_id: int,
    payload: DuplicateLeadReviewRequest,
    db: Session = Depends(get_db),
    reviewer: User = Depends(require_admin),
):
    report = db.scalar(
        select(DuplicateLeadReport)
        .where(DuplicateLeadReport.id == report_id)
        .with_for_update()
    )
    if not report:
        raise HTTPException(status_code=404, detail="重复报备记录不存在")
    if report.status != "pending":
        raise HTTPException(status_code=409, detail="该重复报备记录已经处理，请刷新页面")

    reviewed_at = datetime.now().replace(microsecond=0)
    new_lead_id = None
    try:
        if payload.action == "not_duplicate":
            # The administrator explicitly confirmed that the identity match
            # is a false positive, so create a fresh pending lead. It remains
            # unassigned until the normal lead-review workflow completes.
            customer = Customer(
                name=report.reported_name,
                phone=report.reported_phone,
                wechat_id=report.reported_wechat,
                source="重复报备复核",
                source_note=payload.review_note,
                source_category=None,
                notes="经管理员确认不是同一客户",
                reported_by_id=report.new_reported_by_id,
                reported_at=report.created_at,
                lead_status="pending",
                status="active",
                member_level="普通",
                submission_id=f"resolved-duplicate-{uuid4().hex}",
            )
            db.add(customer)
            db.flush()
            new_lead_id = customer.id

        report.status = {
            "confirm_duplicate": "confirmed_duplicate",
            "not_duplicate": "not_duplicate",
            "reject": "rejected",
        }[payload.action]
        report.reviewed_by_id = reviewer.id
        report.reviewed_at = reviewed_at
        report.review_note = payload.review_note
        db.commit()
    except Exception:
        db.rollback()
        raise

    messages = {
        "confirm_duplicate": "已确认为重复报备，保留原客户",
        "not_duplicate": "已确认不是同一客户，已创建新的待审核线索",
        "reject": "已驳回重复报备记录",
    }
    return {
        "message": messages[payload.action],
        "report_id": report.id,
        "status": report.status,
        "new_lead_id": new_lead_id,
    }
