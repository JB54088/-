from datetime import datetime

from sqlalchemy.orm import Session

from ...models import IntegrationLog
from .client import DataPoolClient
from .schemas import DataPoolCustomerPayload, DataPoolOrderPayload, DataPoolSyncSummary
from .service import upsert_customer_from_pool, upsert_order_from_pool


class DataPoolSyncError(RuntimeError):
    pass


def _raw_object(raw) -> dict:
    return raw if isinstance(raw, dict) else {"value": str(raw)}


def _log_row(db: Session, event_type: str, external_id: str | None, status: str, raw_data: dict, error_message: str | None = None) -> None:
    db.add(IntegrationLog(source="data_pool", event_type=event_type, external_id=external_id, status=status, raw_data=raw_data, error_message=error_message, created_at=datetime.now()))


def sync_from_data_pool(db: Session, client: DataPoolClient) -> dict:
    started_at = datetime.now()
    summary_log = IntegrationLog(source="data_pool", event_type="sync", status="running", raw_data={"status": "running"}, started_at=started_at, created_at=started_at)
    db.add(summary_log)
    db.commit()
    errors: list[str] = []
    new_customers = updated_customers = new_orders = updated_orders = failure_count = 0
    matched_customers = conflict_customers = manual_required_customers = 0
    payment_mismatch_count = 0
    try:
        customer_rows = client.fetch_customers()
        order_rows = client.fetch_orders()
    except Exception as exc:
        finished_at = datetime.now()
        summary_log.status = "failed"
        summary_log.finished_at = finished_at
        summary_log.failure_count = 1
        summary_log.error_message = str(exc)
        summary_log.raw_data = {"status": "failed", "errors": [str(exc)]}
        db.commit()
        raise DataPoolSyncError(str(exc)) from exc

    for raw in customer_rows:
        raw_data = _raw_object(raw)
        external_id = str(raw_data.get("external_customer_id") or raw_data.get("customer_id") or raw_data.get("id") or "") or None
        try:
            with db.begin_nested():
                payload = DataPoolCustomerPayload.model_validate(raw_data)
                result = upsert_customer_from_pool(db, payload, raw_data)
                _log_row(db, "customer", payload.external_customer_id or payload.phone, "success", raw_data)
                db.flush()
            if result.action == "created":
                new_customers += 1
            else:
                updated_customers += 1
            if result.match_status == "matched":
                matched_customers += 1
            elif result.match_status == "conflict":
                conflict_customers += 1
            elif result.match_status == "manual_required":
                manual_required_customers += 1
        except Exception as exc:
            failure_count += 1
            message = f"客户 {external_id or raw_data.get('phone', 'unknown')}: {exc}"
            errors.append(message)
            _log_row(db, "customer", external_id, "failed", raw_data, str(exc))

    for raw in order_rows:
        raw_data = _raw_object(raw)
        external_id = str(raw_data.get("external_order_id") or raw_data.get("order_id") or raw_data.get("id") or "") or None
        try:
            with db.begin_nested():
                payload = DataPoolOrderPayload.model_validate(raw_data)
                result = upsert_order_from_pool(db, payload, raw_data)
                _log_row(db, "order", payload.external_order_id, "success", raw_data)
                if result.payment_amount_mismatch:
                    payment_mismatch_count += 1
                    mismatch_message = result.payment_amount_error or "医保/自费金额无法通过总金额校验"
                    errors.append(f"订单 {payload.external_order_id}: {mismatch_message}")
                    _log_row(db, "payment_amount_mismatch", payload.external_order_id, "failed", raw_data, mismatch_message)
                db.flush()
            if result.action == "created":
                new_orders += 1
            else:
                updated_orders += 1
        except Exception as exc:
            failure_count += 1
            message = f"订单 {external_id or 'unknown'}: {exc}"
            errors.append(message)
            _log_row(db, "order", external_id, "failed", raw_data, str(exc))

    finished_at = datetime.now()
    total_rows = len(customer_rows) + len(order_rows)
    status = "failed" if total_rows and failure_count == total_rows else "partial" if failure_count or payment_mismatch_count else "success"
    summary = DataPoolSyncSummary(
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        new_customers=new_customers,
        updated_customers=updated_customers,
        new_orders=new_orders,
        updated_orders=updated_orders,
        failure_count=failure_count,
        matched_customers=matched_customers,
        conflict_customers=conflict_customers,
        manual_required_customers=manual_required_customers,
        payment_mismatch_count=payment_mismatch_count,
        errors=errors[:50],
    )
    summary_log.status = status
    summary_log.finished_at = finished_at
    summary_log.new_customers = new_customers
    summary_log.updated_customers = updated_customers
    summary_log.new_orders = new_orders
    summary_log.updated_orders = updated_orders
    summary_log.failure_count = failure_count
    summary_log.raw_data = summary.model_dump(mode="json")
    summary_log.error_message = "; ".join(errors[:5]) if errors else None
    db.commit()
    return summary.model_dump(mode="json")
