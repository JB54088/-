"use client";

import { useEffect, useState } from "react";

import { formatMoney } from "./charts";
import { Badge, Empty, Loading } from "./ui";
import { apiFetch } from "../lib/api";
import { formatBusinessDate24h } from "../lib/datetime";

type ReportPeriod = "week" | "month";

type ReportData = {
  period_type: ReportPeriod;
  period_start: string;
  period_end: string;
  ai_summary: string;
  metrics: {
    total_customers: number;
    assigned_customers: number;
    unassigned_customers: number;
    total_revenue: number;
    revenue: number;
    growth_rate: number;
    new_customers: number;
    period_insurance: number;
    period_self_pay: number;
    recharge: number;
    refund: number;
    current_prepaid_balance: number;
    insurance_ratio: number;
    self_pay_ratio: number;
    salesperson_performance: {
      id: number;
      name: string;
      customer_count: number;
      period_revenue: number;
      period_insurance: number;
      period_self_pay: number;
      new_customers: number;
      high_value_customers: number;
    }[];
    source_analysis: {
      code: string;
      name: string;
      customer_count: number;
      new_customers: number;
      customer_percentage: number;
      period_revenue: number;
    }[];
    top_customers: { id: number; name: string; total_spend: number }[];
  };
};

const fmtDate = formatBusinessDate24h;

function Metric({ label, value, hint, tone = "text-[#182230]" }: { label: string; value: string; hint?: string; tone?: string }) {
  return <div className="rounded-xl border border-[#e7ebf0] bg-white p-3 shadow-sm"><div className="text-[11px] text-[#98a2b3]">{label}</div><div className={`mt-1 text-lg font-semibold ${tone}`}>{value}</div>{hint && <div className="mt-1 text-[11px] text-[#98a2b3]">{hint}</div>}</div>;
}

