import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { LayoutGrid, Building2, Columns3, Calculator, Radar, Lightbulb, FileBarChart, FolderOpen, Settings } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutGrid, end: true },
  { to: "/concurrenten", label: "Concurrenten", icon: Building2 },
  { to: "/voorwaarden", label: "Voorwaardenvergelijker", icon: Columns3 },
  { to: "/premielab", label: "Premielab", icon: Calculator },
  { to: "/marktmonitor", label: "Marktmonitor", icon: Radar, badge: "notifications" },
  { to: "/verbeterradar", label: "Verbeterradar", icon: Lightbulb },
  { to: "/rapportages", label: "Rapportages", icon: FileBarChart },
  { to: "/bronnen", label: "Bronnen & documenten", icon: FolderOpen },
  { to: "/instellingen", label: "Instellingen", icon: Settings },
];

export function Sidebar() {
  const notes = useQuery({ queryKey: ["notif-count"], queryFn: () => api.get<any[]>("/notifications", { status: "nieuw" }), refetchInterval: 60_000 });
  const count = notes.data?.length || 0;
  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-[248px] flex-col border-r border-line bg-[#fafafa]/90 backdrop-blur-xl">
      <div className="flex items-center gap-2.5 px-5 pt-6 pb-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-[9px] bg-accent shadow-[0_1px_2px_rgba(0,0,0,0.2)]">
          <svg viewBox="0 0 64 64" className="h-4 w-4"><path d="M14 18l18 30 18-30" fill="none" stroke="#fff" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </div>
        <div className="leading-tight">
          <div className="text-[14px] font-semibold text-ink tracking-tight">Vetera Intelligence</div>
          <div className="text-[11.5px] text-ink-muted">Competitive Intelligence</div>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 px-3">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className="block">
            {({ isActive }) => (
              <div className={cn("relative flex items-center gap-2.5 rounded-[9px] px-2.5 py-[7px] text-[13.5px] transition-colors", isActive ? "text-ink font-medium" : "text-ink-soft hover:bg-black/[0.035] hover:text-ink")}>
                {isActive && <motion.div layoutId="nav-active" className="absolute inset-0 rounded-[9px] bg-white shadow-[0_1px_2px_rgba(0,0,0,0.06),0_0_0_0.5px_rgba(0,0,0,0.06)]" transition={{ type: "spring", bounce: 0.12, duration: 0.4 }} />}
                <n.icon className={cn("relative h-[17px] w-[17px] shrink-0", isActive ? "text-accent" : "text-ink-muted")} strokeWidth={1.8} />
                <span className="relative flex-1 truncate">{n.label}</span>
                {n.badge && count > 0 && <span className="relative rounded-full bg-accent px-1.5 text-[10.5px] font-semibold text-white tabular leading-[17px]">{count}</span>}
              </div>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 py-4 text-[11px] leading-relaxed text-ink-faint">
        Lokaal · 127.0.0.1
        <br />
        Gegevens blijven op deze computer
      </div>
    </aside>
  );
}
