import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, ShieldCheck, Download, UploadCloud, Trash2, Plus, Database, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api, useCloud } from "@/lib/api";
import { date, eur, num } from "@/lib/utils";
import { Dialog, TabPanel, Tabs } from "@/components/ui/overlay";
import { Badge, Button, Card, CardHeader, Field, Input, KeyValue, Loading, Notice, PageHeader, Select, Switch } from "@/components/ui/primitives";

export default function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "ai";
  const qc = useQueryClient();
  const { data: s } = useQuery({ queryKey: ["settings"], queryFn: () => api.get("/settings") });
  const cloud = useCloud();
  const save = async (body: any) => {
    try {
      await api.patch("/settings", body);
      ["settings", "ai-status", "monitor-status", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      toast.success("Opgeslagen");
    } catch (e: any) { toast.error(e.message); }
  };
  if (!s) return <Loading />;
  return (
    <div>
      <PageHeader module="instellingen" title="Instellingen" subtitle={cloud ? "De app draait online bij je hostingdienst, beveiligd met een wachtwoord. Externe verbindingen worden alleen gemaakt voor functies die dat nodig hebben." : "Alle gegevens staan lokaal op deze computer. Externe verbindingen worden alleen gemaakt voor functies die dat nodig hebben."} />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v })} tabs={[{ value: "ai", label: "AI" }, { value: "rubrieken", label: "Vergelijkingsrubrieken" }, { value: "monitor", label: "Monitor & premies" }, { value: "data", label: "Data & back-up" }, { value: "audit", label: "Audittrail" }, { value: "systeem", label: "Systeem" }]}>
        <TabPanel value="ai"><AiSettings s={s} save={save} /></TabPanel>
        <TabPanel value="rubrieken"><Features /></TabPanel>
        <TabPanel value="monitor"><MonitorSettings s={s} save={save} /></TabPanel>
        <TabPanel value="data"><DataSettings /></TabPanel>
        <TabPanel value="audit"><Audit /></TabPanel>
        <TabPanel value="systeem">
          <Card className="p-6"><KeyValue items={[
            { label: "Datamap", value: <code className="text-[12px]">{s._paths.data_dir}</code> },
            { label: "Server", value: s._cloud ? "Online, beveiligd met wachtwoord" : `${s._host} (alleen lokaal bereikbaar)` },
            { label: "Database", value: "SQLite met Alembic-migraties" },
            { label: "API-documentatie", value: <a className="text-accent hover:underline" href="/api/docs" target="_blank" rel="noreferrer">/api/docs</a> },
          ]} /></Card>
        </TabPanel>
      </Tabs>
    </div>
  );
}

