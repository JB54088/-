from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import LoginAuditLog, User
from ..schemas import LoginAuditLogPage, LoginRequest, TokenResponse, UserBrief, UserProfileUpdate
from ..security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["认证"])


def user_brief(user: User) -> UserBrief:
    return UserBrief(id=user.id, username=user.username, full_name=user.full_name, role=user.role, department_id=user.department_id, department_name=user.department.name if user.department else None)


def record_login_attempt(
    db: Session,
    username: str,
    user: User | None,
    success: bool,
    failure_reason: str | None = None,
) -> None:
    db.add(LoginAuditLog(
        user_id=user.id if user else None,
        username=username[:80],
        full_name=user.full_name if user else None,
        role=user.role if user else None,
        success=success,
        failure_reason=failure_reason,
        created_at=datetime.now(timezone.utc),
    ))
    db.commit()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).options(joinedload(User.department)).where(User.username == payload.username))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        reason = "account_disabled" if user and not user.is_active else "invalid_credentials"
        record_login_attempt(db, payload.username, user, False, reason)
        raise HTTPException(status_code=401, detail="账号或密码错误")
    record_login_attempt(db, payload.username, user, True)
    return TokenResponse(access_token=create_access_token(user.id, remember_me=payload.remember_me), user=user_brief(user))


@router.get("/login-logs", response_model=LoginAuditLogPage)
def login_logs(
    search: str | None = Query(default=None, max_length=80),
    success: bool | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> LoginAuditLogPage:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")

    shanghai = ZoneInfo("Asia/Shanghai")
    filters = []
    if search and search.strip():
        term = f"%{search.strip()}%"
        filters.append(or_(LoginAuditLog.username.ilike(term), LoginAuditLog.full_name.ilike(term)))
    if success is not None:
        filters.append(LoginAuditLog.success == success)
    if start_date:
        filters.append(LoginAuditLog.created_at >= datetime.combine(start_date, time.min, tzinfo=shanghai))
    if end_date:
        next_day = end_date + timedelta(days=1)
        filters.append(LoginAuditLog.created_at < datetime.combine(next_day, time.min, tzinfo=shanghai))

    total = db.scalar(select(func.count(LoginAuditLog.id)).where(*filters)) or 0
    items = db.scalars(
        select(LoginAuditLog)
        .where(*filters)
        .order_by(LoginAuditLog.created_at.desc(), LoginAuditLog.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return LoginAuditLogPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/me", response_model=UserBrief)
def me(user: User = Depends(get_current_user)) -> UserBrief:
    return user_brief(user)


def apply_profile_update(user: User, payload: UserProfileUpdate) -> User:
    if user.role != "salesperson":
        raise HTTPException(status_code=403, detail="只有业务员可以自行修改显示姓名")
    user.full_name = payload.display_name
    return user


@router.patch("/me/profile", response_model=UserBrief)
def update_my_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserBrief:
    apply_profile_update(user, payload)
    db.commit()
    db.refresh(user)
    return user_brief(user)
