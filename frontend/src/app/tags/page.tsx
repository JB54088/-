"use client";

import { useEffect, useState } from "react";

import { AppShell } from "../../components/app-shell";
import { Badge, Empty, Loading, SectionTitle } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import type { Tag } from "../../types";

export default function TagsPage() {
  const [tags, setTags] = useState<Tag[] | null>(null); const [name, setName] = useState(""); const [color, setColor] = useState("blue"); const [error, setError] = useState("");
  const load = () => apiFetch<Tag[]>("/tags").then(setTags).catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  useEffect(() => { load(); }, []);
  const create = async (event: React.FormEvent) => { event.preventDefault(); try { await apiFetch("/tags", { method: "POST", body: JSON.stringify({ name, color }) }); setName(""); load(); } catch (err) { setError(err instanceof Error ? err.message : "创建失败"); } };
  const rename = async (tag: Tag) => { const next = window.prompt("修改标签名称", tag.name); if (!next || next === tag.name) return; try { await apiFetch(`/tags/${tag.id}`, { method: "PATCH", body: JSON.stringify({ name: next }) }); load(); } catch (err) { setError(err instanceof Error ? err.message : "修改失败"); } };
  return <AppShell><div><div className="mb-7"><div className="mb-2 text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">CUSTOMER TAGS</div><h1 className="text-[25px] font-semibold tracking-tight text-[#182230]">客户标签</h1><p className="mt-1.5 text-sm text-[#98a2b3]">管理员动态创建和维护标签，业务员只能查看自己客户的标签</p></div><form onSubmit={create} className="mb-5 flex flex-col gap-3 rounded-2xl border border-[#e7ebf0] bg-white p-5 shadow-soft sm:flex-row"><input required value={name} onChange={(event) => setName(event.target.value)} placeholder="新标签名称，例如：重点跟进" className="h-10 flex-1 rounded-lg border border-[#e7ebf0] px-3 text-sm"/><select value={color} onChange={(event) => setColor(event.target.value)} className="h-10 rounded-lg border border-[#e7ebf0] px-3 text-xs"><option value="blue">蓝色</option><option value="green">绿色</option><option value="amber">琥珀</option><option value="rose">红色</option><option value="violet">紫色</option><option value="gray">灰色</option></select><button className="h-10 rounded-lg bg-[#182230] px-5 text-xs font-medium text-white">创建标签</button></form>{error && <div className="mb-5 rounded-xl bg-[#fff2f0] px-4 py-3 text-xs text-[#c24e43]">{error}</div>}<section className="rounded-2xl border border-[#e7ebf0] bg-white p-5 shadow-soft"><SectionTitle title="标签列表" description="标签数据来自 customer_tags 表"/>{!tags ? <Loading/> : !tags.length ? <Empty/> : <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">{tags.map((tag) => <div key={tag.id} className="flex items-center justify-between rounded-xl border border-[#e7ebf0] p-4"><div><Badge>{tag.name}</Badge><div className="mt-2 text-xs text-[#98a2b3]">已关联 {tag.customer_count || 0} 位客户</div></div><button onClick={() => rename(tag)} className="rounded-lg border border-[#e7ebf0] px-3 py-1.5 text-[11px] text-[#667085]">修改</button></div>)}</div>}</section></div></AppShell>;
}
