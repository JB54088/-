"""Shared consumption-value calculations.

ABC exports can contain a real service/fee row whose actual payment is zero,
for example a fully deducted service.  The application therefore keeps two
separate measures:

* consumption value: the value of the imported items, used for customer value
  and average order value;
* actual paid: the amount actually received;
* effective revenue: the verified insurance + self-pay operating amount, with
  the current fully-deducted-project rule applied once.

All customer-value views should use the helpers in this module so a zero-paid
item is not turned into a zero-value customer.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from sqlalchemy import and_, case, func, or_, select

from .models import Order, OrderItem
from .utils import consumption_key, consumption_key_expression, consumption_order_condition

ZERO = Decimal("0")


def _signed_expression(value, order_model=Order):
    """Apply the persisted ABC direction to one numeric fact.

    Raw columns remain untouched for audit.  Reporting uses absolute charge
    facts, with refunds always contributing a negative value, regardless of
    whether ABC exported the refund amount as positive or negative.
    """
    magnitude = func.abs(func.coalesce(value, 0))
    return case((order_model.is_refund.is_(True), -magnitude), else_=magnitude)


def effective_insurance_expression(order_model=Order):
    """Return the net insurance portion of real consumption rows."""
    return case(
        (consumption_order_condition(order_model), _signed_expression(order_model.insurance_amount, order_model)),
        else_=0,
    )


def consumption_net_keys_subquery(*conditions):
    """Group charge/refund rows by visit/order and expose their net value."""
    key = consumption_key_expression()
    return (
        select(
            Order.customer_id.label("customer_id"),
            key.label("consumption_key"),
            func.coalesce(func.sum(consumption_value_expression()), 0).label("net_value"),
        )
        .where(*conditions)
        .group_by(Order.customer_id, key)
        .subquery()
    )


def consumption_count_by_customer_subquery(*conditions):
    """Count only visits/orders whose net consumption remains positive."""
    net_keys = consumption_net_keys_subquery(*conditions)
    return (
        select(
            net_keys.c.customer_id,
            func.count().label("order_count"),
        )
        .where(net_keys.c.net_value > 0)
        .group_by(net_keys.c.customer_id)
        .subquery()
    )


def consumption_count_query(*conditions):
    """Return a scalar query for positive-net consumption visits/orders."""
    net_keys = consumption_net_keys_subquery(*conditions)
    return select(func.count()).select_from(net_keys).where(net_keys.c.net_value > 0)


def consumption_value_expression(order_model=Order):
    """SQL expression for one order's consumption value.

    ``order_items.amount`` is authoritative whenever an order has imported
    item rows.  Orders created by older versions without item rows fall back
    to the legacy ``total_amount`` value.  Invalid/non-consumption rows are
    excluded by the independent ``has_consumption_record`` flag.
    """

    item_total = (
        select(func.sum(OrderItem.amount))
        .where(OrderItem.order_id == order_model.id)
        .correlate(order_model)
        .scalar_subquery()
    )
    # A payment/refund row can carry item names but no item amounts (the
    # amount is present only on the corresponding 流水 row).  Treat an empty
    # or zero-only item aggregate as missing when the order total is non-zero,
    # otherwise the refund would appear as a zero-value detail row.
    item_value = case(
        (and_(item_total.is_not(None), item_total != 0), item_total),
        else_=func.coalesce(order_model.total_amount, 0),
    )
    value = _signed_expression(item_value, order_model)
    return case((consumption_order_condition(order_model), value), else_=0)


def actual_paid_expression(order_model=Order):
    """SQL expression for actual received amount, kept separate from value."""

    paid = _signed_expression(func.coalesce(order_model.paid_amount, order_model.total_amount), order_model)
    return case((consumption_order_condition(order_model), paid), else_=0)


def _deduction_only_condition(order_model=Order):
    """SQL predicate for a fully deducted, non-insurance consumption row."""

    consumption_value = consumption_value_expression(order_model)
    actual_paid = actual_paid_expression(order_model)
    return and_(
        order_model.has_consumption_record.is_(True),
        or_(order_model.is_refund.is_(False), order_model.is_refund.is_(None)),
        consumption_value > 0,
        func.coalesce(order_model.insurance_amount, 0) == 0,
        actual_paid <= 0,
        func.coalesce(order_model.deduction_amount, 0) != 0,
    )


def effective_self_pay_expression(order_model=Order):
    """SQL expression for the business-defined self-pay amount.

    A fully deducted project is confirmed as self-pay by the current business
    rule.  The deduction itself is not added a second time; the project value
    is used exactly once.
    """

    consumption_value = consumption_value_expression(order_model)
    self_pay_source = case(
        (order_model.self_pay_amount.is_not(None), _signed_expression(order_model.self_pay_amount, order_model)),
        (order_model.balance_payment_amount.is_not(None), _signed_expression(order_model.balance_payment_amount, order_model)),
        else_=0,
    )
    resolved = case(
        (_deduction_only_condition(order_model), consumption_value),
        else_=self_pay_source,
    )
    return case((consumption_order_condition(order_model), resolved), else_=0)


def effective_revenue_expression(order_model=Order):
    """SQL expression for effective operating revenue.

    Normal rows use the verified insurance + self-pay split when available.
    A fully deducted row uses its project value as effective revenue even
    though its actual received amount is zero.
    """

    consumption_value = consumption_value_expression(order_model)
    actual_paid = actual_paid_expression(order_model)
    effective_self_pay = effective_self_pay_expression(order_model)
    has_self_pay = order_model.self_pay_amount.is_not(None) | order_model.balance_payment_amount.is_not(None)
    resolved = case(
        (_deduction_only_condition(order_model), consumption_value),
        (
            (order_model.insurance_amount.is_not(None) & has_self_pay),
            effective_insurance_expression(order_model) + effective_self_pay,
        ),
        else_=actual_paid,
    )
    return case((consumption_order_condition(order_model), resolved), else_=0)


def order_consumption_value(order: Order) -> Decimal:
    """Return one order's imported project value for Python-side summaries."""

    if not getattr(order, "has_consumption_record", True) or getattr(order, "transaction_kind", "consumption") == "balance_transaction":
        return ZERO

    items = list(order.items or [])
    if items:
        item_total = sum(
            (
                item.amount
                if item.amount is not None
                else (item.unit_price or ZERO) * (item.quantity or 0)
            )
            for item in items
        )
        # Imported detail rows may contain names only and be stored as zero
        # placeholders.  In that case the order-level ABC amount is the only
        # available project value and must be used for both charge and refund.
        if item_total != ZERO or (order.total_amount or ZERO) == ZERO:
            return _signed_value(item_total, bool(getattr(order, "is_refund", False)))
    return _signed_value(order.total_amount, bool(getattr(order, "is_refund", False)))


