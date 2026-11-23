import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Microscope, Pencil, Trash2, ExternalLink, FileText, ShieldCheck, Globe, Check } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, date } from "@/lib/utils";
import { SUGGESTION_CATEGORIES, SUGGESTION_STATUS } from "@/lib/labels";
import { useAiAction } from "@/components/AiAction";
import { SourceRef } from "@/components/common";
import { SuggestionBadges } from "./Radar";
import { Dialog } from "@/components/ui/overlay";
import { Badge, Button, Card, CardHeader, Field, Input, Loading, Notice, Select, Switch, Textarea } from "@/components/ui/primitives";

const FIELDS: [string, string][] = [
  ["summary", "Korte samenvatting"], ["gap", "Geconstateerde kans of tekortkoming"], ["vetera_situation", "Huidige Vetera-situatie (voor zover aantoonbaar)"],
  ["market_context", "Relevante concurrenten of marktontwikkelingen"], ["suggestion", "Concrete verbetersuggestie"], ["customer_benefits", "Verwachte voordelen voor de klant"],
  ["commercial_benefits", "Mogelijke commerciële voordelen voor Vetera"], ["risks", "Mogelijke risico's of beperkingen"], ["follow_up", "Vervolgonderzoek"],
];

export default function SuggestionDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { data: s, refetch } = useQuery({ queryKey: ["suggestion", id], queryFn: () => api.get(`/radar/suggestions/${id}`) });
  const [edit, setEdit] = React.useState(false);
  const [web, setWeb] = React.useState(false);
  const [dossier, setDossier] = React.useState<any>(null);
  const deep = useAiAction("/ai/dossier", { onDone: (r: any) => { refetch(); setDossier({ content: r.content, title: "Nieuw dossier", created_at: new Date().toISOString() }); } });
  if (!s) return <Loading />;
  const setStatus = async (status: string) => {
    await api.patch(`/radar/suggestions/${s.id}`, { status });
    refetch();
    qc.invalidateQueries({ queryKey: ["suggestions"] });
  };
  const del = async () => {
    if (!confirm("Suggestie en dossiers verwijderen?")) return;
    await api.del(`/radar/suggestions/${s.id}`);
    qc.invalidateQueries({ queryKey: ["suggestions"] });
    nav("/verbeterradar");
  };
  return (
    <div>
      <button onClick={() => nav("/verbeterradar")} className="mb-5 inline-flex items-center gap-1 text-[13px] text-ink-muted hover:text-ink"><ArrowLeft className="h-3.5 w-3.5" /> Verbeterradar</button>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <div className="text-[13px] text-ink-muted">{s.category}</div>
          <h1 className="mt-1 text-[26px] font-semibold tracking-tightest leading-tight">{s.title}</h1>
          <div className="mt-3"><SuggestionBadges s={s} /></div>
        </div>
        <div className="flex gap-2">
          <Button icon={<Pencil className="h-4 w-4" />} onClick={() => setEdit(true)}>Bewerken</Button>
          <Button variant="ghost" icon={<Trash2 className="h-4 w-4" />} onClick={del} aria-label="Verwijderen" />
        </div>
      </div>
      <div className="mb-6 flex flex-wrap items-center gap-1 rounded-2xl bg-surface p-1">
        {SUGGESTION_STATUS.map((st, i) => {
          const idx = SUGGESTION_STATUS.findIndex((x) => x.key === s.status);
          const active = st.key === s.status;
          return (
            <button key={st.key} onClick={() => setStatus(st.key)} className={cn("flex items-center gap-1.5 rounded-xl px-3.5 py-1.5 text-[12.5px] font-medium transition-colors", active ? "bg-white text-ink shadow-sm" : i < idx && s.status !== "afgewezen" ? "text-accent" : "text-ink-muted hover:text-ink")}>
              {i < idx && s.status !== "afgewezen" && <Check className="h-3 w-3" />}{st.label}
            </button>
          );
        })}
      </div>
      {s.kind === "innovatiehypothese" && <Notice tone="attention" className="mb-6" title="Innovatiehypothese">Dit is een idee voor doorontwikkeling, geen bewezen marktkans en geen bestaande productvoorwaarde. Toets de aannames met vervolgonderzoek.</Notice>}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <Card className="divide-y divide-line">
            {FIELDS.map(([k, l]) => (
              <div key={k} className="grid grid-cols-1 gap-1 px-6 py-4 md:grid-cols-[240px_1fr] md:gap-6">
                <div className="text-[12.5px] font-medium text-ink-muted">{l}</div>
                <div className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink">{s[k] || <span className="text-ink-faint">Niet ingevuld</span>}</div>
              </div>
            ))}
          </Card>
          {s.dossiers.map((d: any) => <DossierCard key={d.id} d={d} />)}
          {dossier && !s.dossiers.length && <DossierCard d={dossier} />}
        </div>
        <div className="space-y-6">
          <Card className="p-5">
            <div className="flex items-center gap-2 text-[14px] font-semibold"><Microscope className="h-4 w-4 text-accent" /> Onderzoek verder</div>
            <p className="mt-1.5 text-[12.5px] text-ink-muted">Stel een verdiepend dossier op: achtergrond, concurrentieanalyse, marktcijfers (alleen met bron), doelgroep, aanpassingen, kansen, risico's, open vragen en vervolgstappen.</p>
            <div className="mt-3"><Switch checked={web} onCheckedChange={setWeb} label="Webonderzoek toestaan" /></div>
            <Button className="mt-3 w-full" variant="primary" loading={deep.busy} onClick={() => deep.start({ suggestion_id: s.id, web })}>Onderzoek verder</Button>
          </Card>
          <Card>
            <CardHeader title="Onderbouwing en bronnen" />
            <ul className="space-y-2 px-5 pb-5 text-[12.5px]">
              {!s.evidence?.length && <li className="text-ink-muted">Geen bronverwijzingen{s.kind === "datagedreven" ? " — beoordeel de betrouwbaarheid kritisch." : "."}</li>}
              {s.evidence?.map((e: any, i: number) => (
                <li key={i} className="flex items-start gap-2">
                  {e.type === "web" ? <Globe className="mt-0.5 h-3.5 w-3.5 text-ink-muted" /> : e.document_version_id ? <FileText className="mt-0.5 h-3.5 w-3.5 text-ink-muted" /> : <ShieldCheck className="mt-0.5 h-3.5 w-3.5 text-ink-muted" />}
                  <div className="min-w-0">
                    {e.type === "web" ? <a href={e.url} target="_blank" rel="noreferrer" className="break-all text-accent hover:underline">{e.title || e.url} <ExternalLink className="inline h-3 w-3" /></a> : <span>{e.label || e.ref || `Bevinding #${e.finding_id}`}</span>}
                    {e.document_version_id && <div><SourceRef versionId={e.document_version_id} page={e.page_number} className="-ml-1.5" /></div>}
                  </div>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-5 text-[12.5px]">
            <div className="mb-2 font-semibold text-[13px]">Prioritering</div>
            {Object.entries(s.priority_factors || {}).map(([k, v]) => <div key={k} className="flex justify-between gap-3 py-0.5"><span className="text-ink-muted">{k.replace(/_/g, " ")}</span><span className="text-right">{String(v ?? "–")}</span></div>)}
            <p className="mt-2 text-[11.5px] text-ink-faint">Kwalitatieve prioriteit, geen schijnnauwkeurige score. Omzet- of conversie-effect is niet betrouwbaar te bepalen tenzij met bron vermeld.</p>
            <div className="mt-3 text-[11.5px] text-ink-faint">Herkomst: {s.origin} · aangemaakt {date(s.created_at)}</div>
          </Card>
        </div>
      </div>
      <EditDialog open={edit} onOpenChange={setEdit} s={s} onSaved={refetch} />
      {deep.dialog}
    </div>
  );
}

function DossierCard({ d }: { d: any }) {
  const c = d.content || {};
  const list = (k: string, l: string) => c[k]?.length ? <div><div className="mb-1 text-[12.5px] font-semibold">{l}</div><ul className="space-y-0.5 text-[13px] text-ink-soft">{c[k].map((x: string, i: number) => <li key={i}>• {x}</li>)}</ul></div> : null;
  return (
    <Card>
      <CardHeader title={d.title} subtitle={`Onderzoeksdossier · ${date(d.created_at, true)}`} actions={<Badge tone="accent">AI</Badge>} />
      <div className="space-y-4 px-5 pb-5 text-[13px] leading-relaxed">
        {c.background && <p><b>Achtergrond.</b> {c.background}</p>}
        {c.competitive_analysis && <p><b>Concurrentieanalyse.</b> {c.competitive_analysis}</p>}
        {c.target_group && <p><b>Potentiële doelgroep.</b> {c.target_group}</p>}
        {c.market_figures?.length > 0 && <div><div className="mb-1 text-[12.5px] font-semibold">Beschikbare marktcijfers</div>{c.market_figures.map((m: any, i: number) => <div key={i} className="text-ink-soft">• {m.figure} <span className="text-ink-muted">— {m.source}</span></div>)}</div>}
        {list("product_adjustments", "Mogelijke productaanpassingen")}
        {list("commercial_opportunities", "Commerciële kansen")}
        {list("risks", "Risico's")}
        {list("open_questions", "Openstaande vragen")}
        {list("next_steps", "Concrete vervolgstappen")}
        {list("uncertainties", "Onzekerheden")}
        {c._web_results?.length > 0 && <div><div className="mb-1 text-[12.5px] font-semibold">Geraadpleegde webbronnen</div>{c._web_results.slice(0, 10).map((w: any) => <a key={w.url} href={w.url} target="_blank" rel="noreferrer" className="block truncate text-[12px] text-accent hover:underline">{w.title || w.url}</a>)}</div>}
      </div>
    </Card>
  );
}

function EditDialog({ open, onOpenChange, s, onSaved }: { open: boolean; onOpenChange: (v: boolean) => void; s: any; onSaved: () => void }) {
  const [f, setF] = React.useState<any>(s);
  React.useEffect(() => { if (open) setF(s); }, [open, s]);
  const save = async () => {
    try {
      const body = Object.fromEntries(["title", "category", "kind", "priority", "confidence", ...FIELDS.map((x) => x[0])].map((k) => [k, f[k]]));
      await api.patch(`/radar/suggestions/${s.id}`, body);
      onSaved();
      onOpenChange(false);
    } catch (e: any) { toast.error(e.message); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="xl" title="Suggestie bewerken" footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Annuleren</Button><Button variant="primary" onClick={save}>Opslaan</Button></>}>
      <div className="grid grid-cols-4 gap-4">
        <Field label="Titel" className="col-span-4"><Input value={f.title || ""} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field label="Categorie"><Select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{SUGGESTION_CATEGORIES.map((c) => <option key={c}>{c}</option>)}</Select></Field>
        <Field label="Soort"><Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="datagedreven">Datagedreven</option><option value="innovatiehypothese">Innovatiehypothese</option></Select></Field>
        <Field label="Prioriteit"><Select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>{["hoog", "middel", "laag"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
        <Field label="Betrouwbaarheid"><Select value={f.confidence} onChange={(e) => setF({ ...f, confidence: e.target.value })}>{["hoog", "middel", "laag"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
        {FIELDS.map(([k, l]) => <Field key={k} label={l} className="col-span-2"><Textarea rows={3} value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>)}
      </div>
    </Dialog>
  );
}
