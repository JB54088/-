"use client";

import { useEffect, useState } from "react";

import { AppShell, roleLabels, useCurrentUser } from "../../components/app-shell";
import { Badge, Empty, Loading, SectionTitle } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import type { Role } from "../../types";

type UserRow = { id: number; username: string; full_name: string; role: string; department_id?: number | null; is_active: boolean };

export default function UsersPage() {
  const currentUser = useCurrentUser();
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [error, setError] = useState("");
  const load = () => apiFetch<UserRow[]>("/users").then(setUsers).catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  useEffect(() => { load(); }, []);
  const toggle = async (user: UserRow) => { try { await apiFetch(`/users/${user.id}/status?is_active=${!user.is_active}`, { method: "PATCH" }); load(); } catch (err) { setError(err instanceof Error ? err.message : "更新失败"); } };
  const canManage = currentUser?.role === "admin";
  return <AppShell><div>
    <div className="mb-6 md:mb-7"><div className="mb-2 text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">ACCESS CONTROL</div><h1 className="text-[22px] font-semibold tracking-tight text-[#182230] md:text-[25px]">用户权限</h1><p className="mt-1.5 text-sm text-[#98a2b3]">系统仅保留管理员/主管与业务员两种角色</p></div>
    <section className="rounded-2xl border border-[#e7ebf0] bg-white shadow-soft"><div className="p-4 pb-3 md:p-5 md:pb-3"><SectionTitle title="团队成员" description="权限在 FastAPI 后端校验，前端隐藏菜单不作为安全边界"/></div>{error ? <div className="p-5 text-sm text-[#c24e43]">{error}</div> : !users ? <Loading/> : !users.length ? <Empty/> : <div className="divide-y divide-[#f0f2f5]">{users.map((user) => <div key={user.id} className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between md:px-5"><div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#eaf4ff] text-xs font-semibold text-[#3488e8]">{user.full_name.slice(0, 1)}</div><div><div className="text-sm font-medium text-[#182230]">{user.full_name}</div><div className="mt-1 text-[11px] text-[#98a2b3]">@{user.username}</div></div></div><div className="flex items-center justify-between gap-3 sm:justify-end"><Badge tone={user.is_active ? "green" : "gray"}>{user.is_active ? "启用中" : "已停用"}</Badge><span className="w-24 text-xs text-[#667085]">{roleLabels[user.role as Role] || user.role}</span>{canManage && <button disabled={user.id === currentUser?.id} onClick={() => toggle(user)} className="min-h-10 rounded-lg border border-[#e7ebf0] px-3 py-1.5 text-[11px] text-[#667085] disabled:cursor-not-allowed disabled:opacity-40">{user.is_active ? "停用" : "启用"}</button>}</div></div>)}</div>}</section>
  </div></AppShell>;
}
