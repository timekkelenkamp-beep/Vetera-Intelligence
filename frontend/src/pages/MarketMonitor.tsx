import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, AlarmClock, Bell, Flag, Archive, CheckCheck, Eye, CalendarClock, GitCompare, Sparkles, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, date, relative } from "@/lib/utils";
import { CHANGE_TONE, NOTIF_TYPE } from "@/lib/labels";
import { useAiAction } from "@/components/AiAction";
import { Dialog, TabPanel, Tabs } from "@/components/ui/overlay";
import { Badge, Button, Card, CardHeader, EmptyState, Loading, Notice, PageHeader, Select, Stat } from "@/components/ui/primitives";

export default function MarketMonitor() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "bericht";
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["monitor-status"], queryFn: () => api.get("/monitor/status"), refetchInterval: (q) => (q.state.data?.running ? 2500 : false) });
  const wasRunning = React.useRef(false);
  React.useEffect(() => {
    if (wasRunning.current && !status.data?.running) ["notifications", "monitor-runs", "diffs", "sources", "notif-count", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    wasRunning.current = !!status.data?.running;
  }, [status.data?.running]); // eslint-disable-line
  const start = async (trigger: string) => {
    try {
      await api.post("/monitor/run", { trigger });
      toast.success("Broncontrole gestart");
      status.refetch();
    } catch (e: any) { toast.error(e.message); }
  };
  const s = status.data;
  return (
    <div>
      <PageHeader module="marktmonitor" title="Marktmonitor" subtitle="Wekelijkse, respectvolle controle van bronnen (robots.txt, conditionele verzoeken, vertraging per website) met wijzigingsdetectie en meldingen."
        actions={<Button variant="primary" icon={<Play className="h-4 w-4" />} onClick={() => start(s?.overdue ? "inhaal" : "handmatig")} loading={!!s?.running} disabled={!s?.monitored_sources}>{s?.running ? "Controle loopt…" : s?.overdue ? "Inhaalcontrole starten" : "Nu controleren"}</Button>} />
      {s?.overdue && s.monitored_sources > 0 && <Notice tone="caution" icon={<AlarmClock />} className="mb-6" title="Controle gemist">{s.message}</Notice>}
      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-4">
        <Stat label="Gemonitorde bronnen" value={s?.monitored_sources ?? "–"} hint={!s?.monitored_sources ? "Zet ‘monitoren’ aan in het bronregister" : undefined} />
        <Stat label="Laatste controle" value={<span className="text-[20px]">{s?.last_run_at ? relative(s.last_run_at) : "Nog niet"}</span>} />
        <Stat label="Volgende controle" value={<span className="text-[20px]">{s?.next_due_at ? date(s.next_due_at) : "–"}</span>} hint={`Elke ${s?.interval_days ?? 7} dagen`} />
        <Stat label="Planning" value={<span className="text-[20px]">{s?.auto ? "Automatisch" : "Windows-taak"}</span>} hint={s?.auto ? "De server controleert zelf" : "Installeer met scripts\\schedule_weekly_check.bat"} icon={<CalendarClock />} />
      </div>
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v })} tabs={[{ value: "bericht", label: "Marktbericht" }, { value: "meldingen", label: "Meldingen" }, { value: "wijzigingen", label: "Documentwijzigingen" }, { value: "controles", label: "Controles" }]}>
        <TabPanel value="bericht"><MarketBrief /></TabPanel>
        <TabPanel value="meldingen"><Notifications /></TabPanel>
        <TabPanel value="wijzigingen"><Diffs /></TabPanel>
        <TabPanel value="controles"><Runs /></TabPanel>
      </Tabs>
    </div>
  );
}

