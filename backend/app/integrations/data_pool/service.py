from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from ...models import (
    Customer,
    CustomerPoolMatchCandidate,
    CustomerPoolMatchHistory,
    Order,
    OrderItem,
    Store,
)
from ...utils import normalize_phone
from .schemas import DataPoolCustomerPayload, DataPoolOrderPayload


POOL_MATCH_PENDING = "pending"
POOL_MATCHED = "matched"
POOL_MATCH_CONFLICT = "conflict"
POOL_MATCH_MANUAL_REQUIRED = "manual_required"


@dataclass
class UpsertResult:
    action: str
    record_id: int
    match_status: str | None = None
    match_type: str | None = None
    candidate_count: int = 0
    payment_split_status: str | None = None
    payment_amount_mismatch: bool = False
    payment_amount_error: str | None = None


@dataclass(frozen=True)
class PaymentSplit:
    total_amount: Decimal
    insurance_amount: Decimal | None
    self_pay_amount: Decimal | None
    payment_type: str | None
    status: str
    mismatch_reason: str | None = None


def _phone_matches(db: Session, phone: str | None) -> list[Customer]:
    normalized = normalize_phone(phone)
    if not normalized:
        return []
    # Phone values are not assumed to be formatted consistently in old data;
    # compare normalized digits in Python while keeping the original value.
    customers = db.scalars(select(Customer).where(Customer.is_deleted.is_(False)).order_by(Customer.id)).all()
    return [customer for customer in customers if normalize_phone(customer.phone) == normalized]


