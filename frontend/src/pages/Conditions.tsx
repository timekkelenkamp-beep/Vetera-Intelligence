import * as React from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createColumnHelper, flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type SortingState, type VisibilityState } from "@tanstack/react-table";
import { ScatterChart as ScatterIcon, FlaskConical, LayoutGrid, Table2, Gauge, Download, Search, ArrowUpDown, Columns3, Handshake, Sparkles, Info, Check, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAiAction } from "@/components/AiAction";
import { PositioningView, WhatIfView } from "@/components/InsightViews";
import { FindingStatus, ProviderLogo, SourceRef, VerifiedMark, useDebounced } from "@/components/common";
import { FindingEditor } from "@/components/FindingEditor";
import { useProducts } from "@/components/forms";
import { Dialog, Menu } from "@/components/ui/overlay";
import { Badge, Button, Card, EmptyState, Input, Loading, Notice, PageHeader, Segmented, Select, Switch, Tip } from "@/components/ui/primitives";

type View = "kaarten" | "tabel" | "scores" | "positionering" | "watals";

export default function Conditions() {
  const [params, setParams] = useSearchParams();
  const all = useProducts();
  const [view, setView] = React.useState<View>((params.get("view") as View) || "tabel");
  const [selected, setSelected] = React.useState<number[]>([]);
  const [reference, setReference] = React.useState<number | null>(null);

  React.useEffect(() => {
    if (!all.data) return;
    const fromUrl = (params.get("products") || params.get("product") || "").split(",").map(Number).filter(Boolean);
    const vet = all.data.find((p) => p.is_reference);
    const base = fromUrl.length ? fromUrl : all.data.filter((p) => p.provider_status === "actief" && !p.canonical_product_id).slice(0, 6).map((p) => p.id);
    const withRef = vet && !base.includes(vet.id) ? [vet.id, ...base] : base;
    setSelected(withRef);
    setReference(vet?.id ?? null);
  }, [all.data]); // eslint-disable-line

  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <div>
      <PageHeader module="voorwaarden"
        title="Voorwaardenvergelijker"
        subtitle="Vergelijk polisvoorwaarden per kenmerk, met bronverwijzing naar document, pagina en artikel."
        actions={<Segmented value={view} onChange={(v) => { setView(v); setParams((p) => { p.set("view", v); return p; }); }} options={[
          { value: "kaarten", label: <><LayoutGrid className="h-3.5 w-3.5" /> Kaarten</> },
          { value: "tabel", label: <><Table2 className="h-3.5 w-3.5" /> Tabel</> },
          { value: "scores", label: <><Gauge className="h-3.5 w-3.5" /> Scores</> },
          { value: "positionering", label: <><ScatterIcon className="h-3.5 w-3.5" /> Positionering</> },
          { value: "watals", label: <><FlaskConical className="h-3.5 w-3.5" /> Wat als</> },
        ]} />}
      />
      {all.isLoading ? <Loading /> : !all.data?.length ? (
        <Card><EmptyState icon={<Columns3 />} title="Nog geen producten" description="Voeg bij Concurrenten het Vetera-product en de concurrentieproducten toe; leg daarna bevindingen vast of laat ze uit documenten afleiden." /></Card>
      ) : (
        <>
          <Card className={cn("mb-6 p-4", (view === "positionering" || view === "watals") && "hidden")}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="mr-1 text-[12.5px] font-medium text-ink-muted">Producten</span>
              {all.data.map((p) => (
                <button key={p.id} onClick={() => toggle(p.id)} className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12.5px] transition-colors", selected.includes(p.id) ? "border-accent/30 bg-accent-soft text-accent-ink" : "border-line text-ink-soft hover:border-line-strong")}>
                  {selected.includes(p.id) && <Check className="h-3 w-3" />}
                  {p.provider_name} · {p.name}
                  {p.canonical_product_id && <span className="text-ink-faint">(distributie)</span>}
                </button>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-2 border-t border-line pt-3">
              <span className="text-[12.5px] font-medium text-ink-muted">Referentie</span>
              <Select value={reference ?? ""} onChange={(e) => setReference(e.target.value ? Number(e.target.value) : null)} className="h-8 w-80 text-[12.5px]">
                <option value="">Geen referentie</option>
                {all.data.filter((p) => selected.includes(p.id)).map((p) => <option key={p.id} value={p.id}>{p.provider_name} · {p.name}</option>)}
              </Select>
              {!all.data.some((p) => p.is_reference) && <span className="text-[12px] text-caution">Leg eerst het Vetera-product vast om als referentie te gebruiken.</span>}
            </div>
          </Card>
          {view === "positionering" ? <PositioningView /> : view === "watals" ? <WhatIfView products={all.data} /> :
            selected.length === 0 ? <Card><EmptyState title="Selecteer producten" /></Card> :
            view === "tabel" ? <MatrixView ids={selected} reference={reference} products={all.data} /> :
            view === "kaarten" ? <CardsView ids={selected} reference={reference} /> : <ScoresView ids={selected} />}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Tabel */
const ch = createColumnHelper<any>();
// Zachte achtergrondtint per status: de matrix leest als heatmap, de badge blijft de primaire codering.
const STATUS_TINT: Record<string, string> = {
  gedekt: "bg-[#eaf6ee]", uitgesloten: "bg-[#fcefed]", voorwaardelijk: "bg-[#fdf5e6]",
  aanvullende_clausule: "bg-[#ecf3fc]", menselijke_beoordeling: "bg-[#f5f2ff]",
};

function MatrixView({ ids, reference, products }: { ids: number[]; reference: number | null; products: any[] }) {
  const [category, setCategory] = React.useState("");
  const [onlyDiff, setOnlyDiff] = React.useState(false);
  const [onlyUnknown, setOnlyUnknown] = React.useState(false);
  const [urlParams] = useSearchParams();
  const [q, setQ] = React.useState(urlParams.get("q") || "");
  const dq = useDebounced(q);
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [visibility, setVisibility] = React.useState<VisibilityState>({ rubriek: false });
  const [edit, setEdit] = React.useState<any>(null);
  const { data, isFetching } = useQuery({
    queryKey: ["matrix", ids, reference, category, onlyDiff, onlyUnknown, dq],
    queryFn: () => api.get("/compare/matrix", { product_ids: ids.join(","), reference, category, only_differences: onlyDiff, only_unknown: onlyUnknown, q: dq }),
    placeholderData: (p) => p,
  });
  const prodMap = Object.fromEntries(products.map((p) => [p.id, p]));

  const columns = React.useMemo(() => {
    const cols: any[] = [
      ch.accessor((r) => r.feature.category, { id: "rubriek", header: "Rubriek", size: 130, cell: (c) => <span className="text-[12px] text-ink-muted">{c.getValue()}</span> }),
      ch.accessor((r) => r.feature.label, { id: "kenmerk", header: "Kenmerk", size: 220, cell: (c) => <span className="text-[13px] font-medium text-ink">{c.getValue()}</span> }),
    ];
    (data?.products || []).forEach((p: any) => {
      cols.push(ch.display({
        id: `p${p.id}`,
        header: () => (
          <div className="flex items-center gap-2">
            <ProviderLogo name={p.provider_name} logoUrl={p.logo} size={22} id={p.provider_id} isReference={p.is_reference} />
            <div className="min-w-0 leading-tight">
              <div className="truncate text-[12.5px] font-semibold text-ink">{p.provider_name}</div>
              <div className="truncate text-[11px] font-normal text-ink-muted">{p.name}</div>
            </div>
            {p.id === data.reference_product_id && <Badge tone="accent">Ref.</Badge>}
          </div>
        ),
        size: 230,
        cell: (c: any) => {
          const r = c.row.original;
          const cell = r.cells[String(p.id)];
          const diff = r.differences[String(p.id)];
          return (
            <button onClick={() => setEdit({ product: prodMap[p.id] || p, feature: r.feature, finding: cell })} className={cn("block w-full rounded-[10px] p-2 -m-1 text-left transition-all hover:brightness-[0.97] hover:shadow-[inset_0_0_0_1px_rgba(0,0,0,0.06)]", STATUS_TINT[cell?.status] || "hover:bg-surface")}>
              <div className="flex items-center gap-1.5"><FindingStatus status={cell?.status} compact /><VerifiedMark verified={cell?.quote_verified} />{cell && cell.review_status === "te_beoordelen" && cell.origin !== "handmatig" && <Tip content="Nog niet door een mens gecontroleerd"><span className="h-1.5 w-1.5 rounded-full bg-[#5b3fb5]" /></Tip>}</div>
              {cell?.value_text && <div className="mt-1 line-clamp-2 text-[12px] text-ink-soft">{cell.value_text}</div>}
              {cell?.document_version_id && <div className="mt-0.5"><SourceRef versionId={cell.document_version_id} page={cell.page_number} article={cell.article} quote={cell.quote} className="-ml-1.5" /></div>}
              {diff && diff.kind !== "onzeker" && (
                <div className={cn("mt-1 text-[11.5px] leading-snug", diff.kind === "concurrent_ruimer" ? "text-caution" : diff.kind === "referentie_ruimer" ? "text-accent" : "text-ink-muted")}>{diff.text}</div>
              )}
            </button>
          );
        },
      }));
    });
    return cols;
  }, [data]); // eslint-disable-line

  const table = useReactTable<any>({ data: data?.rows || [], columns, state: { sorting, columnVisibility: visibility }, onSortingChange: setSorting, onColumnVisibilityChange: setVisibility, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });
  const exp = (fmt: string) => window.open(api.url("/compare/export", { product_ids: ids.join(","), reference, fmt }), "_blank");

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-64">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Zoek op clausule of kenmerk" className="pl-9" />
        </div>
        <Select value={category} onChange={(e) => setCategory(e.target.value)} className="w-48">
          <option value="">Alle rubrieken</option>
          {data?.categories?.map((c: string) => <option key={c} value={c}>{c}</option>)}
        </Select>
        <div className="flex items-center gap-4 rounded-[10px] border border-line px-3 py-1">
          <Switch checked={onlyDiff} onCheckedChange={setOnlyDiff} label="Alleen verschillen" />
          <Switch checked={onlyUnknown} onCheckedChange={setOnlyUnknown} label="Alleen onbekend" />
        </div>
        <div className="ml-auto flex gap-2">
          <Menu trigger={<Button icon={<Columns3 className="h-4 w-4" />}>Kolommen</Button>} items={table.getAllLeafColumns().map((c) => ({ label: `${c.getIsVisible() ? "✓ " : "   "}${c.id === "rubriek" ? "Rubriek" : c.id === "kenmerk" ? "Kenmerk" : (data?.products.find((p: any) => `p${p.id}` === c.id)?.provider_name ?? c.id)}`, onSelect: () => c.toggleVisibility() }))} />
          <Menu trigger={<Button icon={<Download className="h-4 w-4" />}>Exporteren</Button>} items={[{ label: "Excel (.xlsx)", onSelect: () => exp("xlsx") }, { label: "PDF", onSelect: () => exp("pdf") }]} />
        </div>
      </div>
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead className="sticky top-0 z-10 bg-white/95 backdrop-blur">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id} className="border-b border-line">
                  {hg.headers.map((h) => (
                    <th key={h.id} style={{ minWidth: h.getSize() }} className="px-4 py-3 text-left align-bottom text-[12px] font-medium text-ink-muted">
                      {h.column.getCanSort() ? (
                        <button onClick={h.column.getToggleSortingHandler()} className="inline-flex items-center gap-1 hover:text-ink">{flexRender(h.column.columnDef.header, h.getContext())}<ArrowUpDown className="h-3 w-3" /></button>
                      ) : flexRender(h.column.columnDef.header, h.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody className={cn(isFetching && "opacity-60 transition-opacity")}>
              {table.getRowModel().rows.length === 0 ? (
                <tr><td colSpan={columns.length}><EmptyState title="Geen kenmerken" description="Er zijn geen kenmerken die aan de filters voldoen." /></td></tr>
              ) : table.getRowModel().rows.map((row, i, arr) => {
                const showGroup = sorting.length === 0 && (i === 0 || arr[i - 1].original.feature.category !== row.original.feature.category);
                return (
                  <React.Fragment key={row.id}>
                    {showGroup && <tr className="bg-surface/70"><td colSpan={row.getVisibleCells().length} className="px-4 py-1.5 text-[11.5px] font-semibold uppercase tracking-wide text-ink-muted">{row.original.feature.category}</td></tr>}
                    <tr className="border-b border-line last:border-0 align-top hover:bg-surface/30">
                      {row.getVisibleCells().map((c) => <td key={c.id} className="px-4 py-3">{flexRender(c.column.columnDef.cell, c.getContext())}</td>)}
                    </tr>
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
      <p className="mt-3 flex items-center gap-1.5 text-[12px] text-ink-muted"><Info className="h-3.5 w-3.5" /> Klik op een cel om de bevinding te bekijken, goed te keuren of te corrigeren. ‘Niet gevonden’ betekent niet ‘niet verzekerd’.</p>
      <FindingEditor open={!!edit} onOpenChange={(v) => !v && setEdit(null)} product={edit?.product} feature={edit?.feature} finding={edit?.finding} />
    </>
  );
}

/* ------------------------------------------------------------------ Kaarten */
function CardsView({ ids, reference }: { ids: number[]; reference: number | null }) {
  const nav = useNavigate();
  const { data, isLoading } = useQuery({ queryKey: ["cards", ids, reference], queryFn: () => api.get<any[]>("/compare/cards", { product_ids: ids.join(","), reference }) });
  const [sales, setSales] = React.useState<any>(null);
  if (isLoading) return <Loading />;
  return (
    <>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 2xl:grid-cols-3">
        {data?.map((p) => (
          <Card key={p.id} className="flex flex-col p-6">
            <div className="flex items-start justify-between gap-3">
              <ProviderLogo name={p.provider_name} logoUrl={p.logo} size={40} id={p.provider_id} isReference={p.is_reference} />
              <Badge tone={p.data_status === "goed" ? "positive" : p.data_status === "gedeeltelijk" ? "caution" : "neutral"}>
                {p.features_known}/{p.features_total} kenmerken · {p.features_verified} gecontroleerd
              </Badge>
            </div>
            <div className="mt-4 text-[17px] font-semibold tracking-tight">{p.name}</div>
            <div className="text-[13px] text-ink-muted">{p.provider_name}{p.id === reference && " · referentie"}</div>
            {p.highlights.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-1.5">{p.highlights.map((h: any) => <Badge key={h.feature} tone="neutral">{h.feature}</Badge>)}</div>
            )}
            {p.id !== reference && reference && (
              <div className="mt-5 space-y-3 text-[12.5px]">
                <div>
                  <div className="mb-1 font-medium text-ink">Aantoonbaar ruimer dan referentie</div>
                  {p.advantages.length ? p.advantages.map((a: any, i: number) => <div key={i} className="text-ink-soft">• {a.feature}</div>) : <div className="text-ink-faint">Geen vastgesteld</div>}
                </div>
                <div>
                  <div className="mb-1 font-medium text-ink">Aantoonbaar beperkter dan referentie</div>
                  {p.disadvantages.length ? p.disadvantages.map((a: any, i: number) => <div key={i} className="text-ink-soft">• {a.feature}</div>) : <div className="text-ink-faint">Geen vastgesteld</div>}
                </div>
              </div>
            )}
            <div className="mt-auto flex gap-2 pt-5">
              <Button size="sm" onClick={() => nav(`/producten/${p.id}`)}>Details</Button>
              {reference && p.id !== reference && <Button size="sm" variant="outline" icon={<Handshake className="h-3.5 w-3.5" />} onClick={() => setSales(p)}>Verkoopargumenten</Button>}
            </div>
          </Card>
        ))}
      </div>
      {sales && reference && <SalesCardDialog competitor={sales} veteraId={reference} onClose={() => setSales(null)} />}
    </>
  );
}

export function SalesCardDialog({ competitor, veteraId, onClose }: { competitor: any; veteraId: number; onClose: () => void }) {
  const [card, setCard] = React.useState<any>(null);
  const [busy, setBusy] = React.useState(false);
  const ai = useAiAction("/ai/sales-card", { onDone: (r: any) => setCard(r.content) });
  React.useEffect(() => {
    setBusy(true);
    api.post("/ai/sales-card", { vetera_product_id: veteraId, competitor_product_id: competitor.id, use_ai: false }).then((r) => setCard(r.content)).catch((e) => toast.error(e.message)).finally(() => setBusy(false));
  }, [competitor.id, veteraId]);
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()} size="lg" title={card?.title || "Verkoopargumenten"} description="Feitelijk productverschil → praktisch klantvoordeel → mogelijk verkoopargument. Uitsluitend aantoonbare verschillen."
      footer={<><Button variant="ghost" onClick={onClose}>Sluiten</Button><Button icon={<Sparkles className="h-3.5 w-3.5" />} onClick={() => ai.start({ vetera_product_id: veteraId, competitor_product_id: competitor.id, use_ai: true })} loading={ai.busy}>Verfijnen met AI</Button></>}>
      {busy || !card ? <Loading /> : (
        <div className="space-y-5">
          {card.origin === "ai" && <Badge tone="accent"><Sparkles className="h-3 w-3" /> Opgesteld met AI · controleer vóór gebruik</Badge>}
          {card.arguments.length === 0 ? <Notice tone="neutral">Er zijn (nog) geen aantoonbare punten waarop Vetera ruimer is. Leg meer bevindingen vast voor beide producten.</Notice> : (
            <ol className="space-y-3">
              {card.arguments.map((a: any, i: number) => (
                <li key={i} className="rounded-xl border border-line p-4">
                  <div className="flex items-start gap-3">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent text-[12px] font-semibold text-white">{i + 1}</span>
                    <div className="min-w-0 text-[13px]">
                      <div className="font-medium text-ink">{a.fact}</div>
                      <div className="mt-1 text-ink-soft"><span className="text-ink-muted">Klantvoordeel:</span> {a.customer_benefit}</div>
                      <div className="mt-0.5 text-ink-soft"><span className="text-ink-muted">Verkoopargument:</span> {a.sales_argument}</div>
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {a.unsupported && <Badge tone="negative">Zonder bron</Badge>}
                        {(a.evidence || []).map((e: any, j: number) => e?.document_version_id ? <SourceRef key={j} versionId={e.document_version_id} page={e.page_number} quote={e.quote} /> : e?.finding_id || e?.id ? <Badge key={j}><ShieldCheck className="h-3 w-3" /> bevinding</Badge> : null)}
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
          <div>
            <div className="mb-1.5 text-[13px] font-semibold">Waar {competitor.provider_name} aantoonbaar gunstiger is</div>
            {card.competitor_strengths?.length ? <ul className="space-y-1 text-[12.5px] text-ink-soft">{card.competitor_strengths.map((s: any, i: number) => <li key={i}>• {s.text}</li>)}</ul> : <p className="text-[12.5px] text-ink-muted">Geen aantoonbare punten vastgesteld.</p>}
          </div>
          {card.unknown?.length > 0 && <p className="text-[12px] text-ink-muted">Onbekend en daarom niet meegewogen: {card.unknown.join(", ")}.</p>}
          <div>
            <div className="mb-1.5 text-[13px] font-semibold">Vragen voor de adviseur</div>
            <ul className="space-y-1 text-[12.5px] text-ink-soft">{card.advisor_questions?.map((q: string, i: number) => <li key={i}>• {q}</li>)}</ul>
          </div>
          {card.disclaimer && <p className="text-[11.5px] text-ink-faint">{card.disclaimer}</p>}
        </div>
      )}
      {ai.dialog}
    </Dialog>
  );
}

/* ------------------------------------------------------------------ Scores */
const ASPECTS = [
  { key: "voorwaarden", label: "Voorwaarden" }, { key: "premie", label: "Premie" },
  { key: "acceptatie", label: "Acceptatie" }, { key: "flexibiliteit", label: "Flexibiliteit" },
];

function ScoresView({ ids }: { ids: number[] }) {
  const qc = useQueryClient();
  const sps = useQuery({ queryKey: ["score-profiles"], queryFn: () => api.get<any[]>("/score-profiles") });
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: () => api.get<any[]>("/profiles") });
  const [spId, setSpId] = React.useState<number | null>(null);
  React.useEffect(() => { if (!spId && sps.data?.length) setSpId(sps.data[0].id); }, [sps.data, spId]);
  const sp = sps.data?.find((s) => s.id === spId);
  const [weights, setWeights] = React.useState<Record<string, number>>({});
  React.useEffect(() => { if (sp) setWeights(sp.weights); }, [sp?.id]); // eslint-disable-line
  const dw = useDebounced(weights, 400);
  React.useEffect(() => {
    if (sp && JSON.stringify(dw) !== JSON.stringify(sp.weights)) api.patch(`/score-profiles/${sp.id}`, { weights: dw }).then(() => qc.invalidateQueries({ queryKey: ["score-profiles"] }));
  }, [dw]); // eslint-disable-line
  const scores = useQuery({ queryKey: ["scores", spId, ids, sp?.weights, sp?.reference_profile_id, sp?.min_coverage], queryFn: () => api.get("/scores", { score_profile_id: spId, product_ids: ids.join(",") }), enabled: !!spId });
  const total = Object.values(weights).reduce((a, b) => a + Number(b || 0), 0);
  const update = async (body: any) => { await api.patch(`/score-profiles/${sp.id}`, body); qc.invalidateQueries({ queryKey: ["score-profiles"] }); };
  const newProfile = async () => { const s = await api.post("/score-profiles", { name: "Nieuw scenario" }); qc.invalidateQueries({ queryKey: ["score-profiles"] }); setSpId(s.id); };

  if (!sp) return <Loading />;
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[340px_1fr]">
      <Card className="h-fit p-5">
        <div className="flex items-center gap-2">
          <Select value={spId ?? ""} onChange={(e) => setSpId(Number(e.target.value))} className="flex-1">{sps.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>
          <Button size="sm" onClick={newProfile}>Nieuw</Button>
        </div>
        <Input className="mt-3" defaultValue={sp.name} key={sp.id + "n"} onBlur={(e) => e.target.value !== sp.name && update({ name: e.target.value })} aria-label="Naam scenario" />
        <div className="mt-5 space-y-4">
          {ASPECTS.map((a) => (
            <div key={a.key}>
              <div className="flex justify-between text-[12.5px]"><span className="font-medium">{a.label}</span><span className="tabular text-ink-muted">{Math.round(((weights[a.key] || 0) / (total || 1)) * 100)}%</span></div>
              <input type="range" min={0} max={100} value={weights[a.key] || 0} onChange={(e) => setWeights((w) => ({ ...w, [a.key]: Number(e.target.value) }))} className="mt-1.5 w-full accent-[var(--accent)]" aria-label={`Weging ${a.label}`} />
            </div>
          ))}
        </div>
        <div className="mt-5 space-y-3 border-t border-line pt-4">
          <label className="block text-[12.5px]"><span className="font-medium">Rekenprofiel voor premie</span>
            <Select className="mt-1" value={sp.reference_profile_id ?? ""} onChange={(e) => update({ reference_profile_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">Geen (premie telt niet mee)</option>
              {profiles.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
          </label>
          <label className="block text-[12.5px]"><span className="font-medium">Minimaal bekende kenmerken per aspect</span>
            <Select className="mt-1" value={String(sp.min_coverage)} onChange={(e) => update({ min_coverage: Number(e.target.value) })}>
              {[0.4, 0.5, 0.6, 0.7, 0.8, 1].map((v) => <option key={v} value={v}>{v * 100}%</option>)}
            </Select>
          </label>
        </div>
      </Card>
      <div>
        {scores.isLoading ? <Loading /> : (
          <>
            <Card className="overflow-hidden">
              <table className="w-full text-[13px]">
                <thead><tr className="border-b border-line text-left text-[12px] text-ink-muted"><th className="px-5 py-3 font-medium">Product</th>{ASPECTS.filter((a) => (weights[a.key] || 0) > 0).map((a) => <th key={a.key} className="px-3 font-medium">{a.label}</th>)}<th className="px-5 font-medium">Totaal</th></tr></thead>
                <tbody>
                  {scores.data?.results.map((r: any) => (
                    <tr key={r.product.id} className="border-b border-line last:border-0">
                      <td className="px-5 py-3"><div className="font-medium">{r.product.provider_name}</div><div className="text-[12px] text-ink-muted">{r.product.name}</div></td>
                      {ASPECTS.filter((a) => (weights[a.key] || 0) > 0).map((a) => {
                        const x = r.aspects[a.key];
                        return (
                          <td key={a.key} className="px-3">
                            {x?.score === null || x?.score === undefined ? (
                              <Tip content={x?.note || "Onbekend"}><span className="inline-flex items-center gap-1 text-[12px] text-ink-faint">onbekend <Info className="h-3 w-3" /></span></Tip>
                            ) : (
                              <Tip content={x.known !== undefined ? `${x.known} van ${x.total} kenmerken bekend` : "Op basis van vergelijkbare premie"}>
                                <div className="w-24"><div className="text-[13px] font-semibold tabular">{Math.round(x.score)}</div><div className="mt-1 h-1 rounded-full bg-surface"><div className="h-full rounded-full bg-accent" style={{ width: `${x.score}%` }} /></div></div>
                              </Tip>
                            )}
                          </td>
                        );
                      })}
                      <td className="px-5">{r.total === null ? <Tip content={r.total_note}><span className="text-[12px] text-ink-faint">niet te bepalen</span></Tip> : <span className="text-[16px] font-semibold tabular">{Math.round(r.total)}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Notice tone="neutral" title="Scoremethode" icon={<Info />} className="mt-4">{scores.data?.method}</Notice>
          </>
        )}
      </div>
    </div>
  );
}
