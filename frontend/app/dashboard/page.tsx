"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AppShell, useCurrentUser } from "../../components/app-shell";
import BusinessAgentButton from "../../components/business-agent/BusinessAgentButton";
import { Donut, formatMoney, HorizontalBars, Sparkline } from "../../components/charts";
import { Badge, Empty, Loading, MobileSheet, SectionTitle } from "../../components/ui";
import { ReportDrawer, type ReportPeriod } from "../../components/report-drawer";
import { Icon } from "../../components/icons";
import { apiFetch } from "../../lib/api";
import { formatBusinessDateTime24h } from "../../lib/datetime";
import type { DashboardData } from "../../types";

const periods = [{ key: "today", label: "今日" }, { key: "week", label: "本周" }, { key: "month", label: "本月" }, { key: "custom", label: "自定义" }];

function KpiCard({ label, value, hint, accent = "blue" }: { label: string; value: string; hint?: string; accent?: "blue" | "green" | "amber" | "purple" }) {
  const colors = { blue: "#3488e8", green: "#13b887", amber: "#f4b740", purple: "#9b78df" };
  return <div className="min-h-[84px] rounded-2xl border border-[#e7ebf0] bg-white p-3 shadow-soft md:min-h-[92px] md:p-4"><div className="text-xs text-[#98a2b3]">{label}</div><div className="mt-2 text-[23px] font-semibold tracking-tight text-[#182230] md:text-[25px]">{value}</div>{hint && <div className="mt-2 flex items-center gap-1 text-[11px] text-[#98a2b3]"><span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: colors[accent] }}/><span className="truncate">{hint}</span></div>}</div>;
}

function PaymentSplitSection({ kpi, periodLabel }: { kpi: DashboardData["kpis"]; periodLabel: string }) {
  const periodKnown = kpi.period_payment_split_unknown_orders === 0;
  const amount = (value: number) => formatMoney(value, true);
  const ratio = (value: number) => `${value}%`;
  return <section className="mb-5 rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft md:p-5"><SectionTitle eyebrow="PAYMENT MIX" title="支付类型分析" description={periodKnown ? `${periodLabel}有效经营收入按 ABC Excel 支付口径拆分` : `${periodLabel}有 ${kpi.period_payment_split_unknown_orders} 笔订单尚未提供完整医保/自费金额；下方金额仍按已导入的真实支付字段汇总`}/><div className="grid grid-cols-2 gap-3 lg:grid-cols-6"><div className="rounded-xl bg-[#fbfcfe] p-3"><div className="text-[11px] text-[#98a2b3]">{periodLabel}有效经营收入</div><div className="mt-1 text-lg font-semibold text-[#182230]">{formatMoney(kpi.period_revenue, true)}</div></div><div className="rounded-xl bg-[#f2f8ff] p-3"><div className="text-[11px] text-[#98a2b3]">医保支付</div><div className="mt-1 text-lg font-semibold text-[#3488e8]">{amount(kpi.period_insurance)}</div><div className="mt-1 text-[11px] text-[#98a2b3]">占比 {ratio(kpi.insurance_ratio)}</div></div><div className="rounded-xl bg-[#f1fbf7] p-3"><div className="text-[11px] text-[#98a2b3]">自费支付</div><div className="mt-1 text-lg font-semibold text-[#07875f]">{amount(kpi.period_self_pay)}</div><div className="mt-1 text-[11px] text-[#98a2b3]">占比 {ratio(kpi.self_pay_ratio)}</div></div><div className="rounded-xl bg-[#fbfcfe] p-3"><div className="text-[11px] text-[#98a2b3]">累计拆分</div><div className="mt-1 text-sm font-semibold text-[#182230]">医保 {amount(kpi.total_insurance)}</div><div className="mt-1 text-sm font-semibold text-[#07875f]">自费 {amount(kpi.total_self_pay)}</div></div><div className="rounded-xl bg-[#fff8e8] p-3"><div className="text-[11px] text-[#98a2b3]">抵扣调整</div><div className="mt-1 text-lg font-semibold text-[#d97706]">{formatMoney(kpi.period_deduction, true)}</div><div className="mt-1 text-[11px] text-[#98a2b3]">保留 ABC 原始抵扣金额，避免重复计入</div></div><div className="rounded-xl bg-[#fbfcfe] p-3"><div className="text-[11px] text-[#98a2b3]">优惠调整</div><div className="mt-1 text-lg font-semibold text-[#667085]">{formatMoney(kpi.period_discount, true)}</div><div className="mt-1 text-[11px] text-[#98a2b3]">保留 ABC 原始口径</div></div></div><div className="mt-3 rounded-xl border border-[#f0f2f5] px-3 py-2 text-xs text-[#667085]">{periodLabel}有效经营收入 {formatMoney(kpi.period_revenue, true)} · 医保 {amount(kpi.period_insurance)} · 自费 {amount(kpi.period_self_pay)} · 抵扣 {formatMoney(kpi.period_deduction, true)} · 优惠 {formatMoney(kpi.period_discount, true)}</div></section>;
}

