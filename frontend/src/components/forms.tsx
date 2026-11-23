import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { UploadCloud, FileText, CheckCircle2, XCircle, Link2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DOC_TYPE, PROVIDER_STATUS, PROVIDER_TYPE, VEHICLE } from "@/lib/labels";
import { Dialog } from "./ui/overlay";
import { Button, Field, Input, Notice, Select, Switch, Textarea } from "./ui/primitives";

export function useProviders() {
  return useQuery({ queryKey: ["providers"], queryFn: () => api.get<any[]>("/providers") });
}
export function useProducts(params?: Record<string, any>) {
  return useQuery({ queryKey: ["products", params], queryFn: () => api.get<any[]>("/products", params) });
}

export function ProviderForm({ open, onOpenChange, initial, onSaved }: { open: boolean; onOpenChange: (v: boolean) => void; initial?: any; onSaved?: (p: any) => void }) {
  const [f, setF] = React.useState<any>({});
  const [busy, setBusy] = React.useState(false);
  const qc = useQueryClient();
  React.useEffect(() => setF(initial || { provider_type: "verzekeraar", status: "actief" }), [initial, open]);
  const set = (k: string) => (e: any) => setF((x: any) => ({ ...x, [k]: e.target.value }));
  const save = async () => {
    setBusy(true);
    try {
      const r = initial?.id ? await api.patch(`/providers/${initial.id}`, f) : await api.post("/providers", f);
      qc.invalidateQueries({ queryKey: ["providers"] });
      qc.invalidateQueries({ queryKey: ["provider"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success(initial?.id ? "Aanbieder bijgewerkt" : "Aanbieder toegevoegd");
      onOpenChange(false);
      onSaved?.(r);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={initial?.id ? "Aanbieder bewerken" : "Nieuwe aanbieder"} size="lg"
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Annuleren</Button><Button variant="primary" onClick={save} loading={busy} disabled={!f.name?.trim()}>Opslaan</Button></>}>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Naam" required><Input value={f.name || ""} onChange={set("name")} autoFocus disabled={initial?.is_reference} /></Field>
        <Field label="Officiële website"><Input value={f.website || ""} onChange={set("website")} placeholder="https://" /></Field>
        <Field label="Type aanbieder">
          <Select value={f.provider_type || "onbekend"} onChange={set("provider_type")}>{Object.entries(PROVIDER_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
        </Field>
        <Field label="Status">
          <Select value={f.status || "actief"} onChange={set("status")} disabled={initial?.is_reference}>{Object.entries(PROVIDER_STATUS).filter(([k]) => k !== "samengevoegd").map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</Select>
        </Field>
        <Field label="Omschrijving" className="col-span-2"><Textarea value={f.description || ""} onChange={set("description")} rows={2} /></Field>
        <Field label="Doelgroepen" className="col-span-2"><Input value={f.target_groups || ""} onChange={set("target_groups")} placeholder="Bijv. verzamelaars, liefhebbers van klassieke motoren" /></Field>
        <Field label="Gedocumenteerde sterke punten" hint="Alleen aantoonbare punten; verwijs bij voorkeur naar bronnen."><Textarea value={f.strengths || ""} onChange={set("strengths")} rows={3} /></Field>
        <Field label="Gedocumenteerde zwakke punten" hint="Feitelijk en controleerbaar formuleren."><Textarea value={f.weaknesses || ""} onChange={set("weaknesses")} rows={3} /></Field>
        <Field label="Verificatie / notities" className="col-span-2"><Textarea value={f.verification_note || ""} onChange={set("verification_note")} rows={2} /></Field>
      </div>
    </Dialog>
  );
}

export function ProductForm({ open, onOpenChange, initial, providerId }: { open: boolean; onOpenChange: (v: boolean) => void; initial?: any; providerId?: number }) {
  const [f, setF] = React.useState<any>({});
  const [busy, setBusy] = React.useState(false);
  const qc = useQueryClient();
  const providers = useProviders();
  const products = useProducts({ include_distribution: false });
  const carriers = useQuery({ queryKey: ["carriers"], queryFn: () => api.get<any[]>("/risk-carriers"), enabled: open });
  const [newCarrier, setNewCarrier] = React.useState("");
  React.useEffect(() => setF(initial || { provider_id: providerId, vehicle_category: "auto" }), [initial, open, providerId]);
  const set = (k: string) => (e: any) => setF((x: any) => ({ ...x, [k]: e.target.value === "" ? null : e.target.value }));
  const save = async () => {
    setBusy(true);
    try {
      let body = { ...f };
      if (newCarrier.trim()) {
        const c = await api.post("/risk-carriers", { name: newCarrier.trim() });
        body.risk_carrier_id = c.id;
      }
      ["risk_carrier_id", "canonical_product_id", "provider_id"].forEach((k) => body[k] && (body[k] = Number(body[k])));
      if (initial?.id) await api.patch(`/products/${initial.id}`, body);
      else await api.post("/products", body);
      ["products", "provider", "providers", "dashboard", "product"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      toast.success("Product opgeslagen");
      setNewCarrier("");
      onOpenChange(false);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={initial?.id ? "Product bewerken" : "Nieuw product"} size="lg"
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Annuleren</Button><Button variant="primary" onClick={save} loading={busy} disabled={!f.name?.trim() || !f.provider_id}>Opslaan</Button></>}>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Aanbieder" required>
          <Select value={f.provider_id || ""} onChange={set("provider_id")}>
            <option value="">Kies…</option>
            {providers.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
        </Field>
        <Field label="Productnaam" required><Input value={f.name || ""} onChange={set("name")} /></Field>
        <Field label="Voertuigcategorie">
          <Select value={f.vehicle_category || "auto"} onChange={set("vehicle_category")}>{Object.entries(VEHICLE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
        </Field>
        <Field label="Productpagina"><Input value={f.url || ""} onChange={set("url")} placeholder="https://" /></Field>
        <Field label="Risicodrager">
          <Select value={f.risk_carrier_id || ""} onChange={set("risk_carrier_id")}>
            <option value="">Onbekend</option>
            {carriers.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
        <Field label="…of nieuwe risicodrager"><Input value={newCarrier} onChange={(e) => setNewCarrier(e.target.value)} placeholder="Naam risicodrager" /></Field>
        <Field label="Distributie van ander product" className="col-span-2" hint="Kies dit als hetzelfde product via een andere partij wordt aangeboden. Het telt dan niet dubbel als concurrentieproduct.">
          <Select value={f.canonical_product_id || ""} onChange={set("canonical_product_id")}>
            <option value="">Zelfstandig product</option>
            {products.data?.filter((p) => p.id !== initial?.id).map((p) => <option key={p.id} value={p.id}>{p.provider_name} – {p.name}</option>)}
          </Select>
        </Field>
        <Field label="Omschrijving" className="col-span-2"><Textarea value={f.description || ""} onChange={set("description")} rows={2} /></Field>
      </div>
    </Dialog>
  );
}

export function UploadDialog({ open, onOpenChange, providerId, productId, documentId, onDone }: { open: boolean; onOpenChange: (v: boolean) => void; providerId?: number; productId?: number; documentId?: number; onDone?: (r: any[]) => void }) {
  const [files, setFiles] = React.useState<File[]>([]);
  const [meta, setMeta] = React.useState<any>({});
  const [busy, setBusy] = React.useState(false);
  const [results, setResults] = React.useState<any[] | null>(null);
  const [drag, setDrag] = React.useState(false);
  const [url, setUrl] = React.useState("");
  const providers = useProviders();
  const products = useProducts(meta.provider_id ? { provider_id: meta.provider_id } : undefined);
  const qc = useQueryClient();
  React.useEffect(() => {
    if (open) {
      setFiles([]);
      setResults(null);
      setUrl("");
      setMeta({ provider_id: providerId || "", product_id: productId || "", document_type: "", visibility: "publiek", use_ocr: true });
    }
  }, [open, providerId, productId]);
  const pick = (list: FileList | null) => list && setFiles((f) => [...f, ...Array.from(list).filter((x) => x.name.toLowerCase().endsWith(".pdf"))]);
  const refresh = () => ["documents", "provider", "dashboard", "sources", "document"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const upload = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      Object.entries(meta).forEach(([k, v]) => v !== "" && v !== undefined && fd.append(k, String(v)));
      if (documentId) fd.append("document_id", String(documentId));
      const r = await api.upload<any[]>("/documents/upload", fd);
      setResults(r);
      refresh();
      onDone?.(r);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  const fetchUrl = async () => {
    setBusy(true);
    try {
      const r = await api.post("/documents/fetch-url", { url, provider_id: meta.provider_id || null, product_id: meta.product_id || null, document_type: meta.document_type || null, monitor: true });
      setResults([{ filename: url, ok: r.version.status === "gereed", document: r.document, version: r.version, info: r.info }]);
      refresh();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="lg" title={documentId ? "Nieuwe documentversie" : "Documenten importeren"}
      description={documentId ? "De huidige versie blijft bewaard; de nieuwe versie wordt automatisch vergeleken." : "PDF-polisvoorwaarden, verzekeringskaarten, clausules en productinformatie."}
      footer={results ? <Button variant="primary" onClick={() => onOpenChange(false)}>Gereed</Button> : <><Button variant="ghost" onClick={() => onOpenChange(false)}>Annuleren</Button><Button variant="primary" onClick={upload} loading={busy} disabled={!files.length}>Importeren ({files.length})</Button></>}>
      {results ? (
        <ul className="space-y-2">
          {results.map((r, i) => (
            <li key={i} className={cn("rounded-xl border p-3 text-[13px]", r.ok ? "border-line" : "border-negative/30 bg-negative-soft/40")}>
              <div className="flex items-center gap-2 font-medium">{r.ok ? <CheckCircle2 className="h-4 w-4 text-positive" /> : <XCircle className="h-4 w-4 text-negative" />}{r.filename}</div>
              {r.ok ? (
                <div className="mt-1 text-[12.5px] text-ink-muted">
                  {r.version.page_count} pagina's · {r.version.clause_count} clausules herkend · extractie {r.version.extraction_quality}
                  {r.info?.identificatie && <> · herkend als {DOC_TYPE[r.info.identificatie.document_type] || r.info.identificatie.document_type}{r.info.identificatie.provider_candidates?.[0] && ` van ${r.info.identificatie.provider_candidates[0].name}`}</>}
                  {r.info?.diff_summary && <> · {r.info.diff_summary.aantal_wijzigingen} wijzigingen t.o.v. vorige versie</>}
                  {r.version.unreliable_pages?.length > 0 && <div className="mt-1 text-caution">Onbetrouwbare tekst op pagina {r.version.unreliable_pages.join(", ")} (mogelijk gescand).</div>}
                </div>
              ) : (
                <div className="mt-1 text-[12.5px] text-negative">{r.error}</div>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <>
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files); }}
            className={cn("flex flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-8 text-center transition-colors", drag ? "border-accent bg-accent-soft" : "border-line-strong bg-surface/50")}
          >
            <UploadCloud className="h-7 w-7 text-ink-faint" />
            <div className="mt-2 text-[14px] font-medium">Sleep PDF-bestanden hierheen</div>
            <label className="mt-1 cursor-pointer text-[13px] text-accent hover:underline">
              of kies bestanden
              <input type="file" accept="application/pdf,.pdf" multiple={!documentId} className="hidden" onChange={(e) => pick(e.target.files)} />
            </label>
          </div>
          {files.length > 0 && (
            <ul className="mt-3 space-y-1">
              {files.map((f, i) => (
                <li key={i} className="flex items-center justify-between rounded-lg bg-surface px-3 py-1.5 text-[12.5px]">
                  <span className="flex items-center gap-2 truncate"><FileText className="h-3.5 w-3.5 text-ink-muted" /> {f.name}</span>
                  <span className="text-ink-muted tabular">{(f.size / 1024 / 1024).toFixed(1)} MB</span>
                </li>
              ))}
            </ul>
          )}
          {!documentId && (
            <div className="mt-5 grid grid-cols-2 gap-4">
              <Field label="Aanbieder" hint="Leeg laten: automatisch herkennen">
                <Select value={meta.provider_id} onChange={(e) => setMeta((m: any) => ({ ...m, provider_id: e.target.value, product_id: "" }))}>
                  <option value="">Automatisch herkennen</option>
                  {providers.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </Select>
              </Field>
              <Field label="Product">
                <Select value={meta.product_id} onChange={(e) => setMeta((m: any) => ({ ...m, product_id: e.target.value }))} disabled={!meta.provider_id}>
                  <option value="">Nog niet koppelen</option>
                  {products.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </Select>
              </Field>
              <Field label="Documenttype">
                <Select value={meta.document_type} onChange={(e) => setMeta((m: any) => ({ ...m, document_type: e.target.value }))}>
                  <option value="">Automatisch herkennen</option>
                  {Object.entries(DOC_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </Select>
              </Field>
              <Field label="Zichtbaarheid" hint="Niet-publieke documenten worden nooit zonder toestemming naar AI gestuurd.">
                <Select value={meta.visibility} onChange={(e) => setMeta((m: any) => ({ ...m, visibility: e.target.value }))}>
                  <option value="publiek">Openbaar gepubliceerd</option>
                  <option value="niet_publiek">Niet-publiek / intern</option>
                </Select>
              </Field>
              <div className="col-span-2"><Switch checked={!!meta.use_ocr} onCheckedChange={(v) => setMeta((m: any) => ({ ...m, use_ocr: v }))} label="OCR gebruiken voor gescande pagina's" description="Alleen als Tesseract lokaal is geïnstalleerd; anders worden zulke pagina's als onbetrouwbaar gemarkeerd." /></div>
            </div>
          )}
          {!documentId && (
            <div className="mt-5 rounded-xl border border-line p-4">
              <div className="mb-2 flex items-center gap-2 text-[13px] font-medium"><Link2 className="h-3.5 w-3.5" /> Openbare PDF ophalen via URL</div>
              <div className="flex gap-2">
                <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.aanbieder.nl/polisvoorwaarden.pdf" />
                <Button onClick={fetchUrl} loading={busy} disabled={!url.startsWith("http")}>Ophalen</Button>
              </div>
              <p className="mt-2 text-[11.5px] text-ink-muted">robots.txt wordt gerespecteerd; de bron wordt aan het bronregister toegevoegd voor de wekelijkse controle.</p>
            </div>
          )}
          {documentId && <Notice tone="info" className="mt-4">Een identiek bestand wordt herkend en niet opnieuw opgeslagen.</Notice>}
        </>
      )}
    </Dialog>
  );
}
