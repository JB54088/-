import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import CustomerTag, User
from ...source_categories import SOURCE_LEVEL_1_LABELS, SOURCE_LEVEL_2_OPTIONS
from .schemas import QueryFilters, QueryPlan, TimeRange


class AgentQuestionError(ValueError):
    pass


READONLY_REJECTION = "当前 AI 经营助手仅支持经营数据查询，不执行数据修改、客户分配、标签修改、文件上传或消息发送。"
UNSUPPORTED_MESSAGE = "我还不能准确理解这个问题，可以尝试询问客户数量、消费、医保、自费、来源、业务员或充值退款。"


def _time_range(question: str) -> TimeRange:
    if re.search(r"上月|上个月", question):
        return TimeRange(type="last_month")
    if re.search(r"上周", question):
        return TimeRange(type="last_week")
    if re.search(r"最近\s*7\s*天|近\s*7\s*天", question):
        return TimeRange(type="last_7_days")
    if re.search(r"最近\s*30\s*天|近\s*30\s*天", question):
        return TimeRange(type="last_30_days")
    dates = re.findall(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})", question)
    if len(dates) >= 2:
        start = date(int(dates[0][0]), int(dates[0][1]), int(dates[0][2]))
        end = date(int(dates[1][0]), int(dates[1][1]), int(dates[1][2]))
        return TimeRange(type="custom", start_date=start, end_date=end)
    month_match = re.search(r"(20\d{2})[年./-](\d{1,2})月?", question)
    if month_match:
        year, month = int(month_match.group(1)), int(month_match.group(2))
        start = date(year, month, 1)
        next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        return TimeRange(type="custom", start_date=start, end_date=next_month - timedelta(days=1))
    if re.search(r"今天|今日", question):
        return TimeRange(type="today")
    if re.search(r"本周|这周|本星期", question):
        return TimeRange(type="week")
    if re.search(r"累计|全部|历史|总计", question):
        return TimeRange(type="all")
    return TimeRange(type="month")


def _source_filters(question: str) -> tuple[str | None, str | None]:
    level_2: list[tuple[str, str, str]] = []
    for level_1, options in SOURCE_LEVEL_2_OPTIONS.items():
        for option in options:
            level_2.append((option["name"], option["code"], level_1))
    for name, code, level_1 in sorted(level_2, key=lambda item: len(item[0]), reverse=True):
        if name in question or code in question:
            return level_1, code
    for code, name in SOURCE_LEVEL_1_LABELS.items():
        if name in question or code in question:
            return code, None
    return None, None


def _owner_name(question: str, db: Session) -> str | None:
    names = [row[0] for row in db.execute(select(User.full_name).where(User.role == "salesperson", User.is_active.is_(True))).all()]
    for name in sorted((value for value in names if value), key=len, reverse=True):
        if name in question:
            return name
    return None


def _tag_name(question: str, db: Session) -> str | None:
    names = [row[0] for row in db.execute(select(CustomerTag.name)).all()]
    for name in sorted((value for value in names if value), key=len, reverse=True):
        if name in question:
            return name
    return None


def build_query_plan(question: str, db: Session) -> QueryPlan:
    normalized = question.strip()
    if re.search(r"删除|修改|分配|重新分配|创建|新建|上传|导入|打标签|改标签|发微信|发送消息|退款给|调整余额", normalized):
        raise AgentQuestionError(READONLY_REJECTION)

    source_level_1, source_level_2 = _source_filters(normalized)
    filters = QueryFilters(
        owner_name=_owner_name(normalized, db),
        source_level_1=source_level_1,
        source_level_2=source_level_2,
        tag_name=_tag_name(normalized, db),
    )
    threshold = re.search(r"(?:超过|大于|高于)\s*([\d,.]+)\s*(?:元|块)?", normalized)
    if threshold:
        filters.min_consumption = float(threshold.group(1).replace(",", ""))

    wants_customer_count = bool(re.search(r"有多少客户|客户有多少|多少个客户|客户数量|客户数", normalized))
    if wants_customer_count:
        metric = "customer_count"
    elif re.search(r"医保.{0,5}自费|自费.{0,5}医保", normalized):
        metric = "payment_mix"
    elif re.search(r"充值.{0,5}退款|退款.{0,5}充值", normalized):
        metric = "balance_mix"
    elif re.search(r"充值.{0,8}(?:余额|储值)|(?:余额|储值).{0,8}充值", normalized):
        metric = "balance_overview"
    elif re.search(r"当前会员储值余额|当前储值余额|会员余额|储值余额", normalized):
        metric = "prepaid_balance"
    elif re.search(r"累计使用储值|使用储值|储值消费", normalized):
        metric = "prepaid_spent"
    elif re.search(r"退款|退费", normalized):
        metric = "refund_amount"
    elif re.search(r"充值|储值充值", normalized):
        metric = "recharge_amount"
    elif re.search(r"医保", normalized):
        metric = "insurance_amount"
    elif re.search(r"自费", normalized):
        metric = "self_pay_amount"
    elif re.search(r"有效经营收入|有效收入|营业收入|经营收入|收入", normalized):
        metric = "effective_revenue"
    elif re.search(r"客单价|平均消费", normalized):
        metric = "average_order_value"
    elif re.search(r"消费次数|消费几次|几次消费", normalized):
        metric = "consumption_count"
    elif re.search(r"新增客户|新增线索|新增|新客户", normalized):
        metric = "new_customer_count"
    elif re.search(r"待分配", normalized):
        metric = "unassigned_customer_count"
    elif re.search(r"已分配", normalized):
        metric = "assigned_customer_count"
    elif re.search(r"客户|消费", normalized):
        metric = "total_consumption"
    else:
        raise AgentQuestionError(UNSUPPORTED_MESSAGE)

    group_by = None
    if re.search(r"业务员|负责人|归属", normalized):
        group_by = "owner"
    elif "二级来源" in normalized or (source_level_1 and source_level_2):
        group_by = "source_level_2"
    elif "来源" in normalized:
        group_by = "source_level_1"
    elif re.search(r"前\s*\d+\s*个客户|哪些客户|客户排行|客户排名", normalized):
        group_by = "customer"
    elif re.search(r"趋势|每天|每日|走势", normalized):
        group_by = "date"

    limit_match = re.search(r"前\s*(\d+)", normalized)
    wants_breakdown = bool(re.search(r"各|分别|分布|对比|按|每个|列表", normalized))
    limit = min(int(limit_match.group(1)), 50) if limit_match else (10 if group_by in {"owner", "source_level_1", "source_level_2"} and wants_breakdown else (1 if group_by in {"owner", "source_level_1", "source_level_2"} else 10))
    return QueryPlan(metric=metric, time_range=_time_range(normalized), filters=filters, group_by=group_by, limit=limit)
