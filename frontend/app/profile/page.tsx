"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AppShell, roleLabels, useCurrentUser } from "../../components/app-shell";
import { Badge } from "../../components/ui";
import { apiFetch, logout, setStoredUser } from "../../lib/api";
import type { User } from "../../types";

export default function ProfilePage() {
  const router = useRouter();
  const user = useCurrentUser();
  const [editingName, setEditingName] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [nameError, setNameError] = useState("");
  const [nameSaved, setNameSaved] = useState(false);

  useEffect(() => {
    if (user) setDisplayName(user.full_name);
  }, [user?.id, user?.full_name]);

  async function saveDisplayName(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = displayName.trim();
    if (!normalized) {
      setNameError("姓名不能为空");
      return;
    }
    if (normalized.length > 80) {
      setNameError("姓名不能超过80个字符");
      return;
    }
    setSavingName(true);
    setNameError("");
    setNameSaved(false);
    try {
      const updated = await apiFetch<User>("/auth/me/profile", {
        method: "PATCH",
        body: JSON.stringify({ display_name: normalized }),
      });
      setStoredUser(updated);
      setDisplayName(updated.full_name);
      setEditingName(false);
      setNameSaved(true);
    } catch (error) {
      setNameError(error instanceof Error ? error.message : "姓名保存失败，请重试");
    } finally {
      setSavingName(false);
    }
  }

  return <AppShell><div className="mx-auto max-w-2xl">
    <div className="mb-6"><div className="mb-2 text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">ACCOUNT</div><h1 className="text-[22px] font-semibold tracking-tight text-[#182230] md:text-[25px]">我的</h1><p className="mt-1.5 text-sm text-[#98a2b3]">查看账号信息和常用入口</p></div>
    <section className="rounded-2xl border border-[#e7ebf0] bg-white p-5 shadow-soft md:p-7">
      <div className="flex items-center gap-4"><div className="flex h-16 w-16 items-center justify-center rounded-full bg-[#eaf4ff] text-2xl font-semibold text-[#1d6fd1]">{user?.full_name?.slice(0, 1) || "·"}</div><div><h2 className="text-lg font-semibold text-[#182230]">{user?.full_name || "加载中"}</h2><p className="mt-1 text-sm text-[#98a2b3]">{user?.username || ""}</p></div></div>
      {user?.role === "salesperson" && <section className="mt-5 rounded-xl border border-[#e7ebf0] p-4">
        <div className="flex items-center justify-between gap-3"><div><div className="text-xs text-[#98a2b3]">显示姓名</div><div className="mt-1 text-sm font-medium text-[#182230]">{user.full_name}</div></div><button type="button" onClick={() => { setEditingName((value) => !value); setNameError(""); setNameSaved(false); setDisplayName(user.full_name); }} className="min-h-10 rounded-lg border border-[#d7e6f7] px-3 text-sm font-medium text-[#1d6fd1]">{editingName ? "取消" : "修改姓名"}</button></div>
        {editingName && <form onSubmit={saveDisplayName} className="mt-4 space-y-3">
          <label className="block"><span className="mb-1.5 block text-xs text-[#667085]">新姓名</span><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={80} autoComplete="name" className="h-11 w-full rounded-xl border border-[#e7ebf0] px-3 text-sm outline-none focus:border-[#3488e8]" placeholder="请输入显示姓名" /></label>
          {nameError && <p role="alert" className="text-xs text-[#d7473f]">{nameError}</p>}
          <button disabled={savingName} className="min-h-10 rounded-lg bg-[#1d6fd1] px-4 text-sm font-medium text-white disabled:opacity-60">{savingName ? "保存中…" : "保存姓名"}</button>
        </form>}
        {nameSaved && <p role="status" className="mt-3 text-xs text-emerald-700">姓名已更新，所有页面将同步显示。</p>}
      </section>}
      <div className="mt-6 grid grid-cols-2 gap-3"><div className="rounded-xl bg-[#f7f9fc] p-4"><div className="text-xs text-[#98a2b3]">账号角色</div><div className="mt-2"><Badge tone="blue">{user ? roleLabels[user.role] : "—"}</Badge></div></div><div className="rounded-xl bg-[#f7f9fc] p-4"><div className="text-xs text-[#98a2b3]">所属部门</div><div className="mt-2 text-sm font-medium text-[#182230]">{user?.department_name || "全公司"}</div></div></div>
      <div className="mt-6 grid gap-3 sm:grid-cols-2"><Link href="/customers" className="flex min-h-11 items-center justify-center rounded-xl border border-[#e7ebf0] px-4 text-sm font-medium text-[#182230] hover:bg-[#f7f9fc]">查看客户</Link><Link href="/orders" className="flex min-h-11 items-center justify-center rounded-xl border border-[#e7ebf0] px-4 text-sm font-medium text-[#182230]">查看消费记录</Link></div>
      <button onClick={() => { logout(); router.replace("/login"); }} className="mt-3 min-h-11 w-full rounded-xl bg-[#182230] px-4 text-sm font-medium text-white">退出登录</button>
    </section>
  </div></AppShell>;
}
