"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell, useCurrentUser } from "../../components/app-shell";
import { formatMoney } from "../../components/charts";
import { Badge, Empty, Loading, SectionTitle } from "../../components/ui";
import { Icon } from "../../components/icons";
import { apiFetch } from "../../lib/api";
import { formatBeijingTime, formatBusinessDateTime24h } from "../../lib/datetime";

type Batch = {
  id: number;
  file_name: string;
  uploaded_at: string;
  status: string;
  sheet_names: string[];
  total_rows: number;
  total_customers: number;
  matched_customers: number;
  unmatched_customers: number;
  conflict_customers: number;
  new_transactions: number;
  updated_transactions: number;
  skipped_transactions: number;
  error_rows: number;
  preview?: {
    transactions: { name?: string; total_amount?: string; external_transaction_id?: string; payment_split_status?: string; payment_type_raw?: string }[];
    errors: { sheet?: string; row?: number; message: string }[];
    patient_count?: number;
    sheet_stats?: { sheet_name: string; recognized: boolean; record_count: number; valid_record_count: number; error_rows: number; recognized_fields: { field: string; header: string }[] }[];
  };
};

type UnmatchedTransaction = { id: number; batch_id: number; file_name?: string; external_customer_id?: string; name?: string; phone?: string; external_transaction_id?: string; charged_at?: string; total_amount?: string; status: string; resolution_note?: string; visit_no?: string; transaction_kind?: string; transaction_operation?: string; item_name?: string; payment_type_raw?: string; items?: { item_name?: string }[] };
type Unmatched = { id: number; customer_key: string; external_customer_id?: string; name?: string; phone?: string; status: string; match_status?: string; transaction_count: number; total_amount: string; latest_charged_at?: string; record_ids: number[]; transactions: UnmatchedTransaction[] };
type CustomerOption = { id: number; name: string; phone?: string | null };

const statusLabels: Record<string, string> = { preview: "待确认", success: "已完成", partial: "部分完成", failed: "失败", pending: "待匹配", conflict: "匹配冲突", bound: "已绑定", ignored: "已忽略" };
const statusTone = (status: string) => status === "success" || status === "bound" ? "green" : status === "failed" ? "rose" : "amber";
const dateText = formatBusinessDateTime24h;
const uploadDateText = (value?: string | null) => formatBeijingTime(value);
const fieldLabels: Record<string, string> = { external_customer_id: "客户档案号", name: "患者姓名", phone: "手机号", charged_at: "收费时间", external_transaction_id: "交易号", visit_no: "诊号", payment_method: "支付方式", payment_type_raw: "支付原始值", total_amount: "实收/总金额", original_amount: "原价", receivable_amount: "应收", deduction_amount: "抵扣金额", insurance_amount: "基金支付总额", self_pay_amount: "非基金支付总额", fee_category: "费用分类", category_level_1: "一级分类", category_level_2: "二级分类", category_level_3: "三级分类", item_name: "药品/项目名称", item_code: "药品/项目编码", specification: "规格", manufacturer: "厂家", quantity: "数量", unit: "单位", unit_price: "单价", line_amount: "明细金额", item_note: "项目备注", department: "科室", staff_name: "服务人员" };

function CollapsibleHeader({ title, summary, open, onToggle, badge }: { title: string; summary: string; open: boolean; onToggle: () => void; badge?: React.ReactNode }) {
  return <button type="button" aria-expanded={open} onClick={onToggle} className="flex min-h-[76px] w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-[#fbfcfe] md:px-5">
    <span className="min-w-0"><span className="flex flex-wrap items-center gap-2"><span className="text-[17px] font-semibold leading-6 tracking-tight text-[#182230]">{title}</span>{badge}</span><span className="mt-1 block truncate text-xs leading-5 text-[#98a2b3]">{summary}</span></span>
    <span className="flex shrink-0 items-center gap-1 text-[11px] font-medium text-[#3488e8]">{open ? "收起" : "展开"}<span className={`transition-transform ${open ? "rotate-180" : ""}`}><Icon name="chevron" size={15}/></span></span>
  </button>;
}

