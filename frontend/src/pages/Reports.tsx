import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileBarChart, FileDown, Sheet, Printer, Trash2, Check } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, date } from "@/lib/utils";
import { useProducts } from "@/components/forms";
import { Badge, Button, Card, CardHeader, EmptyState, Field, Input, PageHeader, Select } from "@/components/ui/primitives";

const DESCR: Record<string, string> = {
  concurrentievergelijking: "Aanbieders, voorwaardenmatrix, premies en scores in één rapport.",
  voorwaarden: "Polisvoorwaarden per kenmerk met bronverwijzingen.",
  premie: "Premies per rekenprofiel met vergelijkbaarheidscontrole en grafiek.",
  markt: "Documentwijzigingen, meldingen en broncontroles over een periode.",
  radar: "Alle verbetervoorstellen met onderbouwing en prioriteit.",
  dossier: "Verdiepende onderzoeksdossiers uit de Verbeterradar.",
  verkoop: "Advieskaart: waarom Vetera overwegen ten opzichte van een concurrent.",
  marktbericht: "Wat er sinds de vorige broncontrole is veranderd in de markt.",
};

export default function Reports() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const types = useQuery({ queryKey: ["report-types"], queryFn: () => api.get<any[]>("/reports/types") });
  const reports = useQuery({ queryKey: ["reports"], queryFn: () => api.get<any[]>("/reports") });
  const products = useProducts();
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: () => api.get<any[]>("/profiles") });
  const [type, setType] = React.useState("concurrentievergelijking");
  const [title, setTitle] = React.useState("");
  const [sel, setSel] = React.useState<number[]>([]);
  const [prof, setProf] = React.useState<number[]>([]);
  const [competitor, setCompetitor] = React.useState("");
  const [days, setDays] = React.useState(90);
  const [busy, setBusy] = React.useState(false);
  const vetera = products.data?.find((p) => p.is_reference);
  const needsProducts = ["concurrentievergelijking", "voorwaarden"].includes(type);
  const generate = async () => {
    setBusy(true);
    try {
      const params: any = { title: title || undefined };
      if (needsProducts && sel.length) params.product_ids = sel;
      if (["concurrentievergelijking", "premie"].includes(type) && prof.length) params.profile_ids = prof;
      if (type === "markt") params.days = days;
      if (type === "verkoop") { params.competitor_product_id = Number(competitor); params.vetera_product_id = vetera?.id; }
      const r = await api.post("/reports", { report_type: type, params });
      qc.invalidateQueries({ queryKey: ["reports"] });
      toast.success("Rapport gegenereerd");
      nav(`/rapportages/${r.id}`);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  const del = async (id: number) => { if (!confirm("Rapport verwijderen?")) return; await api.del(`/reports/${id}`); qc.invalidateQueries({ queryKey: ["reports"] }); };
  const chip = (active: boolean) => cn("inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[12px]", active ? "border-accent/30 bg-accent-soft text-accent-ink" : "border-line text-ink-soft hover:border-line-strong");
  return (
    <div>
      <PageHeader module="rapportages" title="Rapportages" subtitle="Professionele rapporten met managementsamenvatting, onderbouwing, bronverwijzingen en beperkingen — uitsluitend op basis van werkelijk vastgelegde gegevens." />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_420px]">
        <div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {types.data?.map((t) => (
              <button key={t.key} onClick={() => setType(t.key)} className={cn("rounded-2xl border p-4 text-left transition-all", type === t.key ? "border-accent/40 bg-accent-soft/40 shadow-soft" : "border-line bg-white hover:border-line-strong")}>
                <div className="flex items-center justify-between"><span className="text-[14px] font-semibold">{t.label}</span>{type === t.key && <Check className="h-4 w-4 text-accent" />}</div>
                <p className="mt-1 text-[12.5px] text-ink-muted">{DESCR[t.key]}</p>
              </button>
            ))}
          </div>
          <Card className="mt-5 p-5 space-y-4">
            <Field label="Titel (optioneel)"><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={types.data?.find((t) => t.key === type)?.label} /></Field>
            {needsProducts && (
              <Field label="Producten" hint="Leeg = alle actieve, zelfstandige producten">
                <div className="flex flex-wrap gap-1.5">{products.data?.map((p) => <button key={p.id} type="button" onClick={() => setSel((s) => s.includes(p.id) ? s.filter((x) => x !== p.id) : [...s, p.id])} className={chip(sel.includes(p.id))}>{p.provider_name} · {p.name}</button>)}</div>
              </Field>
            )}
            {["concurrentievergelijking", "premie"].includes(type) && (
              <Field label="Rekenprofielen" hint="Leeg = alle profielen met premies">
                <div className="flex flex-wrap gap-1.5">{profiles.data?.map((p) => <button key={p.id} type="button" onClick={() => setProf((s) => s.includes(p.id) ? s.filter((x) => x !== p.id) : [...s, p.id])} className={chip(prof.includes(p.id))}>{p.name}</button>)}</div>
              </Field>
            )}
            {type === "markt" && <Field label="Periode (dagen)"><Input type="number" value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-32" /></Field>}
            {type === "verkoop" && (
              <Field label="Concurrentproduct" hint={vetera ? `Vergeleken met ${vetera.name}` : "Leg eerst een Vetera-product vast"}>
                <Select value={competitor} onChange={(e) => setCompetitor(e.target.value)}><option value="">Kies…</option>{products.data?.filter((p) => !p.is_reference).map((p) => <option key={p.id} value={p.id}>{p.provider_name} · {p.name}</option>)}</Select>
              </Field>
            )}
            <div className="flex justify-end"><Button variant="primary" icon={<FileBarChart className="h-4 w-4" />} onClick={generate} loading={busy} disabled={type === "verkoop" && (!competitor || !vetera)}>Rapport genereren</Button></div>
          </Card>
        </div>
        <Card className="h-fit">
          <CardHeader title="Gegenereerde rapporten" />
          {!reports.data?.length ? <EmptyState icon={<FileBarChart />} title="Nog geen rapporten" /> : (
            <ul className="divide-y divide-line">
              {reports.data.map((r) => (
                <li key={r.id} className="px-5 py-3">
                  <button onClick={() => nav(`/rapportages/${r.id}`)} className="text-left"><div className="text-[13.5px] font-medium hover:text-accent">{r.title}</div></button>
                  <div className="mt-0.5 flex items-center justify-between">
                    <span className="text-[12px] text-ink-muted">{date(r.created_at, true)}</span>
                    <div className="flex gap-0.5">
                      <a href={api.url(`/reports/${r.id}/download`, { fmt: "pdf" })} className="rounded-md p-1.5 text-ink-muted hover:bg-surface hover:text-ink" title="PDF"><FileDown className="h-3.5 w-3.5" /></a>
                      <a href={api.url(`/reports/${r.id}/download`, { fmt: "xlsx" })} className="rounded-md p-1.5 text-ink-muted hover:bg-surface hover:text-ink" title="Excel"><Sheet className="h-3.5 w-3.5" /></a>
                      <a href={`/rapportages/${r.id}/print`} target="_blank" rel="noreferrer" className="rounded-md p-1.5 text-ink-muted hover:bg-surface hover:text-ink" title="Afdrukken"><Printer className="h-3.5 w-3.5" /></a>
                      <button onClick={() => del(r.id)} className="rounded-md p-1.5 text-ink-muted hover:bg-surface hover:text-negative" title="Verwijderen"><Trash2 className="h-3.5 w-3.5" /></button>
                    </div>
                  </div>
                  <Badge className="mt-1">{r.report_type}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
