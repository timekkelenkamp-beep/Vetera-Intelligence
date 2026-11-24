import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X, Minus, SlidersHorizontal, ArrowUpRight, Info } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { FINDING_STATUS } from "@/lib/labels";
import { ProviderLogo } from "./common";
import { FindingEditor } from "./FindingEditor";
import { Dialog } from "./ui/overlay";
import { Button, Card, EmptyState, Loading, Tip } from "./ui/primitives";

/** Compacte kernvergelijking: symbolen in plaats van tekst, details pas bij klikken. */
export function OverviewView({ ids, reference, level, products }: { ids: number[]; reference: number | null; level: string; products: any[] }) {
  const nav = useNavigate();
  const [pick, setPick] = React.useState(false);
  const [edit, setEdit] = React.useState<any>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["overview", ids, reference, level],
    queryFn: () => api.get("/insights/overview", { product_ids: ids.join(","), reference, level }),
    placeholderData: (p) => p,
  });
  const prodMap = Object.fromEntries(products.map((p) => [p.id, p]));
  const open = async (pid: number, feature: any, findingId?: number) => {
    let finding;
    if (findingId) {
      const all = await api.get<any[]>("/findings", { product_id: pid });
      finding = all.find((f) => f.id === findingId);
    }
    setEdit({ product: prodMap[pid], feature, finding });
  };
  if (isLoading || !data) return <Loading />;
  const comps = data.summaries;

  return (
    <div className="space-y-6">
      {!data.reference_id && <p className="text-[13px] text-ink-muted">Kies Vetera als referentie om te zien waar concurrenten beter of slechter zijn.</p>}
      {comps.length > 0 && data.reference_id && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {comps.map((s: any) => <Summary key={s.id} s={s} onOpen={() => nav(`/concurrenten/${s.provider_id}`)} />)}
        </div>
      )}

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
          <div>
            <div className="text-[15px] font-semibold">Kernkenmerken</div>
            <div className="text-[12px] text-ink-muted">{data.core_count} van {data.feature_count} kenmerken · klik op een cel voor uitleg en bron</div>
          </div>
          <Button size="sm" icon={<SlidersHorizontal className="h-3.5 w-3.5" />} onClick={() => setPick(true)}>Kenmerken kiezen</Button>
        </div>
        {data.rows.length === 0 ? <EmptyState title="Geen kernkenmerken gekozen" action={<Button onClick={() => setPick(true)}>Kenmerken kiezen</Button>} /> : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th className="w-[240px] px-5 py-3" />
                  {data.products.map((p: any) => (
                    <th key={p.id} className={cn("min-w-[130px] px-3 py-3 text-center align-bottom", p.id === data.reference_id && "bg-accent-soft/50")}>
                      <div className="flex flex-col items-center gap-1.5">
                        <ProviderLogo name={p.provider_name} logoUrl={p.logo} size={28} id={p.provider_id} isReference={p.is_reference} />
                        <span className="text-[12.5px] font-semibold leading-tight text-ink">{p.provider_name}</span>
                        <span className="text-[11px] font-normal leading-tight text-ink-muted">{p.level_info?.offered === false ? "niet aangeboden" : p.level_info?.local_name || p.name}</span>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r: any) => (
                  <tr key={r.feature.id} className="border-t border-line">
                    <td className="px-5 py-2.5 text-[13px] font-medium text-ink">{r.feature.label}</td>
                    {data.products.map((p: any) => {
                      const c = r.cells[String(p.id)];
                      return (
                        <td key={p.id} className={cn("px-3 py-2 text-center", p.id === data.reference_id && "bg-accent-soft/50")}>
                          <Tip content={c ? <span>{FINDING_STATUS[c.status]?.label}{c.compare_text ? <><br />{c.compare_text}</> : null}{!c.reviewed ? <><br /><span className="opacity-70">Nog niet gecontroleerd</span></> : null}</span> : "Geen gegevens"}>
                            <button onClick={() => open(p.id, r.feature, c?.finding_id)} className={cn("inline-flex min-h-[34px] min-w-[64px] flex-col items-center justify-center rounded-xl px-2 py-1 transition-colors hover:bg-surface",
                              c?.compare === "beter" && "ring-2 ring-[#e0a800]/70", c?.compare === "slechter" && "ring-2 ring-[rgba(31,78,70,0.55)]")}>
                              <Mark c={c} />
                              {c?.value && <span className="mt-0.5 max-w-[140px] truncate text-[11px] text-ink-soft">{c.value}</span>}
                            </button>
                          </Tip>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t border-line px-5 py-3 text-[11.5px] text-ink-muted">
          <span className="flex items-center gap-1.5"><Mark c={{ symbol: "ja" }} /> gedekt</span>
          <span className="flex items-center gap-1.5"><Mark c={{ symbol: "deels" }} /> onder voorwaarden</span>
          <span className="flex items-center gap-1.5"><Mark c={{ symbol: "nee" }} /> uitgesloten</span>
          <span className="flex items-center gap-1.5"><Mark c={null} /> onbekend</span>
          <span className="flex items-center gap-1.5"><span className="h-3.5 w-5 rounded-md ring-2 ring-[#e0a800]/70" /> concurrent ruimer dan Vetera</span>
          <span className="flex items-center gap-1.5"><span className="h-3.5 w-5 rounded-md ring-2 ring-[rgba(31,78,70,0.55)]" /> Vetera ruimer</span>
        </div>
      </Card>
      <p className="flex items-center gap-1.5 text-[12px] text-ink-muted"><Info className="h-3.5 w-3.5" /> Onbekend betekent: nog niet vastgesteld, niet ‘niet verzekerd’. Alle kenmerken en bronnen staan onder ‘Alle details’.</p>
      <CorePicker open={pick} onOpenChange={setPick} />
      <FindingEditor open={!!edit} onOpenChange={(v) => !v && setEdit(null)} product={edit?.product} feature={edit?.feature} finding={edit?.finding} level={level} />
    </div>
  );
}

function Mark({ c }: { c: any }) {
  const s = c?.symbol || "onbekend";
  if (s === "ja") return <span className="flex h-6 w-6 items-center justify-center rounded-full bg-positive-soft text-positive"><Check className="h-3.5 w-3.5" strokeWidth={3} /></span>;
  if (s === "nee") return <span className="flex h-6 w-6 items-center justify-center rounded-full bg-negative-soft text-negative"><X className="h-3.5 w-3.5" strokeWidth={3} /></span>;
  if (s === "deels") return <span className="flex h-6 w-6 items-center justify-center rounded-full bg-caution-soft text-caution"><svg viewBox="0 0 16 16" className="h-3.5 w-3.5"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="2" /><path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor" /></svg></span>;
  return <span className="flex h-6 w-6 items-center justify-center text-ink-faint"><Minus className="h-3.5 w-3.5" /></span>;
}

function Summary({ s, onOpen }: { s: any; onOpen: () => void }) {
  const chips = (items: string[], tone: string) => (
    items.length === 0 ? <span className="text-ink-faint">niets vastgesteld</span> : (
      <span className="flex flex-wrap gap-1">
        {items.slice(0, 4).map((x) => <span key={x} className={cn("rounded-full px-2 py-0.5 text-[11.5px]", tone)}>{x}</span>)}
        {items.length > 4 && <span className="px-1 text-[11.5px] text-ink-muted">+{items.length - 4}</span>}
      </span>
    )
  );
  const pr = s.price;
  return (
    <Card interactive onClick={onOpen} className="p-5">
      <div className="flex items-center gap-3">
        <ProviderLogo name={s.provider_name} logoUrl={s.logo} size={32} id={s.provider_id} isReference={s.is_reference} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14.5px] font-semibold">{s.provider_name}</div>
          <div className="truncate text-[12px] text-ink-muted">{s.name}</div>
        </div>
        <ArrowUpRight className="h-4 w-4 text-ink-faint" />
      </div>
      <dl className="mt-4 space-y-2.5 text-[12.5px]">
        <div className="grid grid-cols-[92px_1fr] items-start gap-2"><dt className="pt-0.5 text-ink-muted">Ruimer dan Vetera</dt><dd>{chips(s.better, "bg-[#fdf5e0] text-[#8a6100]")}</dd></div>
        <div className="grid grid-cols-[92px_1fr] items-start gap-2"><dt className="pt-0.5 text-ink-muted">Beperkter</dt><dd>{chips(s.worse, "bg-accent-soft text-accent-ink")}</dd></div>
        <div className="grid grid-cols-[92px_1fr] items-start gap-2"><dt className="text-ink-muted">Prijs</dt>
          <dd>{pr.avg_diff_pct === null ? <span className="text-ink-faint">geen vergelijkbare premies</span> : (
            <span><b className="font-semibold tabular">{Math.abs(pr.avg_diff_pct).toFixed(0)}% {pr.avg_diff_pct > 0 ? "duurder" : pr.avg_diff_pct < 0 ? "goedkoper" : ""}</b>{Math.abs(pr.avg_diff_pct) < 1 && "vergelijkbaar"} <span className="text-ink-muted">({pr.profiles} profiel{pr.profiles === 1 ? "" : "en"}{pr.comparable < pr.profiles ? ", deels beperkt vergelijkbaar" : ""})</span></span>
          )}</dd></div>
      </dl>
      <div className="mt-3 text-[11.5px] text-ink-faint">{s.unknown} van {s.total} kenmerken nog onbekend</div>
    </Card>
  );
}

function CorePicker({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["features"], queryFn: () => api.get<any[]>("/features"), enabled: open });
  const toggle = async (f: any) => {
    await api.patch(`/features/${f.id}`, { is_core: !f.is_core });
    qc.invalidateQueries({ queryKey: ["features"] });
    qc.invalidateQueries({ queryKey: ["overview"] });
  };
  const cats = [...new Set((data || []).map((f) => f.category))];
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="lg" title="Kernkenmerken kiezen" description="Deze kenmerken staan in het overzicht. Kies de onderdelen die voor jouw klanten het verschil maken."
      footer={<Button variant="primary" onClick={() => onOpenChange(false)}>Gereed</Button>}>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {cats.map((c) => (
          <div key={c}>
            <div className="mb-1.5 text-[11.5px] font-semibold uppercase tracking-wide text-ink-faint">{c}</div>
            {data!.filter((f) => f.category === c).map((f) => (
              <label key={f.id} className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-[13px] hover:bg-surface">
                <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={f.is_core} onChange={() => toggle(f)} />
                {f.label}
              </label>
            ))}
          </div>
        ))}
      </div>
    </Dialog>
  );
}