export default function ExcelImportsPage() {
  const user = useCurrentUser();
  const [file, setFile] = useState<File | null>(null);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [history, setHistory] = useState<Batch[]>([]);
  const [unmatched, setUnmatched] = useState<Unmatched[]>([]);
  const [customers, setCustomers] = useState<CustomerOption[]>([]);
  const [selectedCustomers, setSelectedCustomers] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [unmatchedOpen, setUnmatchedOpen] = useState(false);
  const [expandedUnmatched, setExpandedUnmatched] = useState<Record<number, boolean>>({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = () => {
    if (!user || user.role !== "admin") return;
    setLoading(true);
    Promise.all([apiFetch<Batch[]>("/excel-imports/abc/history"), apiFetch<Unmatched[]>("/excel-imports/abc/unmatched")])
      .then(([batches, records]) => { setHistory(batches); setUnmatched(records); })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "加载导入记录失败"))
      .finally(() => setLoading(false));
    apiFetch<{ items: CustomerOption[] }>("/customers?page=1&page_size=100").then((result) => setCustomers(result.items)).catch(() => undefined);
  };

  useEffect(() => { load(); }, [user]);

  const preview = async () => {
    if (!file || uploading) return;
    setError(""); setMessage(""); setUploading(true);
    const form = new FormData();
    form.append("upload", file);
    try {
      const result = await apiFetch<Batch>("/excel-imports/abc/preview", { method: "POST", body: form });
      setBatch(result);
      setMessage("文件解析完成，请核对预览结果后确认导入。");
      load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Excel 解析失败"); }
    finally { setUploading(false); }
  };

  const confirm = async () => {
    if (!batch || confirming) return;
    setError(""); setConfirming(true);
    try {
      const result = await apiFetch<Batch>(`/excel-imports/abc/${batch.id}/confirm`, { method: "POST" });
      setBatch(result);
      setMessage("Excel 已导入，未匹配记录请在下方处理。");
      load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "导入失败"); }
    finally { setConfirming(false); }
  };

  const bind = async (record: Unmatched) => {
    const customerId = selectedCustomers[record.id];
    if (!customerId) { setError("请先选择要绑定的正式客户"); return; }
    try {
      await apiFetch(`/excel-imports/abc/unmatched/${record.id}/bind`, { method: "POST", body: JSON.stringify({ customer_id: Number(customerId) }) });
      setMessage(`${record.name || "该记录"} 已绑定并导入消费记录`); load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "绑定失败"); }
  };

  const ignore = async (record: Unmatched) => {
    try {
      await apiFetch(`/excel-imports/abc/unmatched/${record.id}/ignore`, { method: "POST", body: JSON.stringify({}) });
      setMessage("未匹配记录已忽略"); load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "操作失败"); }
  };

  const previewTransactions = batch?.preview?.transactions || [];
  const previewErrors = batch?.preview?.errors || [];
  const sheetStats = batch?.preview?.sheet_stats || [];
  const latestHistory = history.reduce<Batch | null>((latest, item) => !latest || new Date(item.uploaded_at).getTime() > new Date(latest.uploaded_at).getTime() ? item : latest, null);
  const unmatchedCustomerCount = unmatched.length;
  const unmatchedTransactionCount = unmatched.reduce((sum, record) => sum + record.transaction_count, 0);
  const historySummary = loading ? "正在加载导入记录…" : history.length ? `共 ${history.length} 次导入 · 最近一次 ${uploadDateText(latestHistory?.uploaded_at)}` : "暂无导入记录";
  const unmatchedSummary = loading ? "正在加载待匹配记录…" : unmatched.length ? `待匹配客户 ${unmatchedCustomerCount} 人 · 待处理交易 ${unmatchedTransactionCount} 笔` : "暂无待匹配客户";
  const unmatchedBadge = loading ? undefined : unmatched.length ? <Badge tone="amber">待处理 {unmatchedCustomerCount}</Badge> : <Badge tone="green">已处理完</Badge>;
  if (user && user.role !== "admin") return <AppShell><Empty label="仅管理员可以上传 ABC Excel"/></AppShell>;

  return <AppShell><div>
    <div className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-end md:mb-7"><div><div className="mb-2 text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">ABC EXCEL IMPORT</div><h1 className="text-[22px] font-semibold tracking-tight text-[#182230] md:text-[25px]">ABC Excel 导入</h1><p className="mt-1.5 text-sm text-[#98a2b3]">管理员上传 ABC 导出的客户和消费结果，系统在本地数据库完成匹配与统计。</p></div><Link href="/orders" className="text-xs font-medium text-[#1d6fd1]">查看消费管理 →</Link></div>
    {error && <div className="mb-5 rounded-xl border border-[#ffd8d3] bg-[#fff5f3] px-4 py-3 text-xs text-[#c24e43]">{error}</div>}
    {message && <div className="mb-5 rounded-xl border border-[#ccefe1] bg-[#f1fbf7] px-4 py-3 text-xs text-[#07875f]">{message}</div>}

    <section className="mb-5 rounded-2xl border border-[#d5e7fa] bg-[#f7fbff] p-4 shadow-soft md:p-5"><SectionTitle title="上传 ABC Excel" description="支持 .xlsx / .xls；先预览，再确认写入 PostgreSQL。"/><div className="flex flex-col gap-3 sm:flex-row sm:items-center"><input type="file" accept=".xlsx,.xls" onChange={(event) => setFile(event.target.files?.[0] || null)} className="min-h-11 w-full rounded-lg border border-[#d5e7fa] bg-white px-3 py-2 text-sm text-[#667085] file:mr-3 file:rounded-md file:border-0 file:bg-[#eaf4ff] file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-[#1d6fd1] sm:flex-1"/><button onClick={preview} disabled={!file || uploading} className="min-h-11 rounded-lg bg-[#182230] px-5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">{uploading ? "解析中…" : "上传并预览"}</button></div><div className="mt-3 text-[11px] leading-5 text-[#667085]">匹配优先使用患者档案号/患者 ID，其次使用标准化手机号；姓名不会单独自动匹配。缺少稳定客户 ID 或手机号的记录会进入待匹配。</div></section>

    {batch && <section className="mb-5 rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft md:p-5"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div><SectionTitle title={`导入预览 · ${batch.file_name}`} description={`Sheet：${batch.sheet_names?.join("、") || "—"}`}/></div><button onClick={confirm} disabled={batch.status !== "preview" || confirming} className="min-h-11 rounded-lg bg-[#1d6fd1] px-5 text-xs font-medium text-white disabled:opacity-50">{confirming ? "导入中…" : batch.status === "preview" ? "确认导入" : "已处理"}</button></div><div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8"><Metric label="数据行" value={batch.total_rows}/><Metric label="识别患者" value={batch.preview?.patient_count || 0}/><Metric label="客户" value={batch.total_customers}/><Metric label="已匹配" value={batch.matched_customers}/><Metric label="待匹配" value={batch.unmatched_customers}/><Metric label="新增交易" value={batch.new_transactions}/><Metric label="更新交易" value={batch.updated_transactions}/><Metric label="错误行" value={batch.error_rows}/></div>{sheetStats.length ? <div className="mt-4 grid gap-3 md:grid-cols-3">{sheetStats.map((stat) => <details key={stat.sheet_name} className={`rounded-xl border p-3 ${stat.recognized ? "border-[#ccefe1] bg-[#f7fcfa]" : "border-[#ffd8d3] bg-[#fff8f7]"}`}><summary className="cursor-pointer list-none text-xs font-semibold text-[#182230]"><span className="mr-2">{stat.recognized ? "✅" : "⚠️"}</span>{stat.sheet_name}<span className="ml-2 font-normal text-[#667085]">{stat.record_count} 行 · 有效 {stat.valid_record_count}</span></summary><div className="mt-2 border-t border-black/5 pt-2 text-[11px] leading-5 text-[#667085]"><div>错误行：{stat.error_rows}</div><div className="mt-1 font-medium text-[#182230]">识别字段</div><div className="mt-1 flex flex-wrap gap-1.5">{stat.recognized_fields.map((item) => <span key={`${item.field}-${item.header}`} className="rounded-md bg-white px-1.5 py-0.5">{fieldLabels[item.field] || item.field}：{item.header}</span>)}</div></div></details>)}</div> : null}{previewTransactions.length ? <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[560px] text-left text-xs"><thead className="border-y border-[#f0f2f5] bg-[#fbfcfe] text-[#98a2b3]"><tr><th className="px-3 py-2">客户</th><th className="px-3 py-2">交易号</th><th className="px-3 py-2">总金额</th><th className="px-3 py-2">支付原始值</th><th className="px-3 py-2">拆分</th></tr></thead><tbody className="divide-y divide-[#f0f2f5]">{previewTransactions.slice(0, 10).map((item, index) => <tr key={`${item.external_transaction_id || "row"}-${index}`}><td className="px-3 py-2 text-[#182230]">{item.name || "—"}</td><td className="px-3 py-2 text-[#667085]">{item.external_transaction_id || "指纹匹配"}</td><td className="px-3 py-2 font-medium text-[#182230]">{formatMoney(Number(item.total_amount || 0))}</td><td className="px-3 py-2 text-[#667085]">{item.payment_type_raw || "—"}</td><td className="px-3 py-2 text-[#667085]">{item.payment_split_status || "unknown"}</td></tr>)}</tbody></table></div> : null}{previewErrors.length ? <div className="mt-4 rounded-xl bg-[#fff5f3] p-3 text-xs text-[#c24e43]">{previewErrors.slice(0, 5).map((item, index) => <div key={index}>{item.sheet} 第 {item.row} 行：{item.message}</div>)}</div> : null}</section>}

    <section className="mb-5 overflow-hidden rounded-2xl border border-[#e7ebf0] bg-white shadow-soft"><CollapsibleHeader title="导入历史" summary={historySummary} open={historyOpen} onToggle={() => setHistoryOpen((value) => !value)}/>{historyOpen && <div className="border-t border-[#f0f2f5] p-4 md:p-5">{loading ? <Loading label="加载导入历史"/> : !history.length ? <Empty label="暂无 Excel 导入记录"/> : <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-xs"><thead className="border-y border-[#f0f2f5] bg-[#fbfcfe] text-[#98a2b3]"><tr><th className="px-3 py-2">文件</th><th className="px-3 py-2">时间</th><th className="px-3 py-2">状态</th><th className="px-3 py-2">客户匹配</th><th className="px-3 py-2">交易处理</th><th className="px-3 py-2">错误</th></tr></thead><tbody className="divide-y divide-[#f0f2f5]">{history.map((item) => <tr key={item.id}><td className="px-3 py-3 font-medium text-[#182230]">{item.file_name}</td><td className="px-3 py-3 text-[#667085]">{uploadDateText(item.uploaded_at)}</td><td className="px-3 py-3"><Badge tone={statusTone(item.status)}>{statusLabels[item.status] || item.status}</Badge></td><td className="px-3 py-3 text-[#667085]">{item.matched_customers} / {item.total_customers}，待匹配 {item.unmatched_customers + item.conflict_customers}</td><td className="px-3 py-3 text-[#667085]">新增 {item.new_transactions} · 更新 {item.updated_transactions} · 跳过 {item.skipped_transactions}</td><td className="px-3 py-3 text-[#c24e43]">{item.error_rows}</td></tr>)}</tbody></table></div>}</div>}</section>

    <section className="overflow-hidden rounded-2xl border border-[#e7ebf0] bg-white shadow-soft"><CollapsibleHeader title="待匹配客户交易" summary={unmatchedSummary} badge={unmatchedBadge} open={unmatchedOpen} onToggle={() => setUnmatchedOpen((value) => !value)}/>{unmatchedOpen && <div className="border-t border-[#f0f2f5] p-4 md:p-5">{!unmatched.length ? <Empty label="暂无待匹配记录"/> : <div className="space-y-3">{unmatched.map((record) => { const detailsOpen = Boolean(expandedUnmatched[record.id]); return <article key={record.id} className="rounded-xl border border-[#f0f2f5] bg-[#fbfcfe] p-3 md:p-4"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold text-[#182230]">{record.name || "未命名客户"}</span><Badge tone="amber">{statusLabels[record.status] || record.status}</Badge></div><div className="mt-1 text-xs text-[#667085]">手机号：{record.phone || "未提供"} · ABC患者ID：{record.external_customer_id || "未提供"}</div><div className="mt-1 text-[11px] text-[#98a2b3]">待处理交易：{record.transaction_count} 笔 · 累计交易金额：{formatMoney(Number(record.total_amount || 0))} · 最近交易：{record.latest_charged_at ? dateText(record.latest_charged_at) : "—"}</div></div><div className="flex flex-col gap-2 sm:flex-row sm:items-center"><button type="button" onClick={() => setExpandedUnmatched((current) => ({ ...current, [record.id]: !detailsOpen }))} className="min-h-11 rounded-lg border border-[#d5e7fa] px-4 text-xs font-medium text-[#1d6fd1]">{detailsOpen ? "收起交易明细" : "查看交易明细"}</button><select value={selectedCustomers[record.id] || ""} onChange={(event) => setSelectedCustomers((current) => ({ ...current, [record.id]: event.target.value }))} className="min-h-11 min-w-[210px] rounded-lg border border-[#e7ebf0] bg-white px-3 text-xs text-[#667085]"><option value="">选择已有正式客户</option>{customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name} · {customer.phone || "无手机号"}</option>)}</select><button onClick={() => bind(record)} className="min-h-11 rounded-lg bg-[#1d6fd1] px-4 text-xs font-medium text-white">绑定并导入</button><button onClick={() => ignore(record)} className="min-h-11 rounded-lg border border-[#e7ebf0] px-4 text-xs text-[#667085]">忽略</button></div></div>{detailsOpen && <div className="mt-3 border-t border-[#e7ebf0] pt-3"><div className="space-y-2">{record.transactions.map((transaction) => <div key={transaction.id} className="grid gap-2 rounded-lg bg-white p-3 text-xs sm:grid-cols-[1fr_auto] sm:items-center"><div className="min-w-0"><div className="font-medium text-[#182230]">{transaction.item_name || transaction.items?.[0]?.item_name || "未分类项目"}</div><div className="mt-1 text-[#667085]">{transaction.charged_at ? dateText(transaction.charged_at) : "—"} · 诊号 {transaction.visit_no || "—"} · {transaction.payment_type_raw || "支付方式未知"}</div><div className="mt-1 text-[11px] text-[#98a2b3]">{transaction.external_transaction_id || "无稳定交易号"} · {transaction.transaction_operation || "交易"}</div></div><div className={`text-right text-sm font-semibold ${Number(transaction.total_amount || 0) < 0 ? "text-[#c24e43]" : "text-[#182230]"}`}>{formatMoney(Number(transaction.total_amount || 0))}</div></div>)}</div></div>}</article>; })}</div>}</div>}</section>
  </div></AppShell>;
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-xl bg-[#fbfcfe] p-3"><div className="text-[11px] text-[#98a2b3]">{label}</div><div className="mt-1 text-lg font-semibold text-[#182230]">{value}</div></div>;
}
