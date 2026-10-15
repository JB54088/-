from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

import openpyxl
import xlrd

from ...utils import normalize_phone
from ...balance import resolve_balance_payment_amount, resolve_is_refund


class ExcelParseError(ValueError):
    pass


HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "external_customer_id": ("患者档案号", "患者档案ID", "患者ID", "患者编号", "档案号", "patient_id", "patient_no", "external_customer_id", "customer_id"),
    "name": ("患者姓名", "客户姓名", "姓名", "患者", "patient_name", "name"),
    "phone": ("手机号", "手机", "联系电话", "联系方式", "phone", "mobile", "telephone"),
    "charged_at": ("收费时间", "交易时间", "消费时间", "结算时间", "发生时间", "paid_at", "charged_at", "transaction_time", "order_time"),
    "external_transaction_id": ("收费单号", "结算单号", "交易流水号", "收费流水ID", "收费流水号", "流水号", "交易号", "订单号", "external_transaction_id", "transaction_id", "order_id"),
    "visit_no": ("诊号", "就诊号", "就诊记录号", "visit_no", "encounter_no"),
    "payment_method": ("支付方式", "付款方式", "payment_method", "pay_method"),
    "payment_type": ("支付类型", "payment_type", "pay_type"),
    "payment_type_raw": ("支付方式", "付款方式", "支付类型", "payment_method", "payment_type", "pay_method", "pay_type"),
    # ABC uses 开单来源/一级分类/费用分类 for the business type in
    # different sheets. Keep one canonical classification field for balance
    # recharge/refund detection without changing the raw row data.
    "transaction_type": ("开单来源", "项目类型", "一级分类", "费用分类", "类型", "transaction_type", "transaction_kind"),
    "transaction_operation": ("业务类型", "交易类型", "收费类型", "类型", "operation", "transaction_operation", "flow_type"),
    "balance_payment_amount": ("会员卡支付", "会员余额支付", "储值支付", "余额支付", "储值卡支付", "余额扣减", "balance_payment_amount", "prepaid_amount", "balance_amount"),
    # ``total_amount`` is the amount used for revenue reporting. For ABC
    # exports that means the actual received amount, mapped separately below
    # as ``paid_amount``. Keep receivable as its own raw field instead of
    # treating it as revenue when no paid column exists.
    "total_amount": ("总金额", "消费总额", "total_amount", "total_fee", "收费金额"),
    "paid_amount": ("实收", "实收金额", "paid_amount", "paid", "received_amount"),
    "original_amount": ("原价", "原价金额", "original_amount", "original_price"),
    "single_negotiation_amount": ("单项协商金额", "单项议价金额", "单项议价", "single_negotiation_amount", "single_negotiation"),
    "writeoff_amount": ("核销金额", "核销", "writeoff_amount", "write_off_amount"),
    "receivable_amount": ("应收", "应收金额", "receivable_amount", "receivable"),
    "deduction_amount": ("抵扣金额", "抵扣", "deduction_amount"),
    "discount_amount": ("优惠金额", "优惠", "折扣金额", "折扣", "discount_amount"),
    "negotiation_amount": ("协商金额", "议价金额", "议价", "negotiation_amount"),
    "arrears_change": ("欠款变动", "欠款变化", "欠款变更", "欠费变更", "arrears_change"),
    "insurance_amount": ("基金支付总额", "医保支付", "医保金额", "基金支付", "insurance_amount", "insurance_payment_amount", "medical_amount"),
    "self_pay_amount": ("非基金支付总额", "自费支付", "自费金额", "个人支付总额", "self_pay_amount", "self_payment_amount", "out_of_pocket_amount"),
    "non_insurance_amount": ("非基金支付总额", "非医保支付总额", "non_insurance_amount"),
    "other_personal_amount": ("其它个人支付", "其他个人支付", "其它自费支付", "其他自费支付", "个人其它支付"),
    "category_level_1": ("一级分类", "大类", "项目大类", "category_level_1", "category1"),
    "category_level_2": ("二级分类", "中类", "项目中类", "category_level_2", "category2"),
    "category_level_3": ("三级分类", "小类", "项目小类", "category_level_3", "category3"),
    "fee_category": ("费用分类", "费用类别", "fee_category", "fee_type"),
    "item_name": ("项目名称", "药品名称", "药品/项目名称", "消费项目", "项目", "商品名称", "item_name", "product_name"),
    "item_code": ("项目编码", "药品编码", "药品/项目编码", "项目代码", "商品编码", "item_code", "product_code"),
    "specification": ("规格", "规格型号", "specification"),
    "manufacturer": ("厂家", "生产厂家", "manufacturer"),
    "item_note": ("项目备注", "明细备注", "item_note"),
    "quantity": ("数量", "qty", "quantity"),
    "unit": ("单位", "unit"),
    "unit_price": ("单价", "unit_price", "price"),
    "line_amount": ("明细金额", "项目金额", "药品金额", "金额", "line_amount", "item_amount"),
    "store": ("门店", "门诊", "store", "store_name"),
    "organization": ("机构", "组织", "organization", "organization_name"),
    "department": ("科室", "部门", "department", "department_name"),
    "staff_name": ("服务人员", "服务医生", "医生", "操作人员", "staff_name", "staff", "doctor"),
}


