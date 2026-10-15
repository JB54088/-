import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from app.consumption import calculate_customer_consumption_summary, calculate_transaction_financials


def order_with_item(*, item_amount, paid, insurance, self_pay, deduction=Decimal("0")):
    item_amount = Decimal(str(item_amount))
    return SimpleNamespace(
        items=[SimpleNamespace(amount=item_amount, unit_price=item_amount, quantity=1)],
        total_amount=paid,
        paid_amount=paid,
        insurance_amount=insurance,
        self_pay_amount=self_pay,
        deduction_amount=deduction,
        has_consumption_record=True,
        discount_amount=Decimal("0"),
        visit_no="visit-1",
        external_transaction_id="order-1",
        transaction_fingerprint="fingerprint-1",
        customer_id=1,
        paid_at=datetime(2026, 8, 31, 10, 0),
    )


class ConsumptionFinancialsTest(unittest.TestCase):
    def test_regular_cash_or_wechat_uses_self_pay(self):
        result = calculate_transaction_financials(
            order_with_item(
                item_amount=300,
                paid=300,
                insurance=Decimal("0"),
                self_pay=Decimal("300"),
            )
        )
        self.assertEqual(result.total_consumption, Decimal("300"))
        self.assertEqual(result.self_pay_amount, Decimal("300"))
        self.assertEqual(result.effective_revenue, Decimal("300"))

    def test_pure_insurance_uses_insurance_amount(self):
        result = calculate_transaction_financials(
            order_with_item(
                item_amount=500,
                paid=500,
                insurance=Decimal("500"),
                self_pay=Decimal("0"),
            )
        )
        self.assertEqual(result.total_consumption, Decimal("500"))
        self.assertEqual(result.insurance_amount, Decimal("500"))
        self.assertEqual(result.self_pay_amount, Decimal("0"))
        self.assertEqual(result.effective_revenue, Decimal("500"))

    def test_mixed_payment_uses_verified_split(self):
        result = calculate_transaction_financials(
            order_with_item(
                item_amount=1000,
                paid=1000,
                insurance=Decimal("600"),
                self_pay=Decimal("400"),
            )
        )
        self.assertEqual(result.total_consumption, Decimal("1000"))
        self.assertEqual(result.effective_revenue, Decimal("1000"))
        self.assertEqual(result.self_pay_amount, Decimal("400"))

    def test_fully_deducted_project_counts_as_self_pay_once(self):
        result = calculate_transaction_financials(
            order_with_item(
                item_amount=258,
                paid=Decimal("0"),
                insurance=Decimal("0"),
                self_pay=Decimal("0"),
                deduction=Decimal("-258"),
            )
        )
        self.assertEqual(result.total_consumption, Decimal("258"))
        self.assertEqual(result.actual_paid_amount, Decimal("0"))
        self.assertEqual(result.deduction_amount, Decimal("-258"))
        self.assertEqual(result.self_pay_amount, Decimal("258"))
        self.assertEqual(result.effective_revenue, Decimal("258"))

    def test_balance_recharge_is_retained_but_excluded_from_business_metrics(self):
        order = order_with_item(
            item_amount=1000,
            paid=Decimal("1000"),
            insurance=Decimal("0"),
            self_pay=Decimal("1000"),
        )
        order.transaction_kind = "balance_transaction"
        result = calculate_transaction_financials(order)
        summary = calculate_customer_consumption_summary([order])

        self.assertEqual(result.total_consumption, Decimal("0"))
        self.assertEqual(result.effective_revenue, Decimal("0"))
        self.assertIsNone(result.insurance_amount)
        self.assertIsNone(result.self_pay_amount)
        self.assertEqual(result.actual_paid_amount, Decimal("1000"))
        self.assertEqual(summary.total_consumption, Decimal("0"))
        self.assertEqual(summary.effective_revenue, Decimal("0"))
        self.assertEqual(summary.insurance_amount, Decimal("0"))
        self.assertEqual(summary.self_pay_amount, Decimal("0"))
        self.assertEqual(summary.consumption_count, 0)


if __name__ == "__main__":
    unittest.main()
