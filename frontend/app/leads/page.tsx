"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { AppShell, useCurrentUser } from "../../components/app-shell";
import { formatMoney } from "../../components/charts";
import { Badge, Empty, Loading, SectionTitle } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatBeijingTime } from "../../lib/datetime";
import { SOURCE_LEVEL_1_OPTIONS, SOURCE_LEVEL_2_OPTIONS } from "../../lib/source-categories";
import type { Lead, Tag } from "../../types";

type LeadResponse = { items: Lead[]; total: number; page: number; total_pages: number };
type Meta = {
  users: { id: number; name: string; role: string }[];
  source_categories?: { code: string; name: string }[];
  source_level_1_options?: { code: string; name: string }[];
  source_level_2_options?: Record<string, { code: string; name: string }[]>;
  tags: Tag[];
};
type ReviewDraft = { source_level_1: string; source_level_2: string; source_custom_name: string; tag_ids: number[]; assigned_to: string };
type LeadForm = { name: string; phone: string; wechat_id: string; gender: string; source_note: string; notes: string; source_level_1: string; source_level_2: string; source_custom_name: string; tag_ids: number[]; assigned_to: string };

const statusLabels: Record<string, string> = { pending: "待审核", reviewed: "已审核", unassigned: "待分配", assigned: "已分配", approved: "已通过", converted: "已成交", rejected: "已驳回" };
const fmtDate = formatBeijingTime;
const fieldClass = "min-h-11 rounded-lg border border-[#e7ebf0] bg-white px-3 text-sm outline-none focus:border-[#3488e8]";
const emptyDraft = (): ReviewDraft => ({ source_level_1: "", source_level_2: "", source_custom_name: "", tag_ids: [], assigned_to: "" });
const emptyLeadForm = (): LeadForm => ({ name: "", phone: "", wechat_id: "", gender: "", source_note: "", notes: "", source_level_1: "", source_level_2: "", source_custom_name: "", tag_ids: [], assigned_to: "" });

