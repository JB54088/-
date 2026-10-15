from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from ...consumption import consumption_count_query, consumption_value_expression
from ...balance import rebuild_customer_balance, resolve_balance_operation, resolve_balance_payment_amount, resolve_is_refund, sync_order_balance
from ...models import Customer, CustomerPoolMatchHistory, Department, ExcelImportBatch, ExcelImportUnmatchedRecord, IntegrationLog, Order, OrderItem, Store
from ...utils import consumption_key_expression, consumption_order_condition, is_external_placeholder, normalize_phone
from .parser import NormalizedTransaction, ParseResult, parse_excel


@dataclass
class CustomerMatch:
    status: str
    customer: Customer | None
    reason: str
    match_type: str | None = None
    match_key: str | None = None


def _decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _transaction_from_dict(value: dict[str, Any]) -> NormalizedTransaction:
    return NormalizedTransaction(
        external_customer_id=value.get("external_customer_id"),
        name=value.get("name"),
        phone=value.get("phone"),
        external_transaction_id=value.get("external_transaction_id"),
        transaction_fingerprint=value["transaction_fingerprint"],
        visit_no=value.get("visit_no"),
        charged_at=datetime.fromisoformat(value["charged_at"]),
        payment_type=value.get("payment_type"),
        payment_method=value.get("payment_method"),
        payment_type_raw=value.get("payment_type_raw") or value.get("payment_method"),
        transaction_kind=value.get("transaction_kind") or "consumption",
        transaction_operation=value.get("transaction_operation"),
        is_refund=bool(value.get("is_refund", resolve_is_refund(value.get("transaction_operation"), _decimal(value.get("paid_amount")), _decimal(value.get("total_amount"))))),
        balance_payment_amount=_decimal(value.get("balance_payment_amount")),
        total_amount=_decimal(value.get("total_amount"), Decimal("0")) or Decimal("0"),
        original_amount=_decimal(value.get("original_amount")),
        single_negotiation_amount=_decimal(value.get("single_negotiation_amount")),
        writeoff_amount=_decimal(value.get("writeoff_amount")),
        deduction_amount=_decimal(value.get("deduction_amount")),
        deduction_amount_raw=_decimal(value.get("deduction_amount_raw", value.get("deduction_amount"))),
        discount_amount=_decimal(value.get("discount_amount")),
        negotiation_amount=_decimal(value.get("negotiation_amount")),
        receivable_amount=_decimal(value.get("receivable_amount")),
        paid_amount=_decimal(value.get("paid_amount"), _decimal(value.get("total_amount"), Decimal("0"))) or Decimal("0"),
        arrears_change=_decimal(value.get("arrears_change")),
        insurance_amount=_decimal(value.get("insurance_amount")),
        self_pay_amount=_decimal(value.get("self_pay_amount")),
        non_insurance_amount=_decimal(value.get("non_insurance_amount")),
        has_consumption_record=bool(value.get("has_consumption_record", True)),
        payment_split_status=value.get("payment_split_status") or "unknown",
        mismatch_reason=value.get("mismatch_reason"),
        store=value.get("store"),
        organization=value.get("organization"),
        department=value.get("department"),
        staff_name=value.get("staff_name"),
        category_level_1=value.get("category_level_1"),
        category_level_2=value.get("category_level_2"),
        category_level_3=value.get("category_level_3"),
        item_name=value.get("item_name"),
        item_code=value.get("item_code"),
        items=value.get("items") or [],
        raw_data=value.get("raw_data") or {},
        source_sheet=value.get("source_sheet") or "",
        is_detail=bool(value.get("is_detail")),
        total_from_line_amount=bool(value.get("total_from_line_amount")),
    )


def _identity_key(transaction: NormalizedTransaction) -> str:
    return f"external:{transaction.external_customer_id}" if transaction.external_customer_id else f"phone:{normalize_phone(transaction.phone) or transaction.transaction_fingerprint}"


def _placeholder_external_id(customer: Customer) -> str | None:
    if customer.external_customer_id:
        return customer.external_customer_id
    raw_data = customer.external_raw_data or {}
    value = raw_data.get("external_customer_id")
    return str(value) if value else None


def _external_placeholders(db: Session) -> list[Customer]:
    return db.scalars(
        select(Customer).where(
            Customer.is_deleted.is_(False),
            Customer.reported_by_id.is_(None),
            Customer.lead_status == "unassigned",
            Customer.pool_match_status == "pending",
        ).order_by(Customer.id)
    ).all()


def _find_external_placeholder(db: Session, transaction: NormalizedTransaction) -> Customer | None:
    placeholders = _external_placeholders(db)
    external_id = transaction.external_customer_id
    if external_id:
        external_matches = [item for item in placeholders if _placeholder_external_id(item) == external_id]
        if len(external_matches) == 1:
            return external_matches[0]
        if len(external_matches) > 1:
            return None
    normalized_phone = normalize_phone(transaction.phone)
    if not normalized_phone:
        return None
    phone_matches = [item for item in placeholders if normalize_phone(item.phone) == normalized_phone]
    if len(phone_matches) != 1:
        return None
    candidate_external_id = _placeholder_external_id(phone_matches[0])
    if external_id and candidate_external_id and candidate_external_id != external_id:
        return None
    return phone_matches[0]


