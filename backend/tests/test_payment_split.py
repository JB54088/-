"""Mock verification for data-pool payment split facts.

Run inside the backend container with:

    python -m unittest tests.test_payment_split -v
"""

import unittest
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select

from app.consumption import effective_revenue_expression, effective_self_pay_expression
from app.database import SessionLocal
from app.integrations.data_pool.schemas import DataPoolOrderPayload
from app.integrations.data_pool.service import resolve_payment_split, upsert_customer_from_pool, upsert_order_from_pool
from app.models import Customer, Order, User
from app.utils import consumption_order_condition, formal_customer_condition
from app.integrations.data_pool.schemas import DataPoolCustomerPayload
from app.routers.reports import bounds, build_report


class PaymentSplitTest(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.transaction = self.db.begin()
        self.salesperson = self.db.scalar(select(User).where(User.username == "sales01"))
        self.assertIsNotNone(self.salesperson)

    def tearDown(self):
        self.transaction.rollback()
        self.db.close()

    def _pool_customer(self, suffix: str) -> DataPoolCustomerPayload:
        payload = DataPoolCustomerPayload(
            external_customer_id=f"PAYMENT-CUS-{suffix}",
            name=f"支付拆分客户-{suffix}",
            phone=f"138{suffix[:8]}",
        )
        upsert_customer_from_pool(self.db, payload, payload.model_dump(mode="json"))
        return payload

    def test_explicit_amounts_accumulate_and_order_sync_is_idempotent(self):
        suffix = uuid4().hex[:10]
        customer_payload = self._pool_customer(suffix)
        first = DataPoolOrderPayload(
            external_order_id=f"PAYMENT-ORD-1-{suffix}",
            external_customer_id=customer_payload.external_customer_id,
            paid_at=datetime.now(),
            item_name="Mock 医保项目",
            total_amount=Decimal("1000"),
            insurance_amount=Decimal("700"),
            self_pay_amount=Decimal("300"),
        )
        second = DataPoolOrderPayload(
            external_order_id=f"PAYMENT-ORD-2-{suffix}",
            external_customer_id=customer_payload.external_customer_id,
            paid_at=datetime.now(),
            item_name="Mock 自费项目",
            total_amount=Decimal("500"),
            insurance_amount=Decimal("0"),
            self_pay_amount=Decimal("500"),
        )
        upsert_order_from_pool(self.db, first, first.model_dump(mode="json"))
        upsert_order_from_pool(self.db, second, second.model_dump(mode="json"))
        first.total_amount = Decimal("1100")
        first.amount = Decimal("1100")
        first.insurance_amount = Decimal("800")
        first.self_pay_amount = Decimal("300")
        upsert_order_from_pool(self.db, first, first.model_dump(mode="json"))

        orders = self.db.scalars(select(Order).where(Order.external_order_id.in_([first.external_order_id, second.external_order_id]))).all()
        self.assertEqual(len(orders), 2)
        self.assertEqual(sum((order.total_amount for order in orders), Decimal("0")), Decimal("1600.00"))
        self.assertEqual(sum((order.insurance_amount for order in orders), Decimal("0")), Decimal("800.00"))
        self.assertEqual(sum((order.self_pay_amount for order in orders), Decimal("0")), Decimal("800.00"))
        self.assertTrue(all(order.payment_split_status == "verified" for order in orders))

    def test_payment_type_without_split_amounts_uses_the_declared_type(self):
        insurance = DataPoolOrderPayload(
            external_order_id="PAYMENT-TYPE-INSURANCE",
            external_customer_id="PAYMENT-CUSTOMER",
            paid_at=datetime.now(),
            item_name="医保订单",
            amount=Decimal("250"),
            payment_type="insurance",
        )
        self_pay = DataPoolOrderPayload(
            external_order_id="PAYMENT-TYPE-SELF",
            external_customer_id="PAYMENT-CUSTOMER",
            paid_at=datetime.now(),
            item_name="自费订单",
            amount=Decimal("180"),
            payment_type="self_pay",
        )
        insurance_split = resolve_payment_split(insurance)
        self_pay_split = resolve_payment_split(self_pay)
        self.assertEqual((insurance_split.insurance_amount, insurance_split.self_pay_amount), (Decimal("250"), Decimal("0")))
        self.assertEqual((self_pay_split.insurance_amount, self_pay_split.self_pay_amount), (Decimal("0"), Decimal("180")))
        self.assertEqual(insurance_split.status, "verified")
        self.assertEqual(self_pay_split.status, "verified")

    def test_missing_split_is_unknown_and_mismatch_is_explicit(self):
        unknown = DataPoolOrderPayload(
            external_order_id="PAYMENT-UNKNOWN",
            external_customer_id="PAYMENT-CUSTOMER",
            paid_at=datetime.now(),
            item_name="历史订单",
            amount=Decimal("900"),
        )
        mismatch = DataPoolOrderPayload(
            external_order_id="PAYMENT-MISMATCH",
            external_customer_id="PAYMENT-CUSTOMER",
            paid_at=datetime.now(),
            item_name="异常订单",
            total_amount=Decimal("1000"),
            insurance_amount=Decimal("700"),
            self_pay_amount=Decimal("200"),
        )
        unknown_split = resolve_payment_split(unknown)
        mismatch_split = resolve_payment_split(mismatch)
        self.assertEqual(unknown_split.status, "unknown")
        self.assertIsNone(unknown_split.insurance_amount)
        self.assertIsNone(unknown_split.self_pay_amount)
        self.assertEqual(mismatch_split.status, "mismatch")
        self.assertIn("不等于", mismatch_split.mismatch_reason or "")

    def test_report_totals_use_the_same_split_facts_as_orders(self):
        suffix = uuid4().hex[:10]
        customer_payload = self._pool_customer(suffix)
        business_orders = [
            Order.customer_id.in_(select(Customer.id).where(formal_customer_condition())),
            consumption_order_condition(),
        ]
        baseline_total = Decimal(str(self.db.scalar(select(func.coalesce(func.sum(effective_revenue_expression()), 0)).where(*business_orders)) or 0))
        baseline_insurance = Decimal(str(self.db.scalar(select(func.coalesce(func.sum(Order.insurance_amount), 0)).where(*business_orders)) or 0))
        baseline_self_pay = Decimal(str(self.db.scalar(select(func.coalesce(func.sum(effective_self_pay_expression()), 0)).where(*business_orders)) or 0))
        for index, (total, insurance, self_pay) in enumerate(((Decimal("1000"), Decimal("700"), Decimal("300")), (Decimal("500"), Decimal("0"), Decimal("500")))):
            payload = DataPoolOrderPayload(
                external_order_id=f"REPORT-ORD-{suffix}-{index}",
                external_customer_id=customer_payload.external_customer_id,
                paid_at=datetime.now(),
                item_name=f"报告 Mock 项目 {index}",
                total_amount=total,
                insurance_amount=insurance,
                self_pay_amount=self_pay,
            )
            upsert_order_from_pool(self.db, payload, payload.model_dump(mode="json"))

        start, end, previous_start = bounds("month")
        metrics, _ = build_report(self.db, "month", start, end, previous_start)
        self.assertEqual(Decimal(str(metrics["total_revenue"])), baseline_total + Decimal("1500"))
        self.assertEqual(Decimal(str(metrics["total_insurance"])), baseline_insurance + Decimal("700"))
        self.assertEqual(Decimal(str(metrics["total_self_pay"])), baseline_self_pay + Decimal("800"))
        self.assertEqual(Decimal(str(metrics["month_insurance"])), Decimal("700"))
        self.assertEqual(Decimal(str(metrics["month_self_pay"])), Decimal("800"))


if __name__ == "__main__":
    unittest.main()