def _signed_value(value: Decimal | None, is_refund: bool) -> Decimal:
    if value is None:
        return ZERO
    magnitude = abs(value)
    return -magnitude if is_refund else magnitude


@dataclass(frozen=True)
class TransactionFinancials:
    total_consumption: Decimal
    insurance_amount: Decimal | None
    self_pay_amount: Decimal | None
    effective_revenue: Decimal
    actual_paid_amount: Decimal
    deduction_amount: Decimal


def calculate_transaction_financials(order: Order) -> TransactionFinancials:
    """Calculate one order's unified consumption and revenue measures."""

    is_refund = bool(getattr(order, "is_refund", False))
    actual_paid_amount = _signed_value(
        order.paid_amount if order.paid_amount is not None else order.total_amount,
        is_refund,
    )
    deduction_amount = order.deduction_amount or ZERO
    if getattr(order, "transaction_kind", "consumption") == "balance_transaction":
        return TransactionFinancials(
            total_consumption=ZERO,
            insurance_amount=None,
            self_pay_amount=None,
            effective_revenue=ZERO,
            actual_paid_amount=actual_paid_amount,
            deduction_amount=deduction_amount,
        )

    total_consumption = order_consumption_value(order)
    insurance_amount = _signed_value(order.insurance_amount, is_refund) if order.insurance_amount is not None else None
    raw_self_pay_amount = _signed_value(order.self_pay_amount, is_refund) if order.self_pay_amount is not None else None
    if raw_self_pay_amount is None and order.balance_payment_amount is not None:
        raw_self_pay_amount = _signed_value(order.balance_payment_amount, is_refund)
    deduction_only = (
        not is_refund
        and total_consumption > ZERO
        and (insurance_amount or ZERO) == ZERO
        and actual_paid_amount <= ZERO
        and deduction_amount != ZERO
    )
    self_pay_amount = total_consumption if deduction_only else raw_self_pay_amount
    if deduction_only:
        effective_revenue = total_consumption
    elif insurance_amount is not None and self_pay_amount is not None:
        effective_revenue = insurance_amount + self_pay_amount
    else:
        effective_revenue = actual_paid_amount
    return TransactionFinancials(
        total_consumption=total_consumption,
        insurance_amount=insurance_amount,
        self_pay_amount=self_pay_amount,
        effective_revenue=effective_revenue,
        actual_paid_amount=actual_paid_amount,
        deduction_amount=deduction_amount,
    )


