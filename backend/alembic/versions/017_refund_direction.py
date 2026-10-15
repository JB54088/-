"""Persist ABC charge/refund direction for net business metrics."""

from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa


revision = "017_refund_direction"
down_revision = "016_balance_repair"
branch_labels = None
depends_on = None


REFUND_WORDS = ("退费", "退款", "refund", "退卡")
CHARGE_WORDS = ("收费", "充值", "charge", "recharge")
OPERATION_KEYS = ("业务类型", "交易类型", "收费类型", "类型", "operation", "transaction_operation", "flow_type")
AMOUNT_KEYS = ("实收", "实收金额", "paid_amount", "总金额", "消费总额", "total_amount", "收费金额", "原价", "原价金额", "应收", "应收金额")


def _text(value) -> str:
    return str(value or "").strip().lower()


def _find_operation(value):
    if isinstance(value, dict):
        for key in OPERATION_KEYS:
            if key in value and value[key] not in (None, ""):
                return str(value[key]).strip()
        for nested in value.values():
            found = _find_operation(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_operation(nested)
            if found:
                return found
    return None


def _find_amounts(value, result: list[sa.Numeric]):
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in AMOUNT_KEYS:
                try:
                    result.append(float(nested))
                except (TypeError, ValueError):
                    pass
            elif isinstance(nested, (dict, list)):
                _find_amounts(nested, result)
    elif isinstance(value, list):
        for nested in value:
            _find_amounts(nested, result)


def _is_refund(operation: str | None, raw_data, paid_amount, total_amount) -> bool:
    text = _text(operation)
    if any(word in text for word in REFUND_WORDS):
        return True
    if any(word in text for word in CHARGE_WORDS):
        return False
    amounts: list[float] = []
    for value in (paid_amount, total_amount):
        if value is not None:
            try:
                amounts.append(float(value))
            except (TypeError, ValueError):
                pass
    _find_amounts(raw_data, amounts)
    return any(value < 0 for value in amounts)


def upgrade() -> None:
    op.add_column("orders", sa.Column("transaction_operation", sa.String(length=30), nullable=True))
    op.add_column("orders", sa.Column("is_refund", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_orders_transaction_operation", "orders", ["transaction_operation"], unique=False)
    op.create_index("ix_orders_is_refund", "orders", ["is_refund"], unique=False)

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, raw_json, paid_amount, total_amount FROM orders")).mappings().all()
    for row in rows:
        operation = _find_operation(row["raw_json"] or {})
        bind.execute(
            sa.text("UPDATE orders SET transaction_operation = :operation, is_refund = :is_refund WHERE id = :id"),
            {
                "id": row["id"],
                "operation": operation[:30] if operation else None,
                "is_refund": _is_refund(operation, row["raw_json"] or {}, row["paid_amount"], row["total_amount"]),
            },
        )
    op.alter_column("orders", "is_refund", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_orders_is_refund", table_name="orders")
    op.drop_index("ix_orders_transaction_operation", table_name="orders")
    op.drop_column("orders", "is_refund")
    op.drop_column("orders", "transaction_operation")
