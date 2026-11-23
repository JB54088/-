export function SectionTitle({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: React.ReactNode }) {
  return <div className="mb-4 flex items-end justify-between gap-4"><div>{eyebrow && <div className="mb-1 text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">{eyebrow}</div>}<h2 className="text-[17px] font-semibold leading-6 tracking-tight text-[#182230]">{title}</h2>{description && <p className="mt-0.5 text-xs leading-5 text-[#98a2b3]">{description}</p>}</div>{action}</div>;
}

export function Badge({ children, tone = "blue" }: { children: React.ReactNode; tone?: "blue" | "green" | "amber" | "gray" | "rose" }) {
  const styles = { blue: "bg-[#eaf4ff] text-[#1d6fd1]", green: "bg-[#e8faf4] text-[#07875f]", amber: "bg-[#fff7e5] text-[#a56b00]", gray: "bg-[#f1f3f6] text-[#667085]", rose: "bg-[#fff0ee] text-[#cc574a]" };
  return <span className={`inline-flex min-h-6 items-center rounded-full px-2.5 py-1 text-[10px] font-medium leading-4 ${styles[tone]}`}>{children}</span>;
}

export function Loading({ label = "正在加载" }: { label?: string }) { return <div className="flex min-h-[120px] items-center justify-center text-xs text-[#98a2b3]"><span className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-[#dff0ff] border-t-[#3488e8]"/>{label}…</div>; }

export function Empty({ label = "暂无数据" }: { label?: string }) { return <div className="flex min-h-[64px] items-center justify-center px-4 py-4 text-xs text-[#98a2b3]">{label}</div>; }

export function MobileSheet({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: React.ReactNode }) {
  if (!open) return null;
  return <div className="fixed inset-0 z-50 md:hidden">
    <button aria-label="关闭弹层" onClick={onClose} className="absolute inset-0 bg-[#182230]/30" />
    <div className="absolute bottom-0 left-0 right-0 max-h-[88vh] overflow-y-auto rounded-t-[20px] bg-white p-4 shadow-2xl" style={{ paddingBottom: "calc(16px + env(safe-area-inset-bottom))" }}>
      <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-[#d0d5dd]" />
      <div className="mb-4 flex items-center justify-between"><h2 className="text-[17px] font-semibold text-[#182230]">{title}</h2><button aria-label="关闭" onClick={onClose} className="flex h-10 w-10 items-center justify-center rounded-full bg-[#f7f9fc] text-xl text-[#667085]">×</button></div>
      {children}
    </div>
  </div>;
}
