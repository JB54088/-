from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..deps import require_admin
from ..integrations.data_pool.client import DataPoolClient
from ..integrations.data_pool.sync import DataPoolSyncError, sync_from_data_pool
from ..models import Customer, CustomerPoolMatchCandidate, IntegrationLog, User

router = APIRouter(prefix="/internal/data-pool", tags=["数据池同步"])


def _client() -> DataPoolClient:
    return DataPoolClient(
        base_url=settings.data_pool_url,
        api_key=settings.data_pool_api_key,
        timeout_seconds=settings.data_pool_timeout_seconds,
        customers_path=settings.data_pool_customers_path,
        orders_path=settings.data_pool_orders_path,
    )


@router.post("/sync")
def trigger_sync(db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    try:
        return sync_from_data_pool(db, _client())
    except DataPoolSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/logs")
def data_pool_logs(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    rows = db.scalars(select(IntegrationLog).where(IntegrationLog.source == "data_pool").order_by(IntegrationLog.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "external_id": row.external_id,
            "status": row.status,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "new_customers": row.new_customers,
            "updated_customers": row.updated_customers,
            "new_orders": row.new_orders,
            "updated_orders": row.updated_orders,
            "failure_count": row.failure_count,
            "raw_data": row.raw_data,
            "error_message": row.error_message,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/matches")
def data_pool_matches(
    status: str | None = Query(None, pattern="^(pending|matched|conflict|manual_required)$"),
    search: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    operator: User = Depends(require_admin),
):
    """Return internal customers needing a data-pool match decision."""
    query = (
        select(Customer)
        .options(
            selectinload(Customer.pool_match_candidates),
            selectinload(Customer.reported_by_user),
            selectinload(Customer.assigned_to_user),
        )
        .where(Customer.pool_match_status != "matched", Customer.is_deleted.is_(False))
        .order_by(Customer.created_at.desc())
    )
    if status:
        query = query.where(Customer.pool_match_status == status)
    if search:
        query = query.where(Customer.name.ilike(f"%{search}%") | Customer.phone.ilike(f"%{search}%"))
    query = query.limit(limit)
    customers = db.scalars(query).unique().all()
    return [
        {
            "customer_id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "reported_by_name": customer.reported_by_user.full_name if customer.reported_by_user else None,
            "assigned_to_name": customer.assigned_to_user.full_name if customer.assigned_to_user else None,
            "pool_match_status": customer.pool_match_status,
            "external_customer_id": customer.external_customer_id,
            "candidates": [
                {
                    "id": candidate.id,
                    "external_customer_id": candidate.external_customer_id,
                    "name": candidate.name,
                    "phone": candidate.phone,
                    "raw_data": candidate.raw_data,
                    "is_active": candidate.is_active,
                    "created_at": candidate.created_at,
                    "last_seen_at": candidate.last_seen_at,
                }
                for candidate in customer.pool_match_candidates
                if candidate.is_active
            ],
        }
        for customer in customers
    ]