def _header_key(value: Any) -> str:
    return re.sub(r"[\s\u3000_\-:/：（）()\u200b\u200c\u200d\ufeff]+", "", str(value or "").strip().lower())


NORMALIZED_ALIASES = {field_name: {_header_key(alias) for alias in aliases} for field_name, aliases in HEADER_ALIASES.items()}
NORMALIZED_ALIAS_RANKS = {field_name: {_header_key(alias): index for index, alias in enumerate(aliases)} for field_name, aliases in HEADER_ALIASES.items()}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        if value != value:
            return None
        if value.is_integer():
            value = str(int(value))
        else:
            value = format(value, ".15g")
    value = str(value).replace("\u200b", "").replace("\ufeff", "").strip()
    if re.fullmatch(r"[+-]?\d+\.0+", value):
        value = value.split(".", 1)[0]
    elif re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)[eE][+-]?\d+", value):
        try:
            expanded = format(Decimal(value), "f")
            value = expanded.rstrip("0").rstrip(".") if "." in expanded else expanded
        except InvalidOperation:
            pass
    if value.lower() in {"", "-", "—", "–", "null", "none", "nan", "n/a"}:
        return None
    return value or None


def _phone_text(value: Any) -> str | None:
    """Read a phone cell without expanding literal ``e`` characters.

    Some Excel exports (and test fixtures using an alphanumeric external
    value) contain a phone-like text such as ``1380013800e123``.  The generic
    text helper intentionally expands scientific notation for numeric fields,
    which would turn that literal text into an extremely long number.  Keep
    long digit+``e`` text intact here; ``normalize_phone`` will remove the
    non-digit marker during identity matching.  Numeric cells still use the
    normal conversion path.
    """
    if isinstance(value, str):
        raw = value.replace("\u200b", "").replace("\ufeff", "").strip()
        # Phone cells are identifiers, not scientific-notation numbers. A
        # value such as ``1363e368264000`` must stay text; the generic text
        # helper would otherwise expand it into hundreds of thousands of
        # digits before it reaches the database.
        if re.search(r"[A-Za-z]", raw):
            return raw or None
    return _text(value)


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    value_text = str(value).strip().replace(",", "").replace("¥", "").replace("￥", "")
    if not value_text or value_text in {"-", "—", "无", "N/A", "null"}:
        return None
    try:
        return Decimal(value_text)
    except InvalidOperation:
        return None


def _datetime(value: Any, datemode: int | None = None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, (int, float)) and datemode is not None:
        try:
            return xlrd.xldate_as_datetime(value, datemode).replace(tzinfo=None)
        except (TypeError, ValueError, xlrd.XLDateError):
            return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
    for candidate in (normalized, normalized.replace(" ", "T")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _payment_type(value: Any) -> str | None:
    normalized = _text(value)
    if not normalized:
        return None
    normalized = normalized.lower().replace(" ", "").replace("-", "_")
    if normalized in {"insurance", "medical", "医保", "医保支付", "基金支付", "insurance_payment", "医保结算"} or "医保" in normalized or "基金" in normalized:
        return "insurance"
    if normalized in {"self_pay", "selfpay", "out_of_pocket", "自费", "自费支付", "自付", "个人支付", "self_payment", "现金", "微信", "微信支付", "支付宝", "银行卡"} or any(token in normalized for token in ("abc支付", "微信", "支付宝", "现金", "银行卡")):
        return "self_pay"
    return "other"


def _is_balance_transaction(*values: Any) -> bool:
    return any("会员充值" in (_text(value) or "") for value in values)


def _fingerprint(external_customer_id: str | None, phone: str | None, name: str | None, visit_no: str | None, charged_at: datetime, payment_method: str | None, total_amount: Decimal, external_transaction_id: str | None = None) -> str:
    # A stable ABC transaction number must distinguish two same-value visits.
    # Only rows without that identifier fall back to the composite business
    # facts, which preserves idempotence for legacy ABC exports.
    identity = external_transaction_id or external_customer_id or normalize_phone(phone) or name or "unknown"
    basis = "|".join((identity, visit_no or "", charged_at.isoformat(), payment_method or "", str(total_amount)))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


@dataclass
class NormalizedTransaction:
    external_customer_id: str | None
    name: str | None
    phone: str | None
    external_transaction_id: str | None
    transaction_fingerprint: str
    visit_no: str | None
    charged_at: datetime
    payment_type: str | None
    payment_method: str | None
    payment_type_raw: str | None
    transaction_kind: str
    transaction_operation: str | None
    is_refund: bool
    balance_payment_amount: Decimal | None
    total_amount: Decimal
    original_amount: Decimal | None
    single_negotiation_amount: Decimal | None
    writeoff_amount: Decimal | None
    deduction_amount: Decimal | None
    deduction_amount_raw: Decimal | None
    discount_amount: Decimal | None
    negotiation_amount: Decimal | None
    receivable_amount: Decimal | None
    paid_amount: Decimal | None
    arrears_change: Decimal | None
    insurance_amount: Decimal | None
    self_pay_amount: Decimal | None
    non_insurance_amount: Decimal | None
    has_consumption_record: bool
    payment_split_status: str
    mismatch_reason: str | None
    store: str | None
    organization: str | None
    department: str | None
    staff_name: str | None
    category_level_1: str | None
    category_level_2: str | None
    category_level_3: str | None
    item_name: str | None
    item_code: str | None
    items: list[dict[str, Any]] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)
    source_sheet: str = ""
    is_detail: bool = False
    total_from_line_amount: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["charged_at"] = self.charged_at.isoformat()
        value["total_amount"] = str(self.total_amount)
        value["insurance_amount"] = str(self.insurance_amount) if self.insurance_amount is not None else None
        value["self_pay_amount"] = str(self.self_pay_amount) if self.self_pay_amount is not None else None
        return _json_value(value)