export default function LeadsPage() {
  const user = useCurrentUser();
  const isAdmin = user?.role === "admin";
  const [meta, setMeta] = useState<Meta | null>(null);
  const [result, setResult] = useState<LeadResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<LeadForm>(emptyLeadForm());
  const [drafts, setDrafts] = useState<Record<number, ReviewDraft>>({});

  const load = () => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (!isAdmin && status) params.set("status", status);
    const path = isAdmin ? `/leads/pending?${params}` : `/leads?${params}`;
    apiFetch<LeadResponse>(path).then((value) => {
      setResult(value);
      setDrafts((current) => Object.fromEntries(value.items.map((lead) => [lead.id, current[lead.id] || emptyDraft()])));
    }).catch((err) => setError(err instanceof Error ? err.message : "加载失败")).finally(() => setLoading(false));
  };

  useEffect(() => { apiFetch<Meta>("/customers/meta").then(setMeta).catch(() => undefined); }, []);
  useEffect(() => { if (user) load(); }, [page, status, isAdmin, user]);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (saving) return;
    setError("");
    setSaving(true);
    const submission_id = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `lead-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try {
      const created = await apiFetch<{ message: string }>("/leads", { method: "POST", body: JSON.stringify({ ...form, source_level_1: isAdmin ? form.source_level_1 : undefined, source_level_2: isAdmin ? form.source_level_2 : undefined, source_custom_name: isAdmin ? form.source_custom_name : undefined, tag_ids: isAdmin ? form.tag_ids : undefined, assigned_to: isAdmin && form.assigned_to ? Number(form.assigned_to) : undefined, submission_id }) });
      setForm(emptyLeadForm());
      setShowForm(false);
      setMessage(created.message);
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "提交失败"); }
    finally { setSaving(false); }
  };

  const updateDraft = (leadId: number, patch: Partial<ReviewDraft>) => {
    setDrafts((current) => ({ ...current, [leadId]: { ...(current[leadId] || emptyDraft()), ...patch } }));
  };

  const review = async (lead: Lead, action: "approve" | "reject") => {
    const draft = drafts[lead.id] || emptyDraft();
    if (action === "approve" && (!draft.source_level_1 || !draft.source_level_2 || !draft.assigned_to || (draft.source_level_1 === "other" && draft.source_level_2 === "custom" && !draft.source_custom_name.trim()))) {
      setError("审核通过前必须选择完整来源、当前归属业务员；自定义来源还需填写名称");
      return;
    }
    try {
      await apiFetch(`/leads/${lead.id}/review`, { method: "POST", body: JSON.stringify({ action, source_level_1: draft.source_level_1 || null, source_level_2: draft.source_level_2 || null, source_custom_name: draft.source_custom_name.trim() || null, tag_ids: draft.tag_ids, assigned_to: draft.assigned_to ? Number(draft.assigned_to) : null }) });
      setMessage(action === "approve" ? `${lead.name} 已审核通过并进入市场部客户管理` : `${lead.name} 已驳回`);
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "审核失败"); }
  };

  const sourceLevel1Options = meta?.source_level_1_options?.length ? meta.source_level_1_options : SOURCE_LEVEL_1_OPTIONS;
  const sourceLevel2Options = (level1: string) => meta?.source_level_2_options?.[level1] || SOURCE_LEVEL_2_OPTIONS[level1 as keyof typeof SOURCE_LEVEL_2_OPTIONS] || [];

  return <AppShell><div>
    <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end md:mb-7">
      <div><div className="mb-2 text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">{isAdmin ? "LEAD REVIEW" : "LEAD REPORTING"}</div><h1 className="text-[22px] font-semibold tracking-tight text-[#182230] md:text-[25px]">{isAdmin ? "客户线索审核" : "报备客户线索"}</h1><p className="mt-1.5 text-sm text-[#98a2b3]">{isAdmin ? "审核业务员提交的客户线索，完善来源、标签并分配客户归属。" : "提交基础线索后由主管审核，审核通过后进入市场部客户管理。"}</p></div>
      <div className="flex flex-wrap gap-2"><button onClick={() => setShowForm((value) => !value)} className="min-h-11 rounded-lg bg-[#1d6fd1] px-4 py-2.5 text-xs font-medium text-white">{showForm ? "收起表单" : isAdmin ? "新建客户线索" : "提交新线索"}</button>{isAdmin && <Link href="/duplicate-reports" className="inline-flex min-h-11 items-center justify-center rounded-lg border border-[#d5e7fa] bg-white px-4 py-2.5 text-xs font-medium text-[#1d6fd1]">查看重复报备</Link>}</div>
    </div>

    {showForm && <form onSubmit={create} className="mb-5 rounded-2xl border border-[#d5e7fa] bg-[#f7fbff] p-4 shadow-soft md:p-5"><SectionTitle title={isAdmin ? "新建客户线索" : "提交客户线索"} description={isAdmin ? "管理员可直接完善来源、标签并选择当前归属；保存后无需再次审核。" : "业务员只填写基础线索，正式来源和标签由主管审核时确定。"}/><div className="grid grid-cols-1 gap-3 md:grid-cols-3"><input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="客户姓名" className={fieldClass}/><input required type="tel" inputMode="tel" value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} placeholder="手机号" className={fieldClass}/><input value={form.wechat_id} onChange={(event) => setForm({ ...form, wechat_id: event.target.value })} placeholder="微信号" className={fieldClass}/><select value={form.gender} onChange={(event) => setForm({ ...form, gender: event.target.value })} className={fieldClass}><option value="">性别（可选）</option><option value="女">女</option><option value="男">男</option></select><input value={form.source_note} onChange={(event) => setForm({ ...form, source_note: event.target.value })} placeholder="简单来源备注（可选）" className={fieldClass}/><textarea rows={3} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} placeholder="客户情况备注（可选）" className="min-h-24 rounded-lg border border-[#e7ebf0] px-3 py-2 text-sm outline-none focus:border-[#3488e7]"/>{isAdmin && <><label className="block text-xs text-[#667085]">来源一级分类<select required value={form.source_level_1} onChange={(event) => setForm({ ...form, source_level_1: event.target.value, source_level_2: "", source_custom_name: "" })} className={`${fieldClass} mt-1.5 w-full`}><option value="">请选择一级来源</option>{sourceLevel1Options.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label><label className="block text-xs text-[#667085]">来源二级分类<select required disabled={!form.source_level_1} value={form.source_level_2} onChange={(event) => setForm({ ...form, source_level_2: event.target.value, source_custom_name: event.target.value === "custom" ? form.source_custom_name : "" })} className={`${fieldClass} mt-1.5 w-full disabled:bg-[#f2f4f7]`}><option value="">{form.source_level_1 ? "请选择二级来源" : "请先选择一级来源"}</option>{sourceLevel2Options(form.source_level_1).map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label><label className="block text-xs text-[#667085]">当前归属业务员<select value={form.assigned_to} onChange={(event) => setForm({ ...form, assigned_to: event.target.value })} className={`${fieldClass} mt-1.5 w-full`}><option value="">暂不分配</option>{meta?.users.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{form.source_level_1 === "other" && form.source_level_2 === "custom" && <input required value={form.source_custom_name} onChange={(event) => setForm({ ...form, source_custom_name: event.target.value })} placeholder="请输入自定义来源名称" className={`${fieldClass} w-full`}/>}<div className="md:col-span-3"><div className="mb-1.5 text-xs text-[#667085]">客户标签（可多选）</div><div className="flex flex-wrap gap-2">{meta?.tags.map((tag) => <label key={tag.id} className={`cursor-pointer rounded-full border px-2.5 py-1.5 text-[11px] ${form.tag_ids.includes(tag.id) ? "border-[#b7d9fa] bg-[#eaf4ff] text-[#1d6fd1]" : "border-[#e7ebf0] bg-white text-[#667085]"}`}><input type="checkbox" className="sr-only" checked={form.tag_ids.includes(tag.id)} onChange={() => setForm({ ...form, tag_ids: form.tag_ids.includes(tag.id) ? form.tag_ids.filter((id) => id !== tag.id) : [...form.tag_ids, tag.id] })}/>{tag.name}</label>)}</div></div></>}</div><div className="sticky bottom-[calc(68px+env(safe-area-inset-bottom))] z-10 mt-4 flex justify-end bg-[#f7fbff]/95 py-1 backdrop-blur md:static md:bg-transparent md:py-0"><button disabled={saving} aria-busy={saving} className="min-h-11 w-full rounded-lg bg-[#182230] px-5 py-2.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60 md:w-auto">{saving ? "保存中…" : isAdmin ? "创建客户线索" : "提交客户线索"}</button></div></form>}

    {isAdmin ? <div className="mb-5 rounded-xl border border-[#d5e7fa] bg-[#f7fbff] px-4 py-3 text-xs text-[#4e6b86]">当前队列只显示 <span className="font-semibold text-[#1d6fd1]">待审核</span> 线索。审核通过后会自动从本页消失，并进入市场部客户管理。</div> : <section className="mb-5 rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft"><div className="flex gap-2 overflow-x-auto scrollbar-hide">{Object.entries({ all: "全部", ...statusLabels }).map(([key, label]) => <button key={key} onClick={() => { setStatus(key === "all" ? "" : key); setPage(1); }} className={`min-h-10 shrink-0 rounded-lg px-3 text-xs ${(!status && key === "all") || status === key ? "bg-[#182230] text-white" : "bg-[#f7f9fc] text-[#667085]"}`}>{label}</button>)}</div></section>}
    {error && <div className="mb-5 rounded-xl bg-[#fff2f0] px-4 py-3 text-xs text-[#c24e43]">{error}</div>}
    {message && <div className="mb-5 rounded-xl bg-[#e8faf4] px-4 py-3 text-xs text-[#07875f]">{message}</div>}

    <section className="rounded-2xl border border-[#e7ebf0] bg-white shadow-soft"><div className="p-4 pb-3 md:p-5 md:pb-3"><SectionTitle title={isAdmin ? "待审核线索" : "我提交的线索"} description={isAdmin ? "完成来源归档、标签和当前归属后一次性审核通过。" : "线索报备人由当前登录账号自动记录，正式客户标签由主管维护。"}/></div>{loading ? <Loading label="正在加载线索"/> : !result?.items.length ? <Empty label={isAdmin ? "当前没有待审核线索" : "暂无匹配线索"}/> : <div className="divide-y divide-[#f0f2f5]">{result.items.map((lead) => {
      const draft = drafts[lead.id] || emptyDraft();
      return <article key={lead.id} className="p-4 md:p-5"><div className="grid grid-cols-1 gap-5 lg:grid-cols-2"><div className="min-w-0"><div className="flex items-start justify-between gap-3"><div><div className="text-[16px] font-semibold text-[#182230]">{lead.name}</div><div className="mt-1 text-xs text-[#667085]">{lead.phone}{lead.wechat_id ? ` · 微信号 ${lead.wechat_id}` : ""}</div></div><Badge tone={lead.lead_status === "pending" ? "amber" : lead.lead_status === "rejected" ? "rose" : "green"}>{statusLabels[lead.lead_status] || lead.lead_status}</Badge></div><div className="mt-4 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4"><div><div className="text-[#98a2b3]">线索报备人</div><div className="mt-1 font-medium text-[#182230]">{lead.reported_by_name || "—"}</div></div><div><div className="text-[#98a2b3]">报备时间</div><div className="mt-1 font-medium text-[#182230]">{fmtDate(lead.reported_at)}</div></div><div><div className="text-[#98a2b3]">性别</div><div className="mt-1 font-medium text-[#182230]">{lead.gender || "—"}</div></div><div><div className="text-[#98a2b3]">历史消费</div><div className="mt-1 font-medium text-[#182230]">{formatMoney(Number(lead.total_spend))} · {lead.order_count} 次</div></div></div>{lead.source_note && <div className="mt-4 rounded-lg bg-[#f7f9fc] px-3 py-2 text-xs text-[#667085]">来源备注：{lead.source_note}</div>}{lead.notes && <div className="mt-2 rounded-lg bg-[#f7f9fc] px-3 py-2 text-xs leading-5 text-[#667085]">客户情况：{lead.notes}</div>}</div>
        {isAdmin && <div className="w-full min-w-0 rounded-xl border border-[#e7ebf0] bg-[#fbfcfe] p-4"><div className="mb-3 text-xs font-semibold text-[#182230]">管理员审核字段</div><label className="block text-xs text-[#667085]">一级来源<select required value={draft.source_level_1} onChange={(event) => updateDraft(lead.id, { source_level_1: event.target.value, source_level_2: "", source_custom_name: "" })} className={`${fieldClass} mt-1.5 w-full`}><option value="">请选择一级来源</option>{sourceLevel1Options.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label><label className="mt-3 block text-xs text-[#667085]">二级来源<select required disabled={!draft.source_level_1} value={draft.source_level_2} onChange={(event) => updateDraft(lead.id, { source_level_2: event.target.value, source_custom_name: event.target.value === "custom" ? draft.source_custom_name : "" })} className={`${fieldClass} mt-1.5 w-full disabled:bg-[#f2f4f7]`}><option value="">{draft.source_level_1 ? "请选择二级来源" : "请先选择一级来源"}</option>{sourceLevel2Options(draft.source_level_1).map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>{draft.source_level_1 === "other" && draft.source_level_2 === "custom" && <input required value={draft.source_custom_name} onChange={(event) => updateDraft(lead.id, { source_custom_name: event.target.value })} placeholder="请输入自定义来源名称" className={`${fieldClass} mt-3 w-full`}/>}<div className="mt-3"><div className="mb-1.5 text-xs text-[#667085]">客户标签（可多选）</div><div className="flex flex-wrap gap-2">{meta?.tags.map((tag) => <label key={tag.id} className={`cursor-pointer rounded-full border px-2.5 py-1.5 text-[11px] ${draft.tag_ids.includes(tag.id) ? "border-[#b7d9fa] bg-[#eaf4ff] text-[#1d6fd1]" : "border-[#e7ebf0] bg-white text-[#667085]"}`}><input type="checkbox" className="sr-only" checked={draft.tag_ids.includes(tag.id)} onChange={() => updateDraft(lead.id, { tag_ids: draft.tag_ids.includes(tag.id) ? draft.tag_ids.filter((id) => id !== tag.id) : [...draft.tag_ids, tag.id] })}/>{tag.name}</label>)}</div></div><label className="mt-3 block text-xs text-[#667085]">当前归属业务员<select required value={draft.assigned_to} onChange={(event) => updateDraft(lead.id, { assigned_to: event.target.value })} className={`${fieldClass} mt-1.5 w-full`}><option value="">请选择业务员</option>{meta?.users.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><div className="mt-4 grid grid-cols-2 gap-2"><button type="button" onClick={() => review(lead, "reject")} className="min-h-11 rounded-lg border border-[#f1c6c0] bg-white text-xs font-medium text-[#c24e43]">驳回</button><button type="button" onClick={() => review(lead, "approve")} className="min-h-11 rounded-lg bg-[#1d6fd1] text-xs font-medium text-white">审核通过</button></div></div>}
      </div>{!isAdmin && <div className="mt-4 border-t border-[#f0f2f5] pt-3 text-xs text-[#98a2b3]">当前归属：{lead.assigned_to_name || "待主管审核分配"} · {fmtDate(lead.reported_at)}</div>}</article>;
    })}</div>}
    {!loading && result && result.items.length > 0 && <div className="flex items-center justify-between border-t border-[#f0f2f5] px-4 py-4 md:px-5"><span className="text-xs text-[#98a2b3]">共 {result.total} 条 · 第 {result.page} / {result.total_pages || 1} 页</span><div className="flex gap-2"><button disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="min-h-10 rounded-lg border border-[#e7ebf0] px-3 text-xs text-[#667085] disabled:opacity-40">上一页</button><button disabled={page >= (result.total_pages || 1)} onClick={() => setPage((value) => value + 1)} className="min-h-10 rounded-lg border border-[#e7ebf0] px-3 text-xs text-[#667085] disabled:opacity-40">下一页</button></div></div>}
    </section>
  </div></AppShell>;
}
