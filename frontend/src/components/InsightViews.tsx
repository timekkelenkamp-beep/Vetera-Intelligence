import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, LabelList, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { ArrowDown, ArrowUp, FlaskConical, Info, Minus, Play, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { cn, eur } from "@/lib/utils";
import { AXIS, colorFor } from "@/lib/chart";
import { FINDING_STATUS } from "@/lib/labels";
import { Badge, Button, Card, CardHeader, EmptyState, Field, Input, Loading, Notice, Select } from "./ui/primitives";

/* ------------------------------------------------------------------ Positioneringskaart */
export function PositioningView() {
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: () => api.get<any[]>("/profiles") });
  const [pid, setPid] = React.useState<number | null>(null);
  React.useEffect(() => { if (!pid && profiles.data?.length) setPid(profiles.data[0].id); }, [profiles.data, pid]);
  const { data } = useQuery({ queryKey: ["positioning", pid], queryFn: () => api.get("/insights/positioning", { profile_id: pid }), enabled: !!pid });
  const pts = (data?.points || []).map((p: any) => ({ ...p, color: colorFor(p.provider_id, p.is_reference), z: p.is_reference ? 260 : 160 }));
  const xs = pts.map((p: any) => p.premium);
  const xmin = xs.length ? Math.floor(Math.min(...xs) * 0.85 / 10) * 10 : 0;
  const xmax = xs.length ? Math.ceil(Math.max(...xs) * 1.12 / 10) * 10 : 100;

  const Dot = (props: any) => {
    const { cx, cy, payload } = props;
    const r = payload.is_reference ? 9 : 7;
    return (
      <g>
        {payload.is_reference && <circle cx={cx} cy={cy} r={r + 6} fill={payload.color} opacity={0.15} />}
        <circle cx={cx} cy={cy} r={r} fill={payload.comparable ? payload.color : "#fff"} stroke={payload.color} strokeWidth={payload.comparable ? 2 : 2.5} />
      </g>
    );
  };
  const Tip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const p = payload[0].payload;
    return (
      <div className="max-w-[260px] rounded-xl border border-line bg-white/95 px-3 py-2.5 text-[12px] shadow-lift backdrop-blur">
        <div className="font-semibold text-ink">{p.provider_name}</div>
        <div className="text-ink-muted">{p.name}</div>
        <div className="mt-1.5 flex justify-between gap-4"><span className="text-ink-muted">Totale jaarlast</span><span className="font-medium tabular">{eur(p.premium)}</span></div>
        <div className="flex justify-between gap-4"><span className="text-ink-muted">Voorwaardenscore</span><span className="font-medium tabular">{Math.round(p.conditions)} ({p.known}/{p.total_features} bekend)</span></div>
        <div className="mt-1 text-ink-soft">{p.quadrant}</div>
        {!p.comparable && <div className="mt-1 text-caution">Premie niet volledig vergelijkbaar: {p.issues.join("; ")}</div>}
      </div>
    );
  };
  const quad = (label: string, cls: string) => <div className={cn("pointer-events-none absolute text-[11px] font-semibold uppercase tracking-wide text-ink-faint/80", cls)}>{label}</div>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Rekenprofiel" className="w-80"><Select value={pid ?? ""} onChange={(e) => setPid(Number(e.target.value))}>{profiles.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
        <p className="max-w-xl pb-1 text-[12.5px] text-ink-muted">Rechtsboven: ruime voorwaarden maar duurder. Linksboven: ruim én voordelig. De hulplijnen liggen op de mediaan van de geplaatste producten.</p>
      </div>
      {!data ? <Loading /> : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_320px]">
          <Card className="p-5">
            {pts.length === 0 ? <EmptyState title="Nog geen producten te plaatsen" description="Een product verschijnt hier zodra er een premie voor dit rekenprofiel én voldoende vastgestelde voorwaarden zijn." /> : (
              <div className="relative">
                {quad("Ruim en voordelig", "left-[72px] top-3")}
                {quad("Ruim en duurder", "right-5 top-3")}
                {quad("Beperkt en voordelig", "left-[72px] bottom-12")}
                {quad("Beperkt en duurder", "right-5 bottom-12")}
                <ResponsiveContainer width="100%" height={440}>
                  <ScatterChart margin={{ top: 28, right: 30, bottom: 20, left: 10 }}>
                    <CartesianGrid stroke="rgba(0,0,0,0.05)" />
                    <XAxis type="number" dataKey="premium" name="Totale jaarlast" domain={[xmin, xmax]} {...AXIS} tickFormatter={(v) => `€${v}`} label={{ value: "Totale jaarlast →", position: "insideBottomRight", offset: -10, fontSize: 11.5, fill: "#86868b" }} />
                    <YAxis type="number" dataKey="conditions" name="Voorwaarden" domain={[0, 100]} {...AXIS} width={56} label={{ value: "Ruimte voorwaarden →", angle: -90, position: "insideLeft", fontSize: 11.5, fill: "#86868b", dy: 60 }} />
                    <ZAxis dataKey="z" range={[60, 260]} />
                    {data.median_premium && <ReferenceLine x={data.median_premium} stroke="rgba(0,0,0,0.18)" strokeDasharray="4 4" />}
                    {data.median_conditions !== null && <ReferenceLine y={data.median_conditions} stroke="rgba(0,0,0,0.18)" strokeDasharray="4 4" />}
                    <Tooltip content={<Tip />} cursor={{ strokeDasharray: "3 3" }} />
                    <Scatter data={pts} shape={<Dot />}>
                      <LabelList dataKey="provider_name" content={(lp: any) => <text x={lp.x + lp.width / 2} y={lp.y - 8} textAnchor="middle" fontSize={11.5} fontWeight={500} fill="#424245">{lp.value}</text>} />
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>
          <div className="space-y-4">
            <Card>
              <CardHeader title="Geplaatst" />
              <ul className="space-y-2 px-5 pb-4 text-[12.5px]">
                {pts.map((p: any) => (
                  <li key={p.id} className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: p.comparable ? p.color : "transparent", boxShadow: `inset 0 0 0 2px ${p.color}` }} />
                    <span className="flex-1 truncate">{p.provider_name}</span>
                    <span className="tabular text-ink-muted">{eur(p.premium, false)} · {Math.round(p.conditions)}</span>
                  </li>
                ))}
                {pts.some((p: any) => !p.comparable) && <li className="pt-1 text-[11.5px] text-ink-muted">Open bolletje: premie niet volledig vergelijkbaar.</li>}
              </ul>
            </Card>
            {data.missing.length > 0 && (
              <Card>
                <CardHeader title="Niet te plaatsen" subtitle="Ontbrekende gegevens" />
                <ul className="space-y-2 px-5 pb-4 text-[12.5px]">
                  {data.missing.map((m: any) => <li key={m.id}><div className="font-medium">{m.provider_name} · {m.name}</div><div className="text-ink-muted">{m.reasons.join(" · ")}</div></li>)}
                </ul>
              </Card>
            )}
            <Notice tone="neutral" icon={<Info />}>{data.method}</Notice>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Wat-als-simulator */
