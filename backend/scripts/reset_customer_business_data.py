"""Preview or transactionally clear customer and demo business data.

Run in the backend container:
    python scripts/reset_customer_business_data.py          # preview only
    python scripts/reset_customer_business_data.py --apply  # apply after backup

User accounts, departments, customer tag definitions, source configuration,
and the database schema are intentionally preserved.
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    AgentQueryLog,
    Customer,
    CustomerAssignmentHistory,
    CustomerBalanceTransaction,
    CustomerPoolMatchCandidate,
    CustomerPoolMatchHistory,
    CustomerTag,
    CustomerTagRelation,
    Department,
    DuplicateLeadReport,
    ExcelImportBatch,
    ExcelImportUnmatchedRecord,
    IntegrationLog,
    Order,
    OrderItem,
    Report,
    User,
)


DELETE_MODELS = (
    ("order_items", OrderItem),
    ("customer_balance_transactions", CustomerBalanceTransaction),
    ("orders", Order),
    ("customer_tag_relations", CustomerTagRelation),
    ("customer_assignment_history", CustomerAssignmentHistory),
    ("customer_pool_match_history", CustomerPoolMatchHistory),
    ("customer_pool_match_candidates", CustomerPoolMatchCandidate),
    ("duplicate_lead_reports", DuplicateLeadReport),
    ("excel_import_unmatched_records", ExcelImportUnmatchedRecord),
    ("reports", Report),
    ("agent_query_logs", AgentQueryLog),
    ("integration_logs", IntegrationLog),
    ("excel_import_batches", ExcelImportBatch),
    ("customers", Customer),
)


def count_rows(db: Session, model: type) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def build_plan(db: Session) -> dict[str, int]:
    plan = {table: count_rows(db, model) for table, model in DELETE_MODELS}
    plan["users_to_preserve"] = count_rows(db, User)
    plan["departments_to_preserve"] = count_rows(db, Department)
    plan["customer_tag_definitions_to_preserve"] = count_rows(db, CustomerTag)
    return plan


def apply_plan(db: Session) -> None:
    # Delete children before parents to respect the real foreign keys.
    for _, model in DELETE_MODELS:
        db.execute(delete(model))
    db.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply the displayed plan in one database transaction",
    )
    args = parser.parse_args()

    if not args.apply:
        with SessionLocal() as db:
            print(json.dumps({"mode": "preview", **build_plan(db)}, ensure_ascii=False, indent=2))
        return

    with SessionLocal.begin() as db:
        plan = build_plan(db)
        print(json.dumps({"mode": "apply", **plan}, ensure_ascii=False, indent=2))
        apply_plan(db)

    with SessionLocal() as db:
        remaining = {table: count_rows(db, model) for table, model in DELETE_MODELS}
        remaining["users"] = count_rows(db, User)
        remaining["departments"] = count_rows(db, Department)
        remaining["customer_tag_definitions"] = count_rows(db, CustomerTag)
        print(json.dumps({"remaining_after_commit": remaining}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
