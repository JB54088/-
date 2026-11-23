"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "../../components/app-shell";
import { Badge, Empty, Loading, MobileSheet, SectionTitle } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatBeijingTime } from "../../lib/datetime";

type HistoryItem = { id: number; customer_id: number; customer_name: string; previous_salesperson_id?: number | null; previous_salesperson_name: string; new_salesperson_id?: number | null; new_salesperson_name: string; changed_by_id?: number | null; changed_by: string; change_reason?: string | null; change_note?: string | null; changed_at: string };
type Meta = { users: { id: number; name: string; role: string }[] };
type UserRow = { id: number; full_name: string; role: string };
const fmtDate = (value: string) => formatBeijingTime(value, true);
const fieldClass = "h-10 rounded-lg border border-[#e7ebf0] bg-white px-3 text-xs outline-none focus:border-[#3488e8]";

export default function AssignmentHistoryPage() {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [allUsers, setAllUsers] = useState<UserRow[]>([]);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [salesperson, setSalesperson] = useState("");
  const [operator, setOperator] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [draft, setDraft] = useState({ salesperson: "", operator: "", start: "", end: "" });

  const load = () => {
    setError("");
    const params = new URLSearchParams({ limit: "500" });
    if (search) params.set("search", search);
    if (salesperson) params.set("salesperson_id", salesperson);
    if (operator) params.set("changed_by_id", operator);
    if (start) params.set("start", `${start}T00:00:00`);
    if (end) params.set("end", `${end}T23:59:59`);
    apiFetch<HistoryItem[]>(`/customers/assignment-history?${params}`).then(setItems).catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  };
  useEffect(() => { apiFetch<Meta>("/customers/meta").then(setMeta).catch(() => undefined); apiFetch<UserRow[]>("/users").then(setAllUsers).catch(() => undefined); load(); }, []);
  useEffect(() => { const timer = window.setTimeout(load, 250); return () => window.clearTimeout(timer); }, [search, salesperson, operator, start, end]);

  const applyDraft = () => { setSalesperson(draft.salesperson); setOperator(draft.operator); setStart(draft.start); setEnd(draft.end); setFiltersOpen(false); };
  const reset = () => { setSalesperson(""); setOperator(""); setStart(""); setEnd(""); setDraft({ salesperson: "", operator: "", start: "", end: "" }); setFiltersOpen(false); };
  const filters = <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"><label className="text-xs text-[#667085]">业务员<select value={salesperson} onChange={(event) => setSalesperson(event.target.value)} className={`${fieldClass} mt-1.5 w-full`}><option value="">全部业务员</option>{allUsers.filter((item) => item.role === "salesperson").map((item) => <option key={item.id} value={item.id}>{item.full_name}</option>)}</select></label><label className="text-xs text-[#667085]">操作管理员<select value={operator} onChange={(event) => setOperator(event.target.value)} className={`${fieldClass} mt-1.5 w-full`}><option value="">全部管理员</option>{allUsers.filter((item) => item.role === "admin").map((item) => <option key={item.id} value={item.id}>{item.full_name}</option>)}</select></label><label className="text-xs text-[#667085]">开始日期<input type="date" value={start} onChange={(event) => setStart(event.target.value)} className={`${fieldClass} mt-1.5 w-full`}/></label><label className="text-xs text-[#667085]">结束日期<input type="date" value={end} onChange={(event) => setEnd(event.target.value)} className={`${fieldClass} mt-1.5 w-full`}/></label></div>;

  return <AppShell><div>
    <div className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><div className="mb-2 text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">ASSIGNMENT AUDIT</div><h1 className="text-[22px] font-semibold tracking-tight text-[#182230] md:text-[25px]">归属变更历史</h1><p className="mt-1.5 text-sm text-[#98a2b3]">追踪客户从首次分配到后续调整的完整记录。</p></div><Badge tone="blue">仅管理员可见</Badge></div>
    <div className="mb-5 flex gap-2"><form onSubmit={(event) => { event.preventDefault(); load(); }} className="relative min-w-0 flex-1"><span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#98a2b3]">⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索客户姓名或手机号" className="h-11 w-full rounded-xl border border-[#e7ebf0] bg-white pl-9 pr-3 text-sm outline-none focus:border-[#3488e8]"/></form><button onClick={() => { setDraft({ salesperson, operator, start, end }); setFiltersOpen(true); }} className="min-h-11 rounded-xl border border-[#e7ebf0] bg-white px-4 text-xs font-medium text-[#667085] md:hidden">筛选</button></div>
    <div className="mb-5 hidden rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft md:block">{filters}</div>
    {error && <div className="mb-5 rounded-xl bg-[#fff2f0] px-4 py-3 text-xs text-[#c24e43]">{error}</div>}
    <section className="rounded-2xl border border-[#e7ebf0] bg-white shadow-soft"><div className="p-4 pb-3 md:p-5 md:pb-3"><SectionTitle title="全部变更记录" description={`共 ${items?.length || 0} 条，首次分配也会保留在这里。`}/></div>{items === null ? <Loading label="正在加载归属历史"/> : !items.length ? <Empty label="暂无归属变更记录"/> : <><div className="hidden overflow-x-auto md:block"><table className="w-full min-w-[900px] text-left"><thead className="border-y border-[#f0f2f5] bg-[#fbfcfe] text-[11px] text-[#98a2b3]"><tr><th className="px-5 py-3">变更时间</th><th className="px-4 py-3">客户</th><th className="px-4 py-3">原归属</th><th className="px-4 py-3">新归属</th><th className="px-4 py-3">操作管理员</th><th className="px-5 py-3">变更原因</th></tr></thead><tbody className="divide-y divide-[#f0f2f5]">{items.map((item) => <tr key={item.id}><td className="px-5 py-4 text-xs text-[#667085]">{fmtDate(item.changed_at)}</td><td className="px-4 py-4"><Link href={`/customers/${item.customer_id}`} className="text-sm font-medium text-[#182230] hover:text-[#1d6fd1]">{item.customer_name}</Link></td><td className="px-4 py-4 text-xs text-[#667085]">{item.previous_salesperson_name}</td><td className="px-4 py-4 text-xs text-[#667085]">{item.new_salesperson_name}</td><td className="px-4 py-4 text-xs text-[#667085]">{item.changed_by}</td><td className="px-5 py-4 text-xs text-[#667085]">{item.change_reason || "—"}{item.change_note && <div className="mt-1 text-[#98a2b3]">{item.change_note}</div>}</td></tr>)}</tbody></table></div><div className="divide-y divide-[#f0f2f5] md:hidden">{items.map((item) => <Link key={item.id} href={`/customers/${item.customer_id}`} className="block p-4"><div className="flex items-start justify-between gap-3"><div><div className="text-[15px] font-semibold text-[#182230]">{item.customer_name}</div><div className="mt-1 text-[11px] text-[#98a2b3]">{fmtDate(item.changed_at)}</div></div><span className="text-xs text-[#1d6fd1]">查看客户 ›</span></div><div className="mt-3 rounded-xl bg-[#f7f9fc] p-3 text-xs"><div className="font-medium text-[#182230]">{item.previous_salesperson_name} → {item.new_salesperson_name}</div><div className="mt-1 text-[#667085]">{item.change_reason || "—"} · 操作人：{item.changed_by}</div>{item.change_note && <div className="mt-1 leading-5 text-[#98a2b3]">{item.change_note}</div>}</div></Link>)}</div></>}</section>
    <MobileSheet open={filtersOpen} title="筛选归属历史" onClose={() => setFiltersOpen(false)}><div className="space-y-4">{filters}<div className="grid grid-cols-2 gap-3 pt-2"><button onClick={reset} className="min-h-11 rounded-xl border border-[#e7ebf0] text-sm text-[#667085]">重置</button><button onClick={applyDraft} className="min-h-11 rounded-xl bg-[#182230] text-sm text-white">确认筛选</button></div></div></MobileSheet>
  </div></AppShell>;
}
