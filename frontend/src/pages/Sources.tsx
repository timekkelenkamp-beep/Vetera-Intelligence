import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload, Plus, FileText, Search, ShieldCheck, AlertTriangle, CheckCircle2, ArrowUpRight, Pencil, Trash2, RefreshCw, Link2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, date, relative } from "@/lib/utils";
import { ACCESS, DOC_TYPE, SOURCE_TYPE } from "@/lib/labels";
import { FindingStatus, OriginBadge, SourceRef, VerifiedMark, useDebounced } from "@/components/common";
import { UploadDialog, useProviders } from "@/components/forms";
import { Dialog, TabPanel, Tabs } from "@/components/ui/overlay";
import { Badge, Button, Card, EmptyState, Field, Input, Loading, PageHeader, Select, Switch, Textarea } from "@/components/ui/primitives";

export default function Sources({ initialTab }: { initialTab?: string }) {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || initialTab || "documenten";
  const quality = useQuery({ queryKey: ["quality"], queryFn: () => api.get("/quality") });
  return (
    <div>
      <PageHeader title="Bronnen & documenten" subtitle="Centraal bronregister, documentbibliotheek met versiebeheer en datakwaliteitscontrole. Iedere conclusie moet hiernaar herleidbaar zijn." />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v })} tabs={[
        { value: "documenten", label: "Documenten" }, { value: "bronnen", label: "Bronregister" },
        { value: "kwaliteit", label: "Datakwaliteit", count: quality.data?.total }, { value: "bevindingen", label: "Te beoordelen bevindingen" },
      ]}>
        <TabPanel value="documenten"><Documents /></TabPanel>
        <TabPanel value="bronnen"><Registry /></TabPanel>
        <TabPanel value="kwaliteit"><Quality /></TabPanel>
        <TabPanel value="bevindingen"><ReviewFindings /></TabPanel>
      </Tabs>
    </div>
  );
}