@dataclass
class ParseResult:
    sheet_names: list[str]
    transactions: list[NormalizedTransaction]
    errors: list[dict[str, Any]]
    total_rows: int
    sheet_stats: list[dict[str, Any]] = field(default_factory=list)
    patient_count: int = 0

    @property
    def preview_data(self) -> dict[str, Any]:
        return {
            "transactions": [item.to_dict() for item in self.transactions],
            "errors": _json_value(self.errors),
            "sheet_stats": _json_value(self.sheet_stats),
            "patient_count": self.patient_count,
        }


def _read_xlsx(data: bytes) -> list[tuple[str, list[Any], list[list[Any]], int | None]]:
    workbook = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True)

    def cell_value(cell: Any) -> Any:
        value = cell.value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            number_format = str(getattr(cell, "number_format", "") or "")
            if re.fullmatch(r"0+", number_format):
                return f"{int(value):0{len(number_format)}d}"
        return value

    result = []
    for worksheet in workbook.worksheets:
        # Some ABC exports declare an incorrect worksheet dimension (for
        # example A1:A5 although cells exist through AO).  In read-only mode
        # openpyxl trusts that dimension and silently drops the other fields.
        # Re-scan the XML dimensions before iterating so the real columns are
        # available to header matching.
        reset_dimensions = getattr(worksheet, "reset_dimensions", None)
        if callable(reset_dimensions):
            reset_dimensions()
        values = [[cell_value(cell) for cell in row] for row in worksheet.iter_rows(values_only=False)]
        if values:
            result.append((worksheet.title, list(values[0]), [list(row) for row in values[1:]], None))
    return result


def _read_xls(data: bytes) -> list[tuple[str, list[Any], list[list[Any]], int | None]]:
    workbook = xlrd.open_workbook(file_contents=data, on_demand=True)
    result = []
    for index in range(workbook.nsheets):
        worksheet = workbook.sheet_by_index(index)
        values = [worksheet.row_values(row_index) for row_index in range(worksheet.nrows)]
        if values:
            result.append((worksheet.name, list(values[0]), values[1:], workbook.datemode))
    return result


def _header_and_rows(headers: list[Any], rows: list[list[Any]], require_transaction_fields: bool = True) -> tuple[list[Any], dict[str, int], list[list[Any]]] | None:
    candidates = [headers, *rows[:8]]
    for row_index, header_row in enumerate(candidates):
        mapping: dict[str, int] = {}
        mapping_ranks: dict[str, int] = {}
        for index, value in enumerate(header_row):
            key = _header_key(value)
            for field_name, aliases in NORMALIZED_ALIASES.items():
                rank = NORMALIZED_ALIAS_RANKS[field_name].get(key)
                if key in aliases and (field_name not in mapping or (rank is not None and rank < mapping_ranks[field_name])):
                    mapping[field_name] = index
                    mapping_ranks[field_name] = rank if rank is not None else len(aliases)
        has_transaction_fields = "charged_at" in mapping or "total_amount" in mapping or "line_amount" in mapping
        has_category_fields = "item_code" in mapping or "item_name" in mapping or "fee_category" in mapping
        has_identity_field = {"external_customer_id", "phone", "name", "external_transaction_id"} & mapping.keys()
        has_required_fields = (has_identity_field and has_transaction_fields) if require_transaction_fields else has_category_fields
        if len(mapping) >= 2 and has_required_fields:
            # ``headers`` is row 0 and the remaining candidates are rows 1..8.
            # The header row itself must not be parsed as a transaction.
            remaining = rows if row_index == 0 else rows[row_index:]
            return list(header_row), mapping, remaining
    return None


