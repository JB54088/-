"""Customer prepaid-balance bookkeeping.

The Excel order remains the source-of-truth audit record.  This module only
projects explicit recharge, refund, and prepaid-consumption facts into a
customer-scoped ledger and keeps the derived balance totals in sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Customer, CustomerBalanceTransaction, IntegrationLog, Order

ZERO = Decimal("0")
REFUND_WORDS = ("退费", "退款", "refund", "退卡")
RECHARGE_WORDS = ("收费", "充值", "recharge", "charge")
BALANCE_PAYMENT_WORDS = (
    "会员卡",
    "会员余额",
    "储值",
    "余额支付",
    "余额扣减",
    "储值卡",
    "prepaid",
    "balance",
)


@dataclass(frozen=True)
class BalanceEffect:
    transaction_type: str
    amount: Decimal


def _text(*values: Any) -> str:
    return " ".join(str(value or "").strip().lower() for value in values if value is not None)


def resolve_is_refund(transaction_operation: str | None, *amounts: Decimal | None) -> bool:
    """Resolve transaction direction with ABC's business type first.

    ``收费`` and ``退费`` are authoritative when present.  Amount sign is
    only the compatibility fallback for older exports that omitted the
    operation column.
    """
    text = _text(transaction_operation)
    if any(word in text for word in REFUND_WORDS):
        return True
    if any(word in text for word in RECHARGE_WORDS):
        return False
    return any(value is not None and value < ZERO for value in amounts)


def resolve_balance_operation(transaction_operation: str | None, transaction_kind: str, amount: Decimal) -> str | None:
    """Resolve the ABC charge/refund operation without changing raw values."""

    if transaction_kind != "balance_transaction":
        # ``类型=收费`` also appears on ordinary treatment/medicine rows; it
        # must never turn a normal consumption into a recharge.
        return None
    text = _text(transaction_operation)
    if any(word in text for word in REFUND_WORDS):
        return "refund"
    if any(word in text for word in RECHARGE_WORDS):
        return "recharge"
    if transaction_kind == "balance_transaction":
        # Real ABC exports normally provide 类型=收费/退费.  This sign fallback
        # keeps older rows usable when that column was omitted.
        return "refund" if amount < ZERO else "recharge"
    return None


def resolve_balance_payment_amount(
    payment_type_raw: str | None,
    payment_method: str | None,
    explicit_amount: Decimal | None,
    paid_amount: Decimal | None,
    total_amount: Decimal | None,
) -> Decimal | None:
    """Return only an explicitly identified prepaid amount.

    If ABC supplies a dedicated balance-payment amount, it wins.  Otherwise a
    clearly labelled balance payment may use the order's positive paid amount;
    ordinary cash, insurance, and WeChat rows never reach this path.
    """

    if explicit_amount is not None:
        return abs(explicit_amount)
    if not any(word in _text(payment_type_raw, payment_method) for word in BALANCE_PAYMENT_WORDS):
        return None
    candidate = paid_amount if paid_amount is not None else total_amount
    if candidate is None or candidate <= ZERO:
        return None
    return abs(candidate)


def _raw_source_amount(order: Order) -> Decimal:
    for value in (order.paid_amount, order.total_amount, order.receivable_amount, order.original_amount):
        if value is not None and value != ZERO:
            return value
    return sum((item.amount or ZERO for item in order.items), ZERO)


def _source_amount(order: Order) -> Decimal:
    return abs(_raw_source_amount(order))


def balance_effect_for_order(order: Order) -> BalanceEffect | None:
    if order.transaction_kind == "balance_transaction":
        operation = order.balance_operation or resolve_balance_operation(None, order.transaction_kind, _raw_source_amount(order))
        if not operation:
            return None
        amount = _source_amount(order)
        if amount == ZERO:
            return None
        return BalanceEffect(operation, amount if operation == "recharge" else -amount)
    if order.balance_payment_amount is not None and order.balance_payment_amount > ZERO:
        signed_payment = order.paid_amount if order.paid_amount is not None else order.total_amount
        if signed_payment is not None and signed_payment < ZERO:
            # ABC can export a negative member-card line when a previous
            # balance-paid service is reversed. Credit it back as an
            # adjustment instead of treating the reversal as another debit.
            return BalanceEffect("adjustment", abs(order.balance_payment_amount))
        return BalanceEffect("consume", -abs(order.balance_payment_amount))
    return None


def _ordered_ledger(db: Session, customer_id: int) -> list[CustomerBalanceTransaction]:
    return db.scalars(
        select(CustomerBalanceTransaction)
        .where(CustomerBalanceTransaction.customer_id == customer_id)
        .order_by(CustomerBalanceTransaction.charged_at, CustomerBalanceTransaction.id)
    ).all()


def _rebuild_customer_balance(db: Session, customer_id: int) -> None:
    ledger = _ordered_ledger(db, customer_id)
    running = ZERO
    recharge = ZERO
    refund = ZERO
    spent = ZERO
    for entry in ledger:
        entry.balance_before = running
        running += entry.amount
        entry.balance_after = running
        if entry.transaction_type == "recharge":
            recharge += entry.amount
        elif entry.transaction_type == "refund":
            refund += -entry.amount
        elif entry.transaction_type == "consume":
            spent += -entry.amount
    customer = db.get(Customer, customer_id)
    if not customer:
        return
    customer.prepaid_balance = running
    customer.total_recharge_amount = recharge
    customer.total_refund_amount = refund
    customer.total_prepaid_spent = spent
    db.flush()


def _would_go_negative(
    db: Session,
    order: Order,
    effect: BalanceEffect,
    existing: CustomerBalanceTransaction | None,
) -> bool:
    entries = [item for item in _ordered_ledger(db, order.customer_id) if not existing or item.id != existing.id]
    entries.append(
        CustomerBalanceTransaction(
            id=existing.id if existing else 0,
            customer_id=order.customer_id,
            transaction_type=effect.transaction_type,
            amount=effect.amount,
            balance_before=ZERO,
            balance_after=ZERO,
            source_transaction_id=order.id,
            charged_at=order.paid_at,
        )
    )
    entries.sort(key=lambda item: (item.charged_at, item.id or 0))
    running = ZERO
    for item in entries:
        running += item.amount
        if running < ZERO:
            return True
    return False


def _record_insufficient(db: Session, order: Order, effect: BalanceEffect) -> None:
    external_id = order.external_transaction_id or order.external_order_id or str(order.id)
    exists = db.scalar(
        select(IntegrationLog.id).where(
            IntegrationLog.source == "abc_excel",
            IntegrationLog.event_type == "balance_insufficient",
            IntegrationLog.external_id == external_id,
        )
    )
    if exists:
        return
    db.add(IntegrationLog(
        source="abc_excel",
        event_type="balance_insufficient",
        external_id=external_id,
        status="failed",
        raw_data=order.raw_json or {},
        error_message=f"储值余额不足：{effect.transaction_type} 需要 {abs(effect.amount):.2f}，当前余额不足",
        started_at=datetime.now().replace(microsecond=0),
        finished_at=datetime.now().replace(microsecond=0),
        failure_count=1,
    ))


def sync_order_balance(db: Session, order: Order) -> str:
    """Idempotently project one order into the customer balance ledger.

    An insufficient balance never aborts the raw order import.  The order stays
    available for reconciliation, while the ledger is left unchanged and a
    ``balance_insufficient`` log is written.
    """

    existing = db.scalar(
        select(CustomerBalanceTransaction).where(CustomerBalanceTransaction.source_transaction_id == order.id)
    )
    effect = balance_effect_for_order(order)
    if effect is None:
        if existing:
            db.delete(existing)
            db.flush()
            _rebuild_customer_balance(db, order.customer_id)
            return "removed"
        return "none"
    if _would_go_negative(db, order, effect, existing):
        _record_insufficient(db, order, effect)
        return "insufficient"
    created = existing is None
    if created:
        existing = CustomerBalanceTransaction(
            source_transaction_id=order.id,
            balance_before=ZERO,
            balance_after=ZERO,
        )
        db.add(existing)
    existing.customer_id = order.customer_id
    existing.external_customer_id = order.external_customer_id
    existing.transaction_type = effect.transaction_type
    existing.amount = effect.amount
    existing.charged_at = order.paid_at
    existing.raw_data = order.raw_json or {}
    db.flush()
    _rebuild_customer_balance(db, order.customer_id)
    return "created" if created else "updated"


def rebuild_customer_balance(db: Session, customer_id: int) -> None:
    """Public wrapper used after an external placeholder is merged."""

    _rebuild_customer_balance(db, customer_id)