def _normalize_payment_type(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace(" ", "").replace("-", "_")
    if normalized in {"insurance", "medical", "医保", "医保支付", "医保结算", "insurance_payment"}:
        return "insurance"
    if normalized in {"self_pay", "selfpay", "out_of_pocket", "自费", "自费支付", "自付", "self_payment"}:
        return "self_pay"
    return None


def _item_amount(item: dict, fallback: Decimal) -> Decimal:
    quantity = max(int(item.get("quantity", 1)), 1)
    raw_amount = item.get("amount", item.get("total_amount"))
    if raw_amount is not None:
        return Decimal(str(raw_amount))
    raw_unit_price = item.get("unit_price")
    return Decimal(str(raw_unit_price)) * quantity if raw_unit_price is not None else fallback


def resolve_payment_split(payload: DataPoolOrderPayload) -> PaymentSplit:
    """Resolve a payment split only from facts present in the pool payload.

    Explicit insurance/self-pay fields have priority. Otherwise an order-level
    or item-level payment type is used. If the source exposes only a total, the
    components remain NULL and the caller records a data-quality warning.
    """
    # ``amount`` is kept as a compatibility input for older pool clients. If
    # the caller supplied only that legacy field, use its current value even
    # when a previous validation pass populated ``total_amount`` for the
    # normalized view. An explicitly supplied canonical total always wins.
    if "total_amount" in payload.model_fields_set:
        total = payload.total_amount
        # Pydantic fills the compatibility field during validation. If an
        # older caller later changes only ``amount`` before an upsert, honor
        # that legacy update as well. A source payload that sends both fields
        # with different values is ambiguous and is handled as a mismatch by
        # the same fact-preserving path below.
        if payload.amount is not None and payload.amount != payload.total_amount and payload.insurance_amount is None and payload.self_pay_amount is None:
            total = payload.amount
    elif "amount" in payload.model_fields_set:
        total = payload.amount
    else:
        total = payload.total_amount if payload.total_amount is not None else payload.amount
    if total is None:
        raise ValueError("消费记录缺少总金额")

    insurance = payload.insurance_amount
    self_pay = payload.self_pay_amount
    payment_type = _normalize_payment_type(payload.payment_type)
    mismatch_reason = None

    typed_items = []
    unknown_typed_items = False
    for item in payload.items:
        raw_type = item.get("payment_type", item.get("pay_type", item.get("支付类型")))
        if raw_type is None:
            continue
        item_type = _normalize_payment_type(raw_type)
        if item_type is None:
            unknown_typed_items = True
        else:
            typed_items.append((item_type, _item_amount(item, total)))

    if insurance is None and self_pay is None and typed_items:
        insurance = sum((amount for kind, amount in typed_items if kind == "insurance"), Decimal("0"))
        self_pay = sum((amount for kind, amount in typed_items if kind == "self_pay"), Decimal("0"))
        payment_type = "mixed" if insurance and self_pay else ("insurance" if insurance else "self_pay")
        if unknown_typed_items:
            mismatch_reason = "存在无法识别的明细支付类型，无法完整校验拆分"
    elif insurance is None and self_pay is None and payment_type:
        if payment_type == "insurance":
            insurance, self_pay = total, Decimal("0")
        elif payment_type == "self_pay":
            insurance, self_pay = Decimal("0"), total
    elif insurance is not None or self_pay is not None:
        # A missing component can be derived arithmetically from an explicit
        # total and the provided component; this is not a ratio estimate.
        if insurance is None and self_pay is not None and total >= self_pay:
            insurance = total - self_pay
        elif insurance is None and self_pay is not None:
            mismatch_reason = f"自费金额 {self_pay} 大于总金额 {total}"
        elif self_pay is None and insurance is not None and total >= insurance:
            self_pay = total - insurance
        elif self_pay is None and insurance is not None:
            mismatch_reason = f"医保金额 {insurance} 大于总金额 {total}"

    if insurance is None or self_pay is None:
        return PaymentSplit(total, insurance, self_pay, payment_type, "mismatch" if mismatch_reason else "unknown", mismatch_reason or "数据池未提供完整的医保/自费拆分")
    if total != insurance + self_pay:
        mismatch_reason = mismatch_reason or f"总金额 {total} 不等于医保 {insurance} + 自费 {self_pay}"
        return PaymentSplit(total, insurance, self_pay, payment_type, "mismatch", mismatch_reason)
    return PaymentSplit(total, insurance, self_pay, payment_type, "verified")


def _name_matches(db: Session, name: str) -> list[Customer]:
    return db.scalars(
        select(Customer)
        .where(Customer.name == name, Customer.external_customer_id.is_(None), Customer.is_deleted.is_(False))
        .order_by(Customer.id)
    ).all()


def _record_match_history(
    db: Session,
    customer: Customer,
    *,
    external_customer_id: str | None,
    match_type: str,
    previous_status: str | None,
    new_status: str,
    matched_by_id: int | None = None,
    note: str | None = None,
) -> None:
    db.add(
        CustomerPoolMatchHistory(
            customer_id=customer.id,
            external_customer_id=external_customer_id,
            match_type=match_type,
            previous_status=previous_status,
            new_status=new_status,
            matched_by_id=matched_by_id,
            matched_at=datetime.now(),
            note=note,
        )
    )


def _set_match_status(
    db: Session,
    customer: Customer,
    status: str,
    *,
    external_customer_id: str | None = None,
    match_type: str = "auto",
    matched_by_id: int | None = None,
    note: str | None = None,
) -> bool:
    previous_status = customer.pool_match_status
    if previous_status == status:
        return False
    customer.pool_match_status = status
    _record_match_history(
        db,
        customer,
        external_customer_id=external_customer_id or customer.external_customer_id,
        match_type=match_type,
        previous_status=previous_status,
        new_status=status,
        matched_by_id=matched_by_id,
        note=note,
    )
    return True


def _upsert_candidate(db: Session, customer: Customer, payload: DataPoolCustomerPayload, raw_data: dict, now: datetime) -> CustomerPoolMatchCandidate:
    if not payload.external_customer_id:
        raise ValueError("数据池客户缺少 external_customer_id，无法建立人工匹配候选")
    candidate = db.scalar(
        select(CustomerPoolMatchCandidate).where(
            CustomerPoolMatchCandidate.customer_id == customer.id,
            CustomerPoolMatchCandidate.external_customer_id == payload.external_customer_id,
        )
    )
    if candidate is None:
        candidate = CustomerPoolMatchCandidate(
            customer_id=customer.id,
            external_customer_id=payload.external_customer_id,
            name=payload.name,
            phone=payload.phone,
            raw_data=raw_data,
            is_active=True,
            last_seen_at=now,
        )
        db.add(candidate)
    else:
        candidate.name = payload.name
        candidate.phone = payload.phone
        candidate.raw_data = raw_data
        candidate.is_active = True
        candidate.last_seen_at = now
        candidate.resolved_at = None
        candidate.resolved_by_id = None
        candidate.resolution_note = None
    db.flush()
    return candidate


def _deactivate_candidates(db: Session, customer_id: int, matched_by_id: int | None = None, note: str | None = None) -> None:
    db.execute(
        update(CustomerPoolMatchCandidate)
        .where(CustomerPoolMatchCandidate.customer_id == customer_id, CustomerPoolMatchCandidate.is_active.is_(True))
        .values(
            is_active=False,
            resolved_at=datetime.now(),
            resolved_by_id=matched_by_id,
            resolution_note=note,
        )
    )


def _apply_external_customer(
    db: Session,
    customer: Customer,
    payload: DataPoolCustomerPayload,
    raw_data: dict,
    *,
    match_type: str,
    matched_by_id: int | None = None,
    note: str | None = None,
) -> UpsertResult:
    if customer.is_deleted:
        raise ValueError("作废客户不能重新绑定外部客户")
    now = datetime.now()
    external_id = payload.external_customer_id
    if not external_id:
        raise ValueError("数据池客户缺少 external_customer_id，不能完成稳定绑定")
    if customer.external_customer_id and customer.external_customer_id != external_id:
        raise ValueError("内部客户已经绑定其他 external_customer_id，拒绝覆盖映射")

    previous_status = customer.pool_match_status
    previous_external_id = customer.external_customer_id
    customer.external_customer_id = external_id
    customer.name = payload.name
    if payload.phone is not None:
        customer.phone = payload.phone
    for field in ("wechat_id", "gender", "age", "source"):
        value = getattr(payload, field)
        if value is not None:
            setattr(customer, field, value)
    if payload.wechat_status is not None:
        customer.wechat_status = payload.wechat_status
    if "total_spend" in payload.model_fields_set:
        customer.external_total_spend = payload.total_spend or Decimal("0")
    if "order_count" in payload.model_fields_set:
        customer.external_order_count = payload.order_count or 0
    if "last_spend_at" in payload.model_fields_set:
        customer.external_last_spend_at = payload.last_spend_at
    customer.external_synced_at = now
    customer.external_raw_data = raw_data
    if payload.last_spend_at:
        customer.last_visit_at = max(customer.last_visit_at or payload.last_spend_at, payload.last_spend_at)

    customer.pool_match_status = POOL_MATCHED
    if previous_status != POOL_MATCHED or previous_external_id != external_id:
        _record_match_history(
            db,
            customer,
            external_customer_id=external_id,
            match_type=match_type,
            previous_status=previous_status,
            new_status=POOL_MATCHED,
            matched_by_id=matched_by_id,
            note=note,
        )
    _deactivate_candidates(db, customer.id, matched_by_id, note)
    db.flush()
    return UpsertResult("updated", customer.id, POOL_MATCHED, match_type)


def _mark_candidates_for_review(
    db: Session,
    candidates: list[Customer],
    payload: DataPoolCustomerPayload,
    raw_data: dict,
    *,
    status: str,
    now: datetime,
) -> UpsertResult:
    candidate_count = 0
    first_customer: Customer | None = None
    for customer in candidates:
        if customer.external_customer_id:
            continue
        first_customer = first_customer or customer
        _upsert_candidate(db, customer, payload, raw_data, now)
        _set_match_status(db, customer, status, external_customer_id=payload.external_customer_id)
        candidate_count += 1
    if first_customer is None:
        raise ValueError("数据池客户的匹配条件与已绑定客户冲突，无法自动覆盖")
    db.flush()
    return UpsertResult("updated", first_customer.id, status, "auto", candidate_count)


def upsert_customer_from_pool(db: Session, payload: DataPoolCustomerPayload, raw_data: dict) -> UpsertResult:
    """Match a pool customer without changing internal ownership or tags.

    Matching order is external_customer_id, then unique phone. Name is only
    used to create an admin-review candidate and is never used for auto binding.
    """
    now = datetime.now()
    if payload.external_customer_id:
        existing = db.scalar(select(Customer).where(Customer.external_customer_id == payload.external_customer_id, Customer.is_deleted.is_(False)))
        if existing:
            return _apply_external_customer(db, existing, payload, raw_data, match_type="auto")

    phone_matches = _phone_matches(db, payload.phone)
    unbound_phone_matches = [customer for customer in phone_matches if not customer.external_customer_id]
    if len(phone_matches) == 1 and len(unbound_phone_matches) == 1:
        return _apply_external_customer(db, unbound_phone_matches[0], payload, raw_data, match_type="auto")
    if phone_matches:
        status = POOL_MATCH_CONFLICT if len(phone_matches) > 1 else POOL_MATCH_MANUAL_REQUIRED
        return _mark_candidates_for_review(db, phone_matches, payload, raw_data, status=status, now=now)

    # A same-name row may be shown to an administrator as a candidate, but it
    # never becomes an automatic match. This also makes missing-phone cases
    # actionable without trusting a non-unique name.
    name_matches = _name_matches(db, payload.name)
    if name_matches:
        status = POOL_MATCH_CONFLICT if len(name_matches) > 1 else POOL_MATCH_MANUAL_REQUIRED
        return _mark_candidates_for_review(db, name_matches, payload, raw_data, status=status, now=now)

    if not payload.external_customer_id:
        raise ValueError("数据池客户缺少 external_customer_id，且手机号无法唯一匹配；暂不创建客户")

    # A genuinely new pool customer is allowed into the internal customer
    # table, but remains unassigned and has no admin-selected source category.
    customer = Customer(
        external_customer_id=payload.external_customer_id,
        name=payload.name,
        phone=payload.phone,
        wechat_id=payload.wechat_id,
        gender=payload.gender,
        age=payload.age,
        source=payload.source,
        source_category=None,
        wechat_status=payload.wechat_status or "unbound",
        external_total_spend=payload.total_spend or Decimal("0"),
        external_order_count=payload.order_count or 0,
        external_last_spend_at=payload.last_spend_at,
        external_synced_at=now,
        external_raw_data=raw_data,
        pool_match_status=POOL_MATCHED,
        lead_status="unassigned",
        status="active",
    )
    db.add(customer)
    db.flush()
    _record_match_history(
        db,
        customer,
        external_customer_id=payload.external_customer_id,
        match_type="auto",
        previous_status=POOL_MATCH_PENDING,
        new_status=POOL_MATCHED,
        note="数据池新客户入库，未匹配到既有内部客户",
    )
    return UpsertResult("created", customer.id, POOL_MATCHED, "auto")


def manually_match_customer(db: Session, customer: Customer, candidate: CustomerPoolMatchCandidate, matched_by_id: int, note: str | None = None) -> UpsertResult:
    if candidate.customer_id != customer.id:
        raise ValueError("匹配候选不属于当前客户")
    if not candidate.is_active:
        raise ValueError("该匹配候选已处理，请刷新后重试")
    existing = db.scalar(
        select(Customer).where(
            Customer.external_customer_id == candidate.external_customer_id,
            Customer.id != customer.id,
            Customer.is_deleted.is_(False),
        )
    )
    if existing:
        raise ValueError("该数据池客户已经绑定到其他内部客户，不能重复绑定")
    raw_data = dict(candidate.raw_data or {})
    raw_data.setdefault("external_customer_id", candidate.external_customer_id)
    raw_data.setdefault("name", candidate.name)
    if candidate.phone is not None:
        raw_data.setdefault("phone", candidate.phone)
    payload = DataPoolCustomerPayload.model_validate(raw_data)
    return _apply_external_customer(db, customer, payload, raw_data, match_type="manual", matched_by_id=matched_by_id, note=note or "管理员人工匹配")


def _find_order(db: Session, payload: DataPoolOrderPayload, order_no: str) -> Order | None:
    order = db.scalar(select(Order).options(selectinload(Order.items)).where(Order.external_order_id == payload.external_order_id))
    if order:
        return order
    order = db.scalar(select(Order).options(selectinload(Order.items)).where(Order.order_no == order_no))
    if order and order.external_order_id not in (None, payload.external_order_id):
        raise ValueError(f"订单号 {order_no} 已映射到其他外部订单")
    return order


def upsert_order_from_pool(db: Session, payload: DataPoolOrderPayload, raw_data: dict) -> UpsertResult:
    customer = db.scalar(select(Customer).where(Customer.external_customer_id == payload.external_customer_id, Customer.is_deleted.is_(False)))
    if not customer:
        raise ValueError(f"找不到外部客户 {payload.external_customer_id}，请先同步客户或完成人工匹配")
    payment_split = resolve_payment_split(payload)
    order_no = payload.order_no or f"DP-{payload.external_order_id}"
    order = _find_order(db, payload, order_no)
    store = None
    if payload.store_name:
        store = db.scalar(select(Store).where(Store.name == payload.store_name))
        if not store:
            store = Store(name=payload.store_name)
            db.add(store)
            db.flush()
    if order is None:
        order = Order(
            order_no=order_no,
            external_order_id=payload.external_order_id,
            customer_id=customer.id,
            paid_at=payload.paid_at,
            item_name=payload.item_name,
            category=payload.category,
            amount=payment_split.total_amount,
            total_amount=payment_split.total_amount,
            insurance_amount=payment_split.insurance_amount,
            self_pay_amount=payment_split.self_pay_amount,
            payment_type=payment_split.payment_type,
            payment_split_status=payment_split.status,
            store_id=store.id if store else None,
            owner_id=customer.assigned_to_id,
            staff_name=payload.staff_name,
            payment_method=payload.payment_method,
            raw_json=raw_data,
            synced_at=datetime.now(),
        )
        db.add(order)
        action = "created"
    else:
        order.order_no = order_no
        order.customer_id = customer.id
        order.paid_at = payload.paid_at
        order.item_name = payload.item_name
        order.category = payload.category
        order.amount = payment_split.total_amount
        order.total_amount = payment_split.total_amount
        order.insurance_amount = payment_split.insurance_amount
        order.self_pay_amount = payment_split.self_pay_amount
        order.payment_type = payment_split.payment_type
        order.payment_split_status = payment_split.status
        order.store_id = store.id if store else order.store_id
        order.staff_name = payload.staff_name
        order.payment_method = payload.payment_method
        order.raw_json = raw_data
        order.synced_at = datetime.now()
        if order.owner_id is None:
            order.owner_id = customer.assigned_to_id
        action = "updated"
    db.flush()
    order.items.clear()
    item_payloads = payload.items or [{"item_name": payload.item_name, "quantity": 1, "unit_price": str(payment_split.total_amount), "amount": str(payment_split.total_amount)}]
    for item in item_payloads:
        quantity = max(int(item.get("quantity", 1)), 1)
        amount = Decimal(str(item.get("amount", payment_split.total_amount)))
        unit_price = Decimal(str(item.get("unit_price", amount / quantity)))
        order.items.append(OrderItem(item_name=str(item.get("item_name", payload.item_name)), quantity=quantity, unit_price=unit_price, amount=amount))
    customer.last_visit_at = max(customer.last_visit_at or payload.paid_at, payload.paid_at)
    db.flush()
    return UpsertResult(
        action,
        order.id,
        payment_split_status=payment_split.status,
        payment_amount_mismatch=payment_split.status == "mismatch",
        payment_amount_error=payment_split.mismatch_reason,
    )
