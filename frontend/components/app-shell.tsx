"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getStoredUser, logout } from "../lib/api";
import type { Role, User } from "../types";
import { Icon } from "./icons";

export const roleLabels: Record<Role, string> = { admin: "管理员 / 主管", salesperson: "业务员" };

const adminNav = [
  { href: "/dashboard", label: "经营看板", icon: "dashboard" },
  { href: "/leads", label: "线索审核", icon: "leads" },
  { href: "/customers", label: "市场部客户管理", icon: "users" },
  { href: "/orders", label: "消费管理", icon: "orders" },
];

const salespersonNav = [
  { href: "/dashboard", label: "我的业绩", icon: "dashboard" },
  { href: "/leads", label: "报备线索", icon: "leads" },
  { href: "/customers", label: "我的客户", icon: "users" },
  { href: "/orders", label: "客户消费", icon: "orders" },
];

function itemsFor(user: User | null) {
  return user?.role === "admin" ? adminNav : salespersonNav;
}

export function useCurrentUser() {
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => { setUser(getStoredUser()); }, []);
  return user;
}

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const user = useCurrentUser();
  const visibleNavItems = itemsFor(user);
  const mobileItems = user?.role === "admin"
    ? [
        { ...adminNav[0], label: "首页" },
        { ...adminNav[2], label: "客户" },
        { ...adminNav[1], label: "分配" },
        { href: "/profile", label: "我的", icon: "user" },
      ]
    : [
        { ...salespersonNav[0], label: "首页" },
        { ...salespersonNav[2], label: "客户" },
        { ...salespersonNav[1], label: "报备" },
        { ...salespersonNav[3], label: "业绩" },
        { href: "/profile", label: "我的", icon: "user" },
      ];

  useEffect(() => {
    const stored = getStoredUser();
    if (!stored) router.replace("/login");
    // useCurrentUser hydrates the same user state after the client is ready.
  }, [router]);

  const handleLogout = () => {
    logout();
    router.replace("/login");
  };

  const currentTitle = pathname.startsWith("/profile") ? "我的" : pathname.startsWith("/tags") ? "客户标签" : pathname.startsWith("/users") ? "用户权限" : pathname.startsWith("/assignment-history") ? "归属变更历史" : pathname.startsWith("/duplicate-reports") ? "重复报备" : pathname.startsWith("/excel-imports") ? "ABC Excel 导入" : pathname.startsWith("/customers/") ? "客户详情" : visibleNavItems.find((item) => isActive(pathname, item.href))?.label || "工作台";

  return (
    <div className="min-h-screen overflow-x-hidden bg-[#f7f9fc]">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[248px] flex-col border-r border-[#e7ebf0] bg-white px-4 py-5 md:flex">
        <div className="mb-8 flex items-center gap-3 px-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-[14px] bg-[#eaf4ff] text-[#3488e8]"><span className="text-lg font-bold">观</span></div>
          <div><div className="text-[16px] font-semibold tracking-tight text-[#182230]">观云春</div><div className="mt-0.5 text-[10px] font-medium tracking-[.18em] text-[#98a2b3]">ASSET OPERATING</div></div>
        </div>
        <div className="mb-3 px-3 text-[11px] font-semibold uppercase tracking-[.16em] text-[#98a2b3]">工作台</div>
        <nav className="space-y-1">
        {visibleNavItems.map((item) => {
          const active = isActive(pathname, item.href);
            return <Link key={item.href} href={item.href} className={`flex min-h-10 items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium transition ${active ? "bg-[#eaf4ff] text-[#1d6fd1]" : "text-[#667085] hover:bg-[#f7f9fc] hover:text-[#182230]"}`}><Icon name={item.icon} size={18}/><span>{item.label}</span>{active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[#3488e8]"/>}</Link>;
          })}
        </nav>
        {user?.role === "admin" && <>
          <div className="mb-2 mt-6 px-3 text-[10px] font-semibold uppercase tracking-[.16em] text-[#98a2b3]">配置</div>
          <Link href="/tags" className={`flex min-h-10 items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium ${pathname.startsWith("/tags") ? "bg-[#eaf4ff] text-[#1d6fd1]" : "text-[#667085] hover:bg-[#f7f9fc]"}`}><Icon name="tag" size={18}/><span>客户标签</span></Link>
          <Link href="/users" className={`mt-1 flex min-h-10 items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium ${pathname.startsWith("/users") ? "bg-[#eaf4ff] text-[#1d6fd1]" : "text-[#667085] hover:bg-[#f7f9fc]"}`}><Icon name="users" size={18}/><span>用户权限</span></Link>
          <Link href="/assignment-history" className={`mt-1 flex min-h-10 items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium ${pathname.startsWith("/assignment-history") ? "bg-[#eaf4ff] text-[#1d6fd1]" : "text-[#667085] hover:bg-[#f7f9fc]"}`}><Icon name="history" size={18}/><span>归属变更历史</span></Link>
          <Link href="/duplicate-reports" className={`mt-1 flex min-h-10 items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium ${pathname.startsWith("/duplicate-reports") ? "bg-[#eaf4ff] text-[#1d6fd1]" : "text-[#667085] hover:bg-[#f7f9fc]"}`}><Icon name="leads" size={18}/><span>重复报备</span></Link>
          <Link href="/excel-imports" className={`mt-1 flex min-h-10 items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium ${pathname.startsWith("/excel-imports") ? "bg-[#eaf4ff] text-[#1d6fd1]" : "text-[#667085] hover:bg-[#f7f9fc]"}`}><Icon name="upload" size={18}/><span>ABC Excel 导入</span></Link>
        </>}
        <div className="mt-auto rounded-2xl bg-[#f7f9fc] p-3">
          <div className="mb-3 flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#dff0ff] text-sm font-semibold text-[#1d6fd1]">{user?.full_name?.slice(0, 1) || "-"}</div><div className="min-w-0"><div className="truncate text-[13px] font-semibold text-[#182230]">{user?.full_name || "加载中"}</div><div className="truncate text-[11px] text-[#98a2b3]">{user ? roleLabels[user.role] : ""}</div></div></div>
          <button onClick={handleLogout} className="flex min-h-10 w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-xs text-[#667085] hover:bg-white hover:text-[#182230]"><Icon name="logout" size={15}/>退出登录</button>
        </div>
      </aside>

      <main className="min-w-0 md:pl-[248px]">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-[#e7ebf0] bg-white/95 px-4 backdrop-blur md:h-[72px] md:px-9">
          <div className="min-w-0">
            <div className="hidden text-sm text-[#98a2b3] md:block">企业客户资产平台 <span className="mx-2 text-[#d0d5dd]">/</span> <span className="text-[#667085]">{currentTitle}</span></div>
            <h1 className="truncate text-[18px] font-semibold tracking-tight text-[#182230] md:hidden">{currentTitle}</h1>
          </div>
          <div className="flex items-center gap-1.5 md:gap-4">
            <Link href="/customers" aria-label="搜索客户" className="flex h-10 w-10 items-center justify-center rounded-xl text-[#667085] hover:bg-[#f7f9fc] md:hidden"><Icon name="search" size={19}/></Link>
            <button aria-label="刷新页面" onClick={() => window.location.reload()} className="flex h-10 w-10 items-center justify-center rounded-xl text-[#667085] hover:bg-[#f7f9fc] md:hidden"><Icon name="refresh" size={18}/></button>
            <div className="hidden text-right sm:block"><div className="text-xs font-medium text-[#182230]">{user?.full_name}</div><div className="text-[11px] text-[#98a2b3]">{user ? roleLabels[user.role] : ""}</div></div>
            <Link href="/profile" aria-label="我的" className="flex h-9 w-9 items-center justify-center rounded-full bg-[#182230] text-xs font-semibold text-white">{user?.full_name?.slice(0, 1) || "·"}</Link>
          </div>
        </header>
        <div className="mobile-safe min-w-0 px-4 py-4 md:px-9 md:py-8">{children}</div>
      </main>

      <nav className={`fixed bottom-0 left-0 right-0 z-30 grid ${user?.role === "admin" ? "grid-cols-4" : "grid-cols-5"} border-t border-[#e7ebf0] bg-white/95 px-1 pt-1.5 backdrop-blur md:hidden`} style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
        {mobileItems.map((item) => {
          const active = isActive(pathname, item.href);
          return <Link key={item.href} href={item.href} className={`flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-lg text-[11px] ${active ? "font-semibold text-[#1d6fd1]" : "text-[#98a2b3]"}`}><Icon name={item.icon} size={19}/>{item.label}</Link>;
        })}
      </nav>
    </div>
  );
}
