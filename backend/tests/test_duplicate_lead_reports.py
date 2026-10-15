"""Tests for duplicate lead matching and idempotent submission storage."""

import unittest
from uuid import uuid4

from sqlalchemy import select

from app.database import SessionLocal
from app.duplicate_leads import find_duplicate_customer
from app.models import Customer, DuplicateLeadReport, User
from app.utils import normalize_phone


class DuplicateLeadReportTest(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.transaction = self.db.begin()
        self.reporter = self.db.scalar(select(User).where(User.username == "sales01"))
        self.other_reporter = self.db.scalar(select(User).where(User.username == "sales02"))
        self.assignee = self.db.scalar(select(User).where(User.username == "sales01"))
        self.assertIsNotNone(self.reporter)
        self.assertIsNotNone(self.other_reporter)

    def tearDown(self):
        self.transaction.rollback()
        self.db.close()

    def _customer(self, name: str, phone: str, wechat_id: str | None = None) -> Customer:
        customer = Customer(
            name=name,
            phone=phone,
            wechat_id=wechat_id,
            reported_by_id=self.reporter.id,
            assigned_to_id=self.assignee.id,
            lead_status="approved",
            status="active",
            source_category="online",
            pool_match_status="pending",
        )
        self.db.add(customer)
        self.db.flush()
        return customer

    def test_phone_normalization_and_priority(self):
        customer = self._customer(f"手机号命中-{uuid4().hex[:8]}", "13800138000", "wx-phone")
        self.assertEqual(normalize_phone("+86 138-0013-8000"), "13800138000")
        match = find_duplicate_customer(self.db, "+86 138-0013-8000", "new-wechat")
        self.assertIsNotNone(match)
        self.assertEqual(match.customer.id, customer.id)
        self.assertEqual(match.reason, "phone")

    def test_wechat_is_second_priority(self):
        customer = self._customer(f"微信命中-{uuid4().hex[:8]}", "13900139000", "wx-exact")
        match = find_duplicate_customer(self.db, "13700137000", " wx-exact ")
        self.assertIsNotNone(match)
        self.assertEqual(match.customer.id, customer.id)
        self.assertEqual(match.reason, "wechat")

    def test_same_name_different_identity_is_allowed(self):
        name = f"同名不拦截-{uuid4().hex[:8]}"
        self._customer(name, "13600136000", "wx-one")
        self.assertIsNone(find_duplicate_customer(self.db, "13500135000", "wx-two"))

    def test_duplicate_report_keeps_only_a_review_record(self):
        existing = self._customer(f"重复记录-{uuid4().hex[:8]}", "13400134000")
        report = DuplicateLeadReport(
            existing_customer_id=existing.id,
            reported_name="重复报备客户",
            reported_phone="13400134000",
            new_reported_by_id=self.other_reporter.id,
            duplicate_reason="phone",
            status="pending",
            submission_id=f"duplicate-{uuid4().hex}",
        )
        self.db.add(report)
        self.db.flush()
        self.assertEqual(self.db.scalar(select(Customer).where(Customer.phone == "13400134000")).id, existing.id)
        self.assertEqual(len(self.db.scalars(select(DuplicateLeadReport).where(DuplicateLeadReport.id == report.id)).all()), 1)
        self.assertEqual(report.status, "pending")


if __name__ == "__main__":
    unittest.main()
