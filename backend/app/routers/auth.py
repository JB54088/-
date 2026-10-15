from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import LoginRequest, TokenResponse, UserBrief
from ..security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["认证"])


def user_brief(user: User) -> UserBrief:
    return UserBrief(id=user.id, username=user.username, full_name=user.full_name, role=user.role, department_id=user.department_id, department_name=user.department.name if user.department else None)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).options(joinedload(User.department)).where(User.username == payload.username))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return TokenResponse(access_token=create_access_token(user.id), user=user_brief(user))


@router.get("/me", response_model=UserBrief)
def me(user: User = Depends(get_current_user)) -> UserBrief:
    return user_brief(user)
