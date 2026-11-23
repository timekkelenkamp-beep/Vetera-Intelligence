import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pencil, Trash2, Columns3 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { DOC_TYPE, VEHICLE } from "@/lib/labels";
import { FindingStatus, OriginBadge, SourceRef, VerifiedMark } from "@/components/common";
import { FindingEditor } from "@/components/FindingEditor";
import { ProductForm } from "@/components/forms";
import { Badge, Button, Card, CardHeader, KeyValue, Loading } from "@/components/ui/primitives";

export default function ProductDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [edit, setEdit] = React.useState(false);
  const [fe, setFe] = React.useState<any>(null);
  const { data: p } = useQuery({ queryKey: ["product", id], queryFn: () => api.get(`/products/${id}`) });
  const features = useQuery({ queryKey: ["features"], queryFn: () => api.get<any[]>("/features") });
  const findings = useQuery({ queryKey: ["findings", "product", id], queryFn: () => api.get<any[]>("/findings", { product_id: id }) });
  if (!p || !features.data) return <Loading />;
  const byFeature = Object.fromEntries((findings.data || []).map((f) => [f.feature_id, f]));
  const cats = [...new Set(features.data.map((f) => f.category))];
  const label = { id: p.id, name: p.name, provider_name: p.summary.provider_name };
  const del = async () => {
    if (!confirm("Product en alle bijbehorende bevindingen verwijderen?")) return;
    await api.del(`/products/${p.id}`);
    qc.invalidateQueries({ queryKey: ["products"] });
    toast.success("Product verwijderd");
    nav(`/concurrenten/${p.provider_id}`);
  };
  return (
    <div>
      <button onClick={() => nav(`/concurrenten/${p.provider_id}`)} className="mb-5 inline-flex items-center gap-1 text-[13px] text-ink-muted hover:text-ink"><ArrowLeft className="h-3.5 w-3.5" /> {p.summary.provider_name}</button>
      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-semibold tracking-tightest">{p.name}</h1>
          <div className="mt-1 flex items-center gap-2 text-[13px] text-ink-muted">{p.summary.provider_name} · {VEHICLE[p.vehicle_category]}{p.summary.is_reference && <Badge tone="accent">Vetera-referentie</Badge>}</div>
        </div>
        <div className="flex gap-2">
          <Button icon={<Columns3 className="h-4 w-4" />} onClick={() => nav(`/voorwaarden?products=${p.id}`)}>Vergelijken</Button>
          <Button icon={<Pencil className="h-4 w-4" />} onClick={() => setEdit(true)}>Bewerken</Button>
          <Button variant="ghost" icon={<Trash2 className="h-4 w-4" />} onClick={del}>Verwijderen</Button>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          {cats.map((c) => (
            <Card key={c}>
              <CardHeader title={c} />
              <ul className="divide-y divide-line">
                {features.data.filter((f) => f.category === c).map((f) => {
                  const x = byFeature[f.id];
                  return (
                    <li key={f.id}>
                      <button onClick={() => setFe({ feature: f, finding: x })} className="grid w-full grid-cols-[220px_1fr] gap-4 px-5 py-3 text-left hover:bg-surface/50">
                        <span className="text-[13px] font-medium">{f.label}</span>
                        <span className="min-w-0">
                          <span className="flex flex-wrap items-center gap-2"><FindingStatus status={x?.status} />{x && <OriginBadge origin={x.origin} review={x.review_status} />}<VerifiedMark verified={x?.quote_verified} />{x?.document_version_id && <SourceRef versionId={x.document_version_id} page={x.page_number} article={x.article} quote={x.quote} />}</span>
                          {x?.value_text && <span className="mt-1 block text-[12.5px] text-ink-soft">{x.value_text}</span>}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </Card>
          ))}
        </div>
        <div className="space-y-6">
          <Card className="p-5">
            <KeyValue items={[
              { label: "Risicodrager", value: p.risk_carrier?.name || "Onbekend" },
              { label: "Productpagina", value: p.url ? <a className="text-accent hover:underline break-all" href={p.url} target="_blank" rel="noreferrer">{p.url}</a> : "–" },
              { label: "Kenmerken", value: `${p.summary.features_known} van ${p.summary.features_total} vastgesteld` },
              { label: "Gecontroleerd", value: `${p.summary.features_verified} door mens` },
              { label: "Premies", value: p.premium_count },
            ]} />
          </Card>
          {p.canonical && <Card className="p-5 text-[13px]"><div className="font-semibold">Distributie van</div><button className="mt-1 text-accent hover:underline" onClick={() => nav(`/producten/${p.canonical.id}`)}>{p.canonical.provider_name} – {p.canonical.name}</button><p className="mt-2 text-[12px] text-ink-muted">Telt niet als zelfstandig concurrentieproduct.</p></Card>}
          {p.distributions.length > 0 && <Card className="p-5 text-[13px]"><div className="font-semibold mb-1">Ook verkrijgbaar via</div>{p.distributions.map((d: any) => <div key={d.id}>{d.provider_name} – {d.name}</div>)}</Card>}
          <Card>
            <CardHeader title="Documenten" />
            <ul className="divide-y divide-line">
              {p.documents.length === 0 && <li className="px-5 pb-4 text-[12.5px] text-ink-muted">Nog geen gekoppelde documenten.</li>}
              {p.documents.map((d: any) => <li key={d.id}><button onClick={() => nav(`/documenten/${d.id}`)} className="w-full px-5 py-2.5 text-left text-[13px] hover:bg-surface/50"><div className="font-medium truncate">{d.title}</div><div className="text-[12px] text-ink-muted">{DOC_TYPE[d.document_type]}</div></button></li>)}
            </ul>
          </Card>
        </div>
      </div>
      <ProductForm open={edit} onOpenChange={setEdit} initial={p} />
      <FindingEditor open={!!fe} onOpenChange={(v) => !v && setFe(null)} product={label} feature={fe?.feature} finding={fe?.finding} />
    </div>
  );
}