function Notifications() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [status, setStatus] = React.useState("open");
  const [type, setType] = React.useState("");
  const [flagged, setFlagged] = React.useState(false);
  const { data, isLoading } = useQuery({ queryKey: ["notifications", status, type, flagged], queryFn: () => api.get<any[]>("/notifications", { status, type, flagged: flagged || undefined }) });
  const upd = async (n: any, body: any) => { await api.patch(`/notifications/${n.id}`, body); ["notifications", "notif-count", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); };
  const all = async () => { await api.post("/notifications/mark-all-read"); ["notifications", "notif-count"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); };
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-44"><option value="open">Open</option><option value="nieuw">Nieuw</option><option value="gelezen">Gelezen</option><option value="gearchiveerd">Gearchiveerd</option><option value="">Alle</option></Select>
        <Select value={type} onChange={(e) => setType(e.target.value)} className="w-56"><option value="">Alle soorten</option>{Object.entries(NOTIF_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
        <Button variant={flagged ? "primary" : "secondary"} icon={<Flag className="h-3.5 w-3.5" />} onClick={() => setFlagged(!flagged)}>Gemarkeerd</Button>
        <Button variant="ghost" className="ml-auto" icon={<CheckCheck className="h-4 w-4" />} onClick={all}>Alles gelezen</Button>
      </div>
      <Card>
        {isLoading ? <Loading /> : !data?.length ? <EmptyState icon={<Bell />} title="Geen meldingen" description="Meldingen verschijnen bij nieuwe concurrenten, gewijzigde voorwaarden, premieverschillen, onbereikbare bronnen en benodigde beoordelingen." /> : (
          <ul className="divide-y divide-line">
            {data.map((n) => (
              <li key={n.id} className={cn("group flex items-start gap-4 px-5 py-3.5", n.status === "nieuw" && "bg-accent-soft/20")}>
                <span className={cn("mt-2 h-2 w-2 shrink-0 rounded-full", n.status === "nieuw" ? "bg-accent" : "bg-transparent")} />
                <button className="min-w-0 flex-1 text-left" onClick={() => { upd(n, { status: n.status === "nieuw" ? "gelezen" : n.status }); n.link && nav(n.link); }}>
                  <div className="flex items-center gap-2">
                    <span className="text-[13.5px] font-medium">{n.title}</span>
                    {n.severity === "belangrijk" && <Badge tone="caution">Belangrijk</Badge>}
                  </div>
                  {n.body && <div className="mt-0.5 line-clamp-2 text-[12.5px] text-ink-muted">{n.body}</div>}
                  <div className="mt-1 text-[11.5px] text-ink-faint">{NOTIF_TYPE[n.type] || n.type} · {relative(n.created_at)}</div>
                </button>
                <div className="flex gap-0.5 opacity-60 group-hover:opacity-100">
                  <Button size="icon" variant="ghost" aria-label="Markeren" onClick={() => upd(n, { flagged: !n.flagged })}><Flag className={cn("h-3.5 w-3.5", n.flagged && "fill-current text-caution")} /></Button>
                  {n.status === "nieuw" && <Button size="icon" variant="ghost" aria-label="Gelezen" onClick={() => upd(n, { status: "gelezen" })}><Eye className="h-3.5 w-3.5" /></Button>}
                  {n.status !== "gearchiveerd" && <Button size="icon" variant="ghost" aria-label="Archiveren" onClick={() => upd(n, { status: "gearchiveerd" })}><Archive className="h-3.5 w-3.5" /></Button>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function Diffs() {
  const { data, isLoading } = useQuery({ queryKey: ["diffs"], queryFn: () => api.get<any[]>("/diffs") });
  const [open, setOpen] = React.useState<number | null>(null);
  return (
    <>
      <Card>
        {isLoading ? <Loading /> : !data?.length ? <EmptyState icon={<GitCompare />} title="Nog geen documentvergelijkingen" description="Een vergelijking ontstaat zodra een nieuwe versie van een document wordt geïmporteerd of door de monitor wordt opgehaald." /> : (
          <ul className="divide-y divide-line">
            {data.map((d) => (
              <li key={d.id}>
                <button className="flex w-full items-center gap-4 px-5 py-3.5 text-left hover:bg-surface/50" onClick={() => setOpen(d.id)}>
                  <div className="min-w-0 flex-1">
                    <div className="text-[13.5px] font-medium">{d.document_title}</div>
                    <div className="text-[12px] text-ink-muted">{d.provider_name || "–"} · {date(d.created_at, true)} · {d.summary?.aantal_wijzigingen} wijzigingen</div>
                  </div>
                  <div className="flex flex-wrap justify-end gap-1">
                    {Object.entries(d.summary?.per_categorie || {}).filter(([k]) => k !== "redactioneel").map(([k, v]: any) => <Badge key={k} tone={CHANGE_TONE[k]}>{v} {k.replace("_", " ")}</Badge>)}
                    {d.ai_analysis_id && <Badge tone="accent"><Sparkles className="h-3 w-3" /> AI</Badge>}
                  </div>
                  <ChevronRight className="h-4 w-4 text-ink-faint" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {open && <DiffDialog id={open} onClose={() => setOpen(null)} />}
    </>
  );
}

export function DiffDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const { data, refetch } = useQuery({ queryKey: ["diff", id], queryFn: () => api.get(`/diffs/${id}`) });
  const [hideRed, setHideRed] = React.useState(true);
  const ai = useAiAction("/ai/diff-analysis", { onDone: () => refetch(), invalidate: [["diffs"]] });
  const changes = (data?.changes || []).map((c: any, i: number) => ({ ...c, i })).filter((c: any) => !hideRed || c.category !== "redactioneel");
  const aiByIndex = Object.fromEntries((data?.ai_analysis?.changes || []).map((c: any) => [c.index, c]));
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()} size="xl" title={data?.document_title || "Wijzigingen"} description={data?.summary?.toelichting}
      footer={<><Button variant="ghost" onClick={() => setHideRed(!hideRed)}>{hideRed ? "Toon redactionele wijzigingen" : "Verberg redactionele wijzigingen"}</Button><Button icon={<Sparkles className="h-3.5 w-3.5" />} onClick={() => ai.start({ diff_id: id })} loading={ai.busy}>Consequenties analyseren met AI</Button></>}>
      {!data ? <Loading /> : (
        <div className="space-y-4">
          {data.ai_analysis && (
            <Notice tone="accent" icon={<Sparkles />} title="AI-analyse (onzekerheden expliciet)">
              <p>{data.ai_analysis.summary}</p>
              {data.ai_analysis.relevance_for_vetera && <p className="mt-1"><b>Relevantie voor Vetera:</b> {data.ai_analysis.relevance_for_vetera}</p>}
              {data.ai_analysis.uncertainties?.length > 0 && <ul className="mt-1">{data.ai_analysis.uncertainties.map((u: string) => <li key={u}>• {u}</li>)}</ul>}
            </Notice>
          )}
          {changes.length === 0 && <p className="text-[13px] text-ink-muted">Geen inhoudelijke wijzigingen.</p>}
          {changes.map((c: any) => (
            <div key={c.i} className="rounded-xl border border-line">
              <div className="flex items-center justify-between border-b border-line px-4 py-2">
                <div className="flex items-center gap-2"><Badge tone={CHANGE_TONE[aiByIndex[c.i]?.category || c.category]}>{aiByIndex[c.i] ? aiByIndex[c.i].category.replace("_", " ") : c.category_label}</Badge><span className="text-[12px] text-ink-muted">{c.type}{c.new_page ? ` · nieuwe versie p. ${c.new_page}` : ""}</span></div>
                {aiByIndex[c.i] && <span className="text-[11.5px] text-ink-muted">zekerheid AI: {aiByIndex[c.i].certainty}</span>}
              </div>
              <div className="grid grid-cols-2 divide-x divide-line text-[12.5px] leading-relaxed">
                <div className="bg-negative-soft/30 p-3 text-ink-soft">{c.old || <span className="text-ink-faint">—</span>}</div>
                <div className="bg-positive-soft/30 p-3 text-ink">{c.new || <span className="text-ink-faint">—</span>}</div>
              </div>
              {aiByIndex[c.i]?.impact && <div className="border-t border-line px-4 py-2 text-[12.5px] text-ink-soft">{aiByIndex[c.i].impact}</div>}
            </div>
          ))}
        </div>
      )}
      {ai.dialog}
    </Dialog>
  );
}

function Runs() {
  const { data } = useQuery({ queryKey: ["monitor-runs"], queryFn: () => api.get<any[]>("/monitor/runs") });
  const [open, setOpen] = React.useState<number | null>(null);
  const detail = useQuery({ queryKey: ["monitor-run", open], queryFn: () => api.get(`/monitor/runs/${open}`), enabled: !!open });
  return (
    <>
      <Card>
        <CardHeader title="Uitgevoerde controles" subtitle="Gepland, handmatig of inhaalcontrole" />
        {!data?.length ? <EmptyState title="Nog geen controles" /> : (
          <ul className="divide-y divide-line">
            {data.map((r) => (
              <li key={r.id}>
                <button onClick={() => setOpen(r.id)} className="flex w-full items-center justify-between gap-4 px-5 py-3 text-left text-[13px] hover:bg-surface/50">
                  <div><div className="font-medium">{date(r.started_at, true)}</div><div className="text-[12px] text-ink-muted">{r.trigger} · {r.summary ? Object.entries(r.summary).map(([k, v]) => `${k}: ${v}`).join(" · ") : "bezig"}</div></div>
                  <Badge tone={r.status === "voltooid" ? "positive" : r.status === "fout" ? "negative" : "info"}>{r.status}</Badge>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Dialog open={!!open} onOpenChange={(v) => !v && setOpen(null)} size="lg" title="Controledetails">
        {!detail.data ? <Loading /> : (
          <ul className="divide-y divide-line text-[13px]">
            {detail.data.checks.map((c: any) => (
              <li key={c.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0"><div className="truncate font-medium">{c.source_title}</div>{c.message && <div className="text-[12px] text-ink-muted">{c.message}</div>}</div>
                <Badge tone={{ ongewijzigd: "neutral", gewijzigd: "caution", nieuw: "info", fout: "negative", geblokkeerd: "negative", niet_beschikbaar: "negative" }[c.result as string] as any}>{c.result}{c.http_status ? ` · ${c.http_status}` : ""}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Dialog>
    </>
  );
}

function MarketBrief() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [days, setDays] = React.useState<string>("auto");
  const since = days === "auto" ? undefined : new Date(Date.now() - Number(days) * 86400000).toISOString().slice(0, 19);
  const { data: b } = useQuery({ queryKey: ["market-brief", days], queryFn: () => api.get("/insights/market-brief", { since }) });
  const reports = useQuery({ queryKey: ["reports"], queryFn: () => api.get<any[]>("/reports") });
  const briefs = (reports.data || []).filter((r) => r.report_type === "marktbericht");
  const [busy, setBusy] = React.useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const r = await api.post("/reports", { report_type: "marktbericht", params: since ? { since } : {} });
      qc.invalidateQueries({ queryKey: ["reports"] });
      nav(`/rapportages/${r.id}`);
    } catch (e: any) { toast.error(e.message); } finally { setBusy(false); }
  };
  if (!b) return <Loading />;
  const color = "#e5493a";
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_320px]">
      <div className="space-y-5">
        <div className="relative overflow-hidden rounded-3xl border border-line bg-white p-7 shadow-soft">
          <div aria-hidden className="pointer-events-none absolute -right-20 -top-28 h-72 w-72 rounded-full blur-3xl" style={{ background: "radial-gradient(circle, rgba(229,73,58,0.16), transparent 65%)" }} />
          <div className="relative flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-[12px] font-semibold uppercase tracking-wide" style={{ color }}>Marktbericht</div>
              <h2 className="mt-1 text-[24px] font-semibold tracking-tightest">{date(b.period.from)} – {date(b.period.to)}</h2>
              <div className="text-[12.5px] text-ink-muted">{b.checks} broncontrole(s) in deze periode</div>
            </div>
            <div className="flex gap-2">
              <Select value={days} onChange={(e) => setDays(e.target.value)} className="w-52"><option value="auto">Sinds vorige controle</option><option value="7">Afgelopen 7 dagen</option><option value="30">Afgelopen 30 dagen</option><option value="90">Afgelopen 90 dagen</option></Select>
              <Button variant="primary" onClick={save} loading={busy}>Opslaan als rapport</Button>
            </div>
          </div>
          <ul className="relative mt-5 space-y-2 text-[14px] leading-relaxed">
            {b.headline.map((h: string) => <li key={h} className="flex gap-2.5"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: color }} />{h}</li>)}
          </ul>
        </div>
        {b.changes.length > 0 && (
          <Card>
            <CardHeader title="Gewijzigde polisvoorwaarden" subtitle="Redactionele wijzigingen zijn weggelaten; classificatie is indicatief" />
            <ul className="divide-y divide-line">
              {b.changes.map((c: any) => (
                <li key={c.diff_id} className="px-5 py-3.5">
                  <button className="w-full text-left" onClick={() => nav(`/documenten/${c.document_id}`)}>
                    <div className="flex flex-wrap items-center gap-2"><span className="text-[13.5px] font-semibold">{c.provider}</span><span className="text-[12.5px] text-ink-muted">· {c.document}</span><Badge tone="caution">{c.count} wijzigingen</Badge></div>
                    <div className="mt-1 flex flex-wrap gap-1">{c.categories.map((k: string) => <Badge key={k}>{k}</Badge>)}</div>
                    {c.examples.slice(0, 2).map((x: any, i: number) => <p key={i} className="mt-1.5 line-clamp-2 border-l-2 border-line-strong pl-3 text-[12.5px] text-ink-muted">{x.new}</p>)}
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        )}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <MiniList title="Nieuwe aanbieders" items={b.new_providers.map((p: any) => ({ t: p.name, s: p.status, to: `/concurrenten/${p.id}` }))} empty="Geen nieuwe aanbieders" />
          <MiniList title="Nieuwe documenten" items={b.new_documents.map((d: any) => ({ t: d.file, to: `/documenten/${d.id}` }))} empty="Geen nieuwe documenten" />
          <MiniList title="Premiesignalen" items={b.price_signals.map((t: string) => ({ t }))} empty="Geen premiesignalen" />
          <MiniList title="Niet bereikbare bronnen" items={b.unavailable_sources.map((t: string) => ({ t }))} empty="Alle bronnen bereikbaar" />
        </div>
      </div>
      <Card className="h-fit">
        <CardHeader title="Eerdere marktberichten" subtitle="Na elke broncontrole automatisch opgesteld" />
        {!briefs.length ? <p className="px-5 pb-5 text-[12.5px] text-ink-muted">Nog geen marktberichten.</p> : (
          <ul className="divide-y divide-line">{briefs.map((r) => <li key={r.id}><button onClick={() => nav(`/rapportages/${r.id}`)} className="w-full px-5 py-2.5 text-left text-[13px] hover:bg-surface/50"><div className="font-medium">{r.title}</div><div className="text-[11.5px] text-ink-muted">{date(r.created_at, true)}</div></button></li>)}</ul>
        )}
      </Card>
    </div>
  );
}

function MiniList({ title, items, empty }: { title: string; items: { t: string; s?: string; to?: string }[]; empty: string }) {
  const nav = useNavigate();
  return (
    <Card className="p-4">
      <div className="mb-2 text-[13px] font-semibold">{title}</div>
      {!items.length ? <p className="text-[12.5px] text-ink-faint">{empty}</p> : (
        <ul className="space-y-1 text-[12.5px]">{items.map((x, i) => <li key={i}>{x.to ? <button className="text-left text-accent hover:underline" onClick={() => nav(x.to!)}>{x.t}</button> : x.t}{x.s && <span className="text-ink-muted"> · {x.s}</span>}</li>)}</ul>
      )}
    </Card>
  );
}