@dataclass(frozen=True)
class ConsumptionSummary:
    total_consumption: Decimal
    actual_paid_amount: Decimal
    effective_revenue: Decimal
    insurance_amount: Decimal | None
    self_pay_amount: Decimal | None
    deduction_amount: Decimal
    discount_amount: Decimal
    consumption_count: int
    average_order_value: Decimal
    last_consumption_at: object | None


def calculate_customer_consumption_summary(orders: Iterable[Order]) -> ConsumptionSummary:
    """Calculate one customer summary from imported order/detail rows.

    Payment rows belonging to the same visit are retained for detail, while
    ``consumption_count`` uses the existing stable visit/order key so one
    visit is counted once.  Item values are summed across the rows of that
    visit; this supports split payments whose item rows are distributed over
    multiple payment records.
    """

    valid_orders = [
        order
        for order in orders
        if getattr(order, "has_consumption_record", True)
        and getattr(order, "transaction_kind", "consumption") != "balance_transaction"
    ]
    financials = [calculate_transaction_financials(order) for order in valid_orders]
    total_consumption = sum((item.total_consumption for item in financials), ZERO)
    actual_paid_amount = sum((item.actual_paid_amount for item in financials), ZERO)
    effective_revenue = sum((item.effective_revenue for item in financials), ZERO)
    split_complete = all(
        order.insurance_amount is not None
        and (order.self_pay_amount is not None or order.balance_payment_amount is not None)
        for order in valid_orders
    )
    insurance_amount = (
        sum(((item.insurance_amount or ZERO) for item in financials), ZERO)
        if split_complete
        else None
    )
    self_pay_amount = (
        sum(((item.self_pay_amount or ZERO) for item in financials), ZERO)
        if split_complete
        else None
    )
    deduction_amount = sum(((order.deduction_amount or ZERO) for order in valid_orders), ZERO)
    discount_amount = sum(((order.discount_amount or ZERO) for order in valid_orders), ZERO)
    net_by_key: dict[str, Decimal] = {}
    latest_charge_at: dict[str, object] = {}
    for order, financial in zip(valid_orders, financials):
        key = consumption_key(order)
        net_by_key[key] = net_by_key.get(key, ZERO) + financial.total_consumption
        if not getattr(order, "is_refund", False):
            current = latest_charge_at.get(key)
            if current is None or order.paid_at > current:
                latest_charge_at[key] = order.paid_at
    consumption_count = sum(1 for value in net_by_key.values() if value > ZERO)
    average_order_value = (
        total_consumption / consumption_count if consumption_count else ZERO
    )
    last_consumption_at = max(latest_charge_at.values(), default=None)
    return ConsumptionSummary(
        total_consumption=total_consumption,
        actual_paid_amount=actual_paid_amount,
        effective_revenue=effective_revenue,
        insurance_amount=insurance_amount,
        self_pay_amount=self_pay_amount,
        deduction_amount=deduction_amount,
        discount_amount=discount_amount,
        consumption_count=consumption_count,
        average_order_value=average_order_value,
        last_consumption_at=last_consumption_at,
    )
