"""Integration-style Mock test for deferred data-pool customer matching.

The test uses the configured PostgreSQL session but rolls back every case, so
it never leaves test customers, orders, or match history in the demo database.
Run inside the backend container with:

    python -m unittest tests.test_data_pool_matching -v
"""

import unittest
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.database import SessionLocal
from app.integrations.data_pool.schemas import DataPoolCustomerPayload, DataPoolOrderPayload
from app.integrations.data_pool.service import manually_match_customer, upsert_customer_from_pool, upsert_order_from_pool
from app.models import Customer, CustomerPoolMatchCandidate, CustomerTag, CustomerTagRelation, Order, User


class DataPoolMatchingTest(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.transaction = self.db.begin()
        self.admin = self.db.scalar(select(User).where(User.username == "admin01"))
        self.reporter = self.db.scalar(select(User).where(User.username == "sales01"))
        self.assignee = self.db.scalar(select(User).where(User.username == "sales02"))
        self.assertIsNotNone(self.admin)
        self.assertIsNotNone(self.reporter)
        self.assertIsNotNone(self.assignee)

    def tearDown(self):
        self.transaction.rollback()
        self.db.close()

    def _internal_customer(self, name: str, phone: str, assigned_to_id: int | None = None) -> Customer:
        customer = Customer(
            name=name,
            phone=phone,
            reported_by_id=self.reporter.id,
            assigned_to_id=assigned_to_id or self.assignee.id,
            source_category="online",
            lead_status="approved",
            status="active",
            pool_match_status="pending",
        )
        self.db.add(customer)
        self.db.flush()
        return customer

    def test_pending_phone_match_preserves_internal_fields_and_deduplicates_order(self):
        suffix = uuid4().hex[:10]
        customer = self._internal_customer(f"待入池客户-{suffix}", f"138{suffix[:8]}")
        # Business data is intentionally empty after demo cleanup; use a
        # retained tag configuration instead of looking for an old relation.
        tag_relation = CustomerTagRelation(customer_id=customer.id, tag_id=self.db.scalar(select(CustomerTag.id).limit(1)))
        self.db.add(tag_relation)
        self.db.flush()
        self.assertEqual(customer.pool_match_status, "pending")

        customer_payload = DataPoolCustomerPayload(
            external_customer_id=f"MOCK-CUS-{suffix}",
            name=customer.name,
            phone=customer.phone,
            total_spend=Decimal("3800"),
            order_count=3,
            last_spend_at=datetime.now(),
        )
        result = upsert_customer_from_pool(self.db, customer_payload, customer_payload.model_dump(mode="json"))
        self.assertEqual(result.match_status, "matched")
        self.assertEqual(result.match_type, "auto")
        self.db.refresh(customer)
        self.assertEqual(customer.external_customer_id, customer_payload.external_customer_id)
        self.assertEqual(customer.assigned_to_id, self.assignee.id)
        self.assertEqual(customer.reported_by_id, self.reporter.id)
        self.assertEqual(customer.pool_match_status, "matched")
        self.assertEqual(len(customer.tag_relations), 1)

        order_payload = DataPoolOrderPayload(
            external_order_id=f"MOCK-ORD-{suffix}",
            external_customer_id=customer_payload.external_customer_id,
            paid_at=datetime.now(),
            item_name="Mock 调理项目",
            amount=Decimal("399"),
        )
        upsert_order_from_pool(self.db, order_payload, order_payload.model_dump(mode="json"))
        order_payload.amount = Decimal("499")
        upsert_order_from_pool(self.db, order_payload, order_payload.model_dump(mode="json"))
        self.assertEqual(self.db.scalar(select(Order).where(Order.external_order_id == order_payload.external_order_id)).amount, Decimal("499.00"))
        self.assertEqual(self.db.scalar(select(Order.id).where(Order.external_order_id == order_payload.external_order_id)).__class__, int)
        self.assertEqual(len(self.db.scalars(select(Order).where(Order.external_order_id == order_payload.external_order_id)).all()), 1)

    def test_same_name_never_auto_matches(self):
        suffix = uuid4().hex[:10]
        internal = self._internal_customer(f"同名测试-{suffix}", f"139{suffix[:8]}")
        result = upsert_customer_from_pool(
            self.db,
            DataPoolCustomerPayload(external_customer_id=f"MOCK-NAME-{suffix}", name=internal.name, phone=f"137{suffix[:8]}"),
            {"external_customer_id": f"MOCK-NAME-{suffix}", "name": internal.name, "phone": f"137{suffix[:8]}"},
        )
        self.assertEqual(result.match_status, "manual_required")
        self.db.refresh(internal)
        self.assertIsNone(internal.external_customer_id)
        self.assertEqual(internal.pool_match_status, "manual_required")
        self.assertEqual(len(self.db.scalars(select(CustomerPoolMatchCandidate).where(CustomerPoolMatchCandidate.customer_id == internal.id)).all()), 1)

    def test_conflict_creates_candidates_and_manual_match_records_history(self):
        suffix = uuid4().hex[:10]
        shared_phone = f"136{suffix[:8]}"
        first = self._internal_customer(f"冲突客户一-{suffix}", shared_phone)
        second = self._internal_customer(f"冲突客户二-{suffix}", shared_phone)
        payload = DataPoolCustomerPayload(external_customer_id=f"MOCK-CONFLICT-{suffix}", name="数据池客户", phone=shared_phone)
        result = upsert_customer_from_pool(self.db, payload, payload.model_dump(mode="json"))
        self.assertEqual(result.match_status, "conflict")
        candidates = self.db.scalars(select(CustomerPoolMatchCandidate).where(CustomerPoolMatchCandidate.external_customer_id == payload.external_customer_id)).all()
        self.assertEqual(len(candidates), 2)

        first_candidate = next(candidate for candidate in candidates if candidate.customer_id == first.id)
        manual_result = manually_match_customer(self.db, first, first_candidate, self.admin.id, "Mock 人工核对")
        self.assertEqual(manual_result.match_type, "manual")
        self.db.refresh(first)
        self.assertEqual(first.pool_match_status, "matched")
        self.assertEqual(first.external_customer_id, payload.external_customer_id)
        self.assertEqual(first.assigned_to_id, self.assignee.id)
        self.assertEqual(second.pool_match_status, "conflict")
        self.assertEqual(first.pool_match_history[-1].match_type, "manual")


if __name__ == "__main__":
    unittest.main()
