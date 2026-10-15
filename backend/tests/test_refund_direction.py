import unittest
from datetime import datetime
from decimal import Decimal

from app.consumption import calculate_customer_consumption_summary, calculate_transaction_financials
from app.models import Customer, Order, OrderItem
from app.database import SessionLocal
from app.balance import resolve_is_refund


class RefundDirectionTest(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.transaction = self.db.begin()
        self.customer = Customer(name="收费退费测试客户", phone="13900000001")
        self.db.add(self.customer)
        self.db.flush()

    def tearDown(self):
        self.transaction.rollback()
        self.db.close()

    def order(self, order_no, amount, operation, *, raw_refund=False, visit_no="V-REFUND"):
        order = Order(
            order_no=order_no,
            external_order_id=order_no,
            external_transaction_id=order_no,
            customer_id=self.customer.id,
            paid_at=datetime(2026, 8, 31, 10, 0),
            visit_no=visit_no,
            item_name="治疗项目",
            category="治疗",
            amount=amount,
            total_amount=amount,
            paid_amount=amount,
            insurance_amount=Decimal("0"),
            self_pay_amount=amount,
            payment_type="self_pay",
            payment_type_raw="现金",
            transaction_kind="consumption",
            transaction_operation=operation,
            is_refund=resolve_is_refund(operation, amount),
            has_consumption_record=True,
            payment_split_status="verified",
            raw_json={"类型": operation, "实收": str(amount)},
        )
        if raw_refund:
            order.is_refund = True
        order.items = [OrderItem(item_name="治疗项目", quantity=1, unit="次", unit_price=abs(amount), amount=abs(amount))]
        self.db.add(order)
        self.db.flush()
        return order

    def test_charge_and_refund_net_to_zero_and_refund_is_not_a_new_visit(self):
        charge = self.order("REF-CHARGE", Decimal("233"), "收费")
        refund = self.order("REF-REFUND", Decimal("-233"), "退费")
        # ABC's refund row may retain item names while omitting line amounts;
        # the order-level refund amount must remain the value source.
        refund.items[0].unit_price = Decimal("0")
        refund.items[0].amount = Decimal("0")
        refund.paid_at = datetime(2026, 9, 1, 10, 0)
        summary = calculate_customer_consumption_summary([charge, refund])
        self.assertEqual(summary.total_consumption, Decimal("0"))
        self.assertEqual(summary.effective_revenue, Decimal("0"))
        self.assertEqual(summary.self_pay_amount, Decimal("0"))
        self.assertEqual(summary.insurance_amount, Decimal("0"))
        self.assertEqual(summary.consumption_count, 0)
        self.assertEqual(calculate_transaction_financials(refund).total_consumption, Decimal("-233"))

    def test_operation_has_priority_over_amount_sign_and_partial_refund_is_net(self):
        charge = self.order("PART-CHARGE", Decimal("1000"), "收费", visit_no="V-PART")
        refund = self.order("PART-REFUND", Decimal("200"), "退费", raw_refund=True, visit_no="V-PART")
        summary = calculate_customer_consumption_summary([charge, refund])
        self.assertEqual(summary.total_consumption, Decimal("800"))
        self.assertEqual(summary.effective_revenue, Decimal("800"))
        self.assertEqual(summary.self_pay_amount, Decimal("800"))
        self.assertEqual(summary.consumption_count, 1)
        self.assertFalse(resolve_is_refund("收费", Decimal("-233")))
        self.assertTrue(resolve_is_refund("退费", Decimal("233")))


if __name__ == "__main__":
    unittest.main()
