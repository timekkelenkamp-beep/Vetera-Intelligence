import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Sparkles, FileText, Package, Calculator, Link2, CheckCircle2, XCircle, AlertTriangle, ShieldCheck, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, eur } from "@/lib/utils";
import { DOC_TYPE, PERIOD, VEHICLE } from "@/lib/labels";
import { useAiAction } from "./AiAction";
import { Dialog } from "./ui/overlay";
import { Badge, Button, Notice } from "./ui/primitives";

/** Automatisch onderzoek van één aanbieder: zoeken → kiezen → importeren → optioneel analyseren met AI. */
export function useAutoResearch(provider: any) {
  const [result, setResult] = React.useState<any>(null);
  const action = useAiAction("/ai/research", { onDone: (r: any) => setResult(r) });
  const start = () => {
    if (!provider.website) return toast.error("Vul eerst de officiële website van deze aanbieder in (Bewerken).");
    action.start({ provider_id: provider.id });
  };
  const dialog = (
    <>
      {action.dialog}
      {result && <ResearchDialog provider={provider} result={result} onClose={() => setResult(null)} />}
    </>
  );
  return { start, busy: action.busy, dialog };
}

function ResearchDialog({ provider, result, onClose }: { provider: any; result: any; onClose: () => void }) {
  const qc = useQueryClient();
  const all = ["products", "documents", "premiums", "calculators"].flatMap((k) => result[k] as any[]);
  const [sel, setSel] = React.useState<Set<string>>(new Set(all.filter((x) => x.selected).map((x) => x.id)));
  const [busy, setBusy] = React.useState(false);
  const [imported, setImported] = React.useState<any>(null);
  const [batch, setBatch] = React.useState<{ estimate?: number; done: number; total: number; running: boolean; results: any[] } | null>(null);
  const toggle = (id: string) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const refresh = () => ["provider", "providers", "products", "documents", "premiums", "calculators", "sources", "dashboard", "matrix", "findings", "timeline", "battlecard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));

  const doImport = async () => {
    setBusy(true);
    try {
      const r = await api.post("/ai/research/import", { provider_id: provider.id, analysis_id: result.analysis_id, selection: [...sel] });
      setImported(r);
      refresh();
    } catch (e: any) { toast.error(e.message); } finally { setBusy(false); }
  };
  const prepareBatch = async () => {
    setBusy(true);
    try {
      let est = 0;
      for (const v of imported.new_versions) {
        const p = await api.post("/ai/extract", { version_id: v.version_id, product_id: v.product_id, dry_run: true });
        est += p.preview.estimated_cost_eur || 0;
      }
      setBatch({ estimate: est, done: 0, total: imported.new_versions.length, running: false, results: [] });
    } catch (e: any) { toast.error(e.message); } finally { setBusy(false); }
  };
  const runBatch = async () => {
    setBatch((b) => b && { ...b, running: true });
    const results: any[] = [];
    for (const [i, v] of imported.new_versions.entries()) {
      try {
        const r = await api.post("/ai/extract", { version_id: v.version_id, product_id: v.product_id });
        results.push({ title: v.title, ok: true, created: r.created, unverified: r.unverified_quotes });
      } catch (e: any) {
        results.push({ title: v.title, ok: false, error: e.message });
      }
      setBatch((b) => b && { ...b, done: i + 1, results: [...results] });
    }
    setBatch((b) => b && { ...b, running: false });
    refresh();
  };

  const Row = ({ item, icon, title, sub, warn, disabled }: { item: any; icon: React.ReactNode; title: React.ReactNode; sub?: React.ReactNode; warn?: React.ReactNode; disabled?: boolean }) => (
    <label className={cn("flex cursor-pointer items-start gap-3 rounded-xl px-3 py-2.5 hover:bg-surface/70", disabled && "cursor-not-allowed opacity-50")}>
      <input type="checkbox" className="mt-1 h-4 w-4 accent-[var(--accent)]" checked={sel.has(item.id)} disabled={disabled} onChange={() => toggle(item.id)} />
      <span className="mt-0.5 text-ink-muted [&_svg]:h-4 [&_svg]:w-4">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[13px] font-medium text-ink">{title}</span>
        {sub && <span className="block truncate text-[11.5px] text-ink-muted">{sub}</span>}
        {warn && <span className="mt-0.5 block text-[11.5px] text-caution">{warn}</span>}
      </span>
    </label>
  );
  const pname = (key: string) => result.products.find((p: any) => p.id === key)?.name;
  const nothing = all.length === 0;

  return (
    <Dialog open onOpenChange={(v) => !v && !busy && !batch?.running && onClose()} size="lg"
      title={<span className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-accent" /> Automatisch onderzoek · {provider.name}</span>}
      description={imported ? "Geïmporteerd. Alles staat op ‘te beoordelen’." : "Gevonden op de officiële website. Kies wat je wilt importeren."}
      footer={
        imported ? <Button variant="primary" onClick={onClose} disabled={batch?.running}>Sluiten</Button> : (
          <><Button variant="ghost" onClick={onClose}>Annuleren</Button><Button variant="primary" onClick={doImport} loading={busy} disabled={sel.size === 0}>Importeren ({sel.size})</Button></>
        )
      }>
      {!imported ? (
        nothing ? <Notice tone="neutral">Er is niets gevonden op de website. Voeg producten en documenten handmatig toe.</Notice> : (
          <div className="space-y-5">
            {result.products.length > 0 && <Group title="Producten">{result.products.map((p: any) => <Row key={p.id} item={p} icon={<Package />} title={p.name} sub={`${VEHICLE[p.vehicle_category]}${p.page_url ? ` · ${p.page_url}` : ""}`} warn={p.existing_product_id ? "Bestaat al; documenten worden aan het bestaande product gekoppeld" : undefined} />)}</Group>}
            {result.documents.length > 0 && <Group title="Polisvoorwaarden en documenten">{result.documents.map((d: any) => <Row key={d.id} item={d} icon={<FileText />} title={d.title} sub={`${DOC_TYPE[d.document_type] || d.document_type}${pname(d.product) ? ` · ${pname(d.product)}` : ""} · ${d.url}`} warn={!d.official ? "Niet op de officiële website" : d.known ? "Staat al in het bronregister" : undefined} />)}</Group>}
            {result.premiums.length > 0 && <Group title="Gepubliceerde premies">{result.premiums.map((p: any) => <Row key={p.id} item={p} icon={<Calculator />} disabled={!p.verified} title={<span className="flex items-center gap-2">{p.amount !== null ? eur(p.amount) : "–"} {PERIOD[p.period]}{p.verified ? <Badge tone="positive"><ShieldCheck className="h-3 w-3" /> op de pagina gevonden</Badge> : <Badge tone="negative">niet teruggevonden</Badge>}</span>} sub={`“${p.quote}” · geldt voor: ${p.conditions}`} warn={!p.verified ? "Het bedrag staat niet letterlijk op de pagina en wordt daarom niet overgenomen." : "Wordt opgeslagen als ‘openbare indicatie’ zonder rekenprofiel."} />)}</Group>}
            {result.calculators.length > 0 && <Group title="Premiecalculators">{result.calculators.map((c: any) => <Row key={c.id} item={c} icon={<Link2 />} title="Toevoegen aan het calculatorregister" sub={c.url} warn="Wordt niet automatisch ingevuld; toestemming eerst vastleggen." />)}</Group>}
            {result.skipped?.length > 0 && <Notice tone="caution" icon={<AlertTriangle />} title="Niet bezocht">{result.skipped.slice(0, 5).map((s: string) => <div key={s} className="truncate">{s}</div>)}</Notice>}
            <p className="text-[11.5px] text-ink-muted">Kosten van dit onderzoek ≈ {eur(result.cost_eur)}. PDF's worden opgehaald met respect voor robots.txt.</p>
          </div>
        )
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {Object.entries({ Producten: imported.created.products, Documenten: imported.created.documents, Premies: imported.created.premiums, Calculators: imported.created.calculators }).map(([k, v]) => (
              <div key={k} className="rounded-xl bg-surface px-3 py-2.5"><div className="text-[11px] text-ink-muted">{k}</div><div className="text-[20px] font-semibold tabular">{v as number}</div></div>
            ))}
          </div>
          {imported.errors.length > 0 && <Notice tone="caution" icon={<AlertTriangle />} title="Niet gelukt">{imported.errors.map((e: string) => <div key={e}>{e}</div>)}</Notice>}
          {imported.new_versions.length > 0 && (
            <div className="rounded-2xl border border-line p-4">
              <div className="text-[14px] font-semibold">Polisvoorwaarden laten analyseren</div>
              <p className="mt-1 text-[12.5px] text-ink-muted">De AI leest {imported.new_versions.length} document(en) en vult de voorwaardenvergelijker in, met bronverwijzing. Jij controleert daarna de bevindingen.</p>
              {!batch ? (
                <Button className="mt-3" icon={<Sparkles className="h-3.5 w-3.5" />} onClick={prepareBatch} loading={busy}>Kosten berekenen</Button>
              ) : batch.done === 0 && !batch.running ? (
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <span className="text-[13px]">Geraamde kosten ≈ <b>{eur(batch.estimate)}</b> voor {batch.total} document(en)</span>
                  <Button variant="primary" icon={<Sparkles className="h-3.5 w-3.5" />} onClick={runBatch}>Versturen en analyseren</Button>
                </div>
              ) : (
                <div className="mt-3 space-y-1.5">
                  <div className="h-1.5 overflow-hidden rounded-full bg-surface"><div className="h-full rounded-full bg-accent transition-all" style={{ width: `${(batch.done / batch.total) * 100}%` }} /></div>
                  <div className="flex items-center gap-2 text-[12.5px] text-ink-muted">{batch.running && <Loader2 className="h-3.5 w-3.5 animate-spin" />}{batch.done} van {batch.total} geanalyseerd</div>
                  {batch.results.map((r, i) => <div key={i} className="flex items-center gap-2 text-[12.5px]">{r.ok ? <CheckCircle2 className="h-3.5 w-3.5 text-positive" /> : <XCircle className="h-3.5 w-3.5 text-negative" />}<span className="truncate">{r.title}</span><span className="text-ink-muted">{r.ok ? `${r.created} bevindingen${r.unverified ? ` · ${r.unverified} citaat niet gevonden` : ""}` : r.error}</span></div>)}
                </div>
              )}
            </div>
          )}
          <Notice tone="info">Premies uit calculators worden niet automatisch opgehaald. Leg ze vast in het Premielab of importeer je Excel-onderzoek.</Notice>
        </div>
      )}
    </Dialog>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 px-3 text-[11.5px] font-semibold uppercase tracking-wide text-ink-faint">{title}</div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}
