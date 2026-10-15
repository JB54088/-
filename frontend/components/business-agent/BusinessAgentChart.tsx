"use client";

type Point = { label: string; value: number };

export default function BusinessAgentChart({ type, data }: { type: "bar" | "pie" | "line"; data: Point[] }) {
  if (!data.length) return null;
  const max = Math.max(...data.map((item) => item.value), 1);
  const format = (value: number) => `¥${value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return <div className="mt-3 rounded-xl border border-[#e7ebf0] bg-[#fbfcfe] p-3">
    <div className="mb-2 text-[11px] font-medium text-[#667085]">{type === "pie" ? "占比拆分" : "结果明细"}</div>
    <div className="space-y-2">{data.slice(0, 10).map((item) => <div key={item.label}>
      <div className="mb-1 flex items-center justify-between gap-3 text-[11px] text-[#667085]"><span className="min-w-0 truncate">{item.label}</span><span className="shrink-0 font-medium text-[#182230]">{Number.isInteger(item.value) ? item.value.toLocaleString("zh-CN") : format(item.value)}</span></div>
      <div className="h-1.5 overflow-hidden rounded-full bg-[#eaf0f6]"><div className={`h-full rounded-full ${type === "pie" ? "bg-[#3488e8]" : "bg-[#7d5ac7]"}`} style={{ width: `${Math.max(3, Math.min(100, (item.value / max) * 100))}%` }} /></div>
    </div>)}</div></div>
}