def _create_external_placeholder(db: Session, transaction: NormalizedTransaction) -> Customer:
    existing = _find_external_placeholder(db, transaction)
    if existing:
        return existing
    submission_id = f"abc-external-{transaction.transaction_fingerprint}"
    existing_submission = db.scalar(select(Customer).where(Customer.submission_id == submission_id))
    if existing_submission and is_external_placeholder(existing_submission):
        return existing_submission
    external_id = transaction.external_customer_id
    external_id_in_use = bool(external_id and db.scalar(select(Customer.id).where(Customer.external_customer_id == external_id, Customer.is_deleted.is_(False))))
    customer = Customer(
        external_customer_id=None if external_id_in_use else external_id,
        submission_id=submission_id,
        name=transaction.name or "待识别外部客户",
        phone=normalize_phone(transaction.phone),
        external_raw_data={
            "source": "abc_excel_unmatched",
            "external_customer_id": external_id,
            "name": transaction.name,
            "phone": normalize_phone(transaction.phone),
            "last_transaction_fingerprint": transaction.transaction_fingerprint,
        },
        pool_match_status="pending",
        lead_status="unassigned",
        status="active",
    )
    db.add(customer)
    db.flush()
    db.add(CustomerPoolMatchHistory(
        customer_id=customer.id,
        external_customer_id=external_id,
        match_type="excel_unmatched",
        previous_status="pending",
        new_status="pending",
        note="ABC Excel 客户暂未关联业务员线索",
    ))
    db.flush()
    return customer


def match_customer(db: Session, transaction: NormalizedTransaction) -> CustomerMatch:
    """Match external facts without ever using name as the sole identity."""
    normalized_phone = normalize_phone(transaction.phone)
    phone_candidates: list[Customer] = []
    if normalized_phone:
        phone_candidates = [
            customer
            for customer in db.scalars(select(Customer).where(Customer.phone.is_not(None), Customer.lead_status != "rejected", Customer.is_deleted.is_(False))).all()
            if normalize_phone(customer.phone) == normalized_phone and not is_external_placeholder(customer)
        ]

    if transaction.external_customer_id:
        customer = db.scalar(select(Customer).where(Customer.external_customer_id == transaction.external_customer_id, Customer.is_deleted.is_(False)))
        if customer:
            if is_external_placeholder(customer):
                return CustomerMatch("pending_external", customer, "已保存为待关联外部客户", "pending", "external_customer_id")
            if len(phone_candidates) > 1 or any(candidate.id != customer.id for candidate in phone_candidates):
                return CustomerMatch("conflict", None, "患者档案号与手机号分别指向不同客户")
            if normalized_phone and customer.phone and normalize_phone(customer.phone) != normalized_phone:
                return CustomerMatch("conflict", None, "患者档案号匹配成功，但手机号存在冲突")
            return CustomerMatch("matched", customer, "external_customer_id", "auto", "external_customer_id")

    if normalized_phone:
        if len(phone_candidates) > 1:
            return CustomerMatch("conflict", None, "手机号匹配到多个内部客户")
        if len(phone_candidates) == 1:
            customer = phone_candidates[0]
            if (
                transaction.external_customer_id
                and customer.external_customer_id
                and customer.external_customer_id != transaction.external_customer_id
            ):
                return CustomerMatch("conflict", None, "手机号客户已绑定另一个 ABC 患者档案号")
            return CustomerMatch("matched", customer, "normalized_phone", "auto", "phone")

    return CustomerMatch("unmatched", None, "未找到外部客户 ID 或唯一手机号匹配")


def _existing_order(db: Session, transaction: NormalizedTransaction) -> Order | None:
    if transaction.external_transaction_id:
        order = db.scalar(select(Order).where(Order.external_transaction_id == transaction.external_transaction_id))
        if order:
            return order
        # Compatibility with orders imported by the retired data-pool connector.
        order = db.scalar(select(Order).where(Order.external_order_id == transaction.external_transaction_id))
        if order:
            return order
    return db.scalar(select(Order).where(Order.transaction_fingerprint == transaction.transaction_fingerprint))


def _preview_order_action(db: Session, transaction: NormalizedTransaction) -> str:
    return "updated" if _existing_order(db, transaction) else "new"


def _evaluate(result: ParseResult, db: Session) -> tuple[list[dict[str, Any]], dict[str, int]]:
    evaluations: list[dict[str, Any]] = []
    identities: dict[str, str] = {}
    counts = {"matched_customers": 0, "unmatched_customers": 0, "conflict_customers": 0, "new_transactions": 0, "updated_transactions": 0}
    for transaction in result.transactions:
        match = match_customer(db, transaction)
        identity = _identity_key(transaction)
        if identity not in identities:
            identities[identity] = match.status
            customer_count_key = "matched" if match.status == "matched" else "conflict" if match.status == "conflict" else "unmatched"
            counts[f"{customer_count_key}_customers"] += 1
        action = _preview_order_action(db, transaction) if match.status == "matched" else "unmatched"
        if action in {"new", "updated"}:
            counts[f"{action}_transactions"] += 1
        evaluations.append({
            "transaction_fingerprint": transaction.transaction_fingerprint,
            "external_transaction_id": transaction.external_transaction_id,
            "identity_key": identity,
            "match_status": "matched_auto" if match.status == "matched" and match.match_type == "auto" else "unmatched" if match.status == "pending_external" else match.status,
            "match_reason": match.reason,
            "match_type": match.match_type,
            "match_key": match.match_key,
            "customer_id": match.customer.id if match.customer else None,
            "order_action": action,
            "payment_split_status": transaction.payment_split_status,
        })
    return evaluations, counts


def _batch_dict(batch: ExcelImportBatch) -> dict[str, Any]:
    return {
        "id": batch.id,
        "file_name": batch.file_name,
        "uploaded_by": batch.uploaded_by_id,
        "uploaded_at": batch.uploaded_at,
        "status": batch.status,
        "sheet_names": batch.sheet_names or [],
        "total_rows": batch.total_rows,
        "total_customers": batch.total_customers,
        "matched_customers": batch.matched_customers,
        "unmatched_customers": batch.unmatched_customers,
        "conflict_customers": batch.conflict_customers,
        "new_transactions": batch.new_transactions,
        "updated_transactions": batch.updated_transactions,
        "skipped_transactions": batch.skipped_transactions,
        "error_rows": batch.error_rows,
        "error_message": batch.error_message,
        "confirmed_by": batch.confirmed_by_id,
        "confirmed_at": batch.confirmed_at,
    }


