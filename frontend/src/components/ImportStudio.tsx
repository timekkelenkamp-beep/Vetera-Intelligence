import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, UploadCloud, CheckCircle2, AlertTriangle, XCircle, Undo2, ArrowRight, ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, date } from "@/lib/utils";
import { Badge, Button, Card, CardHeader, EmptyState, Field, Input, Notice, Select, Switch } from "./ui/primitives";

const STEPS = ["Bestand", "Koppelen", "Controleren", "Importeren"];

export function ImportStudio() {
  const qc = useQueryClient();
  const [step, setStep] = React.useState(0);
  const [imp, setImp] = React.useState<any>(null);
  const [preview, setPreview] = React.useState<any>(null);
  const [mapping, setMapping] = React.useState<Record<string, string | null>>({});
  const [defaults, setDefaults] = React.useState<any>({});
  const [treatAs, setTreatAs] = React.useState("historisch");
  const [validation, setValidation] = React.useState<any>(null);
  const [skipDup, setSkipDup] = React.useState(true);
  const [tmplName, setTmplName] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [warning, setWarning] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<any>(null);
  const fields = useQuery({ queryKey: ["import-fields"], queryFn: () => api.get<any[]>("/imports/fields") });
  const templates = useQuery({ queryKey: ["import-templates"], queryFn: () => api.get<any[]>("/import-templates") });
  const history = useQuery({ queryKey: ["imports"], queryFn: () => api.get<any[]>("/imports") });

  const reset = () => { setStep(0); setImp(null); setPreview(null); setValidation(null); setResult(null); setWarning(null); };
  const applyPreview = (r: any) => {
    setImp(r.import);
    setPreview(r.preview);
    setMapping(Object.fromEntries(Object.entries(r.preview.mapping).map(([k, v]: any) => [k, v.field])));
  };
  const upload = async (file: File) => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("visibility", "niet_publiek");
      const r = await api.upload("/imports/upload", fd);
      applyPreview(r);
      setWarning(r.warning);
      setStep(1);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  const repreview = async (body: any) => {
    try { applyPreview(await api.post(`/imports/${imp.id}/preview`, body)); } catch (e: any) { toast.error(e.message); }
  };
  const validate = async () => {
    setBusy(true);
    try {
      setValidation(await api.post(`/imports/${imp.id}/validate`, { mapping, defaults, treat_as: treatAs }));
      setStep(2);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  const commit = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/imports/${imp.id}/commit`, { skip_duplicates: skipDup, save_template: tmplName || undefined });
      setResult(r);
      setStep(3);
      ["premiums", "imports", "dashboard", "premium-history", "import-templates"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  const applyTemplate = async (id: string) => {
    if (!id) return;
    const r = await api.post(`/imports/${imp.id}/apply-template`, { template_id: Number(id) });
    setMapping(r.mapping);
    toast.success("Sjabloon toegepast");
  };
  const rollback = async (id: number) => {
    if (!confirm("Alle premies uit deze import verwijderen?")) return;
    const r = await api.post(`/imports/${id}/rollback`);
    toast.success(`${r.removed} premies verwijderd`);
    ["premiums", "imports", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  };
  const used = Object.values(mapping).filter(Boolean);
  const missingReq = (fields.data || []).filter((f) => f.required && !used.includes(f.field));

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        {STEPS.map((s, i) => (
          <React.Fragment key={s}>
            <div className={cn("flex items-center gap-2 text-[13px]", i === step ? "font-semibold text-ink" : i < step ? "text-accent" : "text-ink-faint")}>
              <span className={cn("flex h-6 w-6 items-center justify-center rounded-full text-[11.5px] font-semibold", i < step ? "bg-accent text-white" : i === step ? "bg-ink text-white" : "bg-surface text-ink-muted")}>{i < step ? "✓" : i + 1}</span>
              {s}
            </div>
            {i < STEPS.length - 1 && <div className="h-px w-10 bg-line" />}
          </React.Fragment>
        ))}
      </div>

      {step === 0 && (
        <Card className="p-8">
          <label className="flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-line-strong bg-surface/50 px-6 py-12 text-center hover:border-accent/50">
            <UploadCloud className="h-8 w-8 text-ink-faint" />
            <div className="mt-3 text-[15px] font-medium">Kies een Excel- of CSV-bestand</div>
            <div className="mt-1 text-[13px] text-ink-muted">XLSX, XLS of CSV · meerdere werkbladen · elke kolomindeling</div>
            <input type="file" accept=".xlsx,.xlsm,.xls,.csv" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} disabled={busy} />
          </label>
          <p className="mt-4 text-center text-[12px] text-ink-muted">Het originele bestand wordt lokaal bewaard en standaard als niet-publiek gemarkeerd (niet naar AI).</p>
        </Card>
      )}

      {step === 1 && preview && (
        <>
          {warning && <Notice tone="caution" icon={<AlertTriangle />}>{warning}</Notice>}
          <Card className="p-5">
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Werkblad" className="w-56"><Select value={preview.sheet} onChange={(e) => repreview({ sheet: e.target.value })}>{preview.sheets.map((s: string) => <option key={s}>{s}</option>)}</Select></Field>
              <Field label="Kopregel (rij)" className="w-32"><Input type="number" min={1} defaultValue={preview.header_row} key={preview.sheet + preview.header_row} onBlur={(e) => Number(e.target.value) !== preview.header_row && repreview({ sheet: preview.sheet, header_row: Number(e.target.value) })} /></Field>
              {!!templates.data?.length && <Field label="Koppelsjabloon" className="w-56"><Select defaultValue="" onChange={(e) => applyTemplate(e.target.value)}><option value="">Kies sjabloon…</option>{templates.data.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field>}
              <div className="ml-auto text-[12.5px] text-ink-muted">{preview.row_count} gegevensrijen · {imp.filename}</div>
            </div>
          </Card>
          <Card className="overflow-hidden">
            <CardHeader title="Kolommen koppelen" subtitle="Automatisch herkend waar mogelijk. Controleer elke koppeling; niet-gekoppelde kolommen worden genegeerd." />
            <div className="overflow-x-auto">
              <table className="w-full text-[12.5px]">
                <thead>
                  <tr className="border-y border-line bg-surface/50">
                    {preview.headers.map((h: string, i: number) => (
                      <th key={i} className="min-w-[160px] px-3 py-2.5 text-left align-top font-normal">
                        <div className="mb-1.5 truncate font-semibold text-ink" title={h}>{h}</div>
                        <Select value={mapping[String(i)] || ""} onChange={(e) => setMapping((m) => ({ ...m, [String(i)]: e.target.value || null }))} className={cn("h-8 text-[12px]", mapping[String(i)] && "border-accent/40 bg-accent-soft/30")}>
                          <option value="">Niet importeren</option>
                          {fields.data?.map((f) => <option key={f.field} value={f.field} disabled={used.includes(f.field) && mapping[String(i)] !== f.field}>{f.label}{f.required ? " *" : ""}</option>)}
                        </Select>
                        {preview.mapping[String(i)]?.confidence > 0 && mapping[String(i)] === preview.mapping[String(i)].field && <div className="mt-1 text-[11px] text-ink-muted">automatisch ({Math.round(preview.mapping[String(i)].confidence * 100)}%)</div>}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.slice(0, 10).map((r: any[], ri: number) => (
                    <tr key={ri} className="border-b border-line last:border-0">{r.map((c, ci) => <td key={ci} className={cn("px-3 py-1.5 truncate max-w-[220px]", !mapping[String(ci)] && "text-ink-faint")}>{c === null ? "" : String(c)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card className="p-5">
            <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
              <Field label="Behandel geïmporteerde tarieven als" hint="Oude tarieven worden nooit automatisch als actueel aangemerkt.">
                <Select value={treatAs} onChange={(e) => setTreatAs(e.target.value)}><option value="historisch">Historisch tarief (aanbevolen)</option><option value="actueel">Actuele, handmatig ingevoerde offertes</option></Select>
              </Field>
              <Field label="Standaard onderzoeksdatum" hint="Voor rijen zonder datum"><Input type="date" value={defaults.reference_date || ""} onChange={(e) => setDefaults({ ...defaults, reference_date: e.target.value })} /></Field>
              <Field label="Standaard voertuigcategorie"><Select value={defaults.vehicle_category || ""} onChange={(e) => setDefaults({ ...defaults, vehicle_category: e.target.value })}><option value="">–</option><option value="auto">Auto</option><option value="motor">Motorfiets</option><option value="bromfiets">Bromfiets</option></Select></Field>
            </div>
            {missingReq.length > 0 && <Notice tone="caution" className="mt-4" icon={<AlertTriangle />}>Koppel de verplichte velden: {missingReq.map((f) => f.label).join(", ")}.</Notice>}
          </Card>
          <div className="flex justify-between">
            <Button variant="ghost" icon={<ArrowLeft className="h-4 w-4" />} onClick={reset}>Ander bestand</Button>
            <Button variant="primary" onClick={validate} loading={busy} disabled={missingReq.length > 0}>Controleren <ArrowRight className="h-4 w-4" /></Button>
          </div>
        </>
      )}

      {step === 2 && validation && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Card className="p-4"><div className="text-[12px] text-ink-muted">Rijen</div><div className="text-[24px] font-semibold tabular">{validation.total}</div></Card>
            <Card className="p-4"><div className="text-[12px] text-ink-muted">Geldig</div><div className="text-[24px] font-semibold tabular text-positive">{validation.valid}</div></Card>
            <Card className="p-4"><div className="text-[12px] text-ink-muted">Fouten</div><div className="text-[24px] font-semibold tabular text-negative">{validation.invalid}</div></Card>
            <Card className="p-4"><div className="text-[12px] text-ink-muted">Duplicaten</div><div className="text-[24px] font-semibold tabular text-caution">{validation.duplicates}</div></Card>
          </div>
          <Card className="overflow-hidden">
            <CardHeader title="Importresultaat ter goedkeuring" subtitle="Rijen met fouten worden niet geïmporteerd. Er wordt nog niets opgeslagen." />
            <div className="max-h-[480px] overflow-auto">
              <table className="w-full text-[12.5px]">
                <thead className="sticky top-0 bg-white"><tr className="border-y border-line text-left text-[11.5px] text-ink-muted"><th className="px-4 py-2 font-medium">Rij</th><th className="font-medium">Verzekeraar</th><th className="font-medium">Product</th><th className="font-medium">Voertuig</th><th className="font-medium">Dekking</th><th className="font-medium">Premie</th><th className="font-medium">Datum</th><th className="px-4 font-medium">Status</th></tr></thead>
                <tbody>
                  {validation.rows.map((r: any) => (
                    <tr key={r.row} className={cn("border-b border-line align-top", r.errors.length && "bg-negative-soft/30")}>
                      <td className="px-4 py-2 tabular text-ink-muted">{r.row}</td>
                      <td className="py-2">{r.values.provider || "–"}{r.provider_id && <CheckCircle2 className="ml-1 inline h-3 w-3 text-positive" />}</td>
                      <td>{r.values.product || "–"}</td>
                      <td>{[r.values.vehicle, r.values.build_year].filter(Boolean).join(" · ") || "–"}</td>
                      <td>{r.values.coverage_variant || "–"}</td>
                      <td className="tabular">{r.values.amount ?? "–"}</td>
                      <td>{r.values.reference_date ? date(r.values.reference_date) : "–"}</td>
                      <td className="px-4 py-2">
                        {r.errors.map((e: string) => <div key={e} className="flex items-start gap-1 text-negative"><XCircle className="mt-0.5 h-3 w-3 shrink-0" />{e}</div>)}
                        {r.warnings.map((e: string) => <div key={e} className="flex items-start gap-1 text-caution"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />{e}</div>)}
                        {!r.errors.length && !r.warnings.length && <span className="text-positive">OK</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card className="p-5">
            <div className="grid grid-cols-1 items-end gap-5 md:grid-cols-2">
              <Switch checked={skipDup} onCheckedChange={setSkipDup} label="Duplicaten overslaan" description="Rijen die al in dit bestand of in de database voorkomen." />
              <Field label="Koppeling bewaren als sjabloon (optioneel)"><Input value={tmplName} onChange={(e) => setTmplName(e.target.value)} placeholder="Bijv. Premieonderzoek 2023" /></Field>
            </div>
          </Card>
          <div className="flex justify-between">
            <Button variant="ghost" icon={<ArrowLeft className="h-4 w-4" />} onClick={() => setStep(1)}>Koppeling aanpassen</Button>
            <Button variant="primary" onClick={commit} loading={busy} disabled={validation.valid === 0}>Goedkeuren en {validation.rows.filter((r: any) => !r.errors.length && !(skipDup && r.duplicate)).length} rijen importeren</Button>
          </div>
        </>
      )}

      {step === 3 && result && (
        <Card className="p-8 text-center">
          <CheckCircle2 className="mx-auto h-10 w-10 text-positive" />
          <div className="mt-3 text-[17px] font-semibold">{result.imported} premies geïmporteerd</div>
          <p className="mt-1 text-[13px] text-ink-muted">{treatAs === "historisch" ? "Gemarkeerd als historische tarieven." : "Gemarkeerd als handmatig ingevoerde offertes."} {result.invalid} rijen met fouten overgeslagen.</p>
          <Button className="mt-5" onClick={reset}>Nieuwe import</Button>
        </Card>
      )}

      <Card>
        <CardHeader title="Eerdere imports" />
        {!history.data?.length ? <EmptyState icon={<FileSpreadsheet />} title="Nog geen imports" /> : (
          <ul className="divide-y divide-line">
            {history.data.map((h) => (
              <li key={h.id} className="flex items-center justify-between gap-4 px-5 py-3 text-[13px]">
                <div><div className="font-medium">{h.filename}</div><div className="text-[12px] text-ink-muted">{date(h.created_at, true)} · werkblad {h.sheet} · {h.imported_count} geïmporteerd</div></div>
                <div className="flex items-center gap-2">
                  <Badge tone={h.status === "geimporteerd" ? "positive" : h.status === "teruggedraaid" ? "neutral" : "info"}>{h.status}</Badge>
                  {h.status === "geimporteerd" && <Button size="sm" variant="ghost" icon={<Undo2 className="h-3.5 w-3.5" />} onClick={() => rollback(h.id)}>Terugdraaien</Button>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