function AiSettings({ s, save }: { s: any; save: (b: any) => void }) {
  const ai = s._ai;
  const cloud = useCloud();
  const usage = useQuery({ queryKey: ["ai-analyses"], queryFn: () => api.get<any[]>("/ai/analyses") });
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_420px]">
      <div className="space-y-6">
        <Card className="p-6">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-surface"><KeyRound className="h-5 w-5 text-ink-muted" /></div>
            <div className="flex-1">
              <div className="flex items-center gap-2 text-[15px] font-semibold">Anthropic API-sleutel {ai.configured ? <Badge tone="positive"><CheckCircle2 className="h-3 w-3" /> Ingesteld</Badge> : <Badge tone="neutral"><XCircle className="h-3 w-3" /> Niet ingesteld</Badge>}</div>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-muted">De sleutel wordt om veiligheidsredenen nooit via de browser ingevoerd of opgeslagen. {cloud ? <>Zet hem bij je hostingdienst als omgevingsvariabele <code className="rounded bg-surface px-1">ANTHROPIC_API_KEY</code> (Render: Environment) en start de dienst opnieuw.</> : <>Zet hem in <code className="rounded bg-surface px-1">backend\.env</code> als <code className="rounded bg-surface px-1">ANTHROPIC_API_KEY=…</code> en herstart de app.</>} Zonder sleutel werken alle basisfuncties.</p>
            </div>
          </div>
        </Card>
        <Card className="space-y-4 p-6">
          <Switch checked={!!s.ai_enabled} onCheckedChange={(v) => save({ ai_enabled: v })} label="AI-functies inschakelen" description="Onderzoeksassistent, documentanalyse, verkoopargumenten, Verbeterradar en wijzigingsanalyse." />
          <div className="grid grid-cols-2 gap-4">
            <Field label="Model"><Select value={s.ai_model} onChange={(e) => save({ ai_model: e.target.value })}>{s._models.map((m: string) => <option key={m}>{m}</option>)}</Select></Field>
            <Field label="Denkdiepte (effort)" hint="Hoger = grondiger maar duurder"><Select value={s.ai_effort} onChange={(e) => save({ ai_effort: e.target.value })}>{["low", "medium", "high", "xhigh", "max"].map((m) => <option key={m}>{m}</option>)}</Select></Field>
            <Field label="Maandbudget (€)"><Input type="number" defaultValue={s.ai_monthly_budget_eur} onBlur={(e) => save({ ai_monthly_budget_eur: Number(e.target.value) })} /></Field>
            <Field label="Maximum per verzoek (€)"><Input type="number" step="0.1" defaultValue={s.ai_max_request_cost_eur} onBlur={(e) => save({ ai_max_request_cost_eur: Number(e.target.value) })} /></Field>
          </div>
        </Card>
        <Card className="space-y-4 p-6">
          <div className="flex items-center gap-2 text-[15px] font-semibold"><ShieldCheck className="h-4 w-4 text-accent" /> Privacy</div>
          <Switch checked={!!s.ai_allow_nonpublic} onCheckedChange={(v) => { if (v && !confirm("Niet-publieke documenten en premies kunnen dan — na een extra bevestiging per verzoek — naar de externe AI-dienst worden verstuurd. Doorgaan?")) return; save({ ai_allow_nonpublic: v }); }} label="Niet-publieke gegevens toestaan (per verzoek bevestigen)" description="Standaard uit. Interne documenten en niet-publieke Excel-data worden dan nooit naar AI gestuurd." />
          <Switch checked={!!s.ai_web_research} onCheckedChange={(v) => save({ ai_web_research: v })} label="Webonderzoek door AI toestaan" description="Voor concurrentieontdekking, marktontwikkelingen en verdiepend onderzoek. Er worden alleen openbare webbronnen geraadpleegd." />
          <Notice tone="neutral">{cloud ? "De app draait bij je hostingdienst; AI-verzoeken" : "De app draait lokaal, maar AI-verzoeken"} gaan via internet naar Anthropic. Vóór elk verzoek zie je welke gegevens worden verstuurd en wat de geraamde kosten zijn.</Notice>
        </Card>
      </div>
      <Card className="h-fit">
        <CardHeader title="Gebruik" subtitle={`Deze maand ${eur(ai.month_spend_eur)} van ${eur(ai.monthly_budget_eur)}`} />
        <div className="mx-5 mb-4 h-1.5 overflow-hidden rounded-full bg-surface"><div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(100, (ai.month_spend_eur / (ai.monthly_budget_eur || 1)) * 100)}%` }} /></div>
        <ul className="max-h-[420px] divide-y divide-line overflow-y-auto">
          {!usage.data?.length && <li className="px-5 pb-5 text-[12.5px] text-ink-muted">Nog geen AI-verzoeken.</li>}
          {usage.data?.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 px-5 py-2.5 text-[12.5px]">
              <div className="min-w-0"><div className="truncate font-medium">{a.kind}{a.question ? ` · ${a.question}` : ""}</div><div className="text-ink-muted">{date(a.created_at, true)} · {num(a.input_tokens)} in / {num(a.output_tokens)} uit</div></div>
              <div className="text-right"><div className="tabular">{eur(a.cost_estimate)}</div><Badge tone={a.status === "voltooid" ? "positive" : "negative"}>{a.status}</Badge></div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function Features() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["features", "all"], queryFn: () => api.get<any[]>("/features", { include_inactive: true }) });
  const [add, setAdd] = React.useState(false);
  const [f, setF] = React.useState<any>({ value_type: "status", category: "Dekkingen" });
  const toggle = async (x: any) => { await api.patch(`/features/${x.id}`, { active: !x.active }); qc.invalidateQueries({ queryKey: ["features"] }); };
  const create = async () => {
    try {
      await api.post("/features", { ...f, keywords: (f.keywords || "").split(",") });
      qc.invalidateQueries({ queryKey: ["features"] });
      setAdd(false);
      setF({ value_type: "status", category: "Dekkingen" });
    } catch (e: any) { toast.error(e.message); }
  };
  const cats = [...new Set((data || []).map((x) => x.category))];
  return (
    <>
      <div className="mb-4 flex justify-between"><p className="text-[13px] text-ink-muted">Rubrieken bepalen welke kenmerken worden vergeleken. Trefwoorden sturen de lokale passagezoeker.</p><Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setAdd(true)}>Kenmerk toevoegen</Button></div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {cats.map((c) => (
          <Card key={c}>
            <CardHeader title={c} />
            <ul className="divide-y divide-line">
              {data!.filter((x) => x.category === c).map((x) => (
                <li key={x.id} className="flex items-center justify-between gap-3 px-5 py-2.5">
                  <div className="min-w-0"><div className="text-[13px] font-medium">{x.label}</div><div className="truncate text-[11.5px] text-ink-muted">{x.value_type} · {x.scoring_aspect || "geen score"} · {(x.keywords || []).join(", ")}</div></div>
                  <Switch checked={x.active} onCheckedChange={() => toggle(x)} />
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
      <Dialog open={add} onOpenChange={setAdd} title="Kenmerk toevoegen" footer={<><Button variant="ghost" onClick={() => setAdd(false)}>Annuleren</Button><Button variant="primary" onClick={create} disabled={!f.label}>Toevoegen</Button></>}>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Rubriek"><Input value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} list="cats" /><datalist id="cats">{cats.map((c) => <option key={c} value={c} />)}</datalist></Field>
          <Field label="Kenmerk"><Input value={f.label || ""} onChange={(e) => setF({ ...f, label: e.target.value })} /></Field>
          <Field label="Waardetype"><Select value={f.value_type} onChange={(e) => setF({ ...f, value_type: e.target.value })}><option value="status">Status (gedekt/uitgesloten…)</option><option value="tekst">Tekst</option><option value="bedrag">Bedrag</option></Select></Field>
          <Field label="Scoringsaspect"><Select value={f.scoring_aspect || ""} onChange={(e) => setF({ ...f, scoring_aspect: e.target.value || null })}><option value="">Geen</option>{["dekking", "aanvullend", "waarde", "eigen_risico", "collectie", "acceptatie", "flexibiliteit", "gebruik"].map((a) => <option key={a}>{a}</option>)}</Select></Field>
          <Field label="Trefwoorden (kommagescheiden)" className="col-span-2"><Input value={f.keywords || ""} onChange={(e) => setF({ ...f, keywords: e.target.value })} /></Field>
        </div>
      </Dialog>
    </>
  );
}

function MonitorSettings({ s, save }: { s: any; save: (b: any) => void }) {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Card className="space-y-4 p-6">
        <div className="text-[15px] font-semibold">Broncontrole</div>
        <Field label="Interval (dagen)"><Input type="number" defaultValue={s.monitor_interval_days} onBlur={(e) => save({ monitor_interval_days: Number(e.target.value) })} /></Field>
        <Field label="Wachttijd tussen verzoeken naar dezelfde website (seconden)" hint="Voorkomt onnodige belasting van websites."><Input type="number" defaultValue={s.monitor_request_delay_s} onBlur={(e) => save({ monitor_request_delay_s: Number(e.target.value) })} /></Field>
        {s._auto_monitor ? <Notice tone="info" title="Automatische controle">De server controleert elk uur of de broncontrole aan de beurt is en voert hem dan zelf uit.</Notice> : <Notice tone="info" title="Wekelijkse Windows-taak">Voer eenmalig <code>scripts\schedule_weekly_check.bat</code> uit. De taak draait wanneer de computer aan staat; een gemiste controle wordt bij de volgende start van de app gemeld en kan worden ingehaald.</Notice>}
      </Card>
      <Card className="space-y-4 p-6">
        <div className="text-[15px] font-semibold">Premies</div>
        <Field label="Premie verouderd na (maanden)"><Input type="number" defaultValue={s.premium_stale_months} onBlur={(e) => save({ premium_stale_months: Number(e.target.value) })} /></Field>
        <Field label="Melding bij premieverschil vanaf (%)"><Input type="number" defaultValue={s.premium_difference_alert_pct} onBlur={(e) => save({ premium_difference_alert_pct: Number(e.target.value) })} /></Field>
      </Card>
    </div>
  );
}

function DataSettings() {
  const qc = useQueryClient();
  const backups = useQuery({ queryKey: ["backups"], queryFn: () => api.get<any[]>("/backups") });
  const [busy, setBusy] = React.useState(false);
  const [del, setDel] = React.useState("");
  const [confirmText, setConfirmText] = React.useState("");
  const make = async () => { setBusy(true); try { await api.post("/backup"); backups.refetch(); toast.success("Back-up gemaakt"); } finally { setBusy(false); } };
  const restore = async (file: File) => {
    if (!confirm("De huidige gegevens worden vervangen door de back-up. Er wordt eerst automatisch een veiligheidsback-up gemaakt. Doorgaan?")) return;
    const fd = new FormData();
    fd.append("file", file);
    try { const r = await api.upload("/restore", fd); toast.success(`Hersteld. Veiligheidsback-up: ${r.safety_backup}`); qc.invalidateQueries(); } catch (e: any) { toast.error(e.message); }
  };
  const doDelete = async () => {
    try { const r = await api.post("/data/delete", { what: del, confirm: confirmText }); toast.success(`${r.deleted} items verwijderd`); setDel(""); setConfirmText(""); qc.invalidateQueries(); } catch (e: any) { toast.error(e.message); }
  };
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader title="Back-up en herstel" subtitle="Database, documenten, imports, logo's en rapporten in één ZIP-bestand" actions={<Button variant="primary" icon={<Database className="h-4 w-4" />} onClick={make} loading={busy}>Back-up maken</Button>} />
        <ul className="divide-y divide-line">
          {backups.data?.map((b) => <li key={b.file} className="flex items-center justify-between px-5 py-2.5 text-[12.5px]"><span>{b.file}<span className="ml-2 text-ink-muted">{(b.size / 1024 / 1024).toFixed(1)} MB · {date(b.created, true)}</span></span><a href={api.url(`/backups/${b.file}`)} className="text-accent"><Download className="h-4 w-4" /></a></li>)}
        </ul>
        <div className="border-t border-line p-5">
          <label className="inline-flex cursor-pointer items-center gap-2 text-[13px] text-accent hover:underline"><UploadCloud className="h-4 w-4" /> Back-up terugzetten…<input type="file" accept=".zip" className="hidden" onChange={(e) => e.target.files?.[0] && restore(e.target.files[0])} /></label>
        </div>
      </Card>
      <Card className="space-y-4 p-6">
        <div className="flex items-center gap-2 text-[15px] font-semibold"><Trash2 className="h-4 w-4 text-negative" /> Gegevens verwijderen</div>
        <Field label="Categorie"><Select value={del} onChange={(e) => setDel(e.target.value)}><option value="">Kies…</option><option value="premies">Alle premiewaarnemingen</option><option value="imports">Excel-imports (incl. bestanden en premies)</option><option value="documenten">Alle documenten en bestanden</option><option value="meldingen">Meldingen</option><option value="ai">AI-analyses en gebruiksregistratie</option><option value="monitor">Monitorhistorie</option></Select></Field>
        {del && <><Field label="Typ VERWIJDEREN ter bevestiging"><Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} /></Field><Button variant="danger" onClick={doDelete} disabled={confirmText !== "VERWIJDEREN"}>Definitief verwijderen</Button></>}
        <p className="text-[12px] text-ink-muted">Maak eerst een back-up. Verwijderingen worden vastgelegd in de audittrail.</p>
      </Card>
    </div>
  );
}

function Audit() {
  const [entity, setEntity] = React.useState("");
  const { data } = useQuery({ queryKey: ["audit", entity], queryFn: () => api.get<any[]>("/audit", { entity }) });
  return (
    <>
      <Select value={entity} onChange={(e) => setEntity(e.target.value)} className="mb-4 w-60">
        <option value="">Alle onderdelen</option>
        {["provider", "product", "document", "finding", "premium", "source", "excel_import", "suggestion", "settings", "quality", "data"].map((x) => <option key={x}>{x}</option>)}
      </Select>
      <Card>
        <ul className="divide-y divide-line">
          {data?.map((a) => (
            <li key={a.id} className="px-5 py-2.5 text-[12.5px]">
              <div className="flex items-center justify-between"><span><span className="font-medium">{a.entity}{a.entity_id ? ` #${a.entity_id}` : ""}</span> · {a.action}</span><span className="text-ink-muted">{date(a.at, true)} · {a.actor}</span></div>
              {a.changes && Object.keys(a.changes).length > 0 && <div className="mt-0.5 truncate text-[11.5px] text-ink-muted">{JSON.stringify(a.changes)}</div>}
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
