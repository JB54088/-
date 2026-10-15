"""Tests for the customer soft-void workflow.

Every case runs inside a transaction that is rolled back in tearDown, so the
configured demo database is not changed by the test.
"""

import unittest
from uuid import uuid4

from sqlalchemy import select

from app.database import SessionLocal
from app.duplicate_leads import find_duplicate_customer
from app.integrations.excel_import.service import link_pending_external_customer
from app.models import Customer, CustomerPoolMatchHistory, User
from app.routers.customers import _apply_customer_void
from app.schemas import CustomerVoidRequest
from app.utils import formal_customer_condition


class CustomerVoidTest(unittest.TestCase):
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

    def test_void_hides_customer_releases_mapping_and_allows_rereport(self):
        suffix = uuid4().hex[:10]
        customer = Customer(
            external_customer_id=f"VOID-{suffix}",
            name="林予初",
            phone=f"138{suffix[:8]}",
            wechat_id=f"wx-{suffix}",
            reported_by_id=self.reporter.id,
            assigned_to_id=self.assignee.id,
            source_category="online",
            source_level_1="online",
            source_level_2="wechat",
            lead_status="approved",
            status="active",
            pool_match_status="matched",
            external_raw_data={"source": "test"},
        )
        self.db.add(customer)
        self.db.flush()

        result = _apply_customer_void(
            self.db,
            customer,
            self.admin,
            CustomerVoidRequest(reason="录入错误", note="软删除验收"),
        )
        self.assertTrue(result["is_deleted"])
        self.db.refresh(customer)
        self.assertTrue(customer.is_deleted)
        self.assertIsNone(customer.external_customer_id)
        self.assertEqual(customer.deleted_by_id, self.admin.id)
        self.assertEqual(customer.deleted_reason, "录入错误")
        self.assertEqual(customer.external_raw_data["retired_external_customer_ids"], [f"VOID-{suffix}"])

        history = self.db.scalar(
            select(CustomerPoolMatchHistory).where(
                CustomerPoolMatchHistory.customer_id == customer.id,
                CustomerPoolMatchHistory.match_type == "customer_voided",
            )
        )
        self.assertIsNotNone(history)
        self.assertEqual(history.new_status, "archived")

        # The archived row remains in the database but is absent from the
        # formal customer scope and duplicate detection.
        self.assertIsNone(self.db.scalar(select(Customer).where(Customer.id == customer.id, formal_customer_condition())))
        self.assertIsNone(find_duplicate_customer(self.db, customer.phone, customer.wechat_id))

        placeholder = Customer(
            external_customer_id=f"ABC-{suffix}",
            name="林予初",
            phone=customer.phone,
            lead_status="unassigned",
            status="active",
            pool_match_status="pending",
            external_raw_data={"source": "abc_excel_unmatched"},
        )
        self.db.add(placeholder)
        self.db.flush()

        rereported = Customer(
            name="林予初",
            phone=customer.phone,
            wechat_id=customer.wechat_id,
            reported_by_id=self.reporter.id,
            lead_status="pending",
            status="active",
            pool_match_status="pending",
        )
        self.db.add(rereported)
        self.db.flush()
        self.assertFalse(rereported.is_deleted)
        self.assertIsNone(rereported.assigned_to_id)
        self.assertIsNone(rereported.source_category)
        # A replacement lead is allowed, but an old ABC placeholder is not
        # silently moved to it; migration remains an explicit admin action.
        self.assertIsNone(link_pending_external_customer(self.db, rereported))
        self.assertIsNone(rereported.external_customer_id)
        self.assertEqual(placeholder.external_customer_id, f"ABC-{suffix}")


if __name__ == "__main__":
    unittest.main()
