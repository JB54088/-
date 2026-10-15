"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { API_URL } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("admin01");
  const [password, setPassword] = useState("Admin01@123");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError("");
    try {
      const response = await fetch(`${API_URL}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "账号或密码错误");
      window.localStorage.setItem("customer_assets_token", data.access_token);
      window.localStorage.setItem("customer_assets_user", JSON.stringify(data.user));
      router.replace("/dashboard");
    } catch (err) { setError(err instanceof Error ? err.message : "登录失败"); } finally { setLoading(false); }
  }

  return <main className="flex min-h-screen bg-white">
    <section className="relative hidden w-[48%] overflow-hidden bg-[#142b48] p-12 text-white lg:flex lg:flex-col lg:justify-between">
      <div className="absolute -right-20 -top-20 h-80 w-80 rounded-full border border-white/10"/><div className="absolute -bottom-40 -left-20 h-[420px] w-[420px] rounded-full border border-white/10"/>
      <div className="relative"><div className="mb-12 flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-[14px] bg-white/10 text-lg font-bold">观</div><div><div className="font-semibold tracking-tight">观云春</div><div className="text-[9px] tracking-[.24em] text-white/50">ASSET OPERATING</div></div></div><div className="max-w-md"><div className="mb-5 text-xs font-medium tracking-[.24em] text-[#75b9ff]">CUSTOMER ASSET OPERATING SYSTEM</div><h1 className="text-4xl font-semibold leading-[1.18] tracking-tight">让每一位客户，<br/><span className="text-[#75b9ff]">成为可经营的资产。</span></h1><p className="mt-6 text-sm leading-7 text-white/60">统一客户、归属、消费和复购数据，把分散的经营动作变成清晰的增长决策。</p></div></div>
      <div className="relative grid grid-cols-3 gap-4 border-t border-white/10 pt-6 text-white/70"><div><div className="text-2xl font-semibold text-white">200+</div><div className="mt-1 text-xs">演示客户档案</div></div><div><div className="text-2xl font-semibold text-white">1,000</div><div className="mt-1 text-xs">消费记录已接入</div></div><div><div className="text-2xl font-semibold text-white">5</div><div className="mt-1 text-xs">经营团队部门</div></div></div>
    </section>
    <section className="flex flex-1 items-center justify-center bg-[#f7f9fc] px-6 py-12"><div className="w-full max-w-[390px] rounded-3xl bg-white p-7 shadow-soft sm:p-10"><div className="mb-9"><div className="mb-2 text-2xl font-semibold tracking-tight text-[#182230]">欢迎回来</div><p className="text-sm text-[#98a2b3]">登录客户线索与资产经营工作台</p></div><form onSubmit={submit} className="space-y-5"><label className="block"><span className="mb-2 block text-xs font-medium text-[#667085]">账号</span><input value={username} onChange={(event) => setUsername(event.target.value)} className="h-12 w-full rounded-xl border border-[#e7ebf0] bg-[#fbfcfe] px-4 text-sm outline-none transition focus:border-[#3488e8] focus:ring-4 focus:ring-[#3488e8]/10" placeholder="输入登录账号" autoComplete="username"/></label><label className="block"><div className="mb-2 flex items-center justify-between"><span className="text-xs font-medium text-[#667085]">密码</span><span className="text-xs text-[#98a2b3]">管理员 Admin01@123</span></div><input value={password} onChange={(event) => setPassword(event.target.value)} type="password" className="h-12 w-full rounded-xl border border-[#e7ebf0] bg-[#fbfcfe] px-4 text-sm outline-none transition focus:border-[#3488e8] focus:ring-4 focus:ring-[#3488e8]/10" placeholder="输入登录密码" autoComplete="current-password"/></label>{error && <div className="rounded-xl bg-[#fff2f0] px-4 py-3 text-xs text-[#d7473f]">{error}</div>}<button disabled={loading} className="h-12 w-full rounded-xl bg-[#1d6fd1] text-sm font-semibold text-white shadow-lg shadow-[#1d6fd1]/20 transition hover:bg-[#1556a8] disabled:cursor-not-allowed disabled:opacity-60">{loading ? "正在登录…" : "登录工作台"}</button></form><p className="mt-8 text-center text-[11px] leading-5 text-[#b0b7c3]">登录即表示你同意平台使用规范<br/>企业微信 H5 登录能力将在后续版本接入</p></div></section>
  </main>;
}
