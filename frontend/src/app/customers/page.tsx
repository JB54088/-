"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell, useCurrentUser } from "../../components/app-shell";
import { formatMoney } from "../../components/charts";
import { Badge, Empty, Loading, MobileSheet, SectionTitle } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatBusinessDateTime24h } from "../../lib/datetime";
import { SOURCE_LEVEL_1_OPTIONS, SOURCE_LEVEL_2_OPTIONS, formatSourceCategory } from "../../lib/source-categories";
import type { Customer, Tag } from "../../types";

type CustomerResponse = { items: Customer[]; total: number; page: number; page_size: number; total_pages: number };
type Meta = { departments: { id: number; name: string }[]; users: { id: number; name: string; role: string }[]; source_categories?: { code: string; name: string }[]; source_level_1_options?: { code: string; name: string }[]; source_level_2_options?: Record<string, { code: string; name: string }[]>; statuses: string[]; lead_statuses: string[]; tags: Tag[] };
type AssignmentTarget = { id: number; name: string; assigned_to_id?: number | null; assigned_to_name?: string | null };
type OwnerAssetSummary = { assigned_to_id: number | null; customer_count: number; month_new_customers: number; total_consumption: number; month_consumption: number; total_revenue: number; month_revenue: number; high_value_customers: number; recent_new_customer_at?: string | null };
type OwnerSummaryResponse = { period: string; period_start: string; period_end: string; owners: (OwnerAssetSummary & { id: number; name: string })[]; unassigned: OwnerAssetSummary & { name: string } };

const statusLabels: Record<string, string> = { pending: "待审核", reviewed: "已审核", unassigned: "待分配", assigned: "已分配", approved: "已通过", converted: "已成交", rejected: "已驳回" };
const reasonOptions = ["业务调整", "业务员离职", "客户重新分配", "区域调整", "主管手动调整", "其它"];
const fmtDate = formatBusinessDateTime24h;
const fieldClass = "h-10 rounded-lg border border-[#e7ebf0] bg-white px-3 text-xs outline-none focus:border-[#3488e8]";

