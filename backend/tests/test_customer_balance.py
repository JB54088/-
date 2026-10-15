import unittest
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select

from app.balance import sync_order_balance
from app.consumption import calculate_customer_consumption_summary
from app.database import SessionLocal
from app.models import Customer, CustomerBalanceTransaction, IntegrationLog, Order


class CustomerBalanceTest(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.transaction = self.db.begin()

    def tearDown(self):
        self.transaction.rollback()
        self.db.close()

    def make_customer(self):
        customer = Customer(
            name=f"余额测试客户-{uuid4().hex[:8]}",
            phone=f"138{uuid4().hex[:8]}"[:11],
            lead_status="approved",
            status="active",
            pool_match_status="matched",
        )
        self.db.add(customer)
        self.db.flush()
        return customer

    def make_order(self, customer, order_no, when, *, kind="consumption", amount=Decimal("0"), operation=None, balance_payment=None):
        order = Order(
            order_no=order_no,
            external_order_id=order_no,
            external_transaction_id=order_no,
            transaction_fingerprint=uuid4().hex,
            customer_id=customer.id,
            paid_at=when,
            visit_no=order_no,
            item_name="会员充值" if kind == "balance_transaction" else "三伏灸",
            category="会员充值" if kind == "balance_transaction" else "治疗",
            amount=amount,
            total_amount=amount,
            paid_amount=amount,
            insurance_amount=Decimal("0"),
            self_pay_amount=Decimal("0") if kind == "balance_transaction" else amount,
            transaction_kind=kind,
            balance_operation=operation,
            balance_payment_amount=balance_payment,
            has_consumption_record=True,
            payment_split_status="verified",
            payment_type_raw="会员余额" if balance_payment else "ABC支付(微信)",
            raw_json={"test": order_no},
        )
        self.db.add(order)
        self.db.flush()
        return order

    def test_recharge_consume_refund_and_replay_are_idempotent(self):
        customer = self.make_customer()
        recharge = self.make_order(customer, "BAL-TEST-1", datetime(2026, 8, 1, 10), kind="balance_transaction", amount=Decimal("1000"), operation="recharge")
        consume = self.make_order(customer, "ORD-TEST-1", datetime(2026, 8, 2, 10), amount=Decimal("258"), balance_payment=Decimal("258"))
        refund = self.make_order(customer, "BAL-TEST-2", datetime(2026, 8, 3, 10), kind="balance_transaction", amount=Decimal("200"), operation="refund")

        self.assertEqual(sync_order_balance(self.db, recharge), "created")
        self.assertEqual(sync_order_balance(self.db, consume), "created")
        self.assertEqual(sync_order_balance(self.db, refund), "created")
        self.assertEqual(sync_order_balance(self.db, recharge), "updated")
        self.assertEqual(sync_order_balance(self.db, consume), "updated")
        self.assertEqual(sync_order_balance(self.db, refund), "updated")
        self.db.refresh(customer)

        self.assertEqual(customer.prepaid_balance, Decimal("542.00"))
        self.assertEqual(customer.total_recharge_amount, Decimal("1000.00"))
        self.assertEqual(customer.total_refund_amount, Decimal("200.00"))
        self.assertEqual(customer.total_prepaid_spent, Decimal("258.00"))
        self.assertEqual(self.db.scalar(select(func.count(CustomerBalanceTransaction.id)).where(CustomerBalanceTransaction.customer_id == customer.id)), 3)
        summary = calculate_customer_consumption_summary([recharge, consume, refund])
        self.assertEqual(summary.total_consumption, Decimal("258"))
        self.assertEqual(summary.self_pay_amount, Decimal("258"))
        self.assertEqual(summary.effective_revenue, Decimal("258"))
        self.assertEqual(summary.consumption_count, 1)

    def test_insufficient_balance_keeps_raw_order_without_negative_ledger(self):
        customer = self.make_customer()
        recharge = self.make_order(customer, "BAL-TEST-3", datetime(2026, 8, 1, 10), kind="balance_transaction", amount=Decimal("100"), operation="recharge")
        consume = self.make_order(customer, "ORD-TEST-2", datetime(2026, 8, 2, 10), amount=Decimal("200"), balance_payment=Decimal("200"))
        sync_order_balance(self.db, recharge)
        self.assertEqual(sync_order_balance(self.db, consume), "insufficient")
        self.db.refresh(customer)
        self.db.flush()
        self.assertEqual(customer.prepaid_balance, Decimal("100.00"))
        self.assertEqual(self.db.scalar(select(func.count(CustomerBalanceTransaction.id)).where(CustomerBalanceTransaction.customer_id == customer.id)), 1)
        self.assertIsNotNone(self.db.scalar(select(IntegrationLog.id).where(IntegrationLog.event_type == "balance_insufficient", IntegrationLog.external_id == "ORD-TEST-2")))


if __name__ == "__main__":
    unittest.main()
