"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AppShell, useCurrentUser } from "../../components/app-shell";
import { Badge, Empty, Loading, SectionTitle } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatBeijingTime } from "../../lib/datetime";

type LoginLog = {
  id: number;
  user_id: number | null;
  username: string;
  full_name: string | null;
  role: string | null;
  success: boolean;
  failure_reason: string | null;
  created_at: string;
};
type LoginLogPage = { items: LoginLog[]; total: number; limit: number; offset: number };

const pageSize = 100;
const fieldClass = "h-10 rounded-lg border border-[#e7ebf0] bg-white px-3 text-xs outline-none focus:border-[#3488e8]";
const failureLabels: Record<string, string> = { invalid_credentials: "账号或密码错误", account_disabled: "账号已停用" };
const roleLabels: Record<string, string> = { admin: "管理员", salesperson: "业务员" };

export default function LoginLogsPage() {
  const router = useRouter();
  const user = useCurrentUser();
  const [data, setData] = useState<LoginLogPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [success, setSuccess] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  async function load(offset = 0, values = { search, success, startDate, endDate }) {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
    if (values.search.trim()) params.set("search", values.search.trim());
    if (values.success) params.set("success", values.success);
    if (values.startDate) params.set("start_date", values.startDate);
    if (values.endDate) params.set("end_date", values.endDate);
    try {
      setData(await apiFetch<LoginLogPage>(`/auth/login-logs?${params.toString()}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录日志加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (user?.role === "admin") void load(0);
    else if (user) router.replace("/dashboard");
    // Load once the stored account role is available.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, user?.role, router]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void load(0, { search, success, startDate, endDate });
  }

  function resetFilters() {
    const cleared = { search: "", success: "", startDate: "", endDate: "" };
    setSearch(cleared.search);
    setSuccess(cleared.success);
    setStartDate(cleared.startDate);
    setEndDate(cleared.endDate);
    void load(0, cleared);
  }

  const rows = data?.items || [];
  const resultLabel = (item: LoginLog) => item.success ? "登录成功" : failureLabels[item.failure_reason || ""] || "登录失败";

  return <AppShell><div>
    <div className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><div className="mb-2 text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">ACCOUNT AUDIT</div><h1 className="text-[22px] font-semibold tracking-tight text-[#182230] md:text-[25px]">登录日志</h1><p className="mt-1.5 text-sm text-[#98a2b3]">记录账号登录时间与结果，仅管理员可查看；密码不会写入日志。</p></div><Badge tone="blue">仅管理员可见</Badge></div>

    <form onSubmit={applyFilters} className="mb-5 rounded-2xl border border-[#e7ebf0] bg-white p-4 shadow-soft">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="text-xs text-[#667085]">账号 / 姓名<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索登录账号或姓名" className={`${fieldClass} mt-1.5 w-full`}/></label>
        <label className="text-xs text-[#667085]">登录结果<select value={success} onChange={(event) => setSuccess(event.target.value)} className={`${fieldClass} mt-1.5 w-full`}><option value="">全部结果</option><option value="true">登录成功</option><option value="false">登录失败</option></select></label>
        <label className="text-xs text-[#667085]">开始日期<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className={`${fieldClass} mt-1.5 w-full`}/></label>
        <label className="text-xs text-[#667085]">结束日期<input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className={`${fieldClass} mt-1.5 w-full`}/></label>
        <div className="flex items-end gap-2"><button type="submit" className="min-h-10 flex-1 rounded-lg bg-[#182230] px-3 text-xs font-medium text-white">查询</button><button type="button" onClick={resetFilters} className="min-h-10 rounded-lg border border-[#e7ebf0] px-3 text-xs text-[#667085]">重置</button></div>
      </div>
    </form>

    {error && <div role="alert" className="mb-5 rounded-xl bg-[#fff2f0] px-4 py-3 text-xs text-[#c24e43]">{error}</div>}
    <section className="rounded-2xl border border-[#e7ebf0] bg-white shadow-soft">
      <div className="p-4 pb-3 md:p-5 md:pb-3"><SectionTitle title="账号登录记录" description={data ? `当前筛选共 ${data.total} 条，按时间倒序显示。` : "显示账号、登录结果和北京时间。"}/></div>
      {loading && !data ? <Loading label="正在加载登录日志"/> : !rows.length ? <Empty label={loading ? "正在刷新" : "没有符合条件的登录记录"}/> : <>
        <div className="hidden overflow-x-auto md:block"><table className="w-full min-w-[760px] text-left"><thead className="border-y border-[#f0f2f5] bg-[#fbfcfe] text-[11px] text-[#98a2b3]"><tr><th className="px-5 py-3">登录时间（北京时间）</th><th className="px-4 py-3">账号</th><th className="px-4 py-3">角色</th><th className="px-4 py-3">结果</th><th className="px-5 py-3">说明</th></tr></thead><tbody className="divide-y divide-[#f0f2f5]">{rows.map((item) => <tr key={item.id}><td className="whitespace-nowrap px-5 py-4 text-xs text-[#667085]">{formatBeijingTime(item.created_at, true)}</td><td className="px-4 py-4"><div className="text-sm font-medium text-[#182230]">{item.username}</div><div className="mt-0.5 text-[11px] text-[#98a2b3]">{item.full_name || "未匹配到系统账号"}</div></td><td className="px-4 py-4 text-xs text-[#667085]">{item.role ? roleLabels[item.role] || item.role : "—"}</td><td className="px-4 py-4"><Badge tone={item.success ? "green" : "rose"}>{item.success ? "成功" : "失败"}</Badge></td><td className="px-5 py-4 text-xs text-[#667085]">{resultLabel(item)}</td></tr>)}</tbody></table></div>
        <div className="divide-y divide-[#f0f2f5] md:hidden">{rows.map((item) => <article key={item.id} className="p-4"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="truncate text-sm font-semibold text-[#182230]">{item.full_name || item.username}</div><div className="mt-1 truncate text-[11px] text-[#98a2b3]">账号：{item.username}{item.role ? ` · ${roleLabels[item.role] || item.role}` : ""}</div></div><Badge tone={item.success ? "green" : "rose"}>{item.success ? "成功" : "失败"}</Badge></div><div className="mt-2 text-xs text-[#667085]">{formatBeijingTime(item.created_at, true)}</div>{!item.success && <div className="mt-1 text-[11px] text-[#98a2b3]">{resultLabel(item)}</div>}</article>)}</div>
      </>}
      {data && data.total > 0 && <div className="flex items-center justify-between gap-3 border-t border-[#f0f2f5] px-4 py-3 md:px-5"><span className="text-[11px] text-[#98a2b3]">{data.offset + 1}–{Math.min(data.offset + data.items.length, data.total)} / {data.total}</span><div className="flex gap-2"><button type="button" disabled={data.offset === 0 || loading} onClick={() => void load(Math.max(0, data.offset - pageSize))} className="min-h-9 rounded-lg border border-[#e7ebf0] px-3 text-xs text-[#667085] disabled:opacity-40">上一页</button><button type="button" disabled={data.offset + data.items.length >= data.total || loading} onClick={() => void load(data.offset + pageSize)} className="min-h-9 rounded-lg border border-[#e7ebf0] px-3 text-xs text-[#667085] disabled:opacity-40">下一页</button></div></div>}
    </section>
  </div></AppShell>;
}
