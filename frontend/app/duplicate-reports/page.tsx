"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "../../components/app-shell";
import { Badge, Empty, Loading, SectionTitle } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatBeijingTime } from "../../lib/datetime";
import type { DuplicateLeadReport } from "../../types";

type Result = { items: DuplicateLeadReport[]; total: number; page: number; total_pages: number };

const statusLabels: Record<string, string> = {
  pending: "待确认",
  confirmed_duplicate: "已确认为重复",
  not_duplicate: "已确认不是重复",
  rejected: "已驳回",
};
const reasonLabels: Record<string, string> = { phone: "手机号一致", wechat: "微信号一致" };
const fmtDate = (value?: string | null) => formatBeijingTime(value, true);

function statusTone(status: string) {
  if (status === "pending") return "amber" as const;
  if (status === "rejected") return "rose" as const;
  return "green" as const;
}

export default function DuplicateReportsPage() {
  const [result, setResult] = useState<Result | null>(null);
  const [status, setStatus] = useState("pending");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [actionId, setActionId] = useState<number | null>(null);
  const [reviewNote, setReviewNote] = useState("");

  const load = () => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ page: "1", page_size: "50" });
    if (status) params.set("status", status);
    if (search.trim()) params.set("search", search.trim());
    apiFetch<Result>(`/duplicate-reports?${params.toString()}`)
      .then(setResult)
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [status]);

  const review = async (report: DuplicateLeadReport, action: "confirm_duplicate" | "not_duplicate" | "reject") => {
    const actionText = action === "confirm_duplicate" ? "确认为重复" : action === "not_duplicate" ? "确认不是重复" : "驳回";
    if (!window.confirm(`确定${actionText}“${report.reported_name}”的重复报备吗？`)) return;
    setActionId(report.id);
    setError("");
    try {
      await apiFetch(`/duplicate-reports/${report.id}/review`, {
        method: "POST",
        body: JSON.stringify({ action, review_note: reviewNote.trim() || null }),
      });
      setMessage(action === "not_duplicate" ? "已创建新的待审核线索" : `已${actionText}`);
      setReviewNote("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setActionId(null);
    }
  };

  return <AppShell><div>
    <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end md:mb-7">
      <div><div className="mb-2 text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">DUPLICATE REPORTS</div><h1 className="text-[22px] font-semibold tracking-tight text-[#182230] md:text-[25px]">重复报备</h1><p className="mt-1.5 text-sm text-[#98a2b3]">查看线索提交时命中的重复客户，确认是否为同一客户。</p></div>
      <Link href="/leads" className="inline-flex min-h-11 items-center justify-center rounded-lg border border-[#d5e7fa] bg-white px-4 py-2.5 text-xs font-medium text-[#1d6fd1]">返回线索审核</Link>
    </div>

    <section className="mb-5 rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft md:p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex gap-2 overflow-x-auto scrollbar-hide">
          {[['pending', '待确认'], ['', '全部'], ['confirmed_duplicate', '已确认为重复'], ['not_duplicate', '不是重复'], ['rejected', '已驳回']].map(([value, label]) => <button key={value || 'all'} onClick={() => setStatus(value)} className={`min-h-10 shrink-0 rounded-lg px-3 text-xs ${status === value ? 'bg-[#182230] text-white' : 'bg-[#f7f9fc] text-[#667085]'}`}>{label}</button>)}
        </div>
        <form onSubmit={(event) => { event.preventDefault(); load(); }} className="flex w-full gap-2 md:max-w-[360px]"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索客户姓名或手机号" className="min-h-11 min-w-0 flex-1 rounded-lg border border-[#e7ebf0] px-3 text-sm outline-none focus:border-[#3488e8]"/><button className="min-h-11 rounded-lg bg-[#182230] px-4 text-xs font-medium text-white">搜索</button></form>
      </div>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center"><label className="text-xs text-[#98a2b3]">处理备注（可选）</label><input value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder="例如：已电话核实，不是同一人" className="min-h-10 flex-1 rounded-lg border border-[#e7ebf0] px-3 text-xs outline-none focus:border-[#3488e8]"/></div>
    </section>

    {error && <div className="mb-5 rounded-xl bg-[#fff2f0] px-4 py-3 text-xs text-[#c24e43]">{error}</div>}
    {message && <div className="mb-5 rounded-xl bg-[#e8faf4] px-4 py-3 text-xs text-[#07875f]">{message}</div>}

    <section className="rounded-2xl border border-[#e7ebf0] bg-white shadow-soft"><div className="p-4 pb-3 md:p-5 md:pb-3"><SectionTitle title="重复报备记录" description={`共 ${result?.total || 0} 条，管理员可以确认重复、确认不是重复或驳回。`}/></div>{loading ? <Loading label="正在加载重复报备"/> : !result?.items.length ? <Empty label={status === "pending" ? "当前没有待确认重复报备" : "暂无匹配记录"}/> : <div className="divide-y divide-[#f0f2f5]">{result.items.map((report) => <article key={report.id} className="p-4 md:p-5"><div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-start gap-2"><div><div className="text-[16px] font-semibold text-[#182230]">{report.reported_name}</div><div className="mt-1 text-xs text-[#667085]">本次线索手机号：{report.reported_phone}{report.reported_wechat ? ` · 微信号 ${report.reported_wechat}` : ""}</div></div><Badge tone={statusTone(report.status)}>{statusLabels[report.status] || report.status}</Badge></div><div className="mt-4 grid grid-cols-1 gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4"><div><div className="text-[#98a2b3]">原客户</div><Link href={`/customers/${report.existing_customer_id}`} className="mt-1 block font-medium text-[#1d6fd1]">{report.existing_customer_name} · {report.existing_customer_phone || "无手机号"}</Link></div><div><div className="text-[#98a2b3]">重复原因</div><div className="mt-1 font-medium text-[#182230]">{reasonLabels[report.duplicate_reason] || report.duplicate_reason}</div></div><div><div className="text-[#98a2b3]">原线索报备人 / 当前归属</div><div className="mt-1 font-medium text-[#182230]">{report.existing_reported_by_name || "—"} / {report.existing_assigned_to_name || "待分配"}</div></div><div><div className="text-[#98a2b3]">本次线索报备人 / 提交时间</div><div className="mt-1 font-medium text-[#182230]">{report.new_reported_by_name || "—"}<span className="block font-normal text-[#98a2b3]">{fmtDate(report.created_at)}</span></div></div></div>{report.review_note && <div className="mt-4 rounded-lg bg-[#f7f9fc] px-3 py-2 text-xs text-[#667085]">处理备注：{report.review_note}</div>}</div>{report.status === "pending" && <div className="grid w-full shrink-0 grid-cols-1 gap-2 sm:grid-cols-3 lg:w-[330px]"><button disabled={actionId === report.id} onClick={() => review(report, "confirm_duplicate")} className="min-h-11 rounded-lg border border-[#b7d9fa] bg-[#eaf4ff] px-3 text-xs font-medium text-[#1d6fd1] disabled:opacity-50">确认为重复</button><button disabled={actionId === report.id} onClick={() => review(report, "not_duplicate")} className="min-h-11 rounded-lg border border-[#b7e4d3] bg-[#e8faf4] px-3 text-xs font-medium text-[#07875f] disabled:opacity-50">确认不是重复</button><button disabled={actionId === report.id} onClick={() => review(report, "reject")} className="min-h-11 rounded-lg border border-[#f1c6c0] bg-white px-3 text-xs font-medium text-[#c24e43] disabled:opacity-50">驳回</button></div>}</div></article>)}</div>}</section>
  </div></AppShell>;
}
