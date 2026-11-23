import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search, Building2, Package, FileText, ListChecks, Quote, Lightbulb, Calculator, CornerDownLeft, Sparkles, type LucideIcon } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { MODULES, NAV_ORDER, tileStyle } from "@/lib/modules";
import { useDebounced } from "./common";
import { useSourceViewer } from "./SourceViewer";

const TYPE: Record<string, { label: string; icon: LucideIcon; color: string }> = {
  aanbieder: { label: "Aanbieder", icon: Building2, color: MODULES.concurrenten.color },
  product: { label: "Product", icon: Package, color: MODULES.voorwaarden.color },
  document: { label: "Document", icon: FileText, color: MODULES.bronnen.color },
  kenmerk: { label: "Kenmerk", icon: ListChecks, color: MODULES.voorwaarden.color },
  clausule: { label: "Clausule", icon: Quote, color: MODULES.bronnen.color },
  tekst: { label: "In documenttekst", icon: Quote, color: MODULES.bronnen.color },
  verbetervoorstel: { label: "Verbetervoorstel", icon: Lightbulb, color: MODULES.verbeterradar.color },
  rekenprofiel: { label: "Rekenprofiel", icon: Calculator, color: MODULES.premielab.color },
};

type Item = { key: string; title: string; subtitle?: string; icon: LucideIcon; color: string; group: string; run: () => void };

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const nav = useNavigate();
  const viewer = useSourceViewer();
  const [q, setQ] = React.useState("");
  const [idx, setIdx] = React.useState(0);
  const dq = useDebounced(q, 150);
  const { data, isFetching } = useQuery({ queryKey: ["quicksearch", dq], queryFn: () => api.get<any[]>("/insights/quicksearch", { q: dq }), enabled: open && dq.length > 1 });
  React.useEffect(() => { if (open) { setQ(""); setIdx(0); } }, [open]);
  React.useEffect(() => setIdx(0), [dq, data]);

  const go = (fn: () => void) => () => { onOpenChange(false); fn(); };
  const items: Item[] = React.useMemo(() => {
    const out: Item[] = [];
    const ql = q.toLowerCase().trim();
    NAV_ORDER.filter((k) => !ql || MODULES[k].label.toLowerCase().includes(ql)).forEach((k) => {
      const m = MODULES[k];
      out.push({ key: `nav-${k}`, title: m.label, icon: m.icon, color: m.color, group: "Ga naar", run: go(() => nav(m.to)) });
    });
    if (ql.length > 2) out.push({ key: "ask", title: `Onderzoek: “${q.trim()}”`, subtitle: "Vraag stellen aan de onderzoeksassistent", icon: Sparkles, color: MODULES.dashboard.color, group: "Acties", run: go(() => nav(`/onderzoek?q=${encodeURIComponent(q.trim())}`)) });
    (data || []).forEach((r, i) => {
      const t = TYPE[r.type] || TYPE.document;
      out.push({
        key: `r${i}`, title: r.title, subtitle: `${t.label} · ${r.subtitle || ""}`, icon: t.icon, color: t.color, group: "Resultaten",
        run: go(() => (r.version_id ? viewer.open({ versionId: r.version_id, page: r.page || 1, quote: r.type === "tekst" ? r.title.replace(/…/g, "") : undefined }) : nav(r.link))),
      });
    });
    return out;
  }, [q, data]); // eslint-disable-line

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(items.length - 1, i + 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(0, i - 1)); }
    if (e.key === "Enter" && items[idx]) { e.preventDefault(); items[idx].run(); }
  };
  const listRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => { listRef.current?.querySelector(`[data-idx="${idx}"]`)?.scrollIntoView({ block: "nearest" }); }, [idx]);

  let last = "";
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-[60] bg-black/20 backdrop-blur-[2px] data-[state=open]:animate-[fadeIn_120ms_ease-out]" />
        <DialogPrimitive.Content onKeyDown={onKey} className="fixed left-1/2 top-[14vh] z-[60] w-[min(640px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden rounded-2xl border border-line bg-white/95 shadow-[0_24px_80px_rgba(0,0,0,0.22)] backdrop-blur-xl">
          <DialogPrimitive.Title className="sr-only">Snelzoeken</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">Zoek aanbieders, producten, documenten, clausules en tekst</DialogPrimitive.Description>
          <div className="flex items-center gap-3 border-b border-line px-4">
            <Search className="h-4 w-4 text-ink-faint" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Zoek aanbieders, producten, clausules of tekst in polisvoorwaarden…" className="h-14 flex-1 bg-transparent text-[15px] text-ink placeholder:text-ink-faint focus:outline-none" style={{ boxShadow: "none" }} aria-label="Zoeken" />
            {isFetching && <span className="text-[11px] text-ink-faint">zoeken…</span>}
          </div>
          <div ref={listRef} className="max-h-[52vh] overflow-y-auto p-2">
            {items.length === 0 && <div className="px-3 py-8 text-center text-[13px] text-ink-muted">Geen resultaten voor “{q}”.</div>}
            {items.map((it, i) => {
              const head = it.group !== last ? it.group : null;
              last = it.group;
              return (
                <React.Fragment key={it.key}>
                  {head && <div className="px-3 pb-1 pt-2.5 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">{head}</div>}
                  <button data-idx={i} onMouseMove={() => setIdx(i)} onClick={it.run} className={cn("flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left", i === idx && "bg-accent-soft")}>
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[8px]" style={tileStyle(it.color)}><it.icon className="h-3.5 w-3.5 text-white" /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13.5px] text-ink">{it.title}</span>
                      {it.subtitle && <span className="block truncate text-[11.5px] text-ink-muted">{it.subtitle}</span>}
                    </span>
                    {i === idx && <CornerDownLeft className="h-3.5 w-3.5 text-ink-faint" />}
                  </button>
                </React.Fragment>
              );
            })}
          </div>
          <div className="flex items-center gap-4 border-t border-line px-4 py-2 text-[11px] text-ink-faint">
            <span>↑↓ navigeren</span><span>↵ openen</span><span>esc sluiten</span>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
