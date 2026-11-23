"use client";

import { useState } from "react";

import BusinessAgentDrawer from "./BusinessAgentDrawer";

export default function BusinessAgentButton() {
  const [open, setOpen] = useState(false);
  return <><button onClick={() => setOpen(true)} className="inline-flex min-h-11 items-center rounded-xl border border-[#d8e9fb] bg-white px-4 text-xs font-medium text-[#1d6fd1] shadow-sm transition hover:bg-[#f7fbff]">✨ AI经营助手</button><BusinessAgentDrawer open={open} onClose={() => setOpen(false)}/></>;
}

