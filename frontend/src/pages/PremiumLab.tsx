import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, LabelList } from "recharts";
import { Plus, AlertTriangle, CheckCircle2, Copy, Pencil, Trash2, Calculator, Car, Bike, Layers, History } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, date, eur, num, pct } from "@/lib/utils";
import { COVERAGE, OBS_TYPE, PERIOD, VEHICLE } from "@/lib/labels";
import { AXIS, colorFor } from "@/lib/chart";
import { useProducts, useProviders } from "@/components/forms";
import { ImportStudio } from "@/components/ImportStudio";
import { Calculators } from "@/components/Calculators";
import { Dialog, TabPanel, Tabs } from "@/components/ui/overlay";
import { Badge, Button, Card, CardHeader, EmptyState, Field, Input, Loading, Notice, PageHeader, Segmented, Select, Switch, Textarea, Tip } from "@/components/ui/primitives";

export default function PremiumLab() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "vergelijking";
  return (
    <div>
      <PageHeader title="Premielab" subtitle="Objectieve premievergelijking op basis van rekenprofielen. Alleen gelijkwaardige scenario's worden zonder waarschuwing naast elkaar gezet; premies worden nooit geschat." />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v })} tabs={[
        { value: "vergelijking", label: "Vergelijking" }, { value: "premies", label: "Premiewaarnemingen" }, { value: "profielen", label: "Rekenprofielen" },
        { value: "import", label: "Excel Import Studio" }, { value: "historie", label: "Historie" }, { value: "analyse", label: "Uitsplitsing" }, { value: "calculators", label: "Proefberekeningen" },
      ]}>
        <TabPanel value="vergelijking"><Comparison /></TabPanel>
        <TabPanel value="premies"><Observations /></TabPanel>
        <TabPanel value="profielen"><Profiles /></TabPanel>
        <TabPanel value="import"><ImportStudio /></TabPanel>
        <TabPanel value="historie"><HistoryView /></TabPanel>
        <TabPanel value="analyse"><Breakdown /></TabPanel>
        <TabPanel value="calculators"><Calculators /></TabPanel>
      </Tabs>
    </div>
  );
}

function useProfiles() {
  return useQuery({ queryKey: ["profiles"], queryFn: () => api.get<any[]>("/profiles") });
}

const ChartTip = ({ active, payload, label, formatter }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-line bg-white/95 px-3 py-2 text-[12px] shadow-lift backdrop-blur">
      {label && <div className="mb-1 font-medium text-ink">{label}</div>}
      {payload.map((p: any, i: number) => (
        <div key={i} className="flex items-center gap-2 text-ink-soft">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color || p.payload?.fill }} />
          <span>{p.name}</span>
          <span className="ml-auto pl-3 font-medium tabular text-ink">{formatter ? formatter(p.value, p) : p.value}</span>
        </div>
      ))}
    </div>
  );
};