function OwnerSummarySection({ data, loading }: { data: OwnerSummaryResponse | null; loading: boolean }) {
  if (loading) return <section className="rounded-2xl border border-[#e7ebf0] bg-white p-5 shadow-soft"><Loading label="正在加载业务员客户资产"/></section>;
  if (!data) return <section className="rounded-2xl border border-[#e7ebf0] bg-white p-5 shadow-soft"><Empty label="暂无业务员客户资产"/></section>;
  const cards = [...data.owners, ...(data.unassigned.customer_count ? [data.unassigned] : [])];
  return <section className="rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft md:p-5"><SectionTitle eyebrow="OWNER ASSETS" title="业务员客户资产" description="按当前归属业务员查看客户池与客户资产，点击卡片进入名下客户。"/><div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">{cards.map((item) => { const isUnassigned = item.assigned_to_id === null; const href = isUnassigned ? "/customers?owner_id=unassigned" : `/customers?owner_id=${item.assigned_to_id}`; return <a key={isUnassigned ? "unassigned" : item.assigned_to_id} href={href} className="rounded-xl border border-[#edf1f5] bg-[#fbfcfe] p-4 transition hover:border-[#b9d8f7] hover:bg-[#f7fbff]"><div className="flex items-start justify-between gap-3"><div><div className="text-base font-semibold text-[#182230]">{item.name}</div><div className="mt-1 text-xs text-[#98a2b3]">{isUnassigned ? "等待管理员分配" : "当前归属客户池"}</div></div><span className="text-xs font-medium text-[#1d6fd1]">查看名下客户 →</span></div><div className="mt-4 grid grid-cols-2 gap-3"><div><div className="text-[11px] text-[#98a2b3]">名下客户</div><div className="mt-1 text-xl font-semibold text-[#182230]">{item.customer_count}</div></div><div><div className="text-[11px] text-[#98a2b3]">本月新增</div><div className="mt-1 text-xl font-semibold text-[#182230]">{item.month_new_customers}</div></div><div><div className="text-[11px] text-[#98a2b3]">累计消费</div><div className="mt-1 text-sm font-semibold text-[#182230]">{formatMoney(item.total_consumption, true)}</div></div><div><div className="text-[11px] text-[#98a2b3]">本月消费</div><div className="mt-1 text-sm font-semibold text-[#1d6fd1]">{formatMoney(item.month_consumption, true)}</div></div><div><div className="text-[11px] text-[#98a2b3]">累计有效收入</div><div className="mt-1 text-sm font-semibold text-[#182230]">{formatMoney(item.total_revenue, true)}</div></div><div><div className="text-[11px] text-[#98a2b3]">本月有效收入</div><div className="mt-1 text-sm font-semibold text-[#07875f]">{formatMoney(item.month_revenue, true)}</div></div></div><div className="mt-3 flex items-center justify-between border-t border-[#edf1f5] pt-3 text-[11px] text-[#98a2b3]"><span>高价值客户 {item.high_value_customers}</span><span>最近新增 {fmtDate(item.recent_new_customer_at)}</span></div></a>; })}</div></section>;
}

export default function CustomersPage() {
  const user = useCurrentUser();
  const isAdmin = user?.role === "admin";
  const [meta, setMeta] = useState<Meta | null>(null);
  const [result, setResult] = useState<CustomerResponse | null>(null);
  const [ownerSummary, setOwnerSummary] = useState<OwnerSummaryResponse | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [directoryMode, setDirectoryMode] = useState<"summary" | "list">("summary");
  const [ownerId, setOwnerId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [tagId, setTagId] = useState("");
  const [sourceCategory, setSourceCategory] = useState("");
  const [sourceLevel2, setSourceLevel2] = useState("");
  const [leadStatus, setLeadStatus] = useState("");
  const [page, setPage] = useState(1);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [draftAssignedTo, setDraftAssignedTo] = useState("");
  const [draftTagId, setDraftTagId] = useState("");
  const [draftSourceCategory, setDraftSourceCategory] = useState("");
  const [draftSourceLevel2, setDraftSourceLevel2] = useState("");
  const [draftLeadStatus, setDraftLeadStatus] = useState("");
  const [assignmentTarget, setAssignmentTarget] = useState<AssignmentTarget | null>(null);
  const [assignmentUser, setAssignmentUser] = useState("");
  const [assignmentReason, setAssignmentReason] = useState(reasonOptions[0]);
  const [assignmentNote, setAssignmentNote] = useState("");
  const [savingAssignment, setSavingAssignment] = useState(false);

  const load = (requestedPage = page) => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ page: String(requestedPage), page_size: "20" });
    if (search) params.set("search", search);
    const scopedOwner = isAdmin && ownerId && ownerId !== "unassigned" ? ownerId : assignedTo;
    if (isAdmin && scopedOwner) params.set("assigned_to_id", scopedOwner);
    if (isAdmin && ownerId === "unassigned") params.set("unassigned", "true");
    if (tagId) params.set("tag_id", tagId);
    if (sourceCategory) params.set("source_level_1", sourceCategory);
    if (sourceLevel2) params.set("source_level_2", sourceLevel2);
    if (leadStatus) params.set("lead_status", leadStatus);
    apiFetch<CustomerResponse>(`/customers?${params}`).then(setResult).catch((err) => setError(err instanceof Error ? err.message : "加载失败")).finally(() => setLoading(false));
  };

  useEffect(() => { apiFetch<Meta>("/customers/meta").then(setMeta).catch(() => undefined); }, []);
  useEffect(() => {
    if (!user) return;
    const params = new URLSearchParams(window.location.search);
    const queryOwner = params.get("owner_id");
    const querySearch = params.get("search") || "";
    setOwnerId(queryOwner);
    setSearch(querySearch);
    setDirectoryMode(user.role === "admin" && !queryOwner && params.get("view") !== "all" && !querySearch ? "summary" : "list");
  }, [user]);
  useEffect(() => {
    if (!user || !isAdmin || directoryMode !== "summary") return;
    setSummaryLoading(true);
    apiFetch<OwnerSummaryResponse>("/customers/owner-summary?period=month").then(setOwnerSummary).catch((err) => setError(err instanceof Error ? err.message : "业务员资产加载失败")).finally(() => setSummaryLoading(false));
  }, [user, isAdmin, directoryMode]);
  useEffect(() => { if (user && directoryMode === "list") load(); }, [page, assignedTo, tagId, sourceCategory, sourceLevel2, leadStatus, ownerId, directoryMode, isAdmin, user]);

  const submitSearch = (event: React.FormEvent) => { event.preventDefault(); setPage(1); if (isAdmin) setDirectoryMode("list"); load(1); };
  const openFilters = () => { setDraftAssignedTo(assignedTo); setDraftSourceCategory(sourceCategory); setDraftSourceLevel2(sourceLevel2); setDraftTagId(tagId); setDraftLeadStatus(leadStatus); setFiltersOpen(true); };
  const applyFilters = () => { setAssignedTo(draftAssignedTo); setSourceCategory(draftSourceCategory); setSourceLevel2(draftSourceLevel2); setTagId(draftTagId); setLeadStatus(draftLeadStatus); setPage(1); setFiltersOpen(false); if (isAdmin) setDirectoryMode("list"); };
  const resetFilters = () => { setDraftAssignedTo(""); setDraftSourceCategory(""); setDraftSourceLevel2(""); setDraftTagId(""); setDraftLeadStatus(""); setAssignedTo(""); setSourceCategory(""); setSourceLevel2(""); setTagId(""); setLeadStatus(""); setPage(1); setFiltersOpen(false); };

  const openAssignment = (item: Customer) => {
    setAssignmentTarget({ id: item.id, name: item.name, assigned_to_id: item.assigned_to_id, assigned_to_name: item.assigned_to_name });
    setAssignmentUser(item.assigned_to_id ? String(item.assigned_to_id) : "");
    setAssignmentReason(reasonOptions[0]);
    setAssignmentNote("");
  };
  const assign = async () => {
    if (!assignmentTarget || !assignmentUser) { setError("请选择新的归属业务员"); return; }
    setSavingAssignment(true);
    try {
      await apiFetch(`/customers/${assignmentTarget.id}/reassign`, { method: "POST", body: JSON.stringify({ new_salesperson_id: Number(assignmentUser), reason: assignmentReason, note: assignmentNote || null }) });
      setMessage(`${assignmentTarget.name} 的当前归属已变更，历史记录已保存`);
      setAssignmentTarget(null);
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "归属变更失败"); } finally { setSavingAssignment(false); }
  };

  const sourceLevel1Options = meta?.source_level_1_options?.length ? meta.source_level_1_options : SOURCE_LEVEL_1_OPTIONS;
  const sourceLevel2Options = (level1: string) => meta?.source_level_2_options?.[level1] || SOURCE_LEVEL_2_OPTIONS[level1 as keyof typeof SOURCE_LEVEL_2_OPTIONS] || [];
  const customerSource = (item: Customer) => formatSourceCategory(item.source_level_1, item.source_level_2, item.source_custom_name, item.source_category);
  const tone = (status: string) => status === "approved" || status === "converted" ? "green" : status === "pending" ? "amber" : "gray";
  const ownerDirectory = isAdmin && !!ownerId && ownerId !== "unassigned";
  const unassignedDirectory = isAdmin && ownerId === "unassigned";
  const ownerName = ownerDirectory ? meta?.users.find((item) => String(item.id) === ownerId)?.name || "业务员" : "";
  const pageTitle = directoryMode === "summary" && isAdmin ? "市场部客户管理" : ownerDirectory ? `${ownerName} · 名下客户` : unassignedDirectory ? "待分配客户" : isAdmin ? "市场部客户管理" : "我的客户";
  const pageDescription = directoryMode === "summary" && isAdmin ? "按业务员管理客户归属与客户资产" : ownerDirectory ? "只显示当前归属到该业务员的正式客户" : unassignedDirectory ? "查看尚未分配业务员的正式客户" : isAdmin ? "管理市场部审核完成的正式客户、客户标签和当前归属" : "只显示当前归属到我的正式客户，客户消费权限随归属变化";

  return <AppShell><div>
    <div className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-end md:mb-7"><div><div className="mb-2 text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">{isAdmin ? "CUSTOMER ASSETS" : "MY CUSTOMER POOL"}</div><h1 className="text-[22px] font-semibold tracking-tight text-[#182230] md:text-[25px]">{pageTitle}</h1><p className="mt-1.5 text-sm text-[#98a2b3]">{pageDescription}</p></div><div className="flex flex-wrap items-center gap-2">{isAdmin && <><Link href="/assignment-history" className="min-h-10 rounded-lg border border-[#e7ebf0] bg-white px-3 py-2 text-xs font-medium text-[#667085]">归属变更历史</Link><Link href="/excel-imports" className="min-h-10 rounded-lg border border-[#d5e7fa] bg-white px-3 py-2 text-xs font-medium text-[#1d6fd1]">ABC Excel 导入</Link>{directoryMode === "summary" ? <a href="/customers?view=all" className="min-h-10 rounded-lg bg-[#182230] px-3 py-2 text-xs font-medium text-white">查看全部客户</a> : <a href="/customers" className="min-h-10 rounded-lg border border-[#e7ebf0] bg-white px-3 py-2 text-xs font-medium text-[#667085]">业务员资产</a>}</>}<Badge tone="green">后端权限隔离</Badge><span className="hidden text-xs text-[#98a2b3] sm:inline">{directoryMode === "summary" && isAdmin ? `${ownerSummary?.owners.length || 0} 位业务员` : `共 ${result?.total || 0} 位客户`}</span></div></div>
    <form onSubmit={submitSearch} className="mb-5 hidden flex-col gap-3 md:flex lg:flex-row"><div className="relative flex-1"><span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#98a2b3]">⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索客户姓名、手机号、微信号" className="h-10 w-full rounded-lg border border-[#e7ebf0] bg-white pl-9 pr-3 text-sm outline-none focus:border-[#3488e8]"/></div>{isAdmin && <select value={assignedTo} onChange={(event) => { setAssignedTo(event.target.value); setPage(1); }} className={fieldClass}><option value="">全部归属业务员</option>{meta?.users.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>}<select value={tagId} onChange={(event) => { setTagId(event.target.value); setPage(1); }} className={fieldClass}><option value="">全部标签</option>{meta?.tags.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><select value={sourceCategory} onChange={(event) => { setSourceCategory(event.target.value); setSourceLevel2(""); setPage(1); }} className={fieldClass}><option value="">全部一级来源</option>{sourceLevel1Options.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select><select value={sourceLevel2} onChange={(event) => { setSourceLevel2(event.target.value); setPage(1); }} className={fieldClass} disabled={!sourceCategory}><option value="">全部二级来源</option>{sourceLevel2Options(sourceCategory).map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select><select value={leadStatus} onChange={(event) => { setLeadStatus(event.target.value); setPage(1); }} className={fieldClass}><option value="">全部状态</option>{meta?.lead_statuses.filter((item) => item !== "pending" && item !== "rejected").map((item) => <option key={item} value={item}>{statusLabels[item] || item}</option>)}</select><button type="submit" className="h-10 rounded-lg bg-[#182230] px-5 text-xs font-medium text-white">查询</button></form>
    <div className="mb-5 flex gap-2 md:hidden"><form onSubmit={submitSearch} className="relative min-w-0 flex-1"><span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#98a2b3]">⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索客户" className="h-11 w-full rounded-xl border border-[#e7ebf0] bg-white pl-9 pr-3 text-sm outline-none focus:border-[#3488e8]"/></form><button onClick={openFilters} className="min-h-11 shrink-0 rounded-xl border border-[#e7ebf0] bg-white px-4 text-xs font-medium text-[#667085]">筛选</button></div>
    {error && <div className="mb-5 rounded-xl bg-[#fff2f0] px-4 py-3 text-xs text-[#c24e43]">{error}</div>}{message && <div className="mb-5 rounded-xl bg-[#e8faf4] px-4 py-3 text-xs text-[#07875f]">{message}</div>}
    {directoryMode === "summary" && isAdmin ? <OwnerSummarySection data={ownerSummary} loading={summaryLoading}/> : <section className="rounded-2xl border border-[#e7ebf0] bg-white shadow-soft"><div className="p-4 pb-3 md:p-5 md:pb-3"><SectionTitle title={ownerDirectory ? `${ownerName} · 名下客户` : unassignedDirectory ? "待分配客户" : isAdmin ? "正式客户档案" : "我的客户档案"} description={ownerDirectory ? "客户资产按 assigned_to 归属到当前业务员。" : unassignedDirectory ? "管理员可以在客户详情中完成归属分配。" : isAdmin ? "线索报备人永久保留；修改当前归属会写入归属变更历史。" : "客户、订单和累计消费均按 assigned_to 过滤。"}/></div>{loading ? <Loading label="正在加载客户"/> : !result?.items.length ? <Empty label="没有找到匹配的正式客户"/> : <>
      <div className="hidden overflow-x-auto md:block"><table className="w-full min-w-[1040px] text-left"><thead className="border-y border-[#f0f2f5] bg-[#fbfcfe] text-[11px] font-medium text-[#98a2b3]"><tr><th className="px-5 py-3">客户</th><th className="px-4 py-3">来源归档分类 / 标签</th>{isAdmin && <th className="px-4 py-3">线索报备人</th>}{isAdmin && !ownerDirectory && !unassignedDirectory && <th className="px-4 py-3">当前归属</th>}<th className="px-4 py-3">客户状态</th><th className="px-4 py-3">累计消费</th><th className="px-4 py-3">消费次数</th><th className="px-5 py-3">最近消费</th></tr></thead><tbody className="divide-y divide-[#f0f2f5]">{result.items.map((item) => <tr key={item.id} className="hover:bg-[#fbfcfe]"><td className="px-5 py-4"><Link href={`/customers/${item.id}`} className="flex items-center gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#eaf4ff] text-xs font-semibold text-[#3488e8]">{item.name.slice(0, 1)}</span><span><span className="block text-sm font-medium text-[#182230]">{item.name}</span><span className="mt-0.5 block text-[11px] text-[#98a2b3]">{item.phone || "手机号未提供"}</span></span></Link></td><td className="px-4 py-4"><div className="text-xs text-[#667085]">{customerSource(item)}</div><div className="mt-1 flex max-w-[190px] flex-wrap gap-1">{item.tags?.map((tag) => <Badge key={tag} tone={tag === "VIP" || tag === "高消费" ? "amber" : "blue"}>{tag}</Badge>)}</div></td>{isAdmin && <td className="px-4 py-4 text-xs text-[#667085]">{item.reported_by_name || "—"}</td>}{isAdmin && !ownerDirectory && !unassignedDirectory && <td className="px-4 py-4"><button onClick={() => openAssignment(item)} className="rounded-lg border border-[#e7ebf0] bg-white px-2.5 py-2 text-left text-xs text-[#667085] hover:border-[#3488e8] hover:text-[#1d6fd1]">{item.assigned_to_name || "待分配"}<span className="ml-2 text-[#98a2b3]">调整</span></button></td>}<td className="px-4 py-4"><Badge tone={tone(item.lead_status)}>{statusLabels[item.lead_status] || item.lead_status}</Badge></td><td className="px-4 py-4 text-sm font-semibold text-[#182230]">{formatMoney(Number(item.total_spend))}</td><td className="px-4 py-4 text-xs text-[#667085]">{item.order_count} 次</td><td className="px-5 py-4 text-xs text-[#667085]">{fmtDate(item.last_spend_at)}</td></tr>)}</tbody></table></div>
      <div className="divide-y divide-[#f0f2f5] md:hidden">{result.items.map((item) => <article key={item.id} className="p-4"><Link href={`/customers/${item.id}`} className="block"><div className="flex items-start justify-between gap-3"><div className="flex min-w-0 items-center gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#eaf4ff] text-xs font-semibold text-[#3488e8]">{item.name.slice(0, 1)}</span><div className="min-w-0"><div className="truncate text-[15px] font-semibold text-[#182230]">{item.name}</div><div className="mt-1 truncate text-[11px] text-[#98a2b3]">{item.phone || "手机号未提供"} · {customerSource(item)}</div></div></div><div className="shrink-0 text-right"><div className="text-[15px] font-semibold text-[#182230]">{formatMoney(Number(item.total_spend))}</div><div className="mt-1 text-[11px] text-[#98a2b3]">{item.order_count} 次消费</div></div></div><div className="mt-3 flex flex-wrap gap-1">{item.tags?.map((tag) => <Badge key={tag}>{tag}</Badge>)}<Badge tone={tone(item.lead_status)}>{statusLabels[item.lead_status] || item.lead_status}</Badge></div><div className="mt-3 flex items-center justify-between text-xs text-[#667085]"><span>最近消费 {fmtDate(item.last_spend_at)}</span>{isAdmin ? <span>线索报备人：{item.reported_by_name || "—"}</span> : <span>查看详情 ›</span>}</div></Link>{isAdmin && <button onClick={() => openAssignment(item)} className="mt-3 min-h-11 w-full rounded-lg border border-[#e7ebf0] bg-[#fbfcfe] text-xs font-medium text-[#667085]">{ownerDirectory || unassignedDirectory ? "修改归属" : `当前归属：${item.assigned_to_name || "待分配"} · 修改归属`}</button>}</article>)}</div>
      <div className="flex items-center justify-between border-t border-[#f0f2f5] px-4 py-4 md:px-5"><span className="text-xs text-[#98a2b3]">第 {result.page} / {result.total_pages || 1} 页</span><div className="flex gap-2"><button disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="min-h-10 rounded-lg border border-[#e7ebf0] px-3 text-xs text-[#667085] disabled:opacity-40">上一页</button><button disabled={page >= (result.total_pages || 1)} onClick={() => setPage((value) => value + 1)} className="min-h-10 rounded-lg border border-[#e7ebf0] px-3 text-xs text-[#667085] disabled:opacity-40">下一页</button></div></div>
    </>}</section>}

    <MobileSheet open={filtersOpen} title="筛选客户" onClose={() => setFiltersOpen(false)}><div className="space-y-4"><label className="block text-sm font-medium text-[#182230]">一级来源<select value={draftSourceCategory} onChange={(event) => { setDraftSourceCategory(event.target.value); setDraftSourceLevel2(""); }} className={`${fieldClass} mt-2 w-full`}><option value="">全部一级来源</option>{sourceLevel1Options.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label><label className="block text-sm font-medium text-[#182230]">二级来源<select value={draftSourceLevel2} onChange={(event) => setDraftSourceLevel2(event.target.value)} className={`${fieldClass} mt-2 w-full`} disabled={!draftSourceCategory}><option value="">全部二级来源</option>{sourceLevel2Options(draftSourceCategory).map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label><label className="block text-sm font-medium text-[#182230]">客户标签<select value={draftTagId} onChange={(event) => setDraftTagId(event.target.value)} className={`${fieldClass} mt-2 w-full`}><option value="">全部标签</option>{meta?.tags.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="block text-sm font-medium text-[#182230]">客户状态<select value={draftLeadStatus} onChange={(event) => setDraftLeadStatus(event.target.value)} className={`${fieldClass} mt-2 w-full`}><option value="">全部状态</option>{meta?.lead_statuses.filter((item) => item !== "pending" && item !== "rejected").map((item) => <option key={item} value={item}>{statusLabels[item] || item}</option>)}</select></label>{isAdmin && <label className="block text-sm font-medium text-[#182230]">归属业务员<select value={draftAssignedTo} onChange={(event) => setDraftAssignedTo(event.target.value)} className={`${fieldClass} mt-2 w-full`}><option value="">全部归属业务员</option>{meta?.users.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}<div className="grid grid-cols-2 gap-3 pt-2"><button type="button" onClick={resetFilters} className="min-h-11 rounded-xl border border-[#e7ebf0] text-sm font-medium text-[#667085]">重置</button><button type="button" onClick={applyFilters} className="min-h-11 rounded-xl bg-[#182230] text-sm font-medium text-white">确认筛选</button></div></div></MobileSheet>
    {assignmentTarget && <div className="fixed inset-0 z-50 flex items-end justify-center bg-[#182230]/25 p-0 md:items-center md:p-5"><div className="w-full rounded-t-[20px] bg-white p-5 shadow-xl md:max-w-md md:rounded-2xl md:p-6" style={{ paddingBottom: "calc(20px + env(safe-area-inset-bottom))" }}><div className="mx-auto mb-4 h-1 w-10 rounded-full bg-[#d0d5dd] md:hidden"/><div className="mb-5 flex items-center justify-between"><div><h2 className="font-semibold text-[#182230]">修改当前归属</h2><p className="mt-1 text-xs text-[#98a2b3]">{assignmentTarget.name} · 线索报备人保持不变</p></div><button onClick={() => setAssignmentTarget(null)} className="flex h-10 w-10 items-center justify-center rounded-full bg-[#f7f9fc] text-xl text-[#98a2b3]">×</button></div><div className="space-y-4"><label className="block"><span className="mb-1.5 block text-xs text-[#667085]">新归属业务员</span><select value={assignmentUser} onChange={(event) => setAssignmentUser(event.target.value)} className="h-11 w-full rounded-lg border border-[#e7ebf0] px-3 text-sm"><option value="">请选择业务员</option>{meta?.users.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="block"><span className="mb-1.5 block text-xs text-[#667085]">变更原因</span><select value={assignmentReason} onChange={(event) => setAssignmentReason(event.target.value)} className="h-11 w-full rounded-lg border border-[#e7ebf0] px-3 text-sm">{reasonOptions.map((item) => <option key={item}>{item}</option>)}</select></label><label className="block"><span className="mb-1.5 block text-xs text-[#667085]">补充备注（可选）</span><textarea value={assignmentNote} onChange={(event) => setAssignmentNote(event.target.value)} rows={3} placeholder="填写本次调整的具体说明" className="w-full rounded-lg border border-[#e7ebf0] px-3 py-2 text-sm outline-none focus:border-[#3488e8]"/></label></div><div className="mt-6 grid grid-cols-2 gap-2"><button onClick={() => setAssignmentTarget(null)} className="min-h-11 rounded-lg border border-[#e7ebf0] text-xs text-[#667085]">取消</button><button disabled={savingAssignment} onClick={assign} className="min-h-11 rounded-lg bg-[#1d6fd1] text-xs font-medium text-white disabled:opacity-50">{savingAssignment ? "保存中…" : "确认变更"}</button></div></div></div>}
  </div></AppShell>;
}
