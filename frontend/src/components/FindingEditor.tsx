import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Pencil, XCircle, Search, History, Lock, Unlock } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { date } from "@/lib/utils";
import { COVERAGE, COVERAGE_LEVELS, FINDING_STATUS } from "@/lib/labels";
import { Dialog } from "./ui/overlay";
import { Badge, Button, Field, Input, Notice, Select, Textarea } from "./ui/primitives";
import { FindingStatus, OriginBadge, SourceRef, VerifiedMark } from "./common";

/** Bekijk, beoordeel en corrigeer één kenmerk van één product. Menselijke invoer wordt vergrendeld. */
export function FindingEditor({ open, onOpenChange, product, feature, finding, level }: { open: boolean; onOpenChange: (v: boolean) => void; product: any; feature: any; finding?: any; level?: string }) {
  const qc = useQueryClient();
  const [mode, setMode] = React.useState<"view" | "edit">("view");
  const [f, setF] = React.useState<any>({});
  const [busy, setBusy] = React.useState(false);
  const docs = useQuery({ queryKey: ["documents", "product", product?.id], queryFn: () => api.get<any[]>("/documents", { product_id: product.id }), enabled: open && !!product });
  const hist = useQuery({ queryKey: ["finding-hist", finding?.id], queryFn: () => api.get<any[]>(`/findings/${finding.id}/history`), enabled: open && !!finding?.id });
  const [passages, setPassages] = React.useState<any[] | null>(null);
  React.useEffect(() => {
    if (open) {
      setMode(finding ? "view" : "edit");
      setPassages(null);
      setF(finding ? { coverage_level: finding.coverage_level || "", status: finding.status, value_text: finding.value_text || "", value_number: finding.value_number ?? "", explanation: finding.explanation || "", document_version_id: finding.document_version_id || "", page_number: finding.page_number || "", article: finding.article || "", quote: finding.quote || "" } : { status: "gedekt", document_version_id: "", coverage_level: level || "" });
    }
  }, [open, finding]);
  const refresh = () => ["matrix", "findings", "product", "cards", "finding-hist", "provider"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const versionOptions = (docs.data || []).filter((d) => d.current_version).map((d) => ({ id: d.current_version.id, label: `${d.title} (${d.current_version.version_label || "huidige versie"})` }));
  React.useEffect(() => {
    if (open && !finding && versionOptions.length === 1 && !f.document_version_id) setF((x: any) => ({ ...x, document_version_id: versionOptions[0].id }));
  }, [docs.data]); // eslint-disable-line

  const body = () => ({
    ...f,
    coverage_level: f.coverage_level || null,
    document_version_id: f.document_version_id ? Number(f.document_version_id) : null,
    page_number: f.page_number ? Number(f.page_number) : null,
    value_number: f.value_number === "" || f.value_number === undefined ? null : Number(f.value_number),
  });
  const save = async () => {
    setBusy(true);
    try {
      if (finding) await api.post(`/findings/${finding.id}/review`, { action: "corrigeren", ...body() });
      else await api.post("/findings", { product_id: product.id, feature_id: feature.id, ...body() });
      toast.success("Vastgelegd als menselijke beoordeling (wordt niet door AI overschreven)");
      refresh();
      onOpenChange(false);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  const review = async (action: string) => {
    try {
      await api.post(`/findings/${finding.id}/review`, { action });
      toast.success({ goedkeuren: "Goedgekeurd", afwijzen: "Afgewezen", ontgrendelen: "Ontgrendeld" }[action]);
      refresh();
      onOpenChange(false);
    } catch (e: any) {
      toast.error(e.message);
    }
  };
  const findPassages = async () => {
    const vid = f.document_version_id || versionOptions[0]?.id;
    if (!vid) return toast.error("Koppel eerst een document aan dit product");
    setPassages(await api.get(`/document-versions/${vid}/passages`, { feature_id: feature.id }));
  };

  if (!product || !feature) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="lg" title={feature.label} description={`${product.provider_name} · ${product.name} · ${feature.category}${level ? ` · ${COVERAGE[level]}` : ""}`}
      footer={mode === "edit" ? (
        <><Button variant="ghost" onClick={() => (finding ? setMode("view") : onOpenChange(false))}>Annuleren</Button><Button variant="primary" onClick={save} loading={busy}>Vastleggen</Button></>
      ) : (
        <>
          {finding?.locked ? <Button variant="ghost" icon={<Unlock className="h-3.5 w-3.5" />} onClick={() => review("ontgrendelen")}>Ontgrendelen</Button> : null}
          <Button variant="danger" icon={<XCircle className="h-3.5 w-3.5" />} onClick={() => review("afwijzen")}>Afwijzen</Button>
          <Button icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setMode("edit")}>Corrigeren</Button>
          {finding?.review_status === "te_beoordelen" && <Button variant="primary" icon={<CheckCircle2 className="h-3.5 w-3.5" />} onClick={() => review("goedkeuren")}>Goedkeuren</Button>}
        </>
      )}>
      {mode === "view" && finding ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <FindingStatus status={finding.status} />
            <Badge tone="neutral">{finding.coverage_level ? COVERAGE[finding.coverage_level] : "Alle dekkingen"}</Badge>
            <OriginBadge origin={finding.origin} review={finding.review_status} />
            {finding.locked && <Badge tone="accent"><Lock className="h-3 w-3" /> Menselijke beoordeling vergrendeld</Badge>}
            {finding.confidence && <Badge>Betrouwbaarheid {finding.confidence}</Badge>}
          </div>
          {finding.value_text && <div className="text-[15px] font-medium">{finding.value_text}</div>}
          {finding.explanation && <p className="text-[13.5px] leading-relaxed text-ink-soft">{finding.explanation}</p>}
          {finding.quote && (
            <blockquote className="rounded-xl border-l-2 border-accent bg-surface px-4 py-3 text-[13px] italic leading-relaxed text-ink-soft">
              “{finding.quote}”
              <div className="mt-2 flex items-center gap-2 not-italic">
                <SourceRef versionId={finding.document_version_id} page={finding.page_number} article={finding.article} quote={finding.quote} label={`${finding.document?.title || "Document"} · p. ${finding.page_number ?? "?"}${finding.article ? ` · art. ${finding.article}` : ""}`} />
                <VerifiedMark verified={finding.quote_verified} />
              </div>
            </blockquote>
          )}
          {!finding.quote && finding.document_version_id && <SourceRef versionId={finding.document_version_id} page={finding.page_number} label="Bron openen" />}
          {finding.status === "niet_gevonden" && <Notice tone="neutral">Niet gevonden betekent niet dat dit onderdeel niet verzekerd is.</Notice>}
          {hist.data && hist.data.length > 1 && (
            <div>
              <div className="mb-2 flex items-center gap-1.5 text-[12.5px] font-medium text-ink-muted"><History className="h-3.5 w-3.5" /> Historie</div>
              <ul className="space-y-1 text-[12.5px]">
                {hist.data.map((h) => (
                  <li key={h.id} className="flex items-center justify-between rounded-lg bg-surface/60 px-3 py-1.5">
                    <span className="flex items-center gap-2"><FindingStatus status={h.status} compact /> <OriginBadge origin={h.origin} review={h.review_status} /></span>
                    <span className="text-ink-muted">{date(h.created_at, true)}{h.is_current ? " · actueel" : ""}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          <Field label="Geldt voor dekking" className="col-span-2" hint="Kies ‘Alle dekkingen’ als de regeling niet afhangt van WA, brand/diefstal, beperkt of volledig casco (bijv. acceptatie of stalling).">
            <Select value={f.coverage_level || ""} onChange={(e) => setF({ ...f, coverage_level: e.target.value })}>
              <option value="">Alle dekkingen</option>
              {COVERAGE_LEVELS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </Select>
          </Field>
          <Field label="Status" className="col-span-2">
            <Select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
              {Object.entries(FINDING_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </Select>
          </Field>
          <Field label="Waarde / regeling" hint="Bijv. ‘€ 150 per gebeurtenis’ of ‘minimaal 25 jaar oud’"><Input value={f.value_text || ""} onChange={(e) => setF({ ...f, value_text: e.target.value })} /></Field>
          <Field label="Numerieke waarde" hint="Optioneel, bijv. bedrag eigen risico"><Input type="number" value={f.value_number ?? ""} onChange={(e) => setF({ ...f, value_number: e.target.value })} /></Field>
          <Field label="Toelichting" className="col-span-2"><Textarea value={f.explanation || ""} onChange={(e) => setF({ ...f, explanation: e.target.value })} rows={2} /></Field>
          <Field label="Brondocument" className="col-span-2">
            <Select value={f.document_version_id || ""} onChange={(e) => setF({ ...f, document_version_id: e.target.value })}>
              <option value="">Geen document</option>
              {versionOptions.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
            </Select>
          </Field>
          <Field label="Pagina"><Input type="number" value={f.page_number || ""} onChange={(e) => setF({ ...f, page_number: e.target.value })} /></Field>
          <Field label="Artikel"><Input value={f.article || ""} onChange={(e) => setF({ ...f, article: e.target.value })} /></Field>
          <Field label="Letterlijk citaat" className="col-span-2" hint="Wordt gecontroleerd tegen de geëxtraheerde tekst."><Textarea value={f.quote || ""} onChange={(e) => setF({ ...f, quote: e.target.value })} rows={3} /></Field>
          <div className="col-span-2">
            <Button size="sm" icon={<Search className="h-3.5 w-3.5" />} onClick={findPassages}>Zoek relevante passages</Button>
            {passages && (passages.length === 0 ? <p className="mt-2 text-[12.5px] text-ink-muted">Geen passages gevonden met de trefwoorden van dit kenmerk.</p> : (
              <ul className="mt-3 space-y-2">
                {passages.map((p, i) => (
                  <li key={i} className="rounded-xl border border-line p-3 text-[12.5px]">
                    <div className="mb-1 flex items-center justify-between">
                      <span className="font-medium">p. {p.page_number}{p.article ? ` · art. ${p.article}` : ""} {p.heading && `· ${p.heading}`}</span>
                      <Button size="sm" variant="ghost" onClick={() => setF({ ...f, page_number: p.page_number, article: p.article || "", quote: p.snippet.slice(0, 600) })}>Gebruik</Button>
                    </div>
                    <p className="line-clamp-4 text-ink-muted">{p.snippet}</p>
                  </li>
                ))}
              </ul>
            ))}
          </div>
        </div>
      )}
    </Dialog>
  );
}
