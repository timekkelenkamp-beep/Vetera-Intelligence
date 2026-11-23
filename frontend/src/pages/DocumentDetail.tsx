import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Upload, Sparkles, ScanSearch, RefreshCw, Trash2, Eye, GitCompare, AlertTriangle, Lock } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { date } from "@/lib/utils";
import { DOC_TYPE } from "@/lib/labels";
import { useAiAction } from "@/components/AiAction";
import { useSourceViewer } from "@/components/SourceViewer";
import { UploadDialog, useProducts, useProviders } from "@/components/forms";
import { DiffDialog } from "./MarketMonitor";
import { Badge, Button, Card, CardHeader, Field, Input, KeyValue, Loading, Notice, Select } from "@/components/ui/primitives";

export default function DocumentDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const viewer = useSourceViewer();
  const { data: d, refetch } = useQuery({ queryKey: ["document", id], queryFn: () => api.get(`/documents/${id}`) });
  const providers = useProviders();
  const products = useProducts(d?.provider_id ? { provider_id: d.provider_id } : undefined);
  const [upload, setUpload] = React.useState(false);
  const [diff, setDiff] = React.useState<number | null>(null);
  const [cmp, setCmp] = React.useState<{ a?: number; b?: number }>({});
  const cv = d?.current_version;
  const clauses = useQuery({ queryKey: ["clauses", cv?.id], queryFn: () => api.get<any[]>(`/document-versions/${cv.id}/clauses`), enabled: !!cv });
  const extract = useAiAction("/ai/extract", { invalidate: [["matrix"], ["findings"], ["quality"]], onDone: (r: any) => toast.success(`${r.created} bevindingen vastgelegd ter beoordeling`, { description: `${r.skipped_locked} menselijke beoordelingen ongemoeid gelaten · ${r.downgraded} omgezet naar ‘menselijke beoordeling’ · ${r.unverified_quotes} niet-verifieerbare citaten` }) });
  if (!d) return <Loading />;

  const update = async (body: any) => {
    try { await api.patch(`/documents/${d.id}`, body); refetch(); qc.invalidateQueries({ queryKey: ["documents"] }); } catch (e: any) { toast.error(e.message); }
  };
  const local = async () => {
    try {
      const r = await api.post(`/document-versions/${cv.id}/local-findings`, {});
      toast.success(`${r.aangemaakt} kandidaatbevindingen aangemaakt`, { description: `${r.overgeslagen_bestaand} bestaande bevindingen ongemoeid gelaten. Controleer ze in de vergelijker.` });
      ["matrix", "findings"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    } catch (e: any) { toast.error(e.message); }
  };
  const reprocess = async () => { await api.post(`/document-versions/${cv.id}/reprocess`); refetch(); toast.success("Opnieuw verwerkt"); };
  const del = async () => { if (!confirm("Document met alle versies verwijderen?")) return; await api.del(`/documents/${d.id}`); qc.invalidateQueries({ queryKey: ["documents"] }); nav("/bronnen"); };
  const compare = async () => {
    try { const r = await api.post(`/documents/${d.id}/compare`, { old_version_id: cmp.a, new_version_id: cmp.b }); setDiff(r.id); refetch(); } catch (e: any) { toast.error(e.message); }
  };
  const ident = d.identification;

  return (
    <div>
      <button onClick={() => nav("/bronnen")} className="mb-5 inline-flex items-center gap-1 text-[13px] text-ink-muted hover:text-ink"><ArrowLeft className="h-3.5 w-3.5" /> Bronnen & documenten</button>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-semibold tracking-tightest">{d.title}</h1>
          <div className="mt-1 flex items-center gap-2 text-[13px] text-ink-muted">{DOC_TYPE[d.document_type]} · {d.provider_name || "aanbieder onbekend"} · {d.version_count} versie(s){d.visibility === "niet_publiek" && <Badge tone="caution"><Lock className="h-3 w-3" /> Niet-publiek</Badge>}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          {cv && <Button icon={<Eye className="h-4 w-4" />} onClick={() => viewer.open({ versionId: cv.id, page: 1 })}>Bekijken</Button>}
          <Button icon={<Upload className="h-4 w-4" />} onClick={() => setUpload(true)}>Nieuwe versie</Button>
          {cv && <Button icon={<ScanSearch className="h-4 w-4" />} onClick={local} disabled={!d.product_id}>Passages zoeken</Button>}
          {cv && <Button variant="primary" icon={<Sparkles className="h-4 w-4" />} loading={extract.busy} disabled={!d.product_id} onClick={() => extract.start({ version_id: cv.id, product_id: d.product_id })}>Analyseer met AI</Button>}
        </div>
      </div>
      {!d.product_id && <Notice tone="caution" icon={<AlertTriangle />} className="mb-6">Koppel dit document aan een product om bevindingen vast te leggen.</Notice>}
      {cv?.extraction_quality === "onbetrouwbaar" && <Notice tone="negative" icon={<AlertTriangle />} className="mb-6" title="Onbetrouwbare tekstextractie">Pagina {cv.unreliable_pages.join(", ")} bevat weinig of onleesbare tekst (mogelijk gescand). Installeer OCR (Tesseract) en verwerk opnieuw, of controleer citaten handmatig.</Notice>}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_380px]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Clausules en artikelen" subtitle={`${clauses.data?.length ?? 0} herkend in de huidige versie`} />
            <div className="max-h-[640px] overflow-y-auto">
              {clauses.data?.length === 0 && <p className="px-5 pb-5 text-[13px] text-ink-muted">Geen artikelstructuur herkend. De tekst is wel per pagina doorzoekbaar.</p>}
              <ul className="divide-y divide-line">
                {clauses.data?.map((c) => (
                  <li key={c.id}>
                    <button onClick={() => viewer.open({ versionId: cv.id, page: c.page_number, quote: c.text.slice(0, 160) })} className="w-full px-5 py-3 text-left hover:bg-surface/50">
                      <div className="flex items-baseline justify-between gap-3"><span className="text-[13px] font-medium">{c.article ? `Art. ${c.article} ` : ""}{c.heading}</span><span className="shrink-0 text-[11.5px] text-ink-faint">p. {c.page_number}</span></div>
                      <p className="mt-0.5 line-clamp-2 text-[12.5px] text-ink-muted">{c.text}</p>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </Card>
        </div>
        <div className="space-y-6">
          <Card className="space-y-3 p-5">
            <Field label="Titel"><Input defaultValue={d.title} key={d.title} onBlur={(e) => e.target.value !== d.title && update({ title: e.target.value })} /></Field>
            <Field label="Aanbieder"><Select value={d.provider_id || ""} onChange={(e) => update({ provider_id: e.target.value ? Number(e.target.value) : null, product_id: null })}><option value="">–</option>{providers.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
            <Field label="Product"><Select value={d.product_id || ""} onChange={(e) => update({ product_id: e.target.value ? Number(e.target.value) : null, provider_id: d.provider_id })} disabled={!d.provider_id}><option value="">–</option>{products.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
            <Field label="Documenttype"><Select value={d.document_type} onChange={(e) => update({ document_type: e.target.value })}>{Object.entries(DOC_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
            <Field label="Zichtbaarheid"><Select value={d.visibility} onChange={(e) => update({ visibility: e.target.value })}><option value="publiek">Openbaar gepubliceerd</option><option value="niet_publiek">Niet-publiek</option></Select></Field>
          </Card>
          {ident && (
            <Card className="p-5 text-[12.5px]">
              <div className="mb-2 text-[13px] font-semibold">Automatische herkenning</div>
              <KeyValue items={[
                { label: "Aanbieder", value: ident.provider_candidates?.map((p: any) => p.name).join(", ") || "niet herkend" },
                { label: "Product", value: ident.product_candidates?.map((p: any) => p.name).join(", ") || "niet herkend" },
                { label: "Type", value: DOC_TYPE[ident.document_type] },
                { label: "Datum", value: ident.doc_date ? date(ident.doc_date) : "niet gevonden" },
                { label: "Versie", value: ident.version_label || "niet gevonden" },
                { label: "Voertuig", value: ident.vehicle_category || "–" },
              ]} />
            </Card>
          )}
          <Card>
            <CardHeader title="Versies" subtitle="Oude versies blijven altijd bewaard" />
            <ul className="divide-y divide-line">
              {d.versions.map((v: any) => (
                <li key={v.id} className="px-5 py-3 text-[12.5px]">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{v.version_label || v.original_filename}</span>
                    <div className="flex items-center gap-1">{v.id === d.current_version_id && <Badge tone="accent">Actueel</Badge>}<Button size="sm" variant="ghost" onClick={() => viewer.open({ versionId: v.id, page: 1 })}>Open</Button></div>
                  </div>
                  <div className="text-ink-muted">{v.doc_date ? `Documentdatum ${date(v.doc_date)} · ` : ""}geïmporteerd {date(v.imported_at, true)} · {v.page_count} p. · {v.extraction_quality}{v.ocr_used ? " · OCR" : ""}</div>
                  <div className="truncate text-[11px] text-ink-faint">sha256 {v.sha256.slice(0, 16)}… {v.source_url && `· ${v.source_url}`}</div>
                  {v.status === "fout" && <div className="text-negative">{v.error}</div>}
                </li>
              ))}
            </ul>
            {d.versions.length > 1 && (
              <div className="flex items-end gap-2 border-t border-line p-4">
                <Select value={cmp.a || ""} onChange={(e) => setCmp({ ...cmp, a: Number(e.target.value) })} className="h-8 text-[12px]"><option value="">Oud…</option>{d.versions.map((v: any) => <option key={v.id} value={v.id}>{v.version_label || `#${v.id}`}</option>)}</Select>
                <Select value={cmp.b || ""} onChange={(e) => setCmp({ ...cmp, b: Number(e.target.value) })} className="h-8 text-[12px]"><option value="">Nieuw…</option>{d.versions.map((v: any) => <option key={v.id} value={v.id}>{v.version_label || `#${v.id}`}</option>)}</Select>
                <Button size="sm" icon={<GitCompare className="h-3.5 w-3.5" />} onClick={compare} disabled={!cmp.a || !cmp.b || cmp.a === cmp.b}>Vergelijk</Button>
              </div>
            )}
          </Card>
          {d.diffs.length > 0 && (
            <Card>
              <CardHeader title="Wijzigingen tussen versies" />
              <ul className="divide-y divide-line">
                {d.diffs.map((x: any) => <li key={x.id}><button onClick={() => setDiff(x.id)} className="w-full px-5 py-2.5 text-left text-[12.5px] hover:bg-surface/50"><span className="font-medium">{date(x.created_at, true)}</span> · {x.summary?.aantal_wijzigingen} wijzigingen</button></li>)}
              </ul>
            </Card>
          )}
          <div className="flex gap-2">
            {cv && <Button size="sm" variant="ghost" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={reprocess}>Opnieuw verwerken</Button>}
            <Button size="sm" variant="ghost" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={del}>Verwijderen</Button>
          </div>
        </div>
      </div>
      <UploadDialog open={upload} onOpenChange={setUpload} documentId={d.id} onDone={() => refetch()} />
      {diff && <DiffDialog id={diff} onClose={() => setDiff(null)} />}
      {extract.dialog}
    </div>
  );
}