function Documents() {
  const nav = useNavigate();
  const providers = useProviders();
  const [prov, setProv] = React.useState("");
  const [type, setType] = React.useState("");
  const [q, setQ] = React.useState("");
  const [ft, setFt] = React.useState("");
  const dft = useDebounced(ft, 300);
  const [upload, setUpload] = React.useState(false);
  const { data, isLoading } = useQuery({ queryKey: ["documents", prov, type, q], queryFn: () => api.get<any[]>("/documents", { provider_id: prov, document_type: type, q }) });
  const hits = useQuery({ queryKey: ["search", dft], queryFn: () => api.get<any[]>("/search", { q: dft }), enabled: dft.length > 2 });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter op titel" className="w-56" />
        <Select value={prov} onChange={(e) => setProv(e.target.value)} className="w-48"><option value="">Alle aanbieders</option>{providers.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select>
        <Select value={type} onChange={(e) => setType(e.target.value)} className="w-52"><option value="">Alle documenttypen</option>{Object.entries(DOC_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
        <Button variant="primary" className="ml-auto" icon={<Upload className="h-4 w-4" />} onClick={() => setUpload(true)}>Documenten importeren</Button>
      </div>
      <Card className="mb-5 p-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
          <Input value={ft} onChange={(e) => setFt(e.target.value)} placeholder="Doorzoek de volledige tekst van alle polisdocumenten, bijv. ‘ambulancetrailer’ of ‘taxatierapport geldig’" className="h-10 pl-9" />
        </div>
        {dft.length > 2 && (
          <div className="mt-3 max-h-72 overflow-auto">
            {!hits.data?.length ? <p className="px-1 text-[12.5px] text-ink-muted">Geen resultaten.</p> : (
              <ul className="divide-y divide-line">
                {hits.data.map((h) => (
                  <li key={h.page_id} className="flex items-start justify-between gap-4 py-2">
                    <div className="min-w-0 text-[12.5px]"><div className="font-medium">{h.provider_name || "–"} · {h.document_title}{!h.is_current && <span className="ml-1 text-ink-faint">(eerdere versie)</span>}</div><p className="text-ink-muted" dangerouslySetInnerHTML={{ __html: h.snippet.replace(/</g, "&lt;").replace(/\[\[/g, '<mark class="mark-hit">').replace(/\]\]/g, "</mark>") }} /></div>
                    <SourceRef versionId={h.version_id} page={h.page_number} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Card>
      <Card>
        {isLoading ? <Loading /> : !data?.length ? <EmptyState icon={<FileText />} title="Nog geen documenten" description="Importeer polisvoorwaarden, verzekeringskaarten, clausules of productinformatie. Meerdere PDF's tegelijk is mogelijk." action={<Button variant="primary" onClick={() => setUpload(true)}>Documenten importeren</Button>} /> : (
          <table className="w-full text-[13px]">
            <thead><tr className="border-b border-line text-left text-[12px] text-ink-muted"><th className="px-5 py-2.5 font-medium">Document</th><th className="font-medium">Aanbieder · product</th><th className="font-medium">Versie</th><th className="font-medium">Extractie</th><th className="font-medium">Bijgewerkt</th><th /></tr></thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.id} onClick={() => nav(`/documenten/${d.id}`)} className="cursor-pointer border-b border-line last:border-0 hover:bg-surface/50">
                  <td className="px-5 py-3"><div className="font-medium">{d.title}</div><div className="text-[12px] text-ink-muted">{DOC_TYPE[d.document_type]}{d.visibility === "niet_publiek" && " · niet-publiek"}</div></td>
                  <td>{d.provider_name || <span className="text-caution">Niet gekoppeld</span>}<div className="text-[12px] text-ink-muted">{d.product_name || "–"}</div></td>
                  <td>{d.current_version?.version_label || "–"}<div className="text-[12px] text-ink-muted">{d.version_count} versie(s)</div></td>
                  <td><Badge tone={d.current_version?.extraction_quality === "goed" ? "positive" : d.current_version?.extraction_quality === "matig" ? "caution" : "negative"}>{d.current_version?.extraction_quality || d.current_version?.status || "–"}</Badge></td>
                  <td className="text-[12.5px] text-ink-muted">{relative(d.updated_at)}</td>
                  <td className="pr-5"><ArrowUpRight className="h-4 w-4 text-ink-faint" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <UploadDialog open={upload} onOpenChange={setUpload} />
    </>
  );
}

function Registry() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["sources"], queryFn: () => api.get<any[]>("/sources") });
  const [edit, setEdit] = React.useState<any>(null);
  const toggle = async (s: any, v: boolean) => { await api.patch(`/sources/${s.id}`, { monitor_enabled: v }); qc.invalidateQueries({ queryKey: ["sources"] }); qc.invalidateQueries({ queryKey: ["monitor-status"] }); };
  const check = async (s: any) => {
    try { await api.post("/monitor/run", { source_ids: [s.id], sync: true }); qc.invalidateQueries({ queryKey: ["sources"] }); toast.success("Bron gecontroleerd"); } catch (e: any) { toast.error(e.message); }
  };
  const del = async (s: any) => { if (!confirm("Bron uit het register verwijderen? Gekoppelde documenten blijven bewaard.")) return; await api.del(`/sources/${s.id}`); qc.invalidateQueries({ queryKey: ["sources"] }); };
  return (
    <>
      <div className="mb-4 flex justify-end"><Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setEdit({})}>Bron toevoegen</Button></div>
      <Card className="overflow-hidden">
        {!data?.length ? <EmptyState icon={<Link2 />} title="Bronregister is leeg" description="Bronnen worden automatisch toegevoegd bij het ophalen van een PDF via URL, of voeg productpagina's en documenten handmatig toe om ze wekelijks te laten controleren." /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead><tr className="border-b border-line text-left text-[11.5px] text-ink-muted">{["Bron", "Aanbieder", "Soort bron", "Toegang", "Status", "Laatste controle", "Monitor", ""].map((h) => <th key={h} className="px-3 py-2.5 font-medium first:pl-5">{h}</th>)}</tr></thead>
              <tbody>
                {data.map((s) => (
                  <tr key={s.id} className="border-b border-line last:border-0 align-top">
                    <td className="max-w-[320px] py-2.5 pl-5 pr-3"><div className="truncate font-medium">{s.title || "Zonder titel"}</div>{s.url && <a href={s.url} target="_blank" rel="noreferrer" className="block truncate text-[11.5px] text-accent hover:underline">{s.url}</a>}<div className="text-[11px] text-ink-faint">{s.content_hash ? `hash ${s.content_hash.slice(0, 12)}…` : ""}{s.version_label ? ` · versie ${s.version_label}` : ""}</div></td>
                    <td className="px-3 py-2.5">{s.provider_name || "–"}</td>
                    <td className="px-3 py-2.5">{SOURCE_TYPE[s.source_type]}<div className="text-[11px] text-ink-muted">{s.kind}{s.visibility === "niet_publiek" ? " · niet-publiek" : ""}</div></td>
                    <td className="px-3 py-2.5"><Badge tone={ACCESS[s.access_status]?.tone}>{ACCESS[s.access_status]?.label}</Badge></td>
                    <td className="px-3 py-2.5">{s.processing_status}{s.last_check_result && <div className="text-[11px] text-ink-muted">{s.last_check_result}</div>}</td>
                    <td className="px-3 py-2.5">{relative(s.last_check_at)}<div className="text-[11px] text-ink-muted">succes: {s.last_success_check_at ? date(s.last_success_check_at) : "–"}</div></td>
                    <td className="px-3 py-2.5"><Switch checked={s.monitor_enabled} onCheckedChange={(v) => toggle(s, v)} disabled={!s.url} /></td>
                    <td className="whitespace-nowrap px-3 py-2 pr-5 text-right">
                      <Button size="icon" variant="ghost" onClick={() => check(s)} disabled={!s.url} aria-label="Nu controleren"><RefreshCw className="h-3.5 w-3.5" /></Button>
                      <Button size="icon" variant="ghost" onClick={() => setEdit(s)} aria-label="Bewerken"><Pencil className="h-3.5 w-3.5" /></Button>
                      <Button size="icon" variant="ghost" onClick={() => del(s)} aria-label="Verwijderen"><Trash2 className="h-3.5 w-3.5" /></Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <SourceForm open={!!edit} onOpenChange={(v) => !v && setEdit(null)} initial={edit?.id ? edit : undefined} />
    </>
  );
}

function SourceForm({ open, onOpenChange, initial }: { open: boolean; onOpenChange: (v: boolean) => void; initial?: any }) {
  const qc = useQueryClient();
  const providers = useProviders();
  const [f, setF] = React.useState<any>({});
  React.useEffect(() => { if (open) setF(initial || { source_type: "officieel_primair", kind: "pagina", access_status: "onbekend", visibility: "publiek", monitor_enabled: true }); }, [open, initial]);
  const set = (k: string) => (e: any) => setF((x: any) => ({ ...x, [k]: e.target.value }));
  const save = async () => {
    try {
      const body = { ...f, provider_id: f.provider_id ? Number(f.provider_id) : null };
      if (initial?.id) await api.patch(`/sources/${initial.id}`, body); else await api.post("/sources", body);
      ["sources", "monitor-status"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onOpenChange(false);
    } catch (e: any) { toast.error(e.message); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="lg" title={initial ? "Bron bewerken" : "Bron toevoegen"} footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Annuleren</Button><Button variant="primary" onClick={save}>Opslaan</Button></>}>
      <div className="grid grid-cols-2 gap-4">
        <Field label="URL" className="col-span-2" hint="Alleen openbare http(s)-adressen; lokale netwerkadressen worden geweigerd."><Input value={f.url || ""} onChange={set("url")} placeholder="https://" /></Field>
        <Field label="Titel"><Input value={f.title || ""} onChange={set("title")} /></Field>
        <Field label="Aanbieder"><Select value={f.provider_id || ""} onChange={set("provider_id")}><option value="">–</option>{providers.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
        <Field label="Soort bron"><Select value={f.source_type} onChange={set("source_type")}>{Object.entries(SOURCE_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
        <Field label="Inhoud"><Select value={f.kind} onChange={set("kind")}><option value="pagina">Productpagina</option><option value="document">Document (PDF)</option><option value="tarief">Tariefinformatie</option><option value="calculator">Calculator</option></Select></Field>
        <Field label="Documenttype"><Select value={f.document_type || ""} onChange={set("document_type")}><option value="">–</option>{Object.entries(DOC_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
        <Field label="Toegangs-/toestemmingsstatus"><Select value={f.access_status} onChange={set("access_status")}>{Object.entries(ACCESS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</Select></Field>
        <Field label="Publicatiedatum"><Input type="date" value={f.published_at || ""} onChange={set("published_at")} /></Field>
        <Field label="Versienummer"><Input value={f.version_label || ""} onChange={set("version_label")} /></Field>
        <Field label="Toelichting toestemming" className="col-span-2"><Textarea rows={2} value={f.permission_note || ""} onChange={set("permission_note")} /></Field>
        <div className="col-span-2"><Switch checked={!!f.monitor_enabled} onCheckedChange={(v) => setF({ ...f, monitor_enabled: v })} label="Meenemen in wekelijkse controle" /></div>
      </div>
    </Dialog>
  );
}

const KIND_LABEL: Record<string, string> = {
  dubbel_document: "Dubbele documenten", productkoppeling: "Productkoppelingen", extractie: "PDF-extractie", clausules: "Ontbrekende clausules",
  verouderde_premie: "Verouderde premies", onvergelijkbare_premie: "Onvergelijkbare premies", tegenstrijdig: "Tegenstrijdige bronnen",
  ai_onderbouwing: "Niet-onderbouwde AI-conclusies", beoordeling: "Beoordeling nodig",
};

function Quality() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const { data, isLoading } = useQuery({ queryKey: ["quality"], queryFn: () => api.get("/quality") });
  const [kind, setKind] = React.useState("");
  const resolve = async (i: any) => { await api.post("/quality/resolve", { key: i.key, resolution: "geaccepteerd" }); qc.invalidateQueries({ queryKey: ["quality"] }); };
  const hist = async (i: any) => { await api.post(`/premiums/${i.entity_id}/mark-historical`); qc.invalidateQueries({ queryKey: ["quality"] }); toast.success("Gemarkeerd als historisch tarief"); };
  if (isLoading) return <Loading />;
  const issues = data.issues.filter((i: any) => !kind || i.kind === kind);
  return (
    <>
      <div className="mb-4 flex flex-wrap gap-1.5">
        <button onClick={() => setKind("")} className={cn("rounded-full border px-3 py-1 text-[12px]", !kind ? "border-ink bg-ink text-white" : "border-line text-ink-soft")}>Alle · {data.total}</button>
        {Object.entries(data.counts).map(([k, v]: any) => <button key={k} onClick={() => setKind(k)} className={cn("rounded-full border px-3 py-1 text-[12px]", kind === k ? "border-ink bg-ink text-white" : "border-line text-ink-soft")}>{KIND_LABEL[k] || k} · {v}</button>)}
      </div>
      <Card>
        {!issues.length ? <EmptyState icon={<ShieldCheck />} title="Geen openstaande signalen" description="Controles op duplicaten, koppelingen, verouderde of onvergelijkbare premies, tegenstrijdige bronnen, onbetrouwbare extractie en niet-onderbouwde AI-conclusies." /> : (
          <ul className="divide-y divide-line">
            {issues.map((i: any) => (
              <li key={i.key} className="flex items-start gap-4 px-5 py-3.5">
                <AlertTriangle className={cn("mt-0.5 h-4 w-4 shrink-0", i.severity === "hoog" ? "text-negative" : i.severity === "middel" ? "text-caution" : "text-ink-faint")} />
                <div className="min-w-0 flex-1">
                  <div className="text-[13.5px] font-medium">{i.title}</div>
                  <div className="mt-0.5 text-[12.5px] text-ink-muted">{i.detail}</div>
                  <div className="mt-1 text-[11.5px] text-ink-faint">{KIND_LABEL[i.kind]} · ernst {i.severity}</div>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  {i.kind === "verouderde_premie" && <Button size="sm" onClick={() => hist(i)}>Markeer historisch</Button>}
                  {i.link && <Button size="sm" onClick={() => nav(i.link)}>Controleren</Button>}
                  <Button size="sm" variant="ghost" icon={<CheckCircle2 className="h-3.5 w-3.5" />} onClick={() => resolve(i)}>Accepteren</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function ReviewFindings() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["findings", "review"], queryFn: () => api.get<any[]>("/findings", { review_status: "te_beoordelen" }) });
  const act = async (f: any, action: string) => {
    await api.post(`/findings/${f.id}/review`, { action });
    ["findings", "matrix", "quality"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  };
  const items = (data || []).filter((f) => f.origin !== "lokaal" || f.status !== "niet_gevonden");
  return (
    <Card>
      {isLoading ? <Loading /> : !items.length ? <EmptyState icon={<CheckCircle2 />} title="Alles beoordeeld" description="AI- en passagezoeker-bevindingen die wachten op menselijke controle verschijnen hier." /> : (
        <ul className="divide-y divide-line">
          {items.map((f) => (
            <li key={f.id} className="px-5 py-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[13px] text-ink-muted">{f.provider_name} · {f.product_name} · {f.feature_category}</div>
                  <div className="text-[14px] font-semibold">{f.feature_label}</div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2"><FindingStatus status={f.status} /><OriginBadge origin={f.origin} review={f.review_status} /><VerifiedMark verified={f.quote_verified} /><SourceRef versionId={f.document_version_id} page={f.page_number} article={f.article} quote={f.quote} /></div>
                  {f.value_text && <div className="mt-1.5 text-[13px]">{f.value_text}</div>}
                  {f.quote && <blockquote className="mt-2 line-clamp-3 border-l-2 border-line-strong pl-3 text-[12.5px] italic text-ink-muted">“{f.quote}”</blockquote>}
                </div>
                <div className="flex gap-1.5">
                  <Button size="sm" variant="danger" onClick={() => act(f, "afwijzen")}>Afwijzen</Button>
                  <Button size="sm" variant="primary" onClick={() => act(f, "goedkeuren")}>Goedkeuren</Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
