import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { Search, LogOut } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { MODULES, NAV_ORDER, tileStyle } from "@/lib/modules";

export function Sidebar({ onSearch, cloud }: { onSearch: () => void; cloud?: boolean }) {
  const notes = useQuery({ queryKey: ["notif-count"], queryFn: () => api.get<any[]>("/notifications", { status: "nieuw" }), refetchInterval: 60_000 });
  const count = notes.data?.length || 0;
  const mac = typeof navigator !== "undefined" && /Mac/i.test(navigator.platform);
  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-[248px] flex-col border-r border-line bg-[#f7f7f8]/90 backdrop-blur-xl">
      <div className="flex items-center gap-2.5 px-5 pt-6 pb-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-[9px] shadow-[0_1px_2px_rgba(0,0,0,0.2)]" style={tileStyle("#1f4e46")}>
          <svg viewBox="0 0 64 64" className="h-4 w-4"><path d="M14 18l18 30 18-30" fill="none" stroke="#fff" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </div>
        <div className="leading-tight">
          <div className="text-[14px] font-semibold text-ink tracking-tight">Vetera Intelligence</div>
          <div className="text-[11.5px] text-ink-muted">Competitive Intelligence</div>
        </div>
      </div>
      <button onClick={onSearch} className="mx-3 mb-3 flex items-center gap-2 rounded-[9px] border border-line bg-white px-2.5 py-[7px] text-left text-[13px] text-ink-faint shadow-[0_1px_1px_rgba(0,0,0,0.03)] hover:text-ink-muted">
        <Search className="h-3.5 w-3.5" />
        <span className="flex-1">Zoeken</span>
        <kbd className="rounded bg-surface px-1.5 font-sans text-[11px] text-ink-muted">{mac ? "⌘" : "Ctrl"} K</kbd>
      </button>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3">
        {NAV_ORDER.map((k) => {
          const n = MODULES[k];
          return (
            <NavLink key={k} to={n.to} end={n.end} className="block">
              {({ isActive }) => (
                <div className={cn("relative flex items-center gap-2.5 rounded-[9px] px-2 py-[6px] text-[13.5px] transition-colors", isActive ? "text-ink font-medium" : "text-ink-soft hover:bg-black/[0.035] hover:text-ink")}>
                  {isActive && <motion.div layoutId="nav-active" className="absolute inset-0 rounded-[9px] bg-white shadow-[0_1px_2px_rgba(0,0,0,0.06),0_0_0_0.5px_rgba(0,0,0,0.06)]" transition={{ type: "spring", bounce: 0.12, duration: 0.4 }} />}
                  <span className="relative flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-[6px] shadow-[0_0.5px_1px_rgba(0,0,0,0.18)]" style={tileStyle(n.color)}>
                    <n.icon className="h-[13px] w-[13px] text-white" strokeWidth={2.2} />
                  </span>
                  <span className="relative flex-1 truncate">{n.label}</span>
                  {k === "marktmonitor" && count > 0 && <span className="relative rounded-full px-1.5 text-[10.5px] font-semibold text-white tabular leading-[17px]" style={{ background: n.color }}>{count}</span>}
                </div>
              )}
            </NavLink>
          );
        })}
      </nav>
      {cloud ? (
        <div className="flex items-center justify-between px-5 py-4 text-[11px] leading-relaxed text-ink-faint">
          <span>Online · beveiligd met wachtwoord</span>
          <button onClick={async () => { await api.post("/auth/logout"); window.location.href = "/"; }} className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-ink-muted hover:bg-black/[0.04] hover:text-ink" title="Uitloggen"><LogOut className="h-3.5 w-3.5" /> Uitloggen</button>
        </div>
      ) : (
        <div className="px-5 py-4 text-[11px] leading-relaxed text-ink-faint">
          Lokaal · 127.0.0.1
          <br />
          Gegevens blijven op deze computer
        </div>
      )}
    </aside>
  );
}