def serialize_batch(batch: ExcelImportBatch, include_preview: bool = False) -> dict[str, Any]:
    value = _batch_dict(batch)
    if include_preview:
        preview = batch.preview_data or {}
        value["preview"] = {
            "transactions": (preview.get("transactions") or [])[:30],
            "evaluations": (preview.get("evaluations") or [])[:30],
            "errors": (preview.get("errors") or [])[:100],
            "sheet_stats": preview.get("sheet_stats") or [],
            "patient_count": preview.get("patient_count") or 0,
        }
    return value


def serialize_unmatched(record: ExcelImportUnmatchedRecord) -> dict[str, Any]:
    stored = record.raw_data or {}
    preview = stored.get("normalized") or stored
    resolved = record.status == "bound"
    return {
        "id": record.id,
        "batch_id": record.batch_id,
        "file_name": record.batch.file_name if record.batch else None,
        "external_customer_id": record.external_customer_id,
        "name": record.name,
        "phone": record.phone,
        "transaction_fingerprint": record.transaction_fingerprint,
        "status": record.status,
        "customer_id": record.customer_id,
        # Stable names for the external-import UI/API contract.  The existing
        # customer_id column remains the persisted binding pointer.
        "system_customer_id": record.customer_id if resolved else None,
        "match_status": "resolved" if resolved else "conflict" if record.status == "conflict" else "unmatched",
        "visit_no": preview.get("visit_no"),
        "transaction_kind": preview.get("transaction_kind"),
        "transaction_operation": preview.get("transaction_operation"),
        "item_name": preview.get("item_name"),
        "items": preview.get("items") or [],
        "charged_at": preview.get("charged_at"),
        "external_transaction_id": preview.get("external_transaction_id"),
        "total_amount": preview.get("total_amount"),
        "original_amount": preview.get("original_amount"),
        "receivable_amount": preview.get("receivable_amount"),
        "paid_amount": preview.get("paid_amount"),
        "deduction_amount": preview.get("deduction_amount"),
        "deduction_amount_raw": preview.get("deduction_amount_raw", preview.get("deduction_amount")),
        "writeoff_amount": preview.get("writeoff_amount"),
        "discount_amount": preview.get("discount_amount"),
        "insurance_amount": preview.get("insurance_amount"),
        "non_insurance_amount": preview.get("non_insurance_amount"),
        "payment_type_raw": preview.get("payment_type_raw"),
        "raw_data": preview.get("raw_data") or preview,
        "resolution_note": record.resolution_note,
        "resolved_at": record.resolved_at,
    }


def _unmatched_group_key(record: ExcelImportUnmatchedRecord) -> tuple[str, str]:
    """Build the customer-level key used by the pending-review surface.

    An external patient ID always wins.  Phone is only a fallback when the
    row has no external ID.  A name is deliberately never used as a grouping
    identity because two people can share the same name.
    """
    external_id = str(record.external_customer_id or "").strip()
    if external_id:
        return "external", external_id
    normalized_phone = normalize_phone(record.phone)
    if normalized_phone:
        return "phone", normalized_phone
    return "record", str(record.id)