export function WhatIfView({ products }: { products: any[] }) {
  const sps = useQuery({ queryKey: ["score-profiles"], queryFn: () => api.get<any[]>("/score-profiles") });
  const feats = useQuery({ queryKey: ["features"], queryFn: () => api.get<any[]>("/features") });
  const vetera = products.filter((p) => p.is_reference);
  const [pid, setPid] = React.useState<number | null>(vetera[0]?.id ?? products[0]?.id ?? null);
  const [spId, setSpId] = React.useState<number | null>(null);
  const [changes, setChanges] = React.useState<Record<string, string>>({});
  const [premium, setPremium] = React.useState("");
  const [result, setResult] = React.useState<any>(null);
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (!spId && sps.data?.length) setSpId(sps.data[0].id); }, [sps.data, spId]);
  const findings = useQuery({ queryKey: ["findings", "product", pid], queryFn: () => api.get<any[]>("/findings", { product_id: pid }), enabled: !!pid });
  const cur = Object.fromEntries((findings.data || []).map((f) => [String(f.feature_id), f.status]));
  const statusFeats = (feats.data || []).filter((f) => f.value_type === "status" && f.scoring_aspect);
  const run = async () => {
    setBusy(true);
    try { setResult(await api.post("/insights/whatif", { score_profile_id: spId, product_id: pid, changes, premium: premium || null })); } finally { setBusy(false); }
  };
  React.useEffect(() => { setResult(null); }, [pid, spId]);
  const cats = [...new Set(statusFeats.map((f) => f.category))];

  return (
    <div className="space-y-5">
      <Notice tone="attention" icon={<FlaskConical />} title="Hypothetisch scenario">Hier verken je wat er met de scores en ranglijst gebeurt als voorwaarden of premie anders zouden zijn. Er wordt niets opgeslagen en dit is geen bestaande productvoorwaarde.</Notice>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[420px_1fr]">
        <Card className="h-fit p-5">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Product"><Select value={pid ?? ""} onChange={(e) => { setPid(Number(e.target.value)); setChanges({}); }}>{products.map((p) => <option key={p.id} value={p.id}>{p.provider_name} · {p.name}</option>)}</Select></Field>
            <Field label="Scoreprofiel"><Select value={spId ?? ""} onChange={(e) => setSpId(Number(e.target.value))}>{sps.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select></Field>
          </div>
          <Field label="Hypothetische totale jaarlast (€)" hint="Telt alleen mee als het scoreprofiel een rekenprofiel voor premie heeft." className="mt-3"><Input type="number" value={premium} onChange={(e) => setPremium(e.target.value)} placeholder="ongewijzigd" /></Field>
          <div className="mt-4 max-h-[440px] space-y-4 overflow-y-auto pr-1">
            {cats.map((c) => (
              <div key={c}>
                <div className="mb-1.5 text-[11.5px] font-semibold uppercase tracking-wide text-ink-faint">{c}</div>
                <div className="space-y-1.5">
                  {statusFeats.filter((f) => f.category === c).map((f) => {
                    const changed = changes[String(f.id)];
                    return (
                      <div key={f.id} className={cn("flex items-center gap-2 rounded-lg px-2 py-1", changed && "bg-[#f5f2ff]")}>
                        <span className="flex-1 truncate text-[12.5px]">{f.label}</span>
                        <Select value={changed || cur[String(f.id)] || ""} onChange={(e) => setChanges((ch) => { const n = { ...ch }; if (e.target.value && e.target.value !== cur[String(f.id)]) n[String(f.id)] = e.target.value; else delete n[String(f.id)]; return n; })} className={cn("h-7 w-40 text-[12px]", changed && "border-[#8b72e0]")}>
                          <option value="">{cur[String(f.id)] ? FINDING_STATUS[cur[String(f.id)]]?.short : "Geen gegevens"}</option>
                          {["gedekt", "voorwaardelijk", "aanvullende_clausule", "uitgesloten"].map((s) => <option key={s} value={s}>{FINDING_STATUS[s].short}</option>)}
                        </Select>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 flex items-center justify-between border-t border-line pt-4">
            <Button variant="ghost" size="sm" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => { setChanges({}); setPremium(""); setResult(null); }}>Herstellen</Button>
            <Button variant="primary" icon={<Play className="h-3.5 w-3.5" />} onClick={run} loading={busy} disabled={!pid || !spId}>Simuleer {Object.keys(changes).length ? `(${Object.keys(changes).length} wijzigingen)` : ""}</Button>
          </div>
        </Card>
        <div>
          {!result ? (
            <Card><EmptyState icon={<FlaskConical />} title="Pas een of meer voorwaarden aan" description="Bijvoorbeeld: wat als circuitgebruik voorwaardelijk gedekt wordt, of de premie € 20 lager is? Klik daarna op Simuleer." /></Card>
          ) : (
            <Card className="overflow-hidden">
              <CardHeader title="Huidig versus scenario" subtitle={result.changes.length ? result.changes.map((c: any) => `${c.feature} → ${c.status.toLowerCase()}`).join(" · ") : "Alleen premie gewijzigd"} />
              <table className="w-full text-[13px]">
                <thead><tr className="border-y border-line text-left text-[12px] text-ink-muted"><th className="px-5 py-2.5 font-medium">Product</th><th className="font-medium">Huidige score</th><th className="font-medium">Scenario</th><th className="px-5 font-medium">Positie</th></tr></thead>
                <tbody>
                  {result.rows.map((r: any) => {
                    const d = r.base_total !== null && r.scenario_total !== null ? r.scenario_total - r.base_total : null;
                    const move = r.base_rank && r.scenario_rank ? r.base_rank - r.scenario_rank : 0;
                    return (
                      <tr key={r.product.id} className={cn("border-b border-line last:border-0", r.is_subject && "bg-[#f5f2ff]")}>
                        <td className="px-5 py-3"><div className="font-medium">{r.product.provider_name}</div><div className="text-[12px] text-ink-muted">{r.product.name}{r.is_subject && " · scenario"}</div></td>
                        <td className="tabular">{r.base_total === null ? <span className="text-ink-faint">niet te bepalen</span> : Math.round(r.base_total)}</td>
                        <td className="tabular">
                          {r.scenario_total === null ? <span className="text-ink-faint">niet te bepalen</span> : <span className="font-semibold">{Math.round(r.scenario_total)}</span>}
                          {d !== null && Math.abs(d) >= 0.5 && <Badge tone={d > 0 ? "positive" : "negative"} className="ml-2">{d > 0 ? "+" : ""}{Math.round(d)}</Badge>}
                        </td>
                        <td className="px-5">
                          <span className="inline-flex items-center gap-1.5 tabular">
                            {r.scenario_rank ? `#${r.scenario_rank}` : "–"}
                            {move > 0 ? <ArrowUp className="h-3.5 w-3.5 text-positive" /> : move < 0 ? <ArrowDown className="h-3.5 w-3.5 text-negative" /> : <Minus className="h-3.5 w-3.5 text-ink-faint" />}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="px-5 py-3 text-[12px] text-ink-muted">{result.note} {result.dropped} Producten zonder voldoende gegevens krijgen geen totaalscore.</p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
