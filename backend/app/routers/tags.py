from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import Customer, CustomerTag, CustomerTagRelation, User
from ..utils import formal_customer_condition
from ..schemas import TagCreate, TagResponse, TagUpdate

router = APIRouter(prefix="/tags", tags=["客户标签"])


def _tag_query():
    return select(CustomerTag, func.count(CustomerTagRelation.id)).outerjoin(CustomerTagRelation, CustomerTagRelation.tag_id == CustomerTag.id).outerjoin(Customer, Customer.id == CustomerTagRelation.customer_id).where((Customer.id.is_(None)) | formal_customer_condition()).group_by(CustomerTag.id).order_by(CustomerTag.name)


@router.get("", response_model=list[TagResponse])
def list_tags(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [TagResponse(id=tag.id, name=tag.name, color=tag.color, customer_count=int(count)) for tag, count in db.execute(_tag_query()).all()]


@router.post("", response_model=TagResponse)
def create_tag(payload: TagCreate, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    if db.scalar(select(CustomerTag).where(CustomerTag.name == payload.name)):
        raise HTTPException(status_code=409, detail="标签名称已存在")
    tag = CustomerTag(name=payload.name, color=payload.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return TagResponse(id=tag.id, name=tag.name, color=tag.color, customer_count=0)


@router.patch("/{tag_id}", response_model=TagResponse)
def update_tag(tag_id: int, payload: TagUpdate, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    tag = db.get(CustomerTag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    if payload.name and db.scalar(select(CustomerTag).where(CustomerTag.name == payload.name, CustomerTag.id != tag_id)):
        raise HTTPException(status_code=409, detail="标签名称已存在")
    if payload.name is not None:
        tag.name = payload.name
    if payload.color is not None:
        tag.color = payload.color
    db.commit()
    count = int(db.scalar(select(func.count(CustomerTagRelation.id)).where(CustomerTagRelation.tag_id == tag.id)) or 0)
    return TagResponse(id=tag.id, name=tag.name, color=tag.color, customer_count=count)


@router.delete("/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    tag = db.get(CustomerTag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    db.delete(tag)
    db.commit()
    return {"message": "标签已删除"}
