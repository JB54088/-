"use client";

import { useEffect, useRef, useState } from "react";

import { apiFetch } from "../../lib/api";
import BusinessAgentChart from "./BusinessAgentChart";

type AgentResponse = {
  answer: string;
  data: { rows?: { label: string; value: number }[] };
  chart?: { type: "bar" | "pie" | "line"; title: string; data: { label: string; value: number }[] } | null;
};

type Message = { role: "user" | "assistant"; text: string; chart?: AgentResponse["chart"] };

const suggestions = ["本月有效经营收入多少？", "本月医保和自费分别多少？", "本月各业务员客户消费最高的是谁？", "累计充值和当前储值余额多少？"];

export default function BusinessAgentDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [messages, setMessages] = useState<Message[]>([{ role: "assistant", text: "你好，我可以帮你查询客户、消费、医保、自费、来源、业务员和会员储值数据。" }]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const messageAreaRef = useRef<HTMLDivElement>(null);
  const touchStartYRef = useRef<number | null>(null);

  useEffect(() => { if (open) endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, open]);
  useEffect(() => { if (!open) return; const handler = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); }; window.addEventListener("keydown", handler); return () => window.removeEventListener("keydown", handler); }, [open, onClose]);
  useEffect(() => {
    if (!open || typeof window === "undefined") return;
    const body = document.body;
    const html = document.documentElement;
    const scrollY = window.scrollY;
    const scrollbarWidth = window.innerWidth - html.clientWidth;
    const previous = {
      overflow: body.style.overflow,
      position: body.style.position,
      top: body.style.top,
      width: body.style.width,
      paddingRight: body.style.paddingRight,
      overscrollBehavior: html.style.overscrollBehavior,
    };

    // Fixed positioning is more reliable than overflow:hidden alone in iOS
    // Safari and the Enterprise WeChat WebView. The scroll offset is restored
    // after releasing the lock so closing the drawer never jumps the page.
    body.style.overflow = "hidden";
    body.style.position = "fixed";
    body.style.top = `-${scrollY}px`;
    body.style.width = "100%";
    if (scrollbarWidth > 0) body.style.paddingRight = `${scrollbarWidth}px`;
    html.style.overscrollBehavior = "none";

    return () => {
      body.style.overflow = previous.overflow;
      body.style.position = previous.position;
      body.style.top = previous.top;
      body.style.width = previous.width;
      body.style.paddingRight = previous.paddingRight;
      html.style.overscrollBehavior = previous.overscrollBehavior;
      window.scrollTo(0, scrollY);
    };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onTouchStart = (event: TouchEvent) => {
      touchStartYRef.current = event.touches[0]?.clientY ?? null;
    };
    const onTouchMove = (event: TouchEvent) => {
      const messageArea = messageAreaRef.current;
      const target = event.target;
      const targetElement = target instanceof Element ? target : null;
      if (targetElement?.closest("[data-ai-horizontal-scroll]")) {
        // Let the browser handle the shortcut row's native horizontal scroll.
        // The body is already fixed, so this cannot move the dashboard behind it.
        return;
      }
      const isMessageTouch = Boolean(messageArea && target instanceof Node && messageArea.contains(target));
      if (!isMessageTouch || !messageArea) {
        // The header, backdrop, and input area must never hand a gesture to
        // the document behind the fixed drawer.
        event.preventDefault();
        return;
      }

      const currentY = event.touches[0]?.clientY;
      const previousY = touchStartYRef.current;
      if (currentY === undefined || previousY === null) return;
      const movingDown = currentY > previousY;
      const movingUp = currentY < previousY;
      const atTop = messageArea.scrollTop <= 0;
      const atBottom = messageArea.scrollTop + messageArea.clientHeight >= messageArea.scrollHeight - 1;
      if ((atTop && movingDown) || (atBottom && movingUp)) event.preventDefault();
      touchStartYRef.current = currentY;
    };

    // iOS Safari and the Enterprise WeChat WebView ignore body overflow locks
    // for some touch gestures, so the listener must be non-passive.
    document.addEventListener("touchstart", onTouchStart, { capture: true, passive: true });
    document.addEventListener("touchmove", onTouchMove, { capture: true, passive: false });
    return () => {
      document.removeEventListener("touchstart", onTouchStart, true);
      document.removeEventListener("touchmove", onTouchMove, true);
      touchStartYRef.current = null;
    };
  }, [open]);

  if (!open) return null;
  const send = async (value = question) => {
    const text = value.trim();
    if (!text || loading) return;
    setQuestion(""); setError(""); setLoading(true); setMessages((items) => [...items, { role: "user", text }]);
    try {
      const result = await apiFetch<AgentResponse>("/agents/business-analysis/query", { method: "POST", body: JSON.stringify({ question: text }) });
      setMessages((items) => [...items, { role: "assistant", text: result.answer, chart: result.chart }]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "查询失败，请稍后重试"); }
    finally { setLoading(false); }
  };
  return <>
    <button aria-label="关闭 AI 经营助手" className="fixed inset-0 z-40 touch-none cursor-default overscroll-none bg-[#182230]/25" onTouchMove={(event) => event.preventDefault()} onClick={onClose}/>
    <aside onTouchMove={(event) => event.stopPropagation()} className="fixed inset-0 z-50 flex h-[100dvh] max-h-[100dvh] flex-col overscroll-none overflow-hidden rounded-none border border-[#e7ebf0] bg-white shadow-2xl md:left-auto md:right-0 md:w-[460px] md:border-y-0 md:border-r-0">
      <header className="flex items-center justify-between border-b border-[#f0f2f5] px-4 py-3 md:px-5"><div><div className="text-[10px] font-semibold uppercase tracking-[.18em] text-[#3488e8]">AI BUSINESS ASSISTANT</div><h2 className="mt-1 text-base font-semibold text-[#182230]">AI经营助手</h2></div><button onClick={onClose} className="min-h-10 min-w-10 rounded-lg text-xl leading-none text-[#98a2b3] hover:bg-[#f7f9fc]" aria-label="关闭">×</button></header>
      <div ref={messageAreaRef} data-ai-message-scroll="vertical" className="min-h-0 flex-1 touch-pan-y space-y-3 overflow-y-auto overscroll-contain px-4 py-4 md:px-5" style={{ WebkitOverflowScrolling: "touch", overscrollBehaviorY: "contain" }}>{messages.map((message, index) => <div key={`${message.role}-${index}`} className={message.role === "user" ? "ml-8" : "mr-3"}><div className={message.role === "user" ? "rounded-2xl rounded-br-md bg-[#182230] px-3 py-2.5 text-sm leading-6 text-white" : "rounded-2xl rounded-bl-md border border-[#e7ebf0] bg-[#fbfcfe] px-3 py-2.5 text-sm leading-6 text-[#344054]"}>{message.text}</div>{message.chart && <BusinessAgentChart type={message.chart.type} data={message.chart.data}/>}</div>)}{loading && <div className="mr-12 rounded-2xl rounded-bl-md border border-[#e7ebf0] bg-[#fbfcfe] px-3 py-2.5 text-sm text-[#98a2b3]">正在查询真实经营数据…</div>}{error && <div className="rounded-xl border border-[#ffd8d3] bg-[#fff5f3] px-3 py-2 text-xs text-[#c24e43]">{error}</div>}<div ref={endRef}/></div>
      <div className="flex-none border-t border-[#f0f2f5] bg-white px-4 pb-[calc(12px+env(safe-area-inset-bottom))] pt-3 md:px-5 md:pb-4"><div data-ai-horizontal-scroll="true" className="scrollbar-hide mb-2 flex flex-nowrap gap-2 overflow-x-auto overflow-y-hidden whitespace-nowrap overscroll-x-contain touch-pan-x">{suggestions.map((item) => <button key={item} onClick={() => send(item)} disabled={loading} className="min-h-8 shrink-0 whitespace-nowrap rounded-full border border-[#d8e9fb] bg-[#f7fbff] px-3 text-[11px] text-[#1d6fd1] disabled:opacity-50">{item}</button>)}</div><div className="flex items-end gap-2"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); } }} rows={2} placeholder="例如：本月各业务员消费最高的是谁？" className="min-h-11 min-w-0 flex-1 resize-none rounded-xl border border-[#e7ebf0] bg-[#fbfcfe] px-3 py-2.5 text-sm outline-none focus:border-[#3488e8]"/><button onClick={() => send()} disabled={loading || !question.trim()} className="min-h-11 shrink-0 rounded-xl bg-[#182230] px-4 text-xs font-medium text-white disabled:opacity-40">{loading ? "查询中" : "发送"}</button></div></div>
    </aside>
  </>;
}