export function ReportDrawer({ open, period, onPeriodChange, onClose }: { open: boolean; period: ReportPeriod; onPeriodChange: (period: ReportPeriod) => void; onClose: () => void }) {
  const [report, setReport] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previousOverflow; };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    apiFetch<ReportData>(`/reports?period=${period}`).then((value) => { if (!cancelled) setReport(value); }).catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "报告加载失败"); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, period]);

  if (!open) return null;
  const m = report?.metrics;
  const periodLabel = period === "week" ? "本周" : "本月";

  return <div className="fixed inset-0 z-50 flex justify-end bg-[#182230]/35" role="dialog" aria-modal="true" aria-label={`${periodLabel}经营报告`}>
    <button aria-label="关闭报告" onClick={onClose} className="absolute inset-0" />
    <section className="relative z-10 flex h-full w-full max-w-[760px] flex-col overflow-hidden bg-[#f7f9fc] shadow-2xl">
      <header className="flex flex-none items-center justify-between border-b border-[#e7ebf0] bg-white px-4 py-3 md:px-6 md:py-4">
        <div><div className="text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">BUSINESS REVIEW</div><h2 className="mt-1 text-[18px] font-semibold text-[#182230]">经营报告</h2></div>
        <div className="flex items-center gap-2"><div className="flex rounded-lg border border-[#e7ebf0] bg-[#fbfcfe] p-1"><button onClick={() => onPeriodChange("week")} className={`min-h-9 rounded-md px-3 text-xs font-medium ${period === "week" ? "bg-[#182230] text-white" : "text-[#667085]"}`}>周报</button><button onClick={() => onPeriodChange("month")} className={`min-h-9 rounded-md px-3 text-xs font-medium ${period === "month" ? "bg-[#182230] text-white" : "text-[#667085]"}`}>月报</button></div><button onClick={onClose} aria-label="关闭" className="flex h-10 w-10 items-center justify-center rounded-full bg-[#f7f9fc] text-xl text-[#667085]">×</button></div>
      </header>
      <main className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 md:px-6 md:py-5">
        {loading ? <Loading label={`正在生成${periodLabel}`}/> : error ? <div className="rounded-xl border border-[#ffd8d3] bg-[#fff5f3] p-4 text-sm text-[#c24e43]">{error}</div> : report && m ? <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-[#98a2b3]"><span className="rounded-full bg-[#eaf4ff] px-3 py-1.5 font-medium text-[#1d6fd1]">{periodLabel}报告</span><span>{fmtDate(report.period_start)} — {fmtDate(report.period_end)}</span><Badge tone="green">数据库自动生成</Badge></div>
          <section className="rounded-xl border border-[#d5e7fa] bg-[#f7fbff] p-4"><div className="mb-2 flex items-center gap-2"><span className="text-sm text-[#3488e8]">✦</span><span className="text-sm font-semibold text-[#182230]">经营摘要</span><Badge tone="blue">规则生成</Badge></div><p className="text-sm leading-6 text-[#667085]">{report.ai_summary}</p></section>
          <section><div className="mb-2 text-sm font-semibold text-[#182230]">核心经营指标</div><div className="grid grid-cols-2 gap-3 md:grid-cols-4"><Metric label="客户总数" value={String(m.total_customers)} hint={`已分配 ${m.assigned_customers} · 待分配 ${m.unassigned_customers}`}/><Metric label={`${periodLabel}新增客户`} value={String(m.new_customers)}/><Metric label={`${periodLabel}有效经营收入`} value={formatMoney(m.revenue, true)} tone="text-[#182230]"/><Metric label="累计有效经营收入" value={formatMoney(m.total_revenue, true)}/><Metric label={`${periodLabel}医保支付`} value={formatMoney(m.period_insurance, true)} tone="text-[#3488e8]" hint={`占比 ${m.insurance_ratio}%`}/><Metric label={`${periodLabel}自费支付`} value={formatMoney(m.period_self_pay, true)} tone="text-[#07875f]" hint={`占比 ${m.self_pay_ratio}%`}/><Metric label={`${periodLabel}充值`} value={formatMoney(m.recharge, true)} tone="text-[#07875f]"/><Metric label={`${periodLabel}退款`} value={formatMoney(m.refund, true)} tone="text-[#a56b00]"/><Metric label="当前储值余额" value={formatMoney(m.current_prepaid_balance, true)} tone="text-[#7d5ac7]"/><Metric label="环比变化" value={`${m.growth_rate >= 0 ? "↑" : "↓"} ${Math.abs(m.growth_rate)}%`} tone={m.growth_rate >= 0 ? "text-[#07875f]" : "text-[#c24e43]"}/></div></section>
          <section className="rounded-xl border border-[#e7ebf0] bg-white p-4"><div className="mb-3 text-sm font-semibold text-[#182230]">业务员表现</div><div className="space-y-2">{m.salesperson_performance.map((item) => <div key={item.id} className="rounded-lg bg-[#fbfcfe] p-3"><div className="flex items-center justify-between gap-3"><span className="text-sm font-medium text-[#182230]">{item.name}</span><span className="text-sm font-semibold text-[#182230]">{formatMoney(item.period_revenue, true)}</span></div><div className="mt-2 grid grid-cols-3 gap-2 text-[11px] text-[#667085]"><span>客户 {item.customer_count}</span><span>新增 {item.new_customers}</span><span>高价值 {item.high_value_customers}</span></div><div className="mt-2 grid grid-cols-2 gap-2 text-[11px]"><span className="rounded-lg bg-[#f2f8ff] px-2 py-1.5 text-[#3488e8]">医保 {formatMoney(item.period_insurance, true)}</span><span className="rounded-lg bg-[#f1fbf7] px-2 py-1.5 text-[#07875f]">自费 {formatMoney(item.period_self_pay, true)}</span></div></div>)}{!m.salesperson_performance.length && <Empty label="暂无业务员数据"/>}</div></section>
          <section className="rounded-xl border border-[#e7ebf0] bg-white p-4"><div className="mb-3 text-sm font-semibold text-[#182230]">来源结构</div>{m.source_analysis.length ? <div className="space-y-2">{m.source_analysis.map((item) => <div key={item.code} className="flex items-center justify-between gap-3 rounded-lg bg-[#fbfcfe] px-3 py-2.5"><div><div className="text-sm font-medium text-[#182230]">{item.name}</div><div className="mt-1 text-[11px] text-[#98a2b3]">客户 {item.customer_count} · 新增 {item.new_customers} · 占比 {item.customer_percentage}%</div></div><span className="shrink-0 text-sm font-semibold text-[#182230]">{formatMoney(item.period_revenue, true)}</span></div>)}</div> : <Empty label="暂无来源数据"/>}</section>
          <section className="rounded-xl border border-[#e7ebf0] bg-white p-4"><div className="mb-3 text-sm font-semibold text-[#182230]">高价值客户</div>{m.top_customers.length ? <div className="divide-y divide-[#f0f2f5]">{m.top_customers.slice(0, 10).map((item, index) => <div key={item.id} className="flex items-center justify-between gap-3 py-2.5"><div className="min-w-0"><span className="mr-2 text-[11px] text-[#98a2b3]">TOP {index + 1}</span><span className="text-sm font-medium text-[#182230]">{item.name}</span></div><span className="shrink-0 text-sm font-semibold text-[#182230]">{formatMoney(item.total_spend, true)}</span></div>)}</div> : <Empty label="暂无高价值客户"/>}</section>
        </div> : <Empty label="暂无报告数据"/>}
      </main>
    </section>
  </div>;
}

export type { ReportPeriod };
