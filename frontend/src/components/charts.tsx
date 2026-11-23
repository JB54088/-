"use client";

export function formatMoney(value: number, compact = false) {
  if (compact && value >= 10000) return `¥${(value / 10000).toFixed(1)}万`;
  return `¥${Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
}

export function Sparkline({ data, color = "#3488e8", height = 88 }: { data: number[]; color?: string; height?: number }) {
  const max = Math.max(...data, 1); const min = Math.min(...data, 0); const range = max - min || 1;
  const points = data.map((value, index) => `${(index / Math.max(data.length - 1, 1)) * 100},${height - ((value - min) / range) * (height - 10) - 5}`).join(" ");
  return <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" className="h-full w-full"><defs><linearGradient id={`fill-${color.replace("#", "")}`} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".18"/><stop offset="1" stopColor={color} stopOpacity="0"/></linearGradient></defs><polyline points={`0,${height} ${points} 100,${height}`} fill={`url(#fill-${color.replace("#", "")})`} stroke="none"/><polyline points={points} fill="none" stroke={color} strokeWidth="2.1" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

export function HorizontalBars({ items, color = "#3488e8", money = false }: { items: { name: string; value: number }[]; color?: string; money?: boolean }) {
  const max = Math.max(...items.map((item) => item.value), 1);
  return <div className="space-y-4">{items.map((item, index) => <div key={`${item.name}-${index}`}><div className="mb-1.5 flex items-center justify-between text-xs"><span className="truncate text-[#667085]">{item.name}</span><span className="font-medium text-[#182230]">{money ? formatMoney(item.value, true) : item.value.toLocaleString()}</span></div><div className="h-2 overflow-hidden rounded-full bg-[#f0f3f7]"><div className="h-full rounded-full transition-all" style={{ width: `${Math.max(5, (item.value / max) * 100)}%`, backgroundColor: color }}/></div></div>)}</div>;
}

export function Donut({ items }: { items: { name: string; value: number }[] }) {
  const total = items.reduce((sum, item) => sum + item.value, 0) || 1; const colors = ["#3488e8", "#13b887", "#f4b740", "#a279e8", "#ee7b68", "#63c2cf", "#8b9aad"];
  let cursor = 0; const stops = items.map((item, index) => { const start = cursor; cursor += (item.value / total) * 360; return `${colors[index % colors.length]} ${start}deg ${cursor}deg`; }).join(", ");
  return <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-6"><div className="relative mx-auto h-32 w-32 shrink-0 rounded-full sm:mx-0" style={{ background: `conic-gradient(${stops || "#e7ebf0 0deg 360deg"})` }}><div className="absolute inset-[18px] flex flex-col items-center justify-center rounded-full bg-white"><span className="text-xl font-semibold text-[#182230]">{total}</span><span className="text-[10px] text-[#98a2b3]">来源归档</span></div></div><div className="min-w-0 flex-1 space-y-2.5">{items.map((item, index) => <div key={item.name} className="flex items-center justify-between gap-3 text-xs"><span className="flex min-w-0 items-center gap-2 text-[#667085]"><i className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: colors[index % colors.length] }}/><span className="truncate">{item.name}</span></span><span className="font-medium text-[#182230]">{Math.round(item.value / total * 100)}%</span></div>)}</div></div>;
}