function SourceAnalysisSection({ rows, level2Rows }: { rows: DashboardData["source_analysis"]; level2Rows: DashboardData["source_level_2_analysis"] }) {
  const [expandedCodes, setExpandedCodes] = useState<Set<string>>(new Set());

  const toggle = (code: string) => {
    setExpandedCodes((current) => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  return <section className="mt-5 rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft md:p-5">
    <SectionTitle eyebrow="SOURCE ANALYSIS" title="一级来源归档分析" description="点击一级来源查看对应二级来源，默认收起"/>
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {rows.map((item) => {
        const expanded = expandedCodes.has(item.code);
        const children = level2Rows.filter((child) => child.level_1_code === item.code);
        return <article key={item.code} className={`overflow-hidden rounded-xl border transition-colors ${expanded ? "border-[#cfe4f8] bg-white" : "border-transparent bg-[#fbfcfe]"}`}>
          <button type="button" aria-expanded={expanded} onClick={() => toggle(item.code)} className="flex min-h-[128px] w-full items-start justify-between gap-3 p-3 text-left hover:bg-[#f7fbff]">
            <span className="min-w-0">
              <span className="block text-sm font-medium text-[#182230]">{item.name}</span>
              <span className="mt-2 block text-xs text-[#667085]">{item.customer_count} 位 · {item.customer_percentage}%</span>
              <span className="mt-2 block text-xs font-semibold text-[#182230]">累计 {formatMoney(item.total_revenue, true)}</span>
              <span className="mt-1 block text-[10px] text-[#98a2b3]">周 {formatMoney(item.week_revenue, true)} · 月 {formatMoney(item.month_revenue, true)}</span>
            </span>
            <span className="flex shrink-0 items-center gap-1 pt-0.5 text-[11px] font-medium text-[#3488e8]">
              {expanded ? "收起" : "展开"}
              <span className={`transition-transform ${expanded ? "rotate-180" : ""}`}><Icon name="chevron" size={15}/></span>
            </span>
          </button>
          {expanded && <div className="border-t border-[#edf1f5] p-3">
            {children.length ? <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {children.map((child) => <div key={`${child.level_1_code}-${child.code}`} className="rounded-lg border border-[#edf1f5] bg-[#fbfcfe] p-2.5">
                <div className="truncate text-xs font-medium text-[#182230]">{child.name}</div>
                <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[10px] text-[#667085]">
                  <span>客户 {child.customer_count}</span>
                  <span>新增 {child.new_customers ?? "—"}</span>
                  <span>收入 {formatMoney(child.total_revenue, true)}</span>
                  <span>消费 {formatMoney(child.total_consumption, true)}</span>
                </div>
              </div>)}
            </div> : <Empty label="暂无二级来源数据"/>}
          </div>}
        </article>;
      })}
    </div>
  </section>;
}

function PrepaidBalanceSection({ kpi, isAdmin, periodLabel }: { kpi: DashboardData["kpis"]; isAdmin: boolean; periodLabel: string }) {
  const compactCard = (label: string, value: string, accent: "blue" | "green" | "amber" | "purple" = "blue") => {
    const colors = { blue: "text-[#182230]", green: "text-[#07875f]", amber: "text-[#a56b00]", purple: "text-[#7d5ac7]" };
    return <div className="min-h-[82px] rounded-xl border border-[#e7ebf0] bg-white px-3 py-2.5 shadow-sm md:min-h-[94px] md:px-4 md:py-3"><div className="text-[11px] leading-4 text-[#98a2b3] md:text-xs">{label}</div><div className={`mt-1 text-[21px] font-semibold leading-7 tracking-tight md:text-[23px] ${colors[accent]}`}>{value}</div></div>;
  };
  return <section className="mt-5 mb-5 rounded-2xl border border-[#d8e9fb] bg-[#f7fbff] p-3 shadow-soft md:mt-6 md:p-4"><div className="mb-3"><div className="mb-0.5 text-[9px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">PREPAID BALANCE</div><h2 className="text-[15px] font-semibold leading-5 tracking-tight text-[#182230] md:text-base">{isAdmin ? "会员储值总览" : "我的会员储值"}</h2><p className="mt-0.5 text-[11px] leading-4 text-[#98a2b3]">充值和退款不直接计入营业收入；真实储值消费才计入消费统计。</p></div><div className="grid grid-cols-2 gap-2.5 md:gap-3 lg:grid-cols-4">{compactCard("当前储值余额", formatMoney(kpi.current_prepaid_balance, true))}{compactCard(`${periodLabel}充值`, formatMoney(kpi.period_recharge, true), "green")}{compactCard(`${periodLabel}退款`, formatMoney(kpi.period_refund, true), "amber")}{compactCard("累计充值", formatMoney(kpi.total_recharge, true), "purple")}</div></section>;
}

const dateTime = formatBusinessDateTime24h;

export default function DashboardPage() {
  const isAdmin = useCurrentUser()?.role === "admin";
  const [period, setPeriod] = useState("month");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [reportPeriod, setReportPeriod] = useState<ReportPeriod>("week");
  const [reportOpen, setReportOpen] = useState(false);
  const [reportMenuOpen, setReportMenuOpen] = useState(false);
  const openReport = (nextPeriod: ReportPeriod) => { setReportPeriod(nextPeriod); setReportMenuOpen(false); setReportOpen(true); };
  useEffect(() => { let cancelled = false; const query = period === "custom" && start && end ? `&start=${start}T00:00:00&end=${end}T23:59:59` : ""; setError(""); apiFetch<DashboardData>(`/dashboard?period=${period}${query}`).then((value) => { if (!cancelled) setData(value); }).catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "加载失败"); }); return () => { cancelled = true; }; }, [period, start, end]);

  const trend = useMemo(() => data?.revenue_trend.map((item) => item.revenue) || [], [data]);
  const kpi = data?.kpis;
  const periodLabel = period === "today" ? "今日" : period === "week" ? "本周" : period === "month" ? "本月" : "当前周期";
  const highValueSection = data?.high_value_customers.length ? <section className="mt-5 rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft md:p-5"><SectionTitle eyebrow="HIGH VALUE CUSTOMERS" title={isAdmin ? "高消费客户排行" : "我的高消费客户"} description="按客户累计消费金额排序"/><div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">{data.high_value_customers.slice(0, 10).map((item, index) => <div key={item.id} className="rounded-xl bg-[#fbfcfe] p-3"><div className="flex items-center justify-between"><span className="text-[11px] text-[#98a2b3]">TOP {index + 1}</span><span className="text-xs font-semibold text-[#182230]">{formatMoney(item.total_spend)}</span></div><div className="mt-2 truncate text-sm font-medium text-[#182230]">{item.name}</div><div className="mt-1 text-[11px] text-[#98a2b3]">{isAdmin ? item.assigned_to_name || "待分配" : "我的客户"}</div></div>)}</div></section> : null;
  const sourceAnalysisSection = isAdmin && data?.source_analysis.length ? <SourceAnalysisSection rows={data.source_analysis} level2Rows={data.source_level_2_analysis || []}/> : null;

  return <AppShell><div className="page-grid -mx-4 -my-4 min-h-0 px-4 py-4 md:-mx-9 md:-my-8 md:min-h-[calc(100vh-72px)] md:px-9 md:py-8">
    <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end md:mb-7"><div><div className="mb-2 text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">{isAdmin ? "OPERATING COCKPIT" : "MY WORKBENCH"}</div><h1 className="text-[22px] font-semibold tracking-tight text-[#182230] md:text-[25px]">{isAdmin ? "企业经营驾驶舱" : "我的客户业绩"}</h1><p className="mt-1.5 text-sm text-[#98a2b3]">{isAdmin ? "客户线索、归属和经营结果统一掌握" : "只展示当前登录业务员负责的客户数据"}</p></div><div className="flex flex-wrap items-center gap-2"><div className="flex max-w-full flex-wrap items-center gap-1 rounded-xl border border-[#e7ebf0] bg-white p-1 shadow-sm">{periods.map((item) => <button key={item.key} onClick={() => setPeriod(item.key)} className={`min-h-10 rounded-lg px-3 text-xs font-medium transition ${period === item.key ? "bg-[#182230] text-white" : "text-[#667085] hover:bg-[#f7f9fc]"}`}>{item.label}</button>)}{period === "custom" && <div className="flex w-full items-center gap-1 px-1 pt-1 sm:w-auto sm:pt-0"><input type="date" value={start} onChange={(event) => setStart(event.target.value)} className="min-h-10 min-w-0 rounded-lg border border-[#e7ebf0] px-2 py-1.5 text-xs text-[#667085]"/><span className="text-xs text-[#98a2b3]">至</span><input type="date" value={end} onChange={(event) => setEnd(event.target.value)} className="min-h-10 min-w-0 rounded-lg border border-[#e7ebf0] px-2 py-1.5 text-xs text-[#667085]"/></div>}</div>{isAdmin && <><div className="hidden items-center gap-1 sm:flex"><button onClick={() => openReport("week")} className="min-h-11 rounded-xl border border-[#e7ebf0] bg-white px-3 text-xs font-medium text-[#667085] shadow-sm hover:border-[#3488e8] hover:text-[#1d6fd1]">周报</button><button onClick={() => openReport("month")} className="min-h-11 rounded-xl border border-[#e7ebf0] bg-white px-3 text-xs font-medium text-[#667085] shadow-sm hover:border-[#3488e8] hover:text-[#1d6fd1]">月报</button></div><button onClick={() => setReportMenuOpen(true)} className="min-h-11 rounded-xl border border-[#e7ebf0] bg-white px-4 text-xs font-medium text-[#667085] shadow-sm sm:hidden">报告</button><BusinessAgentButton/><Link href="/excel-imports" className="inline-flex min-h-11 items-center rounded-xl bg-[#182230] px-4 text-xs font-medium text-white shadow-sm transition hover:bg-[#2c3b4f]">上传 ABC Excel</Link></>}</div></div>
    {error ? <div className="rounded-2xl border border-[#ffd8d3] bg-[#fff5f3] p-5 text-sm text-[#c24e43]">{error}</div> : !data || !kpi ? <Loading label="加载经营数据"/> : <>
      <div className="mb-0 grid grid-cols-2 gap-3 md:hidden">{isAdmin ? <><KpiCard label="客户总数" value={kpi.total_customers.toLocaleString()} hint={`待分配 ${kpi.unassigned_customers}`} /><KpiCard label="本月有效收入" value={formatMoney(kpi.month_revenue, true)} hint="含符合规则的项目消费价值" accent="purple"/><KpiCard label="本周有效收入" value={formatMoney(kpi.week_revenue, true)} hint="含符合规则的项目消费价值" accent="green"/><KpiCard label="新增客户" value={String(kpi.today_new_leads)} hint={`本周 ${kpi.week_new_leads} 条`} accent="amber"/></> : <><KpiCard label="我的客户" value={String(kpi.my_customers)} hint={`待跟进 ${kpi.follow_up_customers}`} /><KpiCard label="本月消费价值" value={formatMoney(kpi.month_my_spend, true)} hint="按项目明细金额" accent="purple"/><KpiCard label="本周消费价值" value={formatMoney(kpi.week_consumption, true)} hint="按项目明细金额" accent="green"/><KpiCard label="新增客户" value={String(kpi.month_new_customers)} hint={`本周 ${kpi.week_new_customers} 位`} accent="amber"/></>}</div>
      <div className="mb-0 hidden grid-cols-2 gap-3 lg:grid-cols-7 md:grid">{isAdmin ? <><KpiCard label="客户总数" value={kpi.total_customers.toLocaleString()} hint={`本周新增线索 ${kpi.week_new_leads}`} /><KpiCard label="已分配客户" value={String(kpi.assigned_customers)} hint={`待分配 ${kpi.unassigned_customers}`} accent="green"/><KpiCard label="今日新增线索" value={String(kpi.today_new_leads)} hint={`本周 ${kpi.week_new_leads} 条`} accent="amber"/><KpiCard label="待分配客户" value={String(kpi.unassigned_customers)} hint={`已成交 ${kpi.converted_customers} 位`} accent="amber"/><KpiCard label="本周有效经营收入" value={formatMoney(kpi.week_revenue, true)} hint={`本月有效经营收入 ${formatMoney(kpi.month_revenue, true)}`} accent="purple"/><KpiCard label="累计有效经营收入" value={formatMoney(kpi.total_revenue, true)} hint="全部 Excel 导入订单" accent="purple"/><KpiCard label="客单价" value={formatMoney(kpi.avg_order_value)} hint="按本月消费价值计算"/></> : <><KpiCard label="我的客户" value={String(kpi.my_customers)} hint={`本周新增 ${kpi.week_new_customers}`} /><KpiCard label="本月新增客户" value={String(kpi.month_new_customers)} hint={`本周 ${kpi.week_new_customers} 位`} accent="green"/><KpiCard label="本月我的消费价值" value={formatMoney(kpi.month_my_spend, true)} hint={`${kpi.my_order_count} 次消费`} accent="amber"/><KpiCard label="累计客户消费价值" value={formatMoney(kpi.my_total_spend, true)} hint="当前客户池累计" accent="purple"/><KpiCard label="待跟进客户" value={String(kpi.follow_up_customers)} hint="客户标签统计"/></>}</div>
      <PaymentSplitSection kpi={kpi} periodLabel={periodLabel}/><PrepaidBalanceSection kpi={kpi} isAdmin={isAdmin} periodLabel={periodLabel}/>
      <div className="mb-5 grid grid-cols-1 gap-4 xl:grid-cols-[1.7fr_1fr]"><section className="rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft md:p-5"><SectionTitle eyebrow="REVENUE TREND" title={isAdmin ? "企业消费趋势" : "我的消费趋势"} description="最近 30 天有效经营收入走势" action={<Badge tone="green">权限范围内数据</Badge>}/><div className="h-[190px] w-full sm:h-[220px]"><Sparkline data={trend} height={220}/></div><div className="mt-3 flex justify-between text-[10px] text-[#b0b7c3]"><span>{data.revenue_trend[0]?.date}</span><span>最近 30 天</span><span>{data.revenue_trend.at(-1)?.date}</span></div></section><section className="rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft md:p-5"><SectionTitle eyebrow={isAdmin ? "CUSTOMER SOURCE" : "CUSTOMER TAGS"} title={isAdmin ? "客户来源归档分类" : "我的客户标签"} description={isAdmin ? "七类来源的客户数量构成" : "当前客户池的标签构成"}/>{isAdmin ? data.source_breakdown.length ? <Donut items={data.source_breakdown}/> : <Empty/> : data.tag_breakdown.length ? <HorizontalBars items={data.tag_breakdown}/> : <Empty/>}</section></div>
      {isAdmin ? <div className="grid grid-cols-1 gap-4 lg:grid-cols-2"><section className="rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft md:p-5"><SectionTitle eyebrow="TEAM PERFORMANCE" title="业务员客户与消费" description="按当前筛选周期统计当前归属；金额为有效经营收入"/><div className="hidden overflow-x-auto md:block"><table className="w-full min-w-[680px] text-left text-xs"><thead className="border-b border-[#f0f2f5] text-[#98a2b3]"><tr><th className="pb-3">业务员</th><th className="pb-3">客户数</th><th className="pb-3">当前周期有效经营收入</th><th className="pb-3">医保</th><th className="pb-3">自费</th></tr></thead><tbody className="divide-y divide-[#f0f2f5]">{data.sales_performance.map((item) => <tr key={item.id}><td className="py-3 font-medium text-[#182230]">{item.name}</td><td className="py-3 text-[#667085]">{item.customer_count}</td><td className="py-3 font-semibold text-[#182230]">{formatMoney(item.revenue)}</td><td className="py-3 text-[#3488e8]">{formatMoney(item.period_insurance || 0)}</td><td className="py-3 text-[#07875f]">{formatMoney(item.period_self_pay || 0)}</td></tr>)}</tbody></table></div><div className="space-y-2 md:hidden">{data.sales_performance.map((item) => <div key={item.id} className="rounded-xl bg-[#fbfcfe] p-3"><div className="flex items-center justify-between"><span className="text-sm font-medium text-[#182230]">{item.name}</span><span className="text-right text-sm font-semibold text-[#182230]">{formatMoney(item.revenue, true)}</span></div><div className="mt-1 text-xs text-[#98a2b3]">{item.customer_count} 位客户 · 当前周期有效经营收入</div><div className="mt-3 grid grid-cols-2 gap-2 text-xs"><span className="rounded-lg bg-[#f2f8ff] px-2 py-1.5 text-[#3488e8]">医保 {formatMoney(item.period_insurance || 0, true)}</span><span className="rounded-lg bg-[#f1fbf7] px-2 py-1.5 text-[#07875f]">自费 {formatMoney(item.period_self_pay || 0, true)}</span></div></div>)}</div></section><section className="rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft md:p-5"><SectionTitle eyebrow="CUSTOMER TAGS" title="客户标签分布" description="管理员维护的动态标签"/><HorizontalBars items={data.tag_breakdown}/></section></div> : <section className="rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft md:p-5"><SectionTitle eyebrow="RECENT ACTIVITY" title="最近客户动态" description="来自我负责客户的消费记录"/>{data.recent_activity.length ? <div className="divide-y divide-[#f0f2f5]">{data.recent_activity.map((item) => <div key={item.id} className="flex items-center justify-between gap-3 py-3"><div className="min-w-0"><div className="truncate text-sm font-medium text-[#182230]">{item.title}</div><div className="mt-1 truncate text-xs text-[#98a2b3]">{item.description}</div></div><span className="shrink-0 text-[11px] text-[#98a2b3]">{dateTime(item.occurred_at)}</span></div>)}</div> : <Empty/>}</section>}
      {sourceAnalysisSection}{highValueSection}
    </>}</div>{isAdmin && <><ReportDrawer open={reportOpen} period={reportPeriod} onPeriodChange={setReportPeriod} onClose={() => setReportOpen(false)}/><MobileSheet open={reportMenuOpen} title="查看经营报告" onClose={() => setReportMenuOpen(false)}><div className="grid grid-cols-2 gap-3"><button onClick={() => openReport("week")} className="min-h-12 rounded-xl bg-[#182230] text-sm font-medium text-white">周报</button><button onClick={() => openReport("month")} className="min-h-12 rounded-xl border border-[#e7ebf0] bg-white text-sm font-medium text-[#182230]">月报</button></div></MobileSheet></>}
  </AppShell>;
}
