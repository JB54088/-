"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { AppShell, roleLabels, useCurrentUser } from "../../components/app-shell";
import { Badge } from "../../components/ui";
import { logout } from "../../lib/api";

export default function ProfilePage() {
  const router = useRouter();
  const user = useCurrentUser();

  return <AppShell><div className="mx-auto max-w-2xl">
    <div className="mb-6"><div className="mb-2 text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">ACCOUNT</div><h1 className="text-[22px] font-semibold tracking-tight text-[#182230] md:text-[25px]">我的</h1><p className="mt-1.5 text-sm text-[#98a2b3]">查看账号信息和常用入口</p></div>
    <section className="rounded-2xl border border-[#e7ebf0] bg-white p-5 shadow-soft md:p-7">
      <div className="flex items-center gap-4"><div className="flex h-16 w-16 items-center justify-center rounded-full bg-[#eaf4ff] text-2xl font-semibold text-[#1d6fd1]">{user?.full_name?.slice(0, 1) || "·"}</div><div><h2 className="text-lg font-semibold text-[#182230]">{user?.full_name || "加载中"}</h2><p className="mt-1 text-sm text-[#98a2b3]">{user?.username || ""}</p></div></div>
      <div className="mt-6 grid grid-cols-2 gap-3"><div className="rounded-xl bg-[#f7f9fc] p-4"><div className="text-xs text-[#98a2b3]">账号角色</div><div className="mt-2"><Badge tone="blue">{user ? roleLabels[user.role] : "—"}</Badge></div></div><div className="rounded-xl bg-[#f7f9fc] p-4"><div className="text-xs text-[#98a2b3]">所属部门</div><div className="mt-2 text-sm font-medium text-[#182230]">{user?.department_name || "全公司"}</div></div></div>
      <div className="mt-6 grid gap-3 sm:grid-cols-2"><Link href="/customers" className="flex min-h-11 items-center justify-center rounded-xl border border-[#e7ebf0] px-4 text-sm font-medium text-[#182230] hover:bg-[#f7f9fc]">查看客户</Link><Link href="/orders" className="flex min-h-11 items-center justify-center rounded-xl border border-[#e7ebf0] px-4 text-sm font-medium text-[#182230]">查看消费记录</Link></div>
      <button onClick={() => { logout(); router.replace("/login"); }} className="mt-3 min-h-11 w-full rounded-xl bg-[#182230] px-4 text-sm font-medium text-white">退出登录</button>
    </section>
  </div></AppShell>;
}
