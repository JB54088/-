"""Application service for the read-only business-analysis assistant."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ...config import settings
from .executor import METRIC_LABELS, execute_query_plan
from .planner import AgentQuestionError, build_query_plan
from .schemas import AgentQueryResponse, ChartPayload, QueryPlan, TimeRange


COUNT_METRICS = {"customer_count", "new_customer_count", "assigned_customer_count", "unassigned_customer_count", "consumption_count"}


def _value(metric: str, raw: Any) -> str:
    if metric in COUNT_METRICS:
        return f"{int(raw or 0):,}"
    return f"¥{float(raw or 0):,.2f}"


def _answer(plan: QueryPlan, result: dict[str, Any]) -> str:
    metric = plan.metric
    label = METRIC_LABELS[metric]
    range_label = result.get("range_label", "当前周期")
    rows = result.get("rows") or []
    if metric == "payment_mix":
        if plan.group_by:
            if not rows:
                return f"{range_label}暂无支付类型数据。"
            top = rows[0]
            return f"{range_label}{top['label']}有效经营收入最高，为 {_value('effective_revenue', top['value'])}；医保 {_value('insurance_amount', top.get('insurance'))}，自费 {_value('self_pay_amount', top.get('self_pay'))}。"
        values = {row["label"]: row["value"] for row in rows}
        return (
            f"{range_label}有效经营收入 {_value('effective_revenue', values.get('有效经营收入'))}，"
            f"医保支付 {_value('insurance_amount', values.get('医保支付'))}，"
            f"自费支付 {_value('self_pay_amount', values.get('自费支付'))}。"
        )
    if metric == "balance_mix":
        values = {row["label"]: row["value"] for row in rows}
        return f"{range_label}充值 {_value('recharge_amount', values.get('充值'))}，退款 {_value('refund_amount', values.get('退款'))}。"
    if metric == "balance_overview":
        values = {row["label"]: row["value"] for row in rows}
        return f"当前储值余额 {_value('prepaid_balance', values.get('当前储值余额'))}，累计充值 {_value('recharge_amount', values.get('累计充值'))}，累计退款 {_value('refund_amount', values.get('累计退款'))}。"
    if rows:
        top = rows[0]
        return f"{range_label}{label}最高的是{top['label']}，为 {_value(metric, top['value'])}。"
    if metric == "prepaid_balance":
        return f"当前会员储值余额为 {_value(metric, result.get('value'))}。"
    return f"{range_label}{label}为 {_value(metric, result.get('value'))}。"


def _chart(plan: QueryPlan, result: dict[str, Any]) -> ChartPayload | None:
    rows = result.get("rows") or []
    if not rows:
        return None
    chart_type = "line" if plan.group_by == "date" else ("pie" if plan.metric in {"payment_mix", "balance_mix", "balance_overview"} else "bar")
    return ChartPayload(type=chart_type, title=METRIC_LABELS[plan.metric], data=[{"label": str(row["label"]), "value": float(row["value"] or 0)} for row in rows])


def run_business_query(db: Session, question: str) -> AgentQueryResponse:
    plan = build_query_plan(question, db)
    result = execute_query_plan(db, plan)
    model_name = settings.ai_model if settings.ai_mock_mode else f"{settings.ai_provider}/{settings.ai_model}"
    return AgentQueryResponse(
        answer=_answer(plan, result),
        data=result,
        query_plan=plan,
        chart=_chart(plan, result),
        model_name=model_name,
    )


def rejected_response(message: str) -> AgentQueryResponse:
    plan = QueryPlan(metric="customer_count", time_range=TimeRange(type="month"))
    return AgentQueryResponse(
        answer=message,
        data={"status": "rejected"},
        query_plan=plan,
        chart=None,
        model_name=settings.ai_model if settings.ai_mock_mode else f"{settings.ai_provider}/{settings.ai_model}",
    )


__all__ = ["AgentQuestionError", "rejected_response", "run_business_query"]
