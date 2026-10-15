from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import User

router = APIRouter(prefix="/users", tags=["用户权限"])


@router.get("")
def list_users(db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    users = db.scalars(select(User).order_by(User.role, User.created_at)).all()
    return [{"id": user.id, "username": user.username, "full_name": user.full_name, "role": user.role, "department_id": user.department_id, "is_active": user.is_active} for user in users]


@router.patch("/{user_id}/status")
def toggle_user_status(user_id: int, is_active: bool, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == operator.id and not is_active:
        raise HTTPException(status_code=400, detail="不能停用当前登录账号")
    user.is_active = is_active
    db.commit()
    return {"message": "用户状态已更新", "is_active": is_active}
