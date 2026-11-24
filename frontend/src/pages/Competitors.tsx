import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { Image as ImageIcon, Plus, Search, ListPlus, Sparkles, Building2, Globe } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { relative } from "@/lib/utils";
import { PROVIDER_STATUS, PROVIDER_TYPE } from "@/lib/labels";
import { useAiAction } from "@/components/AiAction";
import { ProviderLogo, useDebounced } from "@/components/common";
import { ProviderForm } from "@/components/forms";
import { Badge, Button, Card, EmptyState, Input, Loading, PageHeader, Select } from "@/components/ui/primitives";

export default function Competitors() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [q, setQ] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [type, setType] = React.useState("");
  const [sort, setSort] = React.useState("name");
  const [form, setForm] = React.useState(false);
  const dq = useDebounced(q);
  const { data, isLoading } = useQuery({ queryKey: ["providers", dq, status, type, sort], queryFn: () => api.get<any[]>("/providers", { q: dq, status, provider_type: type, sort }) });
  const discover = useAiAction("/ai/discover", {
    invalidate: [["providers"]],
    onDone: (r: any) => toast.success(`${r.added.length} nieuwe aanbieder(s) gevonden met status ‘Te beoordelen’.`),
  });
  const loadStart = async () => {
    const r = await api.post("/providers/startlijst");
    qc.invalidateQueries({ queryKey: ["providers"] });
    toast.success(r.added ? `${r.added} aanbieders toegevoegd met status ‘Te beoordelen’` : "De startlijst is al geladen");
  };
  const fetchLogos = async () => {
    const r = await api.post("/providers/logos/auto");
    toast.success(r.started ? `Logo's worden opgehaald voor ${r.started} aanbieder(s). Dit duurt even.` : "Alle aanbieders met een website hebben al een logo.");
    if (r.started) [4000, 10000, 20000].forEach((t) => setTimeout(() => qc.invalidateQueries({ queryKey: ["providers"] }), t));
  };
  const toReview = data?.filter((p) => p.status === "te_beoordelen").length || 0;

  return (
    <div>
      <PageHeader module="concurrenten"
        title="Concurrenten"
        subtitle="Verzekeraars, gevolmachtigde agenten en tussenpersonen met klassieke auto-, motor- en bromfietsverzekeringen."
        actions={
          <>
            <Button icon={<ListPlus className="h-4 w-4" />} onClick={loadStart}>Startlijst laden</Button>
            <Button icon={<ImageIcon className="h-4 w-4" />} onClick={fetchLogos}>Logo's ophalen</Button>
            <Button icon={<Sparkles className="h-4 w-4" />} onClick={() => discover.start({})} loading={discover.busy}>Ontdekken met AI</Button>
            <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setForm(true)}>Nieuwe aanbieder</Button>
          </>
        }
      />
      <div className="mb-6 flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Zoek aanbieder" className="pl-9" />
        </div>
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-44">
          <option value="">Alle statussen</option>
          {Object.entries(PROVIDER_STATUS).filter(([k]) => k !== "samengevoegd").map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </Select>
        <Select value={type} onChange={(e) => setType(e.target.value)} className="w-48">
          <option value="">Alle typen</option>
          {Object.entries(PROVIDER_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select value={sort} onChange={(e) => setSort(e.target.value)} className="w-48">
          <option value="name">Sorteer op naam</option>
          <option value="products">Meeste producten</option>
          <option value="updated">Laatst bijgewerkt</option>
          <option value="checked">Laatst gecontroleerd</option>
        </Select>
        {toReview > 0 && <Badge tone="attention" className="ml-auto">{toReview} te beoordelen</Badge>}
      </div>
      {isLoading ? (
        <Loading />
      ) : !data?.length ? (
        <Card><EmptyState icon={<Building2 />} title="Geen aanbieders gevonden" description="Voeg handmatig een aanbieder toe, laad de startlijst uit de opdracht of laat AI zoeken naar relevante partijen." action={<Button variant="primary" onClick={() => setForm(true)}>Nieuwe aanbieder</Button>} /></Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((p, i) => (
            <motion.div key={p.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.02, 0.3) }}>
              <Card interactive onClick={() => nav(`/concurrenten/${p.id}`)} className="h-full p-5">
                <div className="flex items-start justify-between gap-3">
                  <ProviderLogo name={p.name} logoUrl={p.logo_url} size={40} id={p.id} isReference={p.is_reference} />
                  <div className="flex flex-wrap justify-end gap-1.5">
                    {p.is_reference && <Badge tone="accent">Referentie</Badge>}
                    <Badge tone={PROVIDER_STATUS[p.status]?.tone}>{PROVIDER_STATUS[p.status]?.label}</Badge>
                  </div>
                </div>
                <div className="mt-4">
                  <div className="text-[16px] font-semibold tracking-tight">{p.name}</div>
                  <div className="mt-0.5 text-[12.5px] text-ink-muted">{PROVIDER_TYPE[p.provider_type]}</div>
                </div>
                {p.website && <div className="mt-2 flex items-center gap-1.5 text-[12px] text-ink-muted truncate"><Globe className="h-3 w-3" />{p.website.replace(/^https?:\/\//, "")}</div>}
                <div className="mt-4 grid grid-cols-3 gap-2 border-t border-line pt-3 text-center">
                  <Mini label="Producten" value={p.product_count} />
                  <Mini label="Documenten" value={p.document_count} />
                  <Mini label="Premies" value={p.premium_count} />
                </div>
                <div className="mt-3 text-[11.5px] text-ink-faint">Laatst bijgewerkt {relative(p.updated_at)}</div>
              </Card>
            </motion.div>
          ))}
        </div>
      )}
      <ProviderForm open={form} onOpenChange={setForm} onSaved={(p) => nav(`/concurrenten/${p.id}`)} />
      {discover.dialog}
    </div>
  );
}

function Mini({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-[15px] font-semibold tabular">{value}</div>
      <div className="text-[11px] text-ink-muted">{label}</div>
    </div>
  );
}