def _cell(row: list[Any], mapping: dict[str, int], field_name: str) -> Any:
    index = mapping.get(field_name)
    return row[index] if index is not None and index < len(row) else None


def _raw_row(headers: list[Any], row: list[Any]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for index, value in enumerate(row):
        if index >= len(headers):
            continue
        key = _text(headers[index]) or f"column_{index + 1}"
        raw[key] = _json_value(value)
    return raw


def _recognized_fields(headers: list[Any], mapping: dict[str, int]) -> list[dict[str, str]]:
    """Return canonical field names and the actual ABC headers used for preview."""
    result: list[dict[str, str]] = []
    seen: set[tuple[str, int]] = set()
    for field_name, index in mapping.items():
        key = (field_name, index)
        if key in seen or index >= len(headers):
            continue
        seen.add(key)
        header = _text(headers[index])
        if header:
            result.append({"field": field_name, "header": header})
    return sorted(result, key=lambda item: (item["field"], item["header"]))


def _is_category_sheet(name: str) -> bool:
    normalized = name.lower()
    return "分类" in normalized and not any(token in normalized for token in ("流水", "收费", "交易", "明细"))


def _is_detail_sheet(name: str) -> bool:
    normalized = name.lower()
    return "明细" in normalized or "项目清单" in normalized or "药品明细" in normalized


def _patient_key(transaction: NormalizedTransaction) -> str:
    return transaction.external_customer_id or normalize_phone(transaction.phone) or transaction.name or "unknown"


def _visit_key(transaction: NormalizedTransaction) -> str:
    return "|".join((_patient_key(transaction), transaction.visit_no or "", transaction.charged_at.isoformat()))


def _parse_row(sheet_name: str, headers: list[Any], row: list[Any], mapping: dict[str, int], datemode: int | None, is_detail: bool, category_lookup: dict[str, dict[str, str | None]]) -> tuple[NormalizedTransaction | None, str | None]:
    name = _text(_cell(row, mapping, "name"))
    phone = _phone_text(_cell(row, mapping, "phone"))
    external_customer_id = _text(_cell(row, mapping, "external_customer_id"))
    external_transaction_id = _text(_cell(row, mapping, "external_transaction_id"))
    charged_at = _datetime(_cell(row, mapping, "charged_at"), datemode)
    line_amount = _decimal(_cell(row, mapping, "line_amount"))
    raw_total_amount = _decimal(_cell(row, mapping, "total_amount"))
    paid_amount = None if is_detail else _decimal(_cell(row, mapping, "paid_amount"))
    original_amount = _decimal(_cell(row, mapping, "original_amount"))
    single_negotiation_amount = _decimal(_cell(row, mapping, "single_negotiation_amount"))
    writeoff_amount = _decimal(_cell(row, mapping, "writeoff_amount"))
    deduction_amount = _decimal(_cell(row, mapping, "deduction_amount"))
    discount_amount = _decimal(_cell(row, mapping, "discount_amount"))
    negotiation_amount = _decimal(_cell(row, mapping, "negotiation_amount"))
    receivable_amount = _decimal(_cell(row, mapping, "receivable_amount"))
    arrears_change = _decimal(_cell(row, mapping, "arrears_change"))
    # In the real 明细 sheet, the shared ``实收`` header is a line amount;
    # it must not be mistaken for the 流水 sheet's order total.
    if is_detail and line_amount is None:
        line_amount = raw_total_amount
    total_amount = None if is_detail else (paid_amount if paid_amount is not None else raw_total_amount)
    total_from_line_amount = False
    if total_amount is None and is_detail and line_amount is not None:
        total_amount = line_amount
        total_from_line_amount = True
    insurance_amount = _decimal(_cell(row, mapping, "insurance_amount"))
    non_insurance_amount = _decimal(_cell(row, mapping, "non_insurance_amount"))
    self_pay_amount = _decimal(_cell(row, mapping, "self_pay_amount"))
    other_personal_amount = _decimal(_cell(row, mapping, "other_personal_amount"))
    if non_insurance_amount is not None:
        self_pay_amount = non_insurance_amount
    if self_pay_amount is None:
        self_pay_amount = other_personal_amount
    elif other_personal_amount is not None:
        self_pay_amount += other_personal_amount
    payment_type_raw = _text(_cell(row, mapping, "payment_type_raw")) or _text(_cell(row, mapping, "payment_method"))
    payment_type = _payment_type(payment_type_raw)
    transaction_operation = _text(_cell(row, mapping, "transaction_operation"))
    balance_payment_amount = _decimal(_cell(row, mapping, "balance_payment_amount"))
    transaction_kind = "balance_transaction" if _is_balance_transaction(
        _cell(row, mapping, "transaction_type"),
        _cell(row, mapping, "category_level_1"),
        _cell(row, mapping, "fee_category"),
        _cell(row, mapping, "item_name"),
    ) else "consumption"
    is_refund = resolve_is_refund(
        transaction_operation,
        paid_amount,
        total_amount,
        original_amount,
        receivable_amount,
        line_amount,
    )
    balance_payment_amount = resolve_balance_payment_amount(
        payment_type_raw,
        None,
        balance_payment_amount,
        paid_amount,
        total_amount,
    )
    if transaction_kind == "consumption" and balance_payment_amount is not None and insurance_amount is None and self_pay_amount is None:
        # A member-balance payment is a real self-pay settlement even when
        # ABC's ordinary ``实收`` column is blank/zero.  The dedicated balance
        # amount remains the source of truth; it is never inferred from a
        # fixed ratio.
        insurance_amount = Decimal("0")
        self_pay_amount = balance_payment_amount
        if total_amount == Decimal("0"):
            total_amount = balance_payment_amount
            paid_amount = balance_payment_amount
    if total_amount is None and insurance_amount is not None and self_pay_amount is not None:
        total_amount = insurance_amount + self_pay_amount
        paid_amount = total_amount
    visit_no = _text(_cell(row, mapping, "visit_no"))
    if not name and not phone and not external_customer_id and not external_transaction_id:
        return None, "缺少患者档案号、手机号和姓名，无法识别客户"
    if charged_at is None:
        return None, "缺少收费时间"
    has_consumption_record = any(
        value is not None and value != Decimal("0")
        for value in (
            original_amount,
            single_negotiation_amount,
            writeoff_amount,
            deduction_amount,
            discount_amount,
            negotiation_amount,
            receivable_amount,
            paid_amount,
            arrears_change,
            insurance_amount,
            non_insurance_amount,
            line_amount,
        )
    ) or charged_at is not None or bool(visit_no) or bool(
        _text(_cell(row, mapping, "item_name"))
        or _text(_cell(row, mapping, "item_code"))
        or _text(_cell(row, mapping, "category_level_1"))
        or _text(_cell(row, mapping, "fee_category"))
    )
    if not has_consumption_record:
        return None, "缺少有效收费时间、诊号、消费项目或金额字段"
    # A valid fee can have zero actual payment (for example, a fully deducted
    # item). Keep it as a transaction; zero is a real amount, not a skip flag.
    if total_amount is None:
        total_amount = paid_amount if paid_amount is not None else Decimal("0")
    if insurance_amount is None and self_pay_amount is None and payment_type == "insurance":
        insurance_amount, self_pay_amount = total_amount, Decimal("0")
    elif insurance_amount is None and self_pay_amount is None and payment_type == "self_pay":
        insurance_amount, self_pay_amount = Decimal("0"), total_amount
    elif insurance_amount is None and self_pay_amount is not None:
        if total_amount >= self_pay_amount:
            insurance_amount = total_amount - self_pay_amount
        else:
            return None, f"自费金额 {self_pay_amount} 大于总金额 {total_amount}"
    elif self_pay_amount is None and insurance_amount is not None:
        if total_amount >= insurance_amount:
            self_pay_amount = total_amount - insurance_amount
        else:
            return None, f"医保金额 {insurance_amount} 大于总金额 {total_amount}"
    mismatch_reason = None
    if insurance_amount is None or self_pay_amount is None:
        payment_split_status = "unknown"
    elif abs(total_amount - insurance_amount - self_pay_amount) > Decimal("0.01"):
        mismatch_reason = f"总金额 {total_amount} 不等于医保 {insurance_amount} + 自费 {self_pay_amount}"
        payment_split_status = "mismatch"
    else:
        payment_split_status = "verified"

    category_level_1 = _text(_cell(row, mapping, "category_level_1")) or _text(_cell(row, mapping, "fee_category"))
    category_level_2 = _text(_cell(row, mapping, "category_level_2"))
    category_level_3 = _text(_cell(row, mapping, "category_level_3"))
    item_name = _text(_cell(row, mapping, "item_name"))
    item_code = _text(_cell(row, mapping, "item_code"))
    category_key = item_code or item_name or ""
    category = category_lookup.get(category_key)
    if category:
        category_level_1 = category_level_1 or category.get("category_level_1")
        category_level_2 = category_level_2 or category.get("category_level_2")
        category_level_3 = category_level_3 or category.get("category_level_3")
    quantity = _decimal(_cell(row, mapping, "quantity")) or Decimal("1")
    unit_price = _decimal(_cell(row, mapping, "unit_price"))
    item_amount = line_amount if line_amount is not None else (unit_price * quantity if unit_price is not None else None)
    items = []
    if item_name or item_code or category_level_1 or item_amount is not None:
        items.append({
            "category_level_1": category_level_1,
            "category_level_2": category_level_2,
            "category_level_3": category_level_3,
            "item_name": item_name or "未命名项目",
            "item_code": item_code,
            "quantity": str(quantity),
            "unit": _text(_cell(row, mapping, "unit")),
            "unit_price": str(unit_price) if unit_price is not None else None,
            "amount": str(item_amount) if item_amount is not None else None,
            "specification": _text(_cell(row, mapping, "specification")),
            "manufacturer": _text(_cell(row, mapping, "manufacturer")),
            "item_note": _text(_cell(row, mapping, "item_note")),
        })
    if transaction_kind == "consumption" and balance_payment_amount is None and any(
        token in (_text(payment_type_raw) or "").lower()
        for token in ("会员卡", "会员余额", "储值", "余额支付", "储值卡", "prepaid", "balance")
    ):
        # Some exports expose only the payment label and put the amount in
        # the project/detail column while ordinary ``实收`` remains zero.
        # Use that explicit project amount only because ABC identified the
        # payment as prepaid; never estimate it from a fixed ratio.
        candidate = paid_amount if paid_amount and paid_amount > Decimal("0") else total_amount if total_amount and total_amount > Decimal("0") else item_amount
        if candidate is not None and candidate > Decimal("0"):
            balance_payment_amount = abs(candidate)
    if transaction_kind == "consumption" and balance_payment_amount is not None:
        if insurance_amount is None and self_pay_amount is None:
            insurance_amount = Decimal("0")
            self_pay_amount = balance_payment_amount
        if total_amount == Decimal("0"):
            total_amount = balance_payment_amount
            paid_amount = balance_payment_amount
        if insurance_amount is not None and self_pay_amount is not None:
            payment_split_status = "verified"
            mismatch_reason = None
    payment_method = _text(_cell(row, mapping, "payment_method")) or payment_type_raw
    return NormalizedTransaction(
        external_customer_id=external_customer_id,
        name=name,
        phone=phone,
        external_transaction_id=external_transaction_id,
        transaction_fingerprint=_fingerprint(external_customer_id, phone, name, visit_no, charged_at, payment_method, total_amount, external_transaction_id),
        visit_no=visit_no,
        charged_at=charged_at,
        payment_type=payment_type,
        payment_method=payment_method,
        payment_type_raw=payment_type_raw,
        transaction_kind=transaction_kind,
        transaction_operation=transaction_operation,
        is_refund=is_refund,
        balance_payment_amount=balance_payment_amount,
        total_amount=total_amount,
        original_amount=original_amount,
        single_negotiation_amount=single_negotiation_amount,
        writeoff_amount=writeoff_amount,
        deduction_amount=deduction_amount,
        deduction_amount_raw=deduction_amount,
        discount_amount=discount_amount,
        negotiation_amount=negotiation_amount,
        receivable_amount=receivable_amount,
        paid_amount=paid_amount if paid_amount is not None else total_amount,
        arrears_change=arrears_change,
        insurance_amount=insurance_amount,
        self_pay_amount=self_pay_amount,
        non_insurance_amount=non_insurance_amount,
        has_consumption_record=has_consumption_record,
        payment_split_status=payment_split_status,
        mismatch_reason=mismatch_reason,
        store=_text(_cell(row, mapping, "store")),
        organization=_text(_cell(row, mapping, "organization")),
        department=_text(_cell(row, mapping, "department")),
        staff_name=_text(_cell(row, mapping, "staff_name")),
        category_level_1=category_level_1,
        category_level_2=category_level_2,
        category_level_3=category_level_3,
        item_name=item_name,
        item_code=item_code,
        items=items,
        raw_data=_raw_row(headers, row),
        source_sheet=sheet_name,
        is_detail=is_detail,
        total_from_line_amount=total_from_line_amount,
    ), None


def _merge_rows(rows: list[NormalizedTransaction]) -> list[NormalizedTransaction]:
    merged: dict[str, NormalizedTransaction] = {}
    for transaction in rows:
        # 明细表通常没有订单号，且每一行金额不同；按患者+诊号+收费时间
        # 聚合，避免把同一笔流水的项目行误当成多笔消费。
        key = transaction.external_transaction_id or (
            f"detail:{_visit_key(transaction)}" if transaction.is_detail else transaction.transaction_fingerprint
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = transaction
            continue
        existing.items.extend(transaction.items)
        if transaction.transaction_kind == "balance_transaction":
            existing.transaction_kind = "balance_transaction"
        existing.transaction_operation = existing.transaction_operation or transaction.transaction_operation
        existing.is_refund = resolve_is_refund(
            existing.transaction_operation,
            existing.paid_amount,
            existing.total_amount,
            existing.original_amount,
            existing.receivable_amount,
            transaction.paid_amount,
            transaction.total_amount,
        )
        existing.balance_payment_amount = existing.balance_payment_amount or transaction.balance_payment_amount
        if existing.total_from_line_amount and transaction.total_from_line_amount:
            existing.total_amount += transaction.total_amount
            if existing.insurance_amount is not None and transaction.insurance_amount is not None:
                existing.insurance_amount += transaction.insurance_amount
            if existing.self_pay_amount is not None and transaction.self_pay_amount is not None:
                existing.self_pay_amount += transaction.self_pay_amount
        existing.name = existing.name or transaction.name
        existing.phone = existing.phone or transaction.phone
        existing.category_level_1 = existing.category_level_1 or transaction.category_level_1
        existing.category_level_2 = existing.category_level_2 or transaction.category_level_2
        existing.category_level_3 = existing.category_level_3 or transaction.category_level_3
        existing.item_name = existing.item_name or transaction.item_name
        existing.item_code = existing.item_code or transaction.item_code
        existing.raw_data.setdefault("detail_rows", []).append(transaction.raw_data)
        if existing.insurance_amount is not None and existing.self_pay_amount is not None:
            if abs(existing.total_amount - existing.insurance_amount - existing.self_pay_amount) <= Decimal("0.01"):
                existing.payment_split_status = "verified"
            else:
                existing.payment_split_status = "mismatch"
                existing.mismatch_reason = f"总金额 {existing.total_amount} 不等于医保 {existing.insurance_amount} + 自费 {existing.self_pay_amount}"
    return list(merged.values())


def parse_excel(data: bytes, file_name: str) -> ParseResult:
    suffix = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""
    if suffix not in {"xlsx", "xls"}:
        raise ExcelParseError("只支持 .xlsx 或 .xls 文件")
    if not data:
        raise ExcelParseError("上传文件为空")
    try:
        sheets = _read_xlsx(data) if suffix == "xlsx" else _read_xls(data)
    except Exception as exc:
        raise ExcelParseError(f"Excel 文件解析失败：{exc}") from exc
    if not sheets:
        raise ExcelParseError("Excel 不包含可读取的 Sheet")

    category_lookup: dict[str, dict[str, str | None]] = {}
    parsed_rows: list[NormalizedTransaction] = []
    detail_rows: list[NormalizedTransaction] = []
    errors: list[dict[str, Any]] = []
    total_rows = 0
    recognized_transaction_sheet = False
    patient_keys: set[str] = set()
    sheet_stats: list[dict[str, Any]] = []

    def new_stat(sheet_name: str) -> dict[str, Any]:
        return {
            "sheet_name": sheet_name,
            "recognized": False,
            "record_count": 0,
            "valid_record_count": 0,
            "error_rows": 0,
            "recognized_fields": [],
        }

    stats_by_name = {sheet_name: new_stat(sheet_name) for sheet_name, *_ in sheets}

    def missing_fields(sheet_name: str, mapping: dict[str, int]) -> list[str]:
        identity = {"external_customer_id", "phone", "name"} & mapping.keys()
        if sheet_name == "流水":
            required = [("收费时间", "charged_at"), ("患者档案号/手机号/患者姓名", "identity"), ("实收", "amount"), ("支付方式", "payment_method")]
        elif sheet_name == "分类":
            required = [("收费时间", "charged_at"), ("患者档案号/手机号/患者姓名", "identity"), ("费用分类", "fee_category"), ("实收", "amount")]
        elif sheet_name == "明细":
            required = [("收费时间", "charged_at"), ("患者档案号/手机号/患者姓名", "identity"), ("一级分类", "category_level_1"), ("药品/项目名称", "item_name")]
        else:
            return []
        return [
            label
            for label, field_name in required
            if (field_name == "identity" and not identity)
            or (field_name == "amount" and not ({"paid_amount", "total_amount"} & mapping.keys()))
            or (field_name not in {"identity", "amount"} and field_name not in mapping)
        ]
    # Read category dictionaries first so a 分类 sheet can appear before or
    # after 流水/明细 without changing the imported result.
    for sheet_name, first_row, rows, _datemode in sheets:
        stat = stats_by_name[sheet_name]
        if not _is_category_sheet(sheet_name):
            continue
        header_info = _header_and_rows(first_row, rows, require_transaction_fields=False)
        if not header_info:
            errors.append({"sheet": sheet_name, "row": 1, "message": "未识别表头：分类表至少需要患者标识、收费时间、费用分类和实收"})
            stat["error_rows"] += 1
            continue
        header_row, mapping, data_rows = header_info
        stat["recognized"] = True
        stat["recognized_fields"] = _recognized_fields(header_row, mapping)
        stat["record_count"] = sum(1 for row in data_rows if any(_text(value) is not None for value in row))
        stat["valid_record_count"] = stat["record_count"]
        for row in data_rows:
            key = _text(_cell(row, mapping, "item_code")) or _text(_cell(row, mapping, "item_name"))
            if key:
                category_lookup[key] = {field_name: _text(_cell(row, mapping, field_name)) for field_name in ("category_level_1", "category_level_2", "category_level_3")}
            identity = _text(_cell(row, mapping, "external_customer_id")) or normalize_phone(_text(_cell(row, mapping, "phone"))) or _text(_cell(row, mapping, "name"))
            if identity:
                patient_keys.add(identity)

    for sheet_name, first_row, rows, datemode in sheets:
        stat = stats_by_name[sheet_name]
        if _is_category_sheet(sheet_name):
            continue
        header_info = _header_and_rows(first_row, rows)
        if not header_info:
            if sheet_name in {"流水", "明细"}:
                errors.append({"sheet": sheet_name, "row": 1, "message": "未识别表头：请确认使用真实 ABC 表头（流水需要收费时间、患者标识、实收、支付方式；明细需要收费时间、患者标识、一级分类、药品/项目名称）"})
                stat["error_rows"] += 1
            continue
        recognized_transaction_sheet = True
        header_row, mapping, data_rows = header_info
        stat["recognized"] = True
        stat["recognized_fields"] = _recognized_fields(header_row, mapping)
        missing = missing_fields(sheet_name, mapping)
        if missing:
            errors.append({"sheet": sheet_name, "row": 1, "message": f"缺少字段：{'、'.join(missing)}"})
            stat["error_rows"] += 1
        is_detail = _is_detail_sheet(sheet_name)
        for row_number, row in enumerate(data_rows, start=2):
            if not any(_text(value) is not None for value in row):
                continue
            stat["record_count"] += 1
            total_rows += 1
            transaction, error = _parse_row(sheet_name, header_row, row, mapping, datemode, is_detail, category_lookup)
            if error:
                errors.append({"sheet": sheet_name, "row": row_number, "message": error, "raw_data": _raw_row(header_row, row)})
                stat["error_rows"] += 1
            elif transaction:
                (detail_rows if is_detail else parsed_rows).append(transaction)
                stat["valid_record_count"] += 1
                patient_keys.add(_patient_key(transaction))

    if not recognized_transaction_sheet:
        raise ExcelParseError("未找到可识别的‘流水’或‘明细’表，请检查 Sheet 名称和真实 ABC 表头")

    parsed_rows = _merge_rows(parsed_rows)
    detail_rows = _merge_rows(detail_rows)
    if parsed_rows:
        main_by_key = {item.external_transaction_id or item.transaction_fingerprint: item for item in parsed_rows}
        main_by_visit = {_visit_key(item): item for item in parsed_rows}
        for detail in detail_rows:
            key = detail.external_transaction_id or detail.transaction_fingerprint
            main = main_by_key.get(key) or main_by_visit.get(_visit_key(detail))
            if main is None:
                parsed_rows.append(detail)
                main_by_key[key] = detail
                main_by_visit[_visit_key(detail)] = detail
                continue
            main.items.extend(detail.items)
            if detail.transaction_kind == "balance_transaction":
                main.transaction_kind = "balance_transaction"
            main.transaction_operation = main.transaction_operation or detail.transaction_operation
            main.is_refund = resolve_is_refund(
                main.transaction_operation,
                main.paid_amount,
                main.total_amount,
                main.original_amount,
                main.receivable_amount,
                detail.paid_amount,
                detail.total_amount,
            )
            main.balance_payment_amount = main.balance_payment_amount or detail.balance_payment_amount
            main.raw_data.setdefault("detail_rows", []).append(detail.raw_data)
            main.category_level_1 = main.category_level_1 or detail.category_level_1
            main.category_level_2 = main.category_level_2 or detail.category_level_2
            main.category_level_3 = main.category_level_3 or detail.category_level_3
            main.item_name = main.item_name or detail.item_name
            main.item_code = main.item_code or detail.item_code
    else:
        parsed_rows = detail_rows
    return ParseResult([sheet[0] for sheet in sheets], parsed_rows, errors, total_rows, list(stats_by_name.values()), len(patient_keys))
