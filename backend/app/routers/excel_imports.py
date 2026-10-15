from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..deps import require_admin
from ..integrations.excel_import.service import bind_unmatched, confirm_import, ignore_unmatched_group, preview_import, serialize_batch, serialize_unmatched_groups
from ..models import Customer, ExcelImportBatch, ExcelImportUnmatchedRecord, User
from ..schemas import ExcelImportBindRequest, ExcelImportIgnoreRequest
from ..utils import formal_customer_condition

router = APIRouter(prefix="/excel-imports", tags=["ABC Excel 导入"])


def _validate_upload(upload: UploadFile, content: bytes) -> None:
    file_name = upload.filename or ""
    if file_name.lower().rsplit(".", 1)[-1] not in {"xlsx", "xls"}:
        raise HTTPException(status_code=400, detail="只支持 .xlsx 或 .xls 文件")
    max_bytes = settings.excel_max_file_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"文件过大，不能超过 {settings.excel_max_file_size_mb}MB")


@router.post("/abc/preview")
async def preview_abc_excel(
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    operator: User = Depends(require_admin),
):
    content = await upload.read()
    _validate_upload(upload, content)
    try:
        batch = preview_import(db, upload.filename or "abc.xlsx", content, operator.id, settings.excel_max_rows)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(batch)
    return serialize_batch(batch, include_preview=True)


@router.post("/abc/{batch_id}/confirm")
def confirm_abc_excel(batch_id: int, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    batch = db.get(ExcelImportBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    try:
        confirm_import(db, batch, operator.id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(batch)
    return serialize_batch(batch, include_preview=False)


@router.get("/abc/history")
def import_history(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    operator: User = Depends(require_admin),
):
    batches = db.scalars(select(ExcelImportBatch).order_by(desc(ExcelImportBatch.uploaded_at)).limit(limit)).all()
    return [serialize_batch(batch) for batch in batches]


@router.get("/abc/unmatched")
def unmatched_records(
    status: str | None = Query(None, pattern="^(pending|conflict)$"),
    batch_id: int | None = None,
    db: Session = Depends(get_db),
    operator: User = Depends(require_admin),
):
    query = select(ExcelImportUnmatchedRecord).options(selectinload(ExcelImportUnmatchedRecord.batch)).order_by(desc(ExcelImportUnmatchedRecord.created_at))
    if status:
        query = query.where(ExcelImportUnmatchedRecord.status == status)
    else:
        query = query.where(ExcelImportUnmatchedRecord.status.in_(["pending", "conflict"]))
    # A legacy row can retain a pending status even after its customer was
    # matched by an older import path.  Keep placeholder pointers visible for
    # manual resolution, but never expose rows already attached to a formal
    # customer in the pending queue.
    query = query.where(
        or_(
            ExcelImportUnmatchedRecord.customer_id.is_(None),
            ~ExcelImportUnmatchedRecord.customer_id.in_(
                select(Customer.id).where(formal_customer_condition())
            ),
        )
    )
    if batch_id:
        query = query.where(ExcelImportUnmatchedRecord.batch_id == batch_id)
    records = db.scalars(query.limit(2000)).all()
    return serialize_unmatched_groups(records)


@router.post("/abc/unmatched/{record_id}/bind")
def bind_excel_record(record_id: int, payload: ExcelImportBindRequest, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    record = db.scalar(select(ExcelImportUnmatchedRecord).options(selectinload(ExcelImportUnmatchedRecord.batch)).where(ExcelImportUnmatchedRecord.id == record_id))
    customer = db.scalar(select(Customer).where(Customer.id == payload.customer_id, Customer.is_deleted.is_(False)))
    if not record:
        raise HTTPException(status_code=404, detail="待匹配记录不存在")
    if not customer:
        raise HTTPException(status_code=404, detail="目标客户不存在")
    if customer.lead_status in {"pending", "rejected"}:
        raise HTTPException(status_code=409, detail="只能绑定到审核完成的正式客户")
    try:
        action = bind_unmatched(db, record, customer, operator.id, payload.note)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {"message": "Excel 记录已绑定并导入", "record_id": record_id, "customer_id": customer.id, "order_action": action}


@router.post("/abc/unmatched/{record_id}/ignore")
def ignore_excel_record(record_id: int, payload: ExcelImportIgnoreRequest, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    record = db.get(ExcelImportUnmatchedRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="待匹配记录不存在")
    try:
        ignore_unmatched_group(db, record, operator.id, payload.note)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"message": "Excel 记录已忽略", "record_id": record_id, "status": record.status}


@router.get("/abc/{batch_id}")
def get_import_batch(batch_id: int, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    batch = db.get(ExcelImportBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    return serialize_batch(batch, include_preview=True)
