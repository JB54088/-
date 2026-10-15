from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, and_, case, func, not_, or_, select

from .models import Customer, Order, User

ADMIN_ROLE = "admin"
SALESPERSON_ROLE = "salesperson"
VALID_ROLES = {ADMIN_ROLE, SALESPERSON_ROLE}
FULL_ACCESS_ROLES = {ADMIN_ROLE}


def normalize_phone(value: str | None) -> str | None:
    """Return a stable digits-only phone identifier for duplicate checks.

    The application accepts common user-entered formats such as ``+86 138...``
    and ``0086-138...`` but stores and compares the mainland number itself.
    This is intentionally normalization, not fuzzy name matching.
    """
    if not value:
        return None
    digits = "".join(character for character in value.strip() if character.isdigit())
    if digits.startswith("0086") and len(digits) == 15:
        digits = digits[4:]
    elif digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    return digits or None


def is_admin(user: User) -> bool:
    return user.role == ADMIN_ROLE


def customer_scope_condition(user: User):
    """All customer reads for salespeople are constrained by current assignment."""
    return True if is_admin(user) else Customer.assigned_to_id == user.id


def is_external_placeholder(customer: Customer) -> bool:
    """Whether a row only represents ABC data waiting for a formal lead.

    These rows retain imported orders, but must stay out of the formal
    customer/lead business views until a salesperson reports the customer.
    """
    return (
        not customer.is_deleted
        and customer.reported_by_id is None
        and customer.lead_status == "unassigned"
        and customer.pool_match_status == "pending"
    )


def formal_customer_condition():
    """SQL predicate excluding ABC-only placeholder rows from business views."""
    return and_(
        Customer.is_deleted.is_(False),
        Customer.lead_status.not_in(["pending", "rejected"]),
        not_(and_(
            Customer.reported_by_id.is_(None),
            Customer.lead_status == "unassigned",
            Customer.pool_match_status == "pending",
        )),
    )


def order_scope_condition(user: User):
    """Orders follow the customer's current assignment, never a client-supplied owner id."""
    if is_admin(user):
        return True
    return Order.customer_id.in_(select(Customer.id).where(Customer.assigned_to_id == user.id, Customer.is_deleted.is_(False)))


def consumption_order_condition(order_model=Order):
    """Return the database predicate for business-consumption rows.

    ``transaction_kind`` is nullable only for compatibility with databases
    created before the classification migration; such rows remain normal
    consumption by default. Balance recharge/refund rows stay in ``orders``
    but must not affect consumption, revenue, payment, or visit metrics.
    """
    return and_(
        order_model.has_consumption_record.is_(True),
        or_(order_model.transaction_kind.is_(None), order_model.transaction_kind != "balance_transaction"),
    )


def is_consumption_order(order: Order) -> bool:
    """Python equivalent used when serializing already-loaded orders."""
    return bool(getattr(order, "has_consumption_record", True)) and getattr(order, "transaction_kind", "consumption") != "balance_transaction"


def consumption_key_expression():
    """Return a SQL key for one real consumption/visit.

    ABC may export one visit as several payment rows.  Keep every Order row
    for audit/detail display, but count a shared visit or external transaction
    only once.  The date is included with visit_no so a reused visit number on
    a different day does not collapse into the previous visit.
    """
    # ABC's visit number is the stable business association for split
    # charges/refunds. Do not append the payment date: a refund may be
    # exported on a later date and must still offset the original visit.
    visit_key = func.concat("visit:", Order.visit_no)
    key = case(
        (Order.visit_no.is_not(None), visit_key),
        (Order.external_transaction_id.is_not(None), func.concat("order:", Order.external_transaction_id)),
        else_=func.concat("fingerprint:", Order.transaction_fingerprint),
    )
    return case((consumption_order_condition(), key), else_=None)


def consumption_key(order: Order) -> str:
    """Python equivalent of :func:`consumption_key_expression` for detail views."""
    if order.visit_no:
        return f"visit:{order.visit_no}"
    if order.external_transaction_id:
        return f"order:{order.external_transaction_id}"
    return f"fingerprint:{order.transaction_fingerprint}"


def apply_scope(query: Select, user: User, model_customer_column=None, model_department_column=None, model_owner_column=None):
    """Compatibility helper for older callers; the new rule is assignment-based."""
    if model_customer_column is not None and not is_admin(user):
        return query.where(model_customer_column == user.id)
    if model_owner_column is not None and not is_admin(user):
        return query.where(model_owner_column == user.id)
    return query


def period_bounds(period: str, start: datetime | None = None, end: datetime | None = None) -> tuple[datetime, datetime]:
    now = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0), now
    if period == "week":
        start_day = now - timedelta(days=now.weekday())
        return start_day.replace(hour=0, minute=0, second=0, microsecond=0), now
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now
    if start and end:
        return start, end.replace(hour=23, minute=59, second=59, microsecond=999999)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now


def money(value: Decimal | None) -> float:
    return round(float(value or 0), 2)


def scoped_conditions(user: User, customer: bool = False) -> list:
    condition = customer_scope_condition(user) if customer else order_scope_condition(user)
    return [] if condition is True else [condition]