def _amount_from_serialized(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _amount_text(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def serialize_unmatched_groups(records: list[ExcelImportUnmatchedRecord]) -> list[dict[str, Any]]:
    """Collapse transaction-level audit rows into one card per ABC customer."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    seen_transactions: set[tuple[tuple[str, str], str]] = set()
    for record in records:
        key = _unmatched_group_key(record)
        transaction_key = (key, record.transaction_fingerprint)
        if transaction_key in seen_transactions:
            continue
        seen_transactions.add(transaction_key)
        transaction = serialize_unmatched(record)
        group = groups.get(key)
        if group is None:
            group = {
                "id": record.id,
                "customer_key": f"{key[0]}:{key[1]}",
                "external_customer_id": transaction.get("external_customer_id"),
                "name": transaction.get("name"),
                "phone": transaction.get("phone"),
                "status": transaction.get("status"),
                "match_status": transaction.get("match_status"),
                "transaction_count": 0,
                "total_amount": Decimal("0"),
                "latest_charged_at": None,
                "record_ids": [],
                "transactions": [],
            }
            groups[key] = group
        group["transaction_count"] += 1
        group["total_amount"] += _amount_from_serialized(transaction.get("total_amount"))
        charged_at = transaction.get("charged_at")
        if charged_at and (not group["latest_charged_at"] or str(charged_at) > str(group["latest_charged_at"])):
            group["latest_charged_at"] = charged_at
        group["record_ids"].append(record.id)
        group["transactions"].append(transaction)
        if transaction.get("status") == "conflict":
            group["status"] = "conflict"
            group["match_status"] = "conflict"

    result = []
    for group in groups.values():
        group["total_amount"] = _amount_text(group["total_amount"])
        result.append(group)
    return result


def preview_import(db: Session, file_name: str, data: bytes, uploaded_by_id: int, max_rows: int = 50000) -> ExcelImportBatch:
    result = parse_excel(data, file_name)
    if result.total_rows > max_rows:
        raise ValueError(f"Excel 行数超过限制（最多 {max_rows} 行）")
    evaluations, counts = _evaluate(result, db)
    preview_data = result.preview_data
    preview_data["evaluations"] = evaluations
    batch = ExcelImportBatch(
        file_name=file_name,
        uploaded_by_id=uploaded_by_id,
        status="preview",
        sheet_names=result.sheet_names,
        preview_data=preview_data,
        total_rows=result.total_rows,
        total_customers=counts["matched_customers"] + counts["unmatched_customers"] + counts["conflict_customers"],
        matched_customers=counts["matched_customers"],
        unmatched_customers=counts["unmatched_customers"],
        conflict_customers=counts["conflict_customers"],
        new_transactions=counts["new_transactions"],
        updated_transactions=counts["updated_transactions"],
        error_rows=len(result.errors),
        error_message="；".join(error["message"] for error in result.errors[:5]) or None,
    )
    db.add(batch)
    db.flush()
    return batch


def _get_store(db: Session, name: str | None) -> Store | None:
    if not name:
        return None
    store = db.scalar(select(Store).where(Store.name == name))
    if not store:
        store = Store(name=name)
        db.add(store)
        db.flush()
    return store


def _get_department(db: Session, name: str | None) -> Department | None:
    if not name:
        return None
    return db.scalar(select(Department).where(Department.name == name))


def _same_order_facts(order: Order, transaction: NormalizedTransaction, customer_id: int) -> bool:
    expected_operation = resolve_balance_operation(
        transaction.transaction_operation,
        transaction.transaction_kind,
        transaction.paid_amount if transaction.paid_amount is not None else transaction.total_amount,
    )
    expected_balance_payment = resolve_balance_payment_amount(
        transaction.payment_type_raw,
        transaction.payment_method,
        transaction.balance_payment_amount,
        transaction.paid_amount,
        transaction.total_amount,
    )
    return (
        order.customer_id == customer_id
        and order.paid_at == transaction.charged_at
        and order.total_amount == transaction.total_amount
        and order.original_amount == transaction.original_amount
        and order.single_negotiation_amount == transaction.single_negotiation_amount
        and order.writeoff_amount == transaction.writeoff_amount
        and order.deduction_amount == transaction.deduction_amount
        and order.deduction_amount_raw == transaction.deduction_amount_raw
        and order.discount_amount == transaction.discount_amount
        and order.negotiation_amount == transaction.negotiation_amount
        and order.receivable_amount == transaction.receivable_amount
        and order.paid_amount == transaction.paid_amount
        and order.arrears_change == transaction.arrears_change
        and order.insurance_amount == transaction.insurance_amount
        and order.self_pay_amount == transaction.self_pay_amount
        and order.non_insurance_amount == transaction.non_insurance_amount
        and order.payment_type_raw == transaction.payment_type_raw
        and order.transaction_kind == transaction.transaction_kind
        and order.transaction_operation == transaction.transaction_operation
        and order.is_refund == transaction.is_refund
        and order.balance_operation == expected_operation
        and order.balance_payment_amount == expected_balance_payment
        and order.has_consumption_record == transaction.has_consumption_record
        and order.payment_method == transaction.payment_method
        and order.item_name == (transaction.item_name or (transaction.items[0].get("item_name") if transaction.items else None) or "未分类消费")
    )


def _replace_items(order: Order, transaction: NormalizedTransaction) -> None:
    if not transaction.items:
        return
    order.items.clear()
    for item in transaction.items:
        quantity_decimal = _decimal(item.get("quantity"), Decimal("1")) or Decimal("1")
        quantity = max(1, int(quantity_decimal))
        amount = _decimal(item.get("amount"))
        unit_price = _decimal(item.get("unit_price"))
        if amount is None and unit_price is not None:
            amount = unit_price * quantity
        amount = amount or Decimal("0")
        unit_price = unit_price or (amount / quantity if quantity else Decimal("0"))
        order.items.append(OrderItem(
            item_name=item.get("item_name") or "未命名项目",
            category_level_1=item.get("category_level_1"),
            category_level_2=item.get("category_level_2"),
            category_level_3=item.get("category_level_3"),
            item_code=item.get("item_code"),
            quantity=quantity,
            unit=item.get("unit"),
            unit_price=unit_price,
            amount=amount,
        ))


def upsert_transaction(db: Session, batch: ExcelImportBatch, customer: Customer, transaction: NormalizedTransaction) -> str:
    order = _existing_order(db, transaction)
    if order and order.customer_id != customer.id:
        existing_owner = db.get(Customer, order.customer_id)
        if existing_owner and existing_owner.is_deleted:
            # A re-reported customer must not inherit an archived customer's
            # historical transaction.  Treat the old row as an idempotent
            # audit record and allow genuinely new rows to append normally.
            return "skipped"
        raise ValueError("交易唯一标识已经绑定到其他客户")
    item_name = transaction.item_name or (transaction.items[0].get("item_name") if transaction.items else None) or "未分类消费"
    category = transaction.category_level_1 or "其他"
    store = _get_store(db, transaction.store)
    department = _get_department(db, transaction.department)
    balance_operation = resolve_balance_operation(
        transaction.transaction_operation,
        transaction.transaction_kind,
        transaction.paid_amount if transaction.paid_amount is not None else transaction.total_amount,
    )
    balance_payment_amount = resolve_balance_payment_amount(
        transaction.payment_type_raw,
        transaction.payment_method,
        transaction.balance_payment_amount,
        transaction.paid_amount,
        transaction.total_amount,
    )
    is_refund = resolve_is_refund(
        transaction.transaction_operation,
        transaction.paid_amount,
        transaction.total_amount,
        transaction.original_amount,
        transaction.receivable_amount,
    )
    if order and _same_order_facts(order, transaction, customer.id) and order.raw_json == transaction.raw_data:
        order.import_batch_id = batch.id
        order.synced_at = datetime.now().replace(microsecond=0)
        sync_order_balance(db, order)
        return "skipped"
    if order is None:
        order = Order(
            order_no=transaction.external_transaction_id or f"XLS-{transaction.transaction_fingerprint[:28]}",
            external_order_id=transaction.external_transaction_id or f"XLS-{transaction.transaction_fingerprint}",
            external_customer_id=transaction.external_customer_id,
            external_transaction_id=transaction.external_transaction_id,
            transaction_fingerprint=transaction.transaction_fingerprint,
            customer_id=customer.id,
            paid_at=transaction.charged_at,
            visit_no=transaction.visit_no,
            item_name=item_name,
            category=category,
            category_level_1=transaction.category_level_1,
            category_level_2=transaction.category_level_2,
            category_level_3=transaction.category_level_3,
            item_code=transaction.item_code,
            amount=transaction.total_amount,
            total_amount=transaction.total_amount,
            original_amount=transaction.original_amount,
            single_negotiation_amount=transaction.single_negotiation_amount,
            writeoff_amount=transaction.writeoff_amount,
            deduction_amount=transaction.deduction_amount,
            deduction_amount_raw=transaction.deduction_amount_raw,
            discount_amount=transaction.discount_amount,
            negotiation_amount=transaction.negotiation_amount,
            receivable_amount=transaction.receivable_amount,
            paid_amount=transaction.paid_amount,
            arrears_change=transaction.arrears_change,
            insurance_amount=transaction.insurance_amount,
            self_pay_amount=transaction.self_pay_amount,
            non_insurance_amount=transaction.non_insurance_amount,
            payment_type=transaction.payment_type,
            payment_type_raw=transaction.payment_type_raw,
            transaction_kind=transaction.transaction_kind,
            transaction_operation=transaction.transaction_operation,
            is_refund=is_refund,
            balance_operation=balance_operation,
            balance_payment_amount=balance_payment_amount,
            has_consumption_record=transaction.has_consumption_record,
            payment_split_status=transaction.payment_split_status,
            import_batch_id=batch.id,
            store_id=store.id if store else None,
            department_id=department.id if department else None,
            owner_id=customer.assigned_to_id,
            staff_name=transaction.staff_name,
            organization=transaction.organization,
            payment_method=transaction.payment_method,
            raw_json=transaction.raw_data,
            synced_at=datetime.now().replace(microsecond=0),
        )
        db.add(order)
        db.flush()
        _replace_items(order, transaction)
        db.flush()
        sync_order_balance(db, order)
        return "new"
    if transaction.external_transaction_id and not order.external_transaction_id:
        order.external_transaction_id = transaction.external_transaction_id
    order.external_customer_id = transaction.external_customer_id or order.external_customer_id
    order.transaction_fingerprint = transaction.transaction_fingerprint
    order.import_batch_id = batch.id
    order.paid_at = transaction.charged_at
    order.visit_no = transaction.visit_no
    order.item_name = item_name
    order.category = category
    order.category_level_1 = transaction.category_level_1
    order.category_level_2 = transaction.category_level_2
    order.category_level_3 = transaction.category_level_3
    order.item_code = transaction.item_code
    order.amount = transaction.total_amount
    order.total_amount = transaction.total_amount
    order.original_amount = transaction.original_amount
    order.single_negotiation_amount = transaction.single_negotiation_amount
    order.writeoff_amount = transaction.writeoff_amount
    order.deduction_amount = transaction.deduction_amount
    order.deduction_amount_raw = transaction.deduction_amount_raw
    order.discount_amount = transaction.discount_amount
    order.negotiation_amount = transaction.negotiation_amount
    order.receivable_amount = transaction.receivable_amount
    order.paid_amount = transaction.paid_amount
    order.arrears_change = transaction.arrears_change
    order.insurance_amount = transaction.insurance_amount
    order.self_pay_amount = transaction.self_pay_amount
    order.non_insurance_amount = transaction.non_insurance_amount
    order.payment_type = transaction.payment_type
    order.payment_type_raw = transaction.payment_type_raw
    order.transaction_kind = transaction.transaction_kind
    order.transaction_operation = transaction.transaction_operation
    order.is_refund = is_refund
    order.balance_operation = balance_operation
    order.balance_payment_amount = balance_payment_amount
    order.has_consumption_record = transaction.has_consumption_record
    order.payment_split_status = transaction.payment_split_status
    order.store_id = store.id if store else order.store_id
    order.department_id = department.id if department else order.department_id
    order.staff_name = transaction.staff_name
    order.organization = transaction.organization
    order.payment_method = transaction.payment_method
    order.raw_json = transaction.raw_data
    order.synced_at = datetime.now().replace(microsecond=0)
    _replace_items(order, transaction)
    db.flush()
    sync_order_balance(db, order)
    return "updated"


def _update_customer_snapshot(db: Session, customer: Customer, transaction: NormalizedTransaction, batch: ExcelImportBatch, *, mark_matched: bool = True) -> None:
    # These are external facts; internal ownership, source, tags and status are untouched.
    if transaction.external_customer_id and not customer.external_customer_id:
        external_id_in_use = db.scalar(select(Customer.id).where(Customer.external_customer_id == transaction.external_customer_id, Customer.id != customer.id, Customer.is_deleted.is_(False)))
        if not external_id_in_use:
            customer.external_customer_id = transaction.external_customer_id
    if transaction.name:
        customer.name = transaction.name
    normalized_phone = normalize_phone(transaction.phone)
    if normalized_phone:
        customer.phone = normalized_phone
    customer.pool_match_status = "matched" if mark_matched else "pending"
    # ``upsert_transaction`` adds imported OrderItem rows after the order's
    # initial flush.  Flush them before the correlated aggregate below so the
    # customer snapshot includes the current project's value in this same
    # transaction, including zero-paid/deduction-only items.
    db.flush()
    summary = db.execute(
        select(
            func.coalesce(func.sum(consumption_value_expression()), 0),
            func.max(Order.paid_at),
        ).where(Order.customer_id == customer.id, consumption_order_condition())
    ).one()
    order_count = int(db.scalar(consumption_count_query(Order.customer_id == customer.id, consumption_order_condition())) or 0)
    customer.external_total_spend = summary[0] or Decimal("0")
    customer.external_order_count = order_count
    customer.external_last_spend_at = summary[1]
    customer.external_synced_at = datetime.now().replace(microsecond=0)
    previous_raw_data = customer.external_raw_data or {}
    customer.external_raw_data = {
        "source": "abc_excel",
        "external_customer_id": transaction.external_customer_id or customer.external_customer_id or previous_raw_data.get("external_customer_id"),
        "pending_external": not mark_matched,
        "last_import_batch_id": batch.id,
        "last_import_file": batch.file_name,
        "last_import_at": customer.external_synced_at.isoformat(),
        "previous_raw_data": previous_raw_data,
    }
    if summary[1] and (customer.last_visit_at is None or summary[1] > customer.last_visit_at):
        customer.last_visit_at = summary[1]


def link_pending_external_customer(db: Session, customer: Customer) -> Customer | None:
    """Attach one unique ABC-only customer to a newly reported formal lead.

    The placeholder owns the imported orders until the salesperson submits a
    lead. Moving the existing orders and unmatched audit rows in the same
    transaction keeps historical totals and item details intact.
    """
    normalized_phone = normalize_phone(customer.phone)
    if not normalized_phone:
        return None
    # A voided customer starts a new business identity.  Do not silently
    # carry an old ABC-only placeholder into the replacement lead; its
    # imported facts remain available for an explicit administrator migration.
    deleted_phones = db.scalars(
        select(Customer.phone).where(
            Customer.phone.is_not(None),
            Customer.is_deleted.is_(True),
        )
    ).all()
    if any(normalize_phone(phone) == normalized_phone for phone in deleted_phones):
        return None
    placeholders = [item for item in _external_placeholders(db) if item.id != customer.id and normalize_phone(item.phone) == normalized_phone]
    if len(placeholders) != 1:
        return None
    placeholder = placeholders[0]
    external_id = _placeholder_external_id(placeholder)
    if external_id:
        existing = db.scalar(select(Customer).where(Customer.external_customer_id == external_id, Customer.id.not_in([placeholder.id, customer.id]), Customer.is_deleted.is_(False)))
        if existing:
            return None
        if customer.external_customer_id and customer.external_customer_id != external_id:
            return None
        # Free the unique external ID on the placeholder before assigning it
        # to the formal lead; PostgreSQL may otherwise flush the UPDATE first.
        placeholder.external_customer_id = None
        db.flush()
        customer.external_customer_id = external_id

    orders = db.scalars(select(Order).where(Order.customer_id == placeholder.id)).all()
    for order in orders:
        order.customer = customer
        for ledger in order.balance_transactions:
            ledger.customer = customer
    db.flush()
    rebuild_customer_balance(db, customer.id)
    # A placeholder may have more than one unmatched audit row (for example
    # one row per transaction, or rows created before the placeholder pointer
    # was attached).  Resolve every still-open row for this external identity,
    # not just rows that happen to point at the placeholder.
    unresolved_identity = [ExcelImportUnmatchedRecord.customer_id == placeholder.id]
    if external_id:
        unresolved_identity.append(ExcelImportUnmatchedRecord.external_customer_id == external_id)
        if normalized_phone:
            unresolved_identity.append(
                and_(
                    ExcelImportUnmatchedRecord.external_customer_id.is_(None),
                    ExcelImportUnmatchedRecord.phone == normalized_phone,
                )
            )
    else:
        unresolved_identity.append(ExcelImportUnmatchedRecord.phone == normalized_phone)
    db.execute(
        update(ExcelImportUnmatchedRecord)
        .where(
            ExcelImportUnmatchedRecord.status.in_(["pending", "conflict"]),
            or_(*unresolved_identity),
        )
        .values(
            customer_id=customer.id,
            status="bound",
            resolution_note="线索报备后按唯一手机号自动关联",
            resolved_at=datetime.now().replace(microsecond=0),
        )
    )
    summary = db.execute(
        select(
            func.coalesce(func.sum(consumption_value_expression()), 0),
            func.count(func.distinct(consumption_key_expression())),
            func.max(Order.paid_at),
        ).where(Order.customer_id == customer.id, consumption_order_condition())
    ).one()
    customer.external_total_spend = summary[0] or Decimal("0")
    customer.external_order_count = int(summary[1] or 0)
    customer.external_last_spend_at = summary[2]
    customer.external_synced_at = placeholder.external_synced_at or datetime.now().replace(microsecond=0)
    customer.external_raw_data = {
        "source": "abc_excel",
        "linked_from_external_placeholder": placeholder.id,
        "external_customer_id": external_id,
        "placeholder_raw_data": placeholder.external_raw_data or {},
    }
    customer.pool_match_status = "matched"
    if summary[2] and (customer.last_visit_at is None or summary[2] > customer.last_visit_at):
        customer.last_visit_at = summary[2]
    db.add(CustomerPoolMatchHistory(
        customer_id=customer.id,
        external_customer_id=external_id,
        match_type="auto_lead_phone",
        previous_status="pending",
        new_status="matched",
        note="线索报备后按唯一手机号自动关联 ABC 历史消费",
    ))
    db.delete(placeholder)
    db.flush()
    return placeholder


def _add_unmatched(db: Session, batch: ExcelImportBatch, transaction: NormalizedTransaction, match: CustomerMatch, customer_id: int | None = None) -> None:
    # The same unresolved transaction can be present in several uploaded
    # files.  The order table already deduplicates the business transaction;
    # keep the review queue idempotent as well so one customer card does not
    # count the same transaction once per upload batch.
    existing = db.scalar(select(ExcelImportUnmatchedRecord).where(
        ExcelImportUnmatchedRecord.transaction_fingerprint == transaction.transaction_fingerprint,
    ).order_by(ExcelImportUnmatchedRecord.id).limit(1))
    if existing:
        return
    db.add(ExcelImportUnmatchedRecord(
        batch_id=batch.id,
        external_customer_id=transaction.external_customer_id,
        name=transaction.name,
        phone=normalize_phone(transaction.phone),
        transaction_fingerprint=transaction.transaction_fingerprint,
        raw_data={"normalized": transaction.to_dict(), "match_reason": match.reason, "match_status": match.status},
        status="conflict" if match.status == "conflict" else "pending",
        customer_id=customer_id,
        resolution_note=match.reason,
    ))


def _resolve_unmatched_records_for_match(
    db: Session,
    customer: Customer,
    transaction: NormalizedTransaction,
    *,
    previous_customer_id: int | None = None,
    note: str = "ABC 客户自动匹配成功，历史待匹配交易已归入正式客户",
) -> int:
    """Close stale unmatched audit rows after an automatic customer match.

    ``customer_id`` on an unresolved row may point at an ABC-only placeholder,
    while rows created before the match may not have that pointer.  Resolve by
    the stable external id first and use the normalized phone only for rows
    without an external id, so a different ABC id sharing a phone is never
    silently merged.
    """
    identity_conditions = []
    if previous_customer_id is not None:
        identity_conditions.append(ExcelImportUnmatchedRecord.customer_id == previous_customer_id)
    external_id = transaction.external_customer_id
    normalized_phone = normalize_phone(transaction.phone)
    if external_id:
        identity_conditions.append(ExcelImportUnmatchedRecord.external_customer_id == external_id)
        if normalized_phone:
            identity_conditions.append(
                and_(
                    ExcelImportUnmatchedRecord.external_customer_id.is_(None),
                    ExcelImportUnmatchedRecord.phone == normalized_phone,
                )
            )
    elif normalized_phone:
        identity_conditions.append(ExcelImportUnmatchedRecord.phone == normalized_phone)
    if not identity_conditions:
        return 0
    result = db.execute(
        update(ExcelImportUnmatchedRecord)
        .where(
            ExcelImportUnmatchedRecord.status.in_(["pending", "conflict"]),
            or_(*identity_conditions),
        )
        .values(
            customer_id=customer.id,
            status="bound",
            resolution_note=note,
            resolved_at=datetime.now().replace(microsecond=0),
        )
    )
    return int(result.rowcount or 0)


def _unmatched_group_records(db: Session, record: ExcelImportUnmatchedRecord) -> list[ExcelImportUnmatchedRecord]:
    """Load all unresolved transaction rows for one ABC customer key."""
    external_id = str(record.external_customer_id or "").strip()
    normalized_phone = normalize_phone(record.phone)
    if external_id:
        identity = ExcelImportUnmatchedRecord.external_customer_id == external_id
    elif normalized_phone:
        identity = and_(
            ExcelImportUnmatchedRecord.external_customer_id.is_(None),
            ExcelImportUnmatchedRecord.phone == normalized_phone,
        )
    else:
        identity = ExcelImportUnmatchedRecord.id == record.id
    return db.scalars(
        select(ExcelImportUnmatchedRecord)
        .options(selectinload(ExcelImportUnmatchedRecord.batch))
        .where(
            ExcelImportUnmatchedRecord.status.in_(["pending", "conflict"]),
            identity,
        )
        .order_by(ExcelImportUnmatchedRecord.created_at, ExcelImportUnmatchedRecord.id)
    ).all()


def _unique_unmatched_records(records: list[ExcelImportUnmatchedRecord]) -> list[ExcelImportUnmatchedRecord]:
    """Return one audit row per transaction fingerprint."""
    seen: set[str] = set()
    unique: list[ExcelImportUnmatchedRecord] = []
    for record in records:
        if record.transaction_fingerprint in seen:
            continue
        seen.add(record.transaction_fingerprint)
        unique.append(record)
    return unique


def _add_mismatch_log(db: Session, batch: ExcelImportBatch, transaction: NormalizedTransaction) -> None:
    if transaction.payment_split_status != "mismatch":
        return
    db.add(IntegrationLog(
        source="abc_excel",
        event_type="payment_amount_mismatch",
        external_id=transaction.external_transaction_id,
        status="failed",
        raw_data=transaction.raw_data,
        error_message=transaction.mismatch_reason,
        started_at=datetime.now().replace(microsecond=0),
        finished_at=datetime.now().replace(microsecond=0),
        failure_count=1,
    ))


def _add_excel_match_history(db: Session, customer: Customer, transaction: NormalizedTransaction, match: CustomerMatch) -> None:
    """Record the first automatic Excel association without touching ownership."""
    if match.status != "matched" or match.match_type != "auto":
        return
    match_key = match.match_key or "external_customer_id"
    external_id = transaction.external_customer_id
    if not external_id:
        return
    exists = db.scalar(
        select(CustomerPoolMatchHistory.id).where(
            CustomerPoolMatchHistory.customer_id == customer.id,
            CustomerPoolMatchHistory.external_customer_id == external_id,
            CustomerPoolMatchHistory.match_type == "auto",
            CustomerPoolMatchHistory.note == f"abc_excel:{match_key}",
        )
    )
    if exists:
        return
    db.add(CustomerPoolMatchHistory(
        customer_id=customer.id,
        external_customer_id=external_id,
        match_type="auto",
        previous_status=customer.pool_match_status,
        new_status="matched",
        matched_by_id=None,
        note=f"abc_excel:{match_key}",
    ))


def confirm_import(db: Session, batch: ExcelImportBatch, confirmed_by_id: int) -> ExcelImportBatch:
    if batch.status != "preview":
        raise ValueError("该 Excel 批次已经确认或处理过")
    transactions = [_transaction_from_dict(item) for item in (batch.preview_data or {}).get("transactions", [])]
    counts = {"matched_customers": 0, "unmatched_customers": 0, "conflict_customers": 0, "new_transactions": 0, "updated_transactions": 0, "skipped_transactions": 0, "error_rows": len((batch.preview_data or {}).get("errors", []))}
    identities: set[str] = set()
    successful = 0
    errors: list[str] = []
    payment_mismatch = False
    for transaction in transactions:
        match = match_customer(db, transaction)
        identity = _identity_key(transaction)
        if identity not in identities:
            identities.add(identity)
            if match.status == "matched": counts["matched_customers"] += 1
            elif match.status == "conflict": counts["conflict_customers"] += 1
            else: counts["unmatched_customers"] += 1
        if match.status != "matched" or match.customer is None:
            # Keep the external customer and its order facts in a pending
            # placeholder so a later salesperson lead can link history by
            # phone. The unmatched record remains the admin audit surface.
            pending_customer = match.customer if match.status == "pending_external" else _create_external_placeholder(db, transaction)
            try:
                with db.begin_nested():
                    _add_unmatched(db, batch, transaction, match, pending_customer.id if pending_customer else None)
                    if pending_customer:
                        action = upsert_transaction(db, batch, pending_customer, transaction)
                        _update_customer_snapshot(db, pending_customer, transaction, batch, mark_matched=False)
                        _add_mismatch_log(db, batch, transaction)
                        payment_mismatch = payment_mismatch or transaction.payment_split_status == "mismatch"
                        counts[f"{action}_transactions"] += 1
                        successful += 1
            except Exception as exc:
                counts["error_rows"] += 1
                errors.append(str(exc))
            continue
        try:
            with db.begin_nested():
                action = upsert_transaction(db, batch, match.customer, transaction)
                _add_excel_match_history(db, match.customer, transaction, match)
                _update_customer_snapshot(db, match.customer, transaction, batch)
                _resolve_unmatched_records_for_match(db, match.customer, transaction)
                _add_mismatch_log(db, batch, transaction)
                payment_mismatch = payment_mismatch or transaction.payment_split_status == "mismatch"
            counts[f"{action}_transactions"] += 1
            successful += 1
        except Exception as exc:
            counts["error_rows"] += 1
            errors.append(str(exc))
    batch.matched_customers = counts["matched_customers"]
    batch.unmatched_customers = counts["unmatched_customers"]
    batch.conflict_customers = counts["conflict_customers"]
    batch.new_transactions = counts["new_transactions"]
    batch.updated_transactions = counts["updated_transactions"]
    batch.skipped_transactions = counts["skipped_transactions"]
    batch.error_rows = counts["error_rows"]
    messages = errors[:10]
    if payment_mismatch:
        messages.append("存在 payment_amount_mismatch：医保/自费金额与总金额超过 0.01 元误差")
    batch.error_message = "；".join(messages) or batch.error_message
    batch.confirmed_by_id = confirmed_by_id
    batch.confirmed_at = datetime.now().replace(microsecond=0)
    batch.status = "success" if not errors and not payment_mismatch and not counts["unmatched_customers"] and not counts["conflict_customers"] and not counts["error_rows"] else ("partial" if successful or counts["unmatched_customers"] or counts["conflict_customers"] else "failed")
    db.add(IntegrationLog(
        source="abc_excel",
        event_type="excel_import",
        external_id=str(batch.id),
        status=batch.status,
        raw_data={"batch_id": batch.id, "file_name": batch.file_name, "sheet_names": batch.sheet_names or []},
        error_message=batch.error_message,
        started_at=batch.uploaded_at,
        finished_at=batch.confirmed_at,
        updated_customers=counts["matched_customers"],
        new_orders=counts["new_transactions"],
        updated_orders=counts["updated_transactions"],
        failure_count=counts["error_rows"] + counts["unmatched_customers"] + counts["conflict_customers"],
    ))
    db.flush()
    return batch


def bind_unmatched(db: Session, record: ExcelImportUnmatchedRecord, customer: Customer, operator_id: int, note: str | None = None) -> str:
    if record.status not in {"pending", "conflict"}:
        raise ValueError("该待匹配记录已经处理")
    all_records = _unmatched_group_records(db, record)
    records = _unique_unmatched_records(all_records)
    if not records:
        raise ValueError("该待匹配客户已经处理")
    transactions = [
        (item, _transaction_from_dict((item.raw_data or {}).get("normalized") or item.raw_data))
        for item in records
    ]
    external_ids = {transaction.external_customer_id for _, transaction in transactions if transaction.external_customer_id}
    if customer.external_customer_id and any(external_id != customer.external_customer_id for external_id in external_ids):
        raise ValueError("外部客户 ID 已经绑定到其他内部客户")
    if len(external_ids) > 1:
        raise ValueError("同一待匹配客户存在多个外部客户 ID，无法批量绑定")
    if external_ids and not customer.external_customer_id:
        customer.external_customer_id = next(iter(external_ids))

    actions: list[str] = []
    for item, transaction in transactions:
        action = upsert_transaction(db, item.batch, customer, transaction)
        _update_customer_snapshot(db, customer, transaction, item.batch)
        _add_mismatch_log(db, item.batch, transaction)
        actions.append(action)
    resolved_at = datetime.now().replace(microsecond=0)
    for item in all_records:
        item.status = "bound"
        item.customer_id = customer.id
        item.resolved_by_id = operator_id
        item.resolved_at = resolved_at
        item.resolution_note = note or f"管理员批量绑定客户（共 {len(records)} 笔交易）"
    return f"批量处理 {len(records)} 笔交易（{','.join(sorted(set(actions)))}）"


def ignore_unmatched_group(db: Session, record: ExcelImportUnmatchedRecord, operator_id: int, note: str | None = None) -> int:
    """Ignore all unresolved rows belonging to one ABC customer."""
    if record.status not in {"pending", "conflict"}:
        raise ValueError("该待匹配客户已经处理")
    records = _unmatched_group_records(db, record)
    if not records:
        raise ValueError("该待匹配客户已经处理")
    resolved_at = datetime.now().replace(microsecond=0)
    for item in records:
        item.status = "ignored"
        item.resolved_by_id = operator_id
        item.resolved_at = resolved_at
        item.resolution_note = note or f"管理员忽略该客户（共 {len(records)} 笔交易）"
    return len(records)


def ignore_unmatched(record: ExcelImportUnmatchedRecord, operator_id: int, note: str | None = None) -> None:
    if record.status not in {"pending", "conflict"}:
        raise ValueError("该待匹配记录已经处理")
    record.status = "ignored"
    record.resolved_by_id = operator_id
    record.resolved_at = datetime.now().replace(microsecond=0)
    record.resolution_note = note or "管理员忽略该记录"