/* ------------------------------------------------------------------ Vergelijking */
function Comparison() {
  const profiles = useProfiles();
  const [pid, setPid] = React.useState<number | null>(null);
  const [asOf, setAsOf] = React.useState("");
  const [hist, setHist] = React.useState(false);
  const [add, setAdd] = React.useState(false);
  React.useEffect(() => { if (!pid && profiles.data?.length) setPid(profiles.data[0].id); }, [profiles.data, pid]);
  const { data } = useQuery({ queryKey: ["premium-compare", pid, asOf, hist], queryFn: () => api.get("/premiums/compare", { profile_id: pid, as_of: asOf, include_historical: hist }), enabled: !!pid });
  const profile = profiles.data?.find((p) => p.id === pid);
  const chart = (data?.rows || []).filter((r: any) => r.total_annual_cost).map((r: any) => ({ name: r.provider_name, value: r.total_annual_cost, fill: colorFor(r.provider_id, r.provider_is_reference), comparable: r.fully_comparable || r.is_baseline }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Rekenprofiel" className="w-80">
          <Select value={pid ?? ""} onChange={(e) => setPid(Number(e.target.value))}>{profiles.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select>
        </Field>
        <Field label="Peildatum" className="w-44"><Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></Field>
        <div className="pb-1.5"><Switch checked={hist} onCheckedChange={setHist} label="Historische tarieven tonen" /></div>
        <Button variant="primary" className="ml-auto" icon={<Plus className="h-4 w-4" />} onClick={() => setAdd(true)}>Premie vastleggen</Button>
      </div>
      {profile && <ProfileSummary p={profile} />}
      {!data ? <Loading /> : data.rows.length === 0 ? (
        <Card><EmptyState icon={<Calculator />} title="Nog geen premies voor dit profiel" description="Leg een premie vast (offerte, openbare indicatie of proefberekening) of importeer een Excel-onderzoek. Ontbrekende premies worden nooit aangevuld." action={<Button variant="primary" onClick={() => setAdd(true)}>Premie vastleggen</Button>} /></Card>
      ) : (
        <>
          <Notice tone={data.baseline === "vetera" ? "info" : "caution"} icon={data.baseline === "vetera" ? <CheckCircle2 /> : <AlertTriangle />}>{data.baseline_note}</Notice>
          <div className="grid grid-cols-1 gap-6 2xl:grid-cols-[1fr_400px]">
            <Card className="overflow-x-auto">
              <table className="w-full text-[13px] [&_td]:px-3 [&_th]:px-3">
                <thead><tr className="border-b border-line text-left text-[12px] text-ink-muted">
                  <th className="px-5 py-3 font-medium">Aanbieder</th><th className="font-medium">Dekking · ER</th><th className="text-right font-medium">Jaarpremie</th><th className="text-right font-medium">Totale jaarlast</th><th className="text-right font-medium">Verschil</th><th className="px-5 font-medium">Vergelijkbaarheid</th>
                </tr></thead>
                <tbody>
                  {data.rows.map((r: any) => (
                    <tr key={r.id} className={cn("border-b border-line last:border-0 align-top", r.is_baseline && "bg-accent-soft/40")}>
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2 font-medium"><span className="h-2.5 w-2.5 rounded-full" style={{ background: colorFor(r.provider_id, r.provider_is_reference) }} />{r.provider_name}{r.is_baseline && <Badge tone="accent">Basis</Badge>}</div>
                        <div className="mt-0.5 text-[12px] text-ink-muted">{r.product_name || "Product onbekend"} · {OBS_TYPE[r.observation_type]} · {date(r.reference_date)}</div>
                      </td>
                      <td className="py-3 text-[12.5px] whitespace-nowrap">{COVERAGE[r.coverage_variant] || r.coverage_variant || "–"}<div className="text-ink-muted">ER {eur(r.deductible, false)}</div></td>
                      <td className="py-3 text-right tabular whitespace-nowrap">{eur(r.annual_premium)}<div className="text-[11.5px] text-ink-muted">{r.tax_included === "ja" ? "incl. assurantiebel." : r.tax_included === "nee" ? "excl. assurantiebel." : "belasting onbekend"}</div></td>
                      <td className="py-3 text-right font-semibold tabular whitespace-nowrap">{eur(r.total_annual_cost)}{(r.membership_costs || r.extra_costs) ? <div className="text-[11.5px] font-normal text-ink-muted">incl. {eur((r.membership_costs || 0) + (r.extra_costs || 0))} kosten</div> : null}</td>
                      <td className="py-3 text-right tabular whitespace-nowrap">{r.diff_abs === null ? "–" : <><div className="font-medium">{pct(r.diff_pct)}</div><div className="text-[11.5px] text-ink-muted">{r.diff_abs > 0 ? "+" : ""}{eur(r.diff_abs)}</div></>}</td>
                      <td className="px-5 py-3">
                        {r.is_baseline ? <span className="text-[12px] text-ink-muted">Referentie</span> : r.fully_comparable ? <Badge tone="positive"><CheckCircle2 className="h-3 w-3" /> Vergelijkbaar</Badge> : (
                          <Tip content={<ul>{r.comparability_issues.map((x: string) => <li key={x}>• {x}</li>)}</ul>}><span><Badge tone="caution"><AlertTriangle className="h-3 w-3" /> {r.comparability_issues.length} afwijking(en)</Badge></span></Tip>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card className="p-5">
              <div className="mb-3 text-[14px] font-semibold">Totale jaarlast</div>
              <ResponsiveContainer width="100%" height={Math.max(160, chart.length * 44)}>
                <BarChart data={chart} layout="vertical" margin={{ left: 0, right: 64 }}>
                  <CartesianGrid horizontal={false} stroke="rgba(0,0,0,0.06)" />
                  <XAxis type="number" {...AXIS} tickFormatter={(v) => `€${v}`} />
                  <YAxis type="category" dataKey="name" width={110} {...AXIS} tick={{ fill: "#424245", fontSize: 12 }} />
                  <Tooltip cursor={{ fill: "rgba(0,0,0,0.03)" }} content={<ChartTip formatter={(v: number, p: any) => `${eur(v)}${p.payload.comparable ? "" : " · beperkt vergelijkbaar"}`} />} />
                  <Bar dataKey="value" name="Totale jaarlast" radius={[0, 4, 4, 0]} barSize={18}>
                    {chart.map((c: any, i: number) => <Cell key={i} fill={c.fill} fillOpacity={c.comparable ? 1 : 0.45} />)}
                    <LabelList dataKey="value" position="right" formatter={(v: number) => eur(v, false)} style={{ fontSize: 11.5, fill: "#424245" }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="mt-2 text-[11.5px] text-ink-muted">Lichtere balken: niet volledig vergelijkbaar met de basis.</p>
            </Card>
          </div>
        </>
      )}
      <ObservationForm open={add} onOpenChange={setAdd} defaults={{ profile_id: pid }} />
    </div>
  );
}

function ProfileSummary({ p }: { p: any }) {
  const items = [VEHICLE[p.vehicle_category], p.vehicle_type, p.build_year && `bouwjaar ${p.build_year}`, p.insured_value && `waarde ${eur(p.insured_value, false)}`, p.annual_km && `${num(p.annual_km)} km/jaar`, COVERAGE[p.coverage], p.deductible !== null && p.deductible !== undefined && `ER ${eur(p.deductible, false)}`, p.storage, p.usage, p.vehicle_count > 1 && `${p.vehicle_count} voertuigen`].filter(Boolean);
  return <div className="flex flex-wrap gap-1.5">{items.map((x, i) => <Badge key={i}>{x}</Badge>)}{p.is_example && <Badge tone="info">Voorbeeld-rekenprofiel</Badge>}</div>;
}

/* ------------------------------------------------------------------ Premiewaarnemingen */
function Observations() {
  const qc = useQueryClient();
  const [type, setType] = React.useState("");
  const [edit, setEdit] = React.useState<any>(null);
  const profiles = useProfiles();
  const { data, isLoading } = useQuery({ queryKey: ["premiums", type], queryFn: () => api.get<any[]>("/premiums", { observation_type: type }) });
  const pmap = Object.fromEntries((profiles.data || []).map((p) => [p.id, p.name]));
  const del = async (o: any) => {
    if (!confirm("Deze premiewaarneming verwijderen?")) return;
    await api.del(`/premiums/${o.id}`);
    qc.invalidateQueries({ queryKey: ["premiums"] });
  };
  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <Select value={type} onChange={(e) => setType(e.target.value)} className="w-64"><option value="">Alle typen</option>{Object.entries(OBS_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
        <span className="text-[12.5px] text-ink-muted">{data?.length ?? 0} waarnemingen</span>
        <Button variant="primary" className="ml-auto" icon={<Plus className="h-4 w-4" />} onClick={() => setEdit({})}>Premie vastleggen</Button>
      </div>
      <Card className="overflow-hidden">
        {isLoading ? <Loading /> : !data?.length ? <EmptyState title="Geen premiewaarnemingen" description="Een nieuwe installatie bevat bewust geen premies." /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead><tr className="border-b border-line text-left text-[11.5px] text-ink-muted">
                {["Aanbieder", "Product", "Profiel / voertuig", "Dekking", "ER", "Jaarpremie", "Type", "Betrouwbaarheid", "Peildatum", ""].map((h) => <th key={h} className="px-3 py-2.5 font-medium first:pl-5">{h}</th>)}
              </tr></thead>
              <tbody>
                {data.map((o) => (
                  <tr key={o.id} className="border-b border-line last:border-0 hover:bg-surface/40">
                    <td className="py-2.5 pl-5 pr-3 font-medium">{o.provider_name || "–"}</td>
                    <td className="px-3">{o.product_name || "–"}</td>
                    <td className="px-3">{o.profile_id ? pmap[o.profile_id] : [o.vehicle_description, o.build_year, o.insured_value && eur(o.insured_value, false)].filter(Boolean).join(" · ") || "–"}</td>
                    <td className="px-3">{COVERAGE[o.coverage_variant] || o.coverage_variant || "–"}</td>
                    <td className="px-3 tabular">{eur(o.deductible, false)}</td>
                    <td className="px-3 tabular font-medium">{eur(o.annual_premium)}</td>
                    <td className="px-3"><Badge tone={o.is_historical ? "neutral" : o.observation_type === "geverifieerd_tarief" ? "positive" : "info"}>{OBS_TYPE[o.observation_type]}</Badge></td>
                    <td className="px-3">{o.reliability}</td>
                    <td className="px-3">{date(o.reference_date)}</td>
                    <td className="px-3 pr-5 text-right whitespace-nowrap">
                      <Button size="icon" variant="ghost" onClick={() => setEdit(o)} aria-label="Bewerken"><Pencil className="h-3.5 w-3.5" /></Button>
                      <Button size="icon" variant="ghost" onClick={() => del(o)} aria-label="Verwijderen"><Trash2 className="h-3.5 w-3.5" /></Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <ObservationForm open={!!edit} onOpenChange={(v) => !v && setEdit(null)} initial={edit?.id ? edit : undefined} />
    </div>
  );
}

export function ObservationForm({ open, onOpenChange, initial, defaults, endpoint }: { open: boolean; onOpenChange: (v: boolean) => void; initial?: any; defaults?: any; endpoint?: string }) {
  const qc = useQueryClient();
  const providers = useProviders();
  const [f, setF] = React.useState<any>({});
  const products = useProducts(f.provider_id ? { provider_id: f.provider_id } : undefined);
  const profiles = useProfiles();
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => {
    if (open) setF(initial || { observation_type: "handmatige_offerte", period: "jaar", tax_included: "onbekend", reliability: "middel", visibility: "niet_publiek", reference_date: new Date().toISOString().slice(0, 10), ...defaults });
  }, [open, initial]); // eslint-disable-line
  React.useEffect(() => {
    const p = profiles.data?.find((x) => x.id === Number(f.profile_id));
    if (p && !initial && open) setF((x: any) => ({ ...x, coverage_variant: x.coverage_variant ?? p.coverage, deductible: x.deductible ?? p.deductible }));
  }, [f.profile_id, profiles.data]); // eslint-disable-line
  const set = (k: string) => (e: any) => setF((x: any) => ({ ...x, [k]: e.target.value }));
  const save = async () => {
    setBusy(true);
    const nums = ["amount", "extra_costs", "membership_costs", "deductible", "provider_id", "product_id", "profile_id"];
    const body: any = { ...f };
    nums.forEach((k) => (body[k] = body[k] === "" || body[k] === undefined || body[k] === null ? null : Number(body[k])));
    body.is_actual_quote = !!f.is_actual_quote;
    try {
      if (initial?.id) await api.patch(`/premiums/${initial.id}`, body);
      else await api.post(endpoint || "/premiums", body);
      ["premiums", "premium-compare", "dashboard", "premium-history", "calculators"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      toast.success("Premie vastgelegd");
      onOpenChange(false);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  const na = f.observation_type === "niet_beschikbaar";
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="lg" title={initial?.id ? "Premie bewerken" : "Premie vastleggen"} description="Leg alleen werkelijk waargenomen premies vast. Gebruik geen echte persoonsgegevens."
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Annuleren</Button><Button variant="primary" onClick={save} loading={busy}>Opslaan</Button></>}>
      <div className="grid grid-cols-3 gap-4">
        <Field label="Aanbieder" required className="col-span-1"><Select value={f.provider_id || ""} onChange={(e) => setF({ ...f, provider_id: e.target.value, product_id: "" })}><option value="">Kies…</option>{providers.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
        <Field label="Product"><Select value={f.product_id || ""} onChange={set("product_id")} disabled={!f.provider_id}><option value="">Onbekend</option>{products.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
        <Field label="Rekenprofiel"><Select value={f.profile_id || ""} onChange={set("profile_id")}><option value="">Geen</option>{profiles.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
        <Field label="Soort waarneming" className="col-span-2"><Select value={f.observation_type} onChange={set("observation_type")}>{Object.entries(OBS_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
        <Field label="Betrouwbaarheid"><Select value={f.reliability} onChange={set("reliability")}>{["hoog", "middel", "laag"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
        {!na && <>
          <Field label="Premiebedrag (€)" required><Input type="number" step="0.01" value={f.amount ?? ""} onChange={set("amount")} /></Field>
          <Field label="Periode"><Select value={f.period} onChange={set("period")}>{Object.entries(PERIOD).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
          <Field label="Assurantiebelasting"><Select value={f.tax_included} onChange={set("tax_included")}><option value="ja">Inclusief</option><option value="nee">Exclusief</option><option value="onbekend">Onbekend</option></Select></Field>
          <Field label="Verplichte lidmaatschapskosten (€/jaar)"><Input type="number" step="0.01" value={f.membership_costs ?? ""} onChange={set("membership_costs")} /></Field>
          <Field label="Overige kosten (€/jaar)"><Input type="number" step="0.01" value={f.extra_costs ?? ""} onChange={set("extra_costs")} /></Field>
          <Field label="Eigen risico (€)"><Input type="number" value={f.deductible ?? ""} onChange={set("deductible")} /></Field>
          <Field label="Dekkingsvariant"><Select value={f.coverage_variant || ""} onChange={set("coverage_variant")}><option value="">Onbekend</option>{Object.entries(COVERAGE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
        </>}
        <Field label="Peildatum"><Input type="date" value={f.reference_date || ""} onChange={set("reference_date")} /></Field>
        <Field label="Zichtbaarheid" hint="Bepaalt of AI dit mag zien"><Select value={f.visibility} onChange={set("visibility")}><option value="niet_publiek">Niet-publiek</option><option value="publiek">Openbaar</option></Select></Field>
        <Field label="Bron / herkomst" className="col-span-3"><Input value={f.source_description || ""} onChange={set("source_description")} placeholder="Bijv. openbare premietabel op website, offerte d.d. …" /></Field>
        <div className="col-span-3"><Switch checked={!!f.is_actual_quote} onCheckedChange={(v) => setF({ ...f, is_actual_quote: v })} label="Daadwerkelijk uitgebrachte offerte" description="Uit = getoonde premie (bijv. op een calculator), geen bindende offerte." /></div>
        <Field label="Opmerkingen" className="col-span-3"><Textarea rows={2} value={f.notes || ""} onChange={set("notes")} /></Field>
      </div>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ Profielen */
const PROFILE_ICON: Record<string, any> = { auto: Car, motor: Bike, bromfiets: Bike, meerdere: Layers };

function Profiles() {
  const profiles = useProfiles();
  const qc = useQueryClient();
  const [edit, setEdit] = React.useState<any>(null);
  const dup = async (p: any) => { await api.post(`/profiles/${p.id}/duplicate`); qc.invalidateQueries({ queryKey: ["profiles"] }); toast.success("Profiel gedupliceerd"); };
  const del = async (p: any) => { if (!confirm("Profiel verwijderen? Premies blijven bewaard zonder profielkoppeling.")) return; await api.del(`/profiles/${p.id}`); qc.invalidateQueries({ queryKey: ["profiles"] }); };
  return (
    <div>
      <Notice tone="info" className="mb-5">Rekenprofielen zijn fictieve risicoprofielen voor vergelijking — geen echte offertegegevens en geen persoonsgegevens.</Notice>
      <div className="mb-4 flex justify-end"><Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setEdit({})}>Nieuw profiel</Button></div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {profiles.data?.map((p) => {
          const Icon = PROFILE_ICON[p.vehicle_category] || Car;
          return (
            <Card key={p.id} className="p-5">
              <div className="flex items-start justify-between">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-surface"><Icon className="h-5 w-5 text-ink-muted" /></div>
                <div className="flex gap-0.5">
                  <Button size="icon" variant="ghost" onClick={() => setEdit(p)} aria-label="Bewerken"><Pencil className="h-3.5 w-3.5" /></Button>
                  <Button size="icon" variant="ghost" onClick={() => dup(p)} aria-label="Dupliceren"><Copy className="h-3.5 w-3.5" /></Button>
                  <Button size="icon" variant="ghost" onClick={() => del(p)} aria-label="Verwijderen"><Trash2 className="h-3.5 w-3.5" /></Button>
                </div>
              </div>
              <div className="mt-3 text-[15px] font-semibold">{p.name}</div>
              <div className="mt-2"><ProfileSummary p={p} /></div>
              <div className="mt-3 text-[12px] text-ink-muted">{p.premium_count} premie(s) gekoppeld</div>
            </Card>
          );
        })}
      </div>
      <ProfileForm open={!!edit} onOpenChange={(v) => !v && setEdit(null)} initial={edit?.id ? edit : undefined} />
    </div>
  );
}

function ProfileForm({ open, onOpenChange, initial }: { open: boolean; onOpenChange: (v: boolean) => void; initial?: any }) {
  const qc = useQueryClient();
  const [f, setF] = React.useState<any>({});
  React.useEffect(() => { if (open) setF(initial || { vehicle_category: "auto", vehicle_count: 1 }); }, [open, initial]);
  const set = (k: string) => (e: any) => setF((x: any) => ({ ...x, [k]: e.target.value }));
  const save = async (force = false) => {
    const body: any = { ...f, force };
    ["build_year", "engine_cc", "insured_value", "valuation_value", "claim_free_years", "annual_km", "deductible", "vehicle_count"].forEach((k) => (body[k] = body[k] === "" || body[k] == null ? null : Number(body[k])));
    try {
      if (initial?.id) await api.patch(`/profiles/${initial.id}`, body);
      else await api.post("/profiles", body);
      qc.invalidateQueries({ queryKey: ["profiles"] });
      onOpenChange(false);
    } catch (e: any) {
      if (e.status === 409 && confirm(e.message + "\n\nToch wijzigen?")) return save(true);
      toast.error(e.message);
    }
  };
  const fld = (k: string, label: string, type = "text") => <Field label={label}><Input type={type} value={f[k] ?? ""} onChange={set(k)} /></Field>;
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="lg" title={initial ? "Rekenprofiel bewerken" : "Nieuw rekenprofiel"}
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Annuleren</Button><Button variant="primary" onClick={() => save()}>Opslaan</Button></>}>
      <div className="grid grid-cols-3 gap-4">
        <Field label="Naam" className="col-span-2"><Input value={f.name || ""} onChange={set("name")} /></Field>
        <Field label="Voertuigcategorie"><Select value={f.vehicle_category} onChange={set("vehicle_category")}>{Object.entries(VEHICLE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
        {fld("make", "Merk")}{fld("model", "Model")}{fld("vehicle_type", "Type voertuig")}
        {fld("build_year", "Bouwjaar", "number")}{fld("engine_cc", "Cilinderinhoud (cc)", "number")}{fld("vehicle_count", "Aantal voertuigen", "number")}
        {fld("insured_value", "Verzekerde waarde (€)", "number")}{fld("valuation_value", "Taxatiewaarde (€)", "number")}{fld("postcode_area", "Postcodegebied (bijv. 35)")}
        <Field label="Leeftijdscategorie bestuurder"><Select value={f.driver_age_band || ""} onChange={set("driver_age_band")}><option value="">–</option>{["18-24", "25-29", "30-45", "45-65", "65+"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
        {fld("claim_free_years", "Schadevrije jaren", "number")}{fld("annual_km", "Kilometers per jaar", "number")}
        {fld("storage", "Stalling")}{fld("usage", "Gebruik")}
        <Field label="Gewenste dekking"><Select value={f.coverage || ""} onChange={set("coverage")}><option value="">–</option>{Object.entries(COVERAGE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
        {fld("deductible", "Eigen risico (€)", "number")}
        <Field label="Notities" className="col-span-3"><Textarea rows={2} value={f.notes || ""} onChange={set("notes")} /></Field>
      </div>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ Historie */
function HistoryView() {
  const profiles = useProfiles();
  const [pid, setPid] = React.useState<string>("");
  const { data } = useQuery({ queryKey: ["premium-history", pid], queryFn: () => api.get("/premiums/history", { profile_id: pid }) });
  const series = data?.series || [];
  const dates = [...new Set(series.flatMap((s: any) => s.points.map((p: any) => p.date)))].sort() as string[];
  const rows = dates.map((d) => {
    const r: any = { date: d };
    series.forEach((s: any) => { const pt = s.points.find((p: any) => p.date === d); if (pt) r[s.key] = pt.annual_premium; });
    return r;
  });
  return (
    <div className="space-y-5">
      <div className="flex items-end gap-3">
        <Field label="Rekenprofiel" className="w-80"><Select value={pid} onChange={(e) => setPid(e.target.value)}><option value="">Alle (ook imports zonder profiel)</option>{profiles.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
      </div>
      <Notice tone="neutral" icon={<History />}>{data?.note || "Elke lijn bevat alleen gelijkwaardige waarnemingen."}</Notice>
      <Card className="p-5">
        {series.length === 0 ? <EmptyState title="Geen historische reeksen" description="Er zijn (nog) geen premies met peildatum voor deze selectie." /> : (
          <>
            <ResponsiveContainer width="100%" height={360}>
              <LineChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="rgba(0,0,0,0.06)" />
                <XAxis dataKey="date" {...AXIS} tickFormatter={(d) => date(d)} />
                <YAxis {...AXIS} tickFormatter={(v) => `€${v}`} width={60} />
                <Tooltip content={<ChartTip formatter={(v: number) => eur(v)} />} cursor={{ stroke: "rgba(0,0,0,0.2)", strokeWidth: 1 }} labelFormatter={(d: string) => date(d)} />
                {series.slice(0, 5).map((s: any, i: number) => (
                  <Line key={s.key} dataKey={s.key} name={s.label} stroke={colorFor(i + 1)} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} activeDot={{ r: 5 }} connectNulls />
                ))}
              </LineChart>
            </ResponsiveContainer>
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-[12px] text-ink-soft">
              {series.slice(0, 5).map((s: any, i: number) => <span key={s.key} className="flex items-center gap-1.5"><span className="h-2 w-4 rounded-full" style={{ background: colorFor(i + 1) }} />{s.label}</span>)}
              {series.length > 5 && <span className="text-ink-muted">+ {series.length - 5} reeksen (kies een profiel om te filteren)</span>}
            </div>
          </>
        )}
      </Card>
      {series.length > 0 && (
        <Card className="overflow-hidden">
          <CardHeader title="Tabelweergave" />
          <table className="w-full text-[12.5px]">
            <thead><tr className="border-y border-line text-left text-[11.5px] text-ink-muted"><th className="px-5 py-2 font-medium">Reeks</th><th className="font-medium">Peildatum</th><th className="font-medium">Jaarpremie</th><th className="px-5 font-medium">Type</th></tr></thead>
            <tbody>{series.flatMap((s: any) => s.points.map((p: any) => <tr key={p.id} className="border-b border-line last:border-0"><td className="px-5 py-2">{s.label}</td><td>{date(p.date)}</td><td className="tabular">{eur(p.annual_premium)}</td><td className="px-5">{OBS_TYPE[p.type]}</td></tr>))}</tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Uitsplitsing */
function Breakdown() {
  const [dim, setDim] = React.useState<"dekking" | "categorie" | "waarde" | "kilometers">("dekking");
  const { data } = useQuery({ queryKey: ["breakdown", dim], queryFn: () => api.get("/premiums/breakdown", { dimension: dim }) });
  const groups = [...new Set((data?.rows || []).map((r: any) => r.group))] as string[];
  const providers = [...new Set((data?.rows || []).map((r: any) => r.provider))] as string[];
  const rows = groups.map((g) => {
    const o: any = { group: g };
    data.rows.filter((r: any) => r.group === g).forEach((r: any) => (o[r.provider] = r.avg_total));
    return o;
  });
  return (
    <div className="space-y-5">
      <Segmented value={dim} onChange={setDim} options={[{ value: "dekking", label: "Per dekkingsvariant" }, { value: "categorie", label: "Per voertuigcategorie" }, { value: "waarde", label: "Naar verzekerde waarde" }, { value: "kilometers", label: "Naar kilometerbundel" }]} />
      <Notice tone="caution" icon={<AlertTriangle />}>{data?.note || "Indicatief."}</Notice>
      <Card className="p-5">
        {!rows.length ? <EmptyState title="Geen actuele premies" description="Historische tarieven worden hier niet meegenomen." /> : (
          <>
            <ResponsiveContainer width="100%" height={340}>
              <BarChart data={rows} margin={{ top: 10, right: 10, left: 0 }} barGap={2}>
                <CartesianGrid vertical={false} stroke="rgba(0,0,0,0.06)" />
                <XAxis dataKey="group" {...AXIS} />
                <YAxis {...AXIS} tickFormatter={(v) => `€${v}`} width={60} />
                <Tooltip cursor={{ fill: "rgba(0,0,0,0.03)" }} content={<ChartTip formatter={(v: number) => eur(v)} />} />
                {providers.slice(0, 6).map((p, i) => <Bar key={p} dataKey={p} name={p} fill={p.toLowerCase().startsWith("vetera") ? colorFor(0, true) : colorFor(i)} radius={[4, 4, 0, 0]} maxBarSize={28} />)}
              </BarChart>
            </ResponsiveContainer>
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-[12px] text-ink-soft">
              {providers.slice(0, 6).map((p, i) => <span key={p} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: p.toLowerCase().startsWith("vetera") ? colorFor(0, true) : colorFor(i) }} />{p}</span>)}
            </div>
            <table className="mt-5 w-full text-[12.5px]">
              <thead><tr className="border-y border-line text-left text-[11.5px] text-ink-muted"><th className="py-2 font-medium">Groep</th><th className="font-medium">Aanbieder</th><th className="font-medium">Gem. totale jaarlast</th><th className="font-medium">Aantal</th></tr></thead>
              <tbody>{data.rows.map((r: any, i: number) => <tr key={i} className="border-b border-line last:border-0"><td className="py-2">{r.group}</td><td>{r.provider}</td><td className="tabular">{eur(r.avg_total)}</td><td className="tabular">{r.n}</td></tr>)}</tbody>
            </table>
          </>
        )}
      </Card>
    </div>
  );
}
