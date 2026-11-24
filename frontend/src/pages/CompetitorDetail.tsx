import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles, ArrowLeft, Pencil, Plus, Upload, Globe, MoreHorizontal, Trash2, Merge, CheckCircle2, ImageOff, Wand2, Search, Package, FileText, ArrowUpRight, ThumbsUp, ThumbsDown } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, date, eur, relative } from "@/lib/utils";
import { DOC_TYPE, OBS_TYPE, PROVIDER_STATUS, PROVIDER_TYPE, SOURCE_TYPE, VEHICLE, ACCESS } from "@/lib/labels";
import { ProviderLogo } from "@/components/common";
import { Battlecard, Timeline } from "@/components/ProviderInsights";
import { useAutoResearch } from "@/components/AutoResearch";
import { ProductForm, ProviderForm, UploadDialog, useProviders } from "@/components/forms";
import { Dialog, Menu, TabPanel, Tabs } from "@/components/ui/overlay";
import { Badge, Button, Card, CardHeader, EmptyState, Field, KeyValue, Loading, Notice, Select } from "@/components/ui/primitives";

export default function CompetitorDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = React.useState("overzicht");
  const [edit, setEdit] = React.useState(false);
  const [prodForm, setProdForm] = React.useState<any>(null);
  const [upload, setUpload] = React.useState(false);
  const [merge, setMerge] = React.useState(false);
  const { data: p, isLoading } = useQuery({ queryKey: ["provider", id], queryFn: () => api.get(`/providers/${id}`) });
  const premiums = useQuery({ queryKey: ["premiums", "provider", id], queryFn: () => api.get<any[]>("/premiums", { provider_id: id }), enabled: tab === "premies" });
  const research = useAutoResearch(p || {});
  if (isLoading || !p) return <Loading />;

  const del = async () => {
    if (!confirm(`Aanbieder ‘${p.name}’ en gekoppelde producten verwijderen? Documenten en premies blijven bewaard zonder koppeling.`)) return;
    try {
      await api.del(`/providers/${p.id}`);
      qc.invalidateQueries({ queryKey: ["providers"] });
      nav("/concurrenten");
    } catch (e: any) {
      toast.error(e.message);
    }
  };
  const setStatus = async (status: string) => {
    await api.patch(`/providers/${p.id}`, { status });
    qc.invalidateQueries({ queryKey: ["provider", id] });
    toast.success(`Status: ${PROVIDER_STATUS[status].label}`);
  };

  return (
    <div>
      <button onClick={() => nav("/concurrenten")} className="mb-5 inline-flex items-center gap-1 text-[13px] text-ink-muted hover:text-ink"><ArrowLeft className="h-3.5 w-3.5" /> Concurrenten</button>
      <div className="mb-8 flex flex-wrap items-start justify-between gap-6">
        <div className="flex items-center gap-5">
          <ProviderLogo name={p.name} logoUrl={p.logo_url} size={56} id={p.id} isReference={p.is_reference} />
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[28px] font-semibold tracking-tightest">{p.name}</h1>
              {p.is_reference && <Badge tone="accent">Referentie</Badge>}
              <Badge tone={PROVIDER_STATUS[p.status]?.tone}>{PROVIDER_STATUS[p.status]?.label}</Badge>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-3 text-[13px] text-ink-muted">
              <span>{PROVIDER_TYPE[p.provider_type]}</span>
              {p.website && <a href={p.website} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline"><Globe className="h-3.5 w-3.5" />{p.website.replace(/^https?:\/\//, "")}</a>}
              <span>Laatste controle: {p.last_checked_at ? relative(p.last_checked_at) : "nog niet"}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          {p.status === "te_beoordelen" && (
            <>
              <Button icon={<ThumbsDown className="h-4 w-4" />} onClick={() => setStatus("afgewezen")}>Niet relevant</Button>
              <Button variant="primary" icon={<ThumbsUp className="h-4 w-4" />} onClick={() => setStatus("actief")}>Goedkeuren</Button>
            </>
          )}
          <Button variant={p.products.length ? "secondary" : "primary"} icon={<Sparkles className="h-4 w-4" />} onClick={research.start} loading={research.busy}>Automatisch onderzoeken</Button>
          <Button icon={<Pencil className="h-4 w-4" />} onClick={() => setEdit(true)}>Bewerken</Button>
          {!p.is_reference && (
            <Menu trigger={<Button size="icon" variant="ghost" aria-label="Meer"><MoreHorizontal className="h-4 w-4" /></Button>}
              items={[{ label: "Samenvoegen met…", icon: <Merge />, onSelect: () => setMerge(true) }, "sep", { label: "Verwijderen", icon: <Trash2 />, onSelect: del, danger: true }]} />
          )}
        </div>
      </div>

      {p.verification_note && p.status === "te_beoordelen" && <Notice tone="attention" title="Te beoordelen" className="mb-6">{p.verification_note}</Notice>}

      <Tabs value={tab} onValueChange={setTab} tabs={[
        { value: "overzicht", label: "Overzicht" }, ...(p.is_reference ? [] : [{ value: "kaart", label: "Concurrentiekaart" }]), { value: "tijdlijn", label: "Tijdlijn" }, { value: "producten", label: "Producten", count: p.products.length },
        { value: "documenten", label: "Documenten", count: p.documents.length }, { value: "premies", label: "Premies", count: p.premium_count },
        { value: "bronnen", label: "Bronnen", count: p.sources.length }, { value: "logo", label: "Logo" },
      ]}>
        <TabPanel value="overzicht">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.4fr_1fr]">
            <div className="space-y-6">
              <Card className="p-6">
                <KeyValue items={[
                  { label: "Omschrijving", value: p.description || <span className="text-ink-faint">Nog niet ingevuld</span> },
                  { label: "Doelgroepen", value: p.target_groups },
                  { label: "Producten", value: p.products.map((x: any) => x.name).join(", ") || "–" },
                  { label: "Polisvoorwaarden", value: `${p.documents.filter((d: any) => d.document_type === "polisvoorwaarden").length} document(en)` },
                  { label: "Verzekeringskaarten", value: `${p.documents.filter((d: any) => d.document_type === "verzekeringskaart").length} document(en)` },
                  { label: "Openbare tarieven", value: `${p.premium_count} waarneming(en)` },
                  { label: "Herkomst", value: { handmatig: "Handmatig toegevoegd", startlijst: "Startlijst", ontdekt: "Automatisch ontdekt" }[p.origin as string] },
                ]} />
              </Card>
              {!p.is_reference && (
                <Card>
                  <CardHeader title="Belangrijkste verschillen met Vetera" subtitle="Alleen aantoonbare verschillen op basis van vastgelegde bevindingen" />
                  <div className="px-5 pb-5">
                    {p.products.length === 0 ? (
                      <p className="text-[13px] text-ink-muted">Voeg eerst een product toe.</p>
                    ) : (
                      p.products.map((prod: any) => (
                        <div key={prod.id} className="mb-4 last:mb-0">
                          <div className="mb-2 text-[13px] font-medium">{prod.name}</div>
                          {prod.summary.advantages.length + prod.summary.disadvantages.length === 0 ? (
                            <p className="text-[12.5px] text-ink-muted">Nog geen aantoonbare verschillen vastgesteld ({prod.summary.features_known} van {prod.summary.features_total} kenmerken bekend).</p>
                          ) : (
                            <ul className="space-y-1.5 text-[12.5px]">
                              {prod.summary.advantages.map((a: any, i: number) => <li key={"a" + i} className="flex gap-2"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-caution" /> <span><b className="font-medium">{a.feature}:</b> {a.text}</span></li>)}
                              {prod.summary.disadvantages.map((a: any, i: number) => <li key={"d" + i} className="flex gap-2"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" /> <span><b className="font-medium">{a.feature}:</b> {a.text}</span></li>)}
                            </ul>
                          )}
                        </div>
                      ))
                    )}
                    <Button size="sm" variant="link" className="mt-3" onClick={() => nav(`/voorwaarden?products=${p.products.map((x: any) => x.id).join(",")}`)}>Open in voorwaardenvergelijker →</Button>
                  </div>
                </Card>
              )}
            </div>
            <div className="space-y-6">
              <Card className="p-5">
                <div className="text-[13px] font-semibold mb-2">Gedocumenteerde sterke punten</div>
                <p className="whitespace-pre-wrap text-[13px] text-ink-soft">{p.strengths || <span className="text-ink-faint">Nog niets vastgelegd</span>}</p>
                <div className="mt-5 text-[13px] font-semibold mb-2">Gedocumenteerde zwakke punten</div>
                <p className="whitespace-pre-wrap text-[13px] text-ink-soft">{p.weaknesses || <span className="text-ink-faint">Nog niets vastgelegd</span>}</p>
              </Card>
              {p.merged_from.length > 0 && <Card className="p-5 text-[13px]"><div className="font-semibold mb-1">Samengevoegd uit</div>{p.merged_from.map((m: any) => m.name).join(", ")}</Card>}
            </div>
          </div>
        </TabPanel>

        <TabPanel value="producten">
          <div className="mb-4 flex justify-end"><Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setProdForm({})}>Product toevoegen</Button></div>
          {p.products.length === 0 ? (
            <Card><EmptyState icon={<Package />} title="Nog geen producten" description={p.is_reference ? "Leg het huidige, openbaar beschikbare Vetera-product vast. Dit is de enige referentie in vergelijkingen." : "Voeg de relevante oldtimer-, motor- of bromfietsproducten van deze aanbieder toe."} /></Card>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {p.products.map((prod: any) => (
                <Card key={prod.id} interactive onClick={() => nav(`/producten/${prod.id}`)} className="p-5">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-[15px] font-semibold">{prod.name}</div>
                      <div className="text-[12.5px] text-ink-muted">{VEHICLE[prod.vehicle_category]}</div>
                    </div>
                    <div className="flex gap-1.5">
                      {prod.canonical_product_id && <Badge tone="info">Distributie</Badge>}
                      <Button size="icon" variant="ghost" onClick={(e) => { e.stopPropagation(); setProdForm(prod); }} aria-label="Bewerken"><Pencil className="h-3.5 w-3.5" /></Button>
                    </div>
                  </div>
                  <div className="mt-4">
                    <div className="flex justify-between text-[12px] text-ink-muted"><span>Kenmerken vastgesteld</span><span className="tabular">{prod.summary.features_known}/{prod.summary.features_total}</span></div>
                    <div className="mt-1.5 h-1.5 rounded-full bg-surface overflow-hidden"><div className="h-full rounded-full bg-accent" style={{ width: `${(prod.summary.features_known / prod.summary.features_total) * 100}%` }} /></div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </TabPanel>

        <TabPanel value="documenten">
          <div className="mb-4 flex justify-end"><Button variant="primary" icon={<Upload className="h-4 w-4" />} onClick={() => setUpload(true)}>Documenten importeren</Button></div>
          <Card>
            {p.documents.length === 0 ? (
              <EmptyState icon={<FileText />} title="Geen documenten" description="Importeer polisvoorwaarden, verzekeringskaarten of clausules als PDF." />
            ) : (
              <ul className="divide-y divide-line">
                {p.documents.map((d: any) => (
                  <li key={d.id}>
                    <button onClick={() => nav(`/documenten/${d.id}`)} className="flex w-full items-center justify-between gap-4 px-5 py-3.5 text-left hover:bg-surface/60">
                      <div className="min-w-0">
                        <div className="truncate text-[13.5px] font-medium">{d.title}</div>
                        <div className="text-[12px] text-ink-muted">{DOC_TYPE[d.document_type]} · {d.version_count} versie(s){d.visibility === "niet_publiek" && " · niet-publiek"}</div>
                      </div>
                      <ArrowUpRight className="h-4 w-4 text-ink-faint" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </TabPanel>

        <TabPanel value="premies">
          <Card>
            {!premiums.data?.length ? (
              <EmptyState title="Geen premies" description="Leg premies vast in het Premielab of importeer een Excel-onderzoek." action={<Button onClick={() => nav("/premielab")}>Naar Premielab</Button>} />
            ) : (
              <table className="w-full text-[13px]">
                <thead><tr className="border-b border-line text-left text-[12px] text-ink-muted"><th className="px-5 py-2.5 font-medium">Product</th><th className="font-medium">Dekking</th><th className="font-medium">Jaarpremie</th><th className="font-medium">Type</th><th className="font-medium pr-5">Peildatum</th></tr></thead>
                <tbody>
                  {premiums.data.map((o) => (
                    <tr key={o.id} className="border-b border-line last:border-0">
                      <td className="px-5 py-2.5">{o.product_name || "–"}</td><td>{o.coverage_variant || "–"}</td><td className="tabular">{eur(o.annual_premium)}</td>
                      <td><Badge tone={o.is_historical ? "neutral" : "info"}>{OBS_TYPE[o.observation_type]}</Badge></td><td className="pr-5">{date(o.reference_date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </TabPanel>

        <TabPanel value="bronnen">
          <Card>
            {p.sources.length === 0 ? <EmptyState title="Geen bronnen" description="Bronnen worden toegevoegd bij het ophalen van documenten via URL of in het bronregister." action={<Button onClick={() => nav("/bronnen?tab=bronnen")}>Naar bronregister</Button>} /> : (
              <ul className="divide-y divide-line">
                {p.sources.map((s: any) => (
                  <li key={s.id} className="flex items-center justify-between gap-4 px-5 py-3 text-[13px]">
                    <div className="min-w-0"><div className="truncate font-medium">{s.title || s.url}</div><div className="truncate text-[12px] text-ink-muted">{SOURCE_TYPE[s.source_type]} · {s.url}</div></div>
                    <div className="flex gap-1.5"><Badge tone={ACCESS[s.access_status]?.tone}>{ACCESS[s.access_status]?.label}</Badge>{s.monitor_enabled && <Badge tone="accent">Gemonitord</Badge>}</div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </TabPanel>

        <TabPanel value="logo"><LogoManager provider={p} /></TabPanel>
        <TabPanel value="kaart"><Battlecard providerId={p.id} /></TabPanel>
        <TabPanel value="tijdlijn"><Timeline providerId={p.id} /></TabPanel>
      </Tabs>

      <ProviderForm open={edit} onOpenChange={setEdit} initial={p} />
      <ProductForm open={!!prodForm} onOpenChange={(v) => !v && setProdForm(null)} initial={prodForm?.id ? prodForm : undefined} providerId={p.id} />
      <UploadDialog open={upload} onOpenChange={setUpload} providerId={p.id} />
      {research.dialog}
      <MergeDialog open={merge} onOpenChange={setMerge} provider={p} />
    </div>
  );
}

function MergeDialog({ open, onOpenChange, provider }: { open: boolean; onOpenChange: (v: boolean) => void; provider: any }) {
  const providers = useProviders();
  const [target, setTarget] = React.useState("");
  const nav = useNavigate();
  const qc = useQueryClient();
  const go = async () => {
    try {
      await api.post(`/providers/${provider.id}/merge`, { target_id: Number(target) });
      qc.invalidateQueries({ queryKey: ["providers"] });
      toast.success("Aanbieders samengevoegd");
      nav(`/concurrenten/${target}`);
    } catch (e: any) {
      toast.error(e.message);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={`${provider.name} samenvoegen`} description="Producten, documenten, bronnen en premies gaan over naar de gekozen aanbieder. De wijziging wordt vastgelegd in de audittrail."
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Annuleren</Button><Button variant="primary" disabled={!target} onClick={go}>Samenvoegen</Button></>}>
      <Field label="Samenvoegen met">
        <Select value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">Kies aanbieder…</option>
          {providers.data?.filter((x) => x.id !== provider.id && !x.is_reference).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </Select>
      </Field>
    </Dialog>
  );
}

function LogoManager({ provider }: { provider: any }) {
  const qc = useQueryClient();
  const cands = useQuery({ queryKey: ["logo-cands", provider.id], queryFn: () => api.get<any[]>(`/providers/${provider.id}/logo/candidates`) });
  const [busy, setBusy] = React.useState(false);
  const [bg, setBg] = React.useState<"light" | "dark" | "check">("check");
  const refresh = () => { cands.refetch(); qc.invalidateQueries({ queryKey: ["provider", String(provider.id)] }); qc.invalidateQueries({ queryKey: ["providers"] }); };
  const act = async (fn: () => Promise<any>, msg?: string) => {
    setBusy(true);
    try {
      const r = await fn();
      if (r?.errors?.length) toast.message(`${r.candidates.length} kandidaat/kandidaten gevonden`, { description: r.errors.slice(0, 2).join("\n") });
      else if (msg) toast.success(msg);
      refresh();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  const upload = (f: File) => {
    const fd = new FormData();
    fd.append("file", f);
    act(() => api.upload(`/providers/${provider.id}/logo/upload`, fd), "Logo geüpload als kandidaat");
  };
  const bgClass = { light: "bg-white", dark: "bg-[#1d1d1f]", check: "bg-[conic-gradient(#f0f0f2_25%,#fff_0_50%,#f0f0f2_0_75%,#fff_0)] bg-[length:16px_16px]" }[bg];
  return (
    <div className="space-y-6">
      <Notice tone="info" title="Alleen officiële logo's">
        Gebruik uitsluitend het officiële logo van de aanbieder (bij voorkeur SVG of transparante PNG) en controleer de merkrichtlijnen. Logo's worden nooit nagemaakt; zonder goedgekeurd logo toont de app een nette tekstweergave.
      </Notice>
      <Card className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className={cn("flex h-20 w-48 items-center justify-center rounded-xl border border-line", bgClass)}>
              <ProviderLogo name={provider.name} logoUrl={provider.logo_url} size={40} id={provider.id} isReference={provider.is_reference} />
            </div>
            <div>
              <div className="text-[14px] font-semibold">Huidig logo</div>
              <div className="text-[12.5px] text-ink-muted">{provider.logo_status === "goedgekeurd" ? (provider.logo_auto ? "Automatisch gekozen van de officiële website — kies hieronder een ander als het niet klopt" : "Door jou gekozen; wordt niet automatisch vervangen") : "Geen logo — tekstweergave actief"}</div>
              {provider.logo_source_url && <div className="text-[11.5px] text-ink-faint truncate max-w-md">Bron: {provider.logo_source_url}</div>}
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="primary" icon={<Wand2 className="h-4 w-4" />} onClick={() => act(() => api.post(`/providers/${provider.id}/logo/auto`), "Logo automatisch gekozen en achtergrond verwijderd")} loading={busy} disabled={!provider.website}>Automatisch kiezen</Button>
            <Button icon={<Search className="h-4 w-4" />} onClick={() => act(() => api.post(`/providers/${provider.id}/logo/discover`))} loading={busy} disabled={!provider.website}>Kandidaten zoeken</Button>
            <label className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-[10px] bg-surface px-3.5 text-[13.5px] font-medium hover:bg-surface-sunken">
              <Upload className="h-4 w-4" /> Uploaden
              <input type="file" accept=".svg,.png,.jpg,.jpeg,.webp" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
            </label>
            {provider.logo_status === "goedgekeurd" && <Button variant="ghost" icon={<ImageOff className="h-4 w-4" />} onClick={() => act(() => api.del(`/providers/${provider.id}/logo`), "Logo verwijderd")}>Verwijderen</Button>}
          </div>
        </div>
      </Card>
      <div className="flex items-center justify-between">
        <h3 className="text-[15px] font-semibold">Kandidaten ter goedkeuring</h3>
        <div className="flex gap-1 rounded-lg bg-surface p-0.5 text-[12px]">
          {(["check", "light", "dark"] as const).map((b) => <button key={b} onClick={() => setBg(b)} className={cn("rounded-md px-2 py-1", bg === b ? "bg-white shadow-sm" : "text-ink-muted")}>{{ check: "Transparantie", light: "Licht", dark: "Donker" }[b]}</button>)}
        </div>
      </div>
      {!cands.data?.length ? (
        <Card><EmptyState title="Geen kandidaten" description={provider.website ? "Zoek op de officiële website of upload een logo." : "Vul eerst de officiële website in, of upload een logo."} /></Card>
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
          {cands.data.map((c: any) => (
            <Card key={c.name} className="overflow-hidden">
              <div className={cn("flex h-32 items-center justify-center p-4", bgClass)}>
                <img src={api.url(`/providers/${provider.id}/logo/candidates/${c.name}`)} alt="" className="max-h-full max-w-full object-contain" />
              </div>
              <div className="border-t border-line p-3">
                <div className="flex flex-wrap gap-1 text-[11px]">
                  <Badge>{c.ext.replace(".", "").toUpperCase()}</Badge>
                  {c.width && <Badge>{c.width}×{c.height}</Badge>}
                  <Badge tone={c.transparent ? "positive" : "caution"}>{c.transparent ? "Transparant" : "Achtergrond"}</Badge>
                  {cands.data?.[0]?.name === c.name && <Badge tone="accent">Beste keuze</Badge>}
                </div>
                <div className="mt-1.5 truncate text-[11px] text-ink-faint" title={c.origin}>{c.origin}</div>
                <div className="mt-2 flex gap-1.5">
                  <Button size="sm" variant="primary" icon={<CheckCircle2 className="h-3.5 w-3.5" />} onClick={() => act(() => api.post(`/providers/${provider.id}/logo/candidates/${c.name}/approve`), "Logo goedgekeurd")}>Goedkeuren</Button>
                  {!c.transparent && c.ext !== ".svg" && <Button size="sm" icon={<Wand2 className="h-3.5 w-3.5" />} onClick={() => act(() => api.post(`/providers/${provider.id}/logo/candidates/${c.name}/transparent`), "Transparante variant gemaakt")}>Transparant</Button>}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
