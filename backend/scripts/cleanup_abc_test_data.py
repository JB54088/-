"""Preview or transactionally remove the currently imported ABC test data.

Run in the backend container:
    python scripts/cleanup_abc_test_data.py          # preview only
    python scripts/cleanup_abc_test_data.py --apply  # apply after a backup

This is deliberately an operator script, not an HTTP endpoint. It scopes
transactions to import batches, preserves manually reported customer records,
and deletes only unmistakable ABC-created placeholders with no manual links.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.balance import rebuild_customer_balance
from app.database import SessionLocal
from app.models import (
    Customer,
    CustomerAssignmentHistory,
    CustomerBalanceTransaction,
    CustomerPoolMatchCandidate,
    CustomerPoolMatchHistory,
    CustomerTag,
    CustomerTagRelation,
    DuplicateLeadReport,
    ExcelImportBatch,
    ExcelImportUnmatchedRecord,
    IntegrationLog,
    Order,
    OrderItem,
    Report,
    User,
)

ABC_HISTORY_TYPES = {"auto", "auto_lead_phone", "excel_unmatched"}
ABC_LOG_TYPES = {"excel_import", "balance_insufficient"}
ABC_RAW_MARKERS = {
    "last_import_batch_id",
    "last_import_file",
    "pending_external",
    "placeholder_raw_data",
    "linked_from_external_placeholder",
}


def _has_abc_marker(raw: Any, batch_ids: set[int]) -> bool:
    if not isinstance(raw, dict):
        return False
    if raw.get("source") == "abc_excel":
        return True
    try:
        if int(raw.get("last_import_batch_id")) in batch_ids:
            return True
    except (TypeError, ValueError):
        pass
    return bool(ABC_RAW_MARKERS.intersection(raw))


@dataclass
class CleanupPlan:
    batch_ids: list[int]
    order_ids: list[int]
    affected_customer_ids: list[int]
    mapped_customer_ids: list[int]
    raw_profile_customer_ids: list[int]
    abc_only_customer_ids: list[int]
    deletable_customer_ids: list[int]
    ambiguous_customer_ids: list[int]
    unmatched_ids: list[int]
    balance_ids: list[int]
    match_history_ids: list[int]
    integration_log_ids: list[int]
    report_ids: list[int]
    item_count: int
    mapped_record_count: int
    user_count: int
    tag_config_count: int
    customer_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": "preview",
            "delete": {
                "excel_import_batches": len(self.batch_ids),
                "orders": len(self.order_ids),
                "order_items": self.item_count,
                "customer_balance_transactions": len(self.balance_ids),
                "excel_import_unmatched_records": len(self.unmatched_ids),
                "abc_match_history_rows": len(self.match_history_ids),
                "abc_integration_logs": len(self.integration_log_ids),
                "stored_report_snapshots": len(self.report_ids),
                "abc_only_customer_profiles": len(self.deletable_customer_ids),
            },
            "clear": {
                "retained_customer_external_mappings": len(
                    set(self.mapped_customer_ids) - set(self.deletable_customer_ids)
                ),
                "customer_external_snapshots": len(
                    set(self.raw_profile_customer_ids) - set(self.deletable_customer_ids)
                ),
            },
            "retain": {
                "customers_after_cleanup": self.customer_count - len(self.deletable_customer_ids),
                "users": self.user_count,
                "customer_tag_configs": self.tag_config_count,
            },
            "mapped_customer_records_affected_including_deleted_profiles": self.mapped_record_count,
            "manual_review_customer_ids": self.ambiguous_customer_ids,
            "abc_only_candidate_ids": self.abc_only_customer_ids,
        }


def build_plan(db: Session) -> CleanupPlan:
    batches = db.scalars(select(ExcelImportBatch).order_by(ExcelImportBatch.id)).all()
    batch_ids = {batch.id for batch in batches}
    batch_orders = (
        db.scalars(select(Order).where(Order.import_batch_id.in_(batch_ids))).all()
        if batch_ids
        else []
    )
    order_ids = {order.id for order in batch_orders}
    unmatched = (
        db.scalars(
            select(ExcelImportUnmatchedRecord).where(
                ExcelImportUnmatchedRecord.batch_id.in_(batch_ids)
            )
        ).all()
        if batch_ids
        else []
    )
    imported_external_ids = {
        value
        for value in [
            *(order.external_customer_id for order in batch_orders),
            *(record.external_customer_id for record in unmatched),
        ]
        if value
    }
    customers = db.scalars(select(Customer).order_by(Customer.id)).all()
    batch_orders_by_customer: dict[int, list[Order]] = {}
    for order in batch_orders:
        batch_orders_by_customer.setdefault(order.customer_id, []).append(order)
    unmatched_by_customer: dict[int, list[ExcelImportUnmatchedRecord]] = {}
    for record in unmatched:
        if record.customer_id is not None:
            unmatched_by_customer.setdefault(record.customer_id, []).append(record)

    raw_profile_ids = {
        customer.id
        for customer in customers
        if _has_abc_marker(customer.external_raw_data, batch_ids)
    }
    mapped_customer_ids = {
        customer.id
        for customer in customers
        if customer.external_customer_id in imported_external_ids
    }
    affected_customer_ids = (
        set(batch_orders_by_customer)
        | set(unmatched_by_customer)
        | raw_profile_ids
        | mapped_customer_ids
    )

    abc_only_candidates = [
        customer
        for customer in customers
        if customer.reported_by_id is None
        and customer.assigned_to_id is None
        and customer.lead_status == "unassigned"
        and not customer.is_deleted
        and _has_abc_marker(customer.external_raw_data, batch_ids)
    ]
    candidate_ids = {customer.id for customer in abc_only_candidates}
    deletable_ids = set(candidate_ids)
    if candidate_ids:
        protected_references = [
            set(
                db.scalars(
                    select(model.customer_id).where(model.customer_id.in_(candidate_ids)).distinct()
                ).all()
            )
            for model in (
                CustomerAssignmentHistory,
                CustomerTagRelation,
                CustomerPoolMatchCandidate,
            )
        ]
        protected_references.append(
            set(
                db.scalars(
                    select(DuplicateLeadReport.existing_customer_id)
                    .where(DuplicateLeadReport.existing_customer_id.in_(candidate_ids))
                    .distinct()
                ).all()
            )
        )
        protected_references.append(
            set(
                db.scalars(
                    select(CustomerPoolMatchHistory.customer_id)
                    .where(
                        CustomerPoolMatchHistory.customer_id.in_(candidate_ids),
                        CustomerPoolMatchHistory.match_type.notin_(ABC_HISTORY_TYPES),
                    )
                    .distinct()
                ).all()
            )
        )
        protected_references.append(
            set(
                db.scalars(
                    select(CustomerBalanceTransaction.customer_id)
                    .where(
                        CustomerBalanceTransaction.customer_id.in_(candidate_ids),
                        (CustomerBalanceTransaction.source_transaction_id.is_(None))
                        | (~CustomerBalanceTransaction.source_transaction_id.in_(order_ids)),
                    )
                    .distinct()
                ).all()
            )
        )
        for protected_ids in protected_references:
            deletable_ids -= protected_ids

    match_history = db.scalars(select(CustomerPoolMatchHistory)).all()
    match_history_ids = [
        row.id
        for row in match_history
        if row.match_type == "excel_unmatched"
        or (row.match_type in ABC_HISTORY_TYPES and row.customer_id in affected_customer_ids)
    ]
    integration_logs = db.scalars(
        select(IntegrationLog).where(
            IntegrationLog.source == "abc_excel",
            IntegrationLog.event_type.in_(ABC_LOG_TYPES),
        )
    ).all()
    balance_ids = (
        db.scalars(
            select(CustomerBalanceTransaction.id).where(
                CustomerBalanceTransaction.source_transaction_id.in_(order_ids)
            )
        ).all()
        if order_ids
        else []
    )
    item_count = (
        int(
            db.scalar(
                select(func.count(OrderItem.id)).where(OrderItem.order_id.in_(order_ids))
            )
            or 0
        )
        if order_ids
        else 0
    )

    return CleanupPlan(
        batch_ids=sorted(batch_ids),
        order_ids=sorted(order_ids),
        affected_customer_ids=sorted(affected_customer_ids),
        mapped_customer_ids=sorted(mapped_customer_ids),
        raw_profile_customer_ids=sorted(raw_profile_ids),
        abc_only_customer_ids=sorted(candidate_ids),
        deletable_customer_ids=sorted(deletable_ids),
        ambiguous_customer_ids=sorted(candidate_ids - deletable_ids),
        unmatched_ids=sorted(record.id for record in unmatched),
        balance_ids=sorted(balance_ids),
        match_history_ids=sorted(match_history_ids),
        integration_log_ids=sorted(log.id for log in integration_logs),
        report_ids=db.scalars(select(Report.id)).all(),
        item_count=item_count,
        mapped_record_count=len(mapped_customer_ids),
        user_count=int(db.scalar(select(func.count(User.id))) or 0),
        tag_config_count=int(db.scalar(select(func.count(CustomerTag.id))) or 0),
        customer_count=len(customers),
    )


def apply_plan(db: Session, plan: CleanupPlan) -> None:
    if plan.ambiguous_customer_ids:
        # Ambiguous profiles are retained, while their identifiable ABC data
        # is still cleaned. The IDs are printed for follow-up by an operator.
        pass

    balance_customer_ids = set(
        db.scalars(
            select(CustomerBalanceTransaction.customer_id).where(
                CustomerBalanceTransaction.id.in_(plan.balance_ids)
            )
        ).all()
    )
    if plan.order_ids:
        db.execute(delete(OrderItem).where(OrderItem.order_id.in_(plan.order_ids)))
        db.execute(
            delete(CustomerBalanceTransaction).where(
                CustomerBalanceTransaction.source_transaction_id.in_(plan.order_ids)
            )
        )
        db.execute(delete(Order).where(Order.id.in_(plan.order_ids)))
    if plan.batch_ids:
        db.execute(
            delete(ExcelImportUnmatchedRecord).where(
                ExcelImportUnmatchedRecord.batch_id.in_(plan.batch_ids)
            )
        )
    if plan.match_history_ids:
        db.execute(
            delete(CustomerPoolMatchHistory).where(
                CustomerPoolMatchHistory.id.in_(plan.match_history_ids)
            )
        )
    if plan.abc_only_customer_ids:
        # Tag, assignment, duplicate-report, non-ABC match-history, and
        # non-import balance references protect a profile from deletion.
        if plan.deletable_customer_ids:
            db.execute(
                delete(CustomerPoolMatchCandidate).where(
                    CustomerPoolMatchCandidate.customer_id.in_(plan.deletable_customer_ids)
                )
            )
            db.execute(
                delete(Customer).where(Customer.id.in_(plan.deletable_customer_ids))
            )

    deleted_customers = set(plan.deletable_customer_ids)
    retained_affected = set(plan.affected_customer_ids) - deleted_customers
    if retained_affected:
        rows = db.scalars(
            select(Customer).where(Customer.id.in_(retained_affected))
        ).all()
        for customer in rows:
            if customer.external_customer_id is not None:
                customer.external_customer_id = None
            if _has_abc_marker(customer.external_raw_data, set(plan.batch_ids)):
                customer.external_raw_data = None
            customer.external_total_spend = 0
            customer.external_order_count = 0
            customer.external_last_spend_at = None
            customer.external_synced_at = None
            customer.pool_match_status = "pending"

    db.execute(
        delete(IntegrationLog).where(IntegrationLog.id.in_(plan.integration_log_ids))
    )
    db.execute(delete(ExcelImportBatch).where(ExcelImportBatch.id.in_(plan.batch_ids)))
    db.execute(delete(Report).where(Report.id.in_(plan.report_ids)))

    for customer_id in sorted(balance_customer_ids - deleted_customers):
        rebuild_customer_balance(db, customer_id)
    db.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="execute the displayed cleanup plan in one database transaction",
    )
    args = parser.parse_args()

    if args.apply:
        with SessionLocal.begin() as db:
            plan = build_plan(db)
            preview = plan.as_dict()
            preview["mode"] = "apply"
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            apply_plan(db, plan)
    else:
        with SessionLocal() as db:
            preview = build_plan(db).as_dict()
            print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    with SessionLocal() as db:
        remaining = {
            "users": int(db.scalar(select(func.count(User.id))) or 0),
            "customer_tags": int(db.scalar(select(func.count(CustomerTag.id))) or 0),
            "customers": int(db.scalar(select(func.count(Customer.id))) or 0),
            "orders": int(db.scalar(select(func.count(Order.id))) or 0),
            "order_items": int(db.scalar(select(func.count(OrderItem.id))) or 0),
            "excel_import_batches": int(db.scalar(select(func.count(ExcelImportBatch.id))) or 0),
            "excel_import_unmatched_records": int(db.scalar(select(func.count(ExcelImportUnmatchedRecord.id))) or 0),
            "customer_balance_transactions": int(db.scalar(select(func.count(CustomerBalanceTransaction.id))) or 0),
            "reports": int(db.scalar(select(func.count(Report.id))) or 0),
        }
        print(json.dumps({"remaining_after_commit": remaining}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
