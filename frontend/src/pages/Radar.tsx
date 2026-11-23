import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { Sparkles, ScanSearch, Plus, Lightbulb, FlaskConical, Globe } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SUGGESTION_CATEGORIES, SUGGESTION_STATUS } from "@/lib/labels";
import { useAiAction, useAiStatus } from "@/components/AiAction";
import { Dialog } from "@/components/ui/overlay";
import { Badge, Button, Card, EmptyState, Field, Input, Loading, Notice, PageHeader, Segmented, Select, Switch, Textarea } from "@/components/ui/primitives";

const PRIO_TONE: Record<string, any> = { hoog: "negative", middel: "caution", laag: "neutral" };

export function SuggestionBadges({ s }: { s: any }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {s.kind === "innovatiehypothese" ? <Badge tone="attention"><FlaskConical className="h-3 w-3" /> Innovatiehypothese</Badge> : <Badge tone="info">Datagedreven</Badge>}
      <Badge tone={PRIO_TONE[s.priority]}>Prioriteit {s.priority}</Badge>
      <Badge>Betrouwbaarheid {s.confidence}</Badge>
    </div>
  );
}

export default function Radar() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [kind, setKind] = React.useState("");
  const [category, setCategory] = React.useState("");
  const [view, setView] = React.useState<"bord" | "lijst">("bord");
  const [gen, setGen] = React.useState(false);
  const [manual, setManual] = React.useState(false);
  const { data, isLoading } = useQuery({ queryKey: ["suggestions", kind, category], queryFn: () => api.get<any[]>("/radar/suggestions", { kind, category }) });
  const scan = async () => {
    const r = await api.post("/radar/scan");
    qc.invalidateQueries({ queryKey: ["suggestions"] });
    toast.success(r.created ? `${r.created} nieuwe datagedreven signalen` : "Geen nieuwe signalen gevonden in de vastgelegde bevindingen");
  };
  const move = async (s: any, status: string) => {
    await api.patch(`/radar/suggestions/${s.id}`, { status });
    qc.invalidateQueries({ queryKey: ["suggestions"] });
  };
  const cols = SUGGESTION_STATUS;
  return (
    <div>
      <PageHeader title="Vetera Verbeterradar" subtitle="Proactieve verbetervoorstellen voor de huidige Vetera-propositie — geen nieuw product. Datagedreven verbeteringen zijn onderbouwd met bronnen; innovatiehypotheses zijn nadrukkelijk onbewezen."
        actions={<>
          <Button icon={<ScanSearch className="h-4 w-4" />} onClick={scan}>Signaleren uit data</Button>
          <Button icon={<Plus className="h-4 w-4" />} onClick={() => setManual(true)}>Eigen idee</Button>
          <Button variant="primary" icon={<Sparkles className="h-4 w-4" />} onClick={() => setGen(true)}>Genereer met AI</Button>
        </>} />
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <Select value={kind} onChange={(e) => setKind(e.target.value)} className="w-56"><option value="">Alle soorten</option><option value="datagedreven">Datagedreven</option><option value="innovatiehypothese">Innovatiehypothese</option></Select>
        <Select value={category} onChange={(e) => setCategory(e.target.value)} className="w-64"><option value="">Alle categorieën</option>{SUGGESTION_CATEGORIES.map((c) => <option key={c}>{c}</option>)}</Select>
        <Segmented className="ml-auto" value={view} onChange={setView} options={[{ value: "bord", label: "Werkproces" }, { value: "lijst", label: "Op prioriteit" }]} />
      </div>
      {isLoading ? <Loading /> : !data?.length ? (
        <Card><EmptyState icon={<Lightbulb />} title="Nog geen verbetervoorstellen" description="‘Signaleren uit data’ zoekt zonder AI naar kenmerken waar concurrenten aantoonbaar ruimer zijn (of Vetera onderscheidend is). Met AI kun je ook innovatiehypotheses laten formuleren." /></Card>
      ) : view === "lijst" ? (
        <div className="space-y-3">
          {data.filter((s) => s.status !== "afgewezen").map((s) => <SuggestionCard key={s.id} s={s} onClick={() => nav(`/verbeterradar/${s.id}`)} wide />)}
        </div>
      ) : (
        <div className="grid grid-cols-6 gap-3 overflow-x-auto pb-2" style={{ minWidth: 1100 }}>
          {cols.map((c) => {
            const items = data.filter((s) => s.status === c.key);
            return (
              <div key={c.key} className="min-w-0 rounded-2xl bg-surface/70 p-2"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { const id = Number(e.dataTransfer.getData("id")); const s = data.find((x) => x.id === id); s && s.status !== c.key && move(s, c.key); }}>
                <div className="flex items-center justify-between px-2 pb-2 pt-1 text-[12.5px] font-semibold text-ink-soft">{c.label}<span className="tabular text-ink-faint">{items.length}</span></div>
                <div className="space-y-2">
                  {items.map((s) => (
                    <div key={s.id} draggable onDragStart={(e) => e.dataTransfer.setData("id", String(s.id))}>
                      <SuggestionCard s={s} onClick={() => nav(`/verbeterradar/${s.id}`)} />
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <GenerateDialog open={gen} onOpenChange={setGen} />
      <ManualDialog open={manual} onOpenChange={setManual} />
    </div>
  );
}

function SuggestionCard({ s, onClick, wide }: { s: any; onClick: () => void; wide?: boolean }) {
  return (
    <motion.div layout>
      <Card interactive onClick={onClick} className={cn("p-3.5", wide && "p-5")}>
        <div className="text-[11.5px] text-ink-muted">{s.category}</div>
        <div className={cn("mt-0.5 font-semibold leading-snug", wide ? "text-[15px]" : "text-[13px]")}>{s.title}</div>
        {wide && s.summary && <p className="mt-1 text-[13px] text-ink-muted">{s.summary}</p>}
        <div className="mt-2.5 flex flex-wrap gap-1">
          {s.kind === "innovatiehypothese" ? <Badge tone="attention">Hypothese</Badge> : <Badge tone="info">Data</Badge>}
          <Badge tone={PRIO_TONE[s.priority]}>{s.priority}</Badge>
          {s.dossier_count > 0 && <Badge tone="accent">dossier</Badge>}
        </div>
      </Card>
    </motion.div>
  );
}

function GenerateDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [focus, setFocus] = React.useState("");
  const [web, setWeb] = React.useState(false);
  const ai = useAiStatus();
  const action = useAiAction("/ai/radar", { invalidate: [["suggestions"]], onDone: (r: any) => { toast.success(`${r.created.length} voorstellen toegevoegd met status ‘Nieuw’`); onOpenChange(false); } });
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Verbetervoorstellen genereren" description="AI analyseert de vastgelegde bevindingen, premies en marktontwikkelingen."
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Annuleren</Button><Button variant="primary" icon={<Sparkles className="h-3.5 w-3.5" />} loading={action.busy} onClick={() => action.start({ focus: focus || undefined, web })}>Bekijk wat wordt verstuurd</Button></>}>
      <Field label="Focus (optioneel)" hint="Bijv. ‘klassieke bromfietsen’, ‘verzamelaars met meerdere voertuigen’, ‘digitale dienstverlening’"><Input value={focus} onChange={(e) => setFocus(e.target.value)} /></Field>
      <div className="mt-4"><Switch checked={web} onCheckedChange={setWeb} disabled={!ai.data?.web_research} label="Breder webonderzoek toestaan" description={ai.data?.web_research ? "Het model mag openbare webbronnen raadplegen voor marktontwikkelingen." : "Schakel webonderzoek eerst in bij Instellingen → AI."} /></div>
      <Notice tone="neutral" className="mt-4" icon={<Globe />}>Er wordt geen Vetera 2.0-product gemaakt. Innovatiehypotheses krijgen dat label en worden nooit als bewezen kans gepresenteerd.</Notice>
      {action.dialog}
    </Dialog>
  );
}

function ManualDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [f, setF] = React.useState<any>({ kind: "innovatiehypothese", category: "Productverbetering", priority: "middel", confidence: "laag" });
  const save = async () => {
    try {
      const s = await api.post("/radar/suggestions", f);
      qc.invalidateQueries({ queryKey: ["suggestions"] });
      onOpenChange(false);
      nav(`/verbeterradar/${s.id}`);
    } catch (e: any) { toast.error(e.message); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Eigen verbeteridee" size="lg"
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Annuleren</Button><Button variant="primary" onClick={save} disabled={!f.title}>Toevoegen</Button></>}>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Titel" className="col-span-2"><Input value={f.title || ""} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field label="Soort"><Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="datagedreven">Datagedreven</option><option value="innovatiehypothese">Innovatiehypothese</option></Select></Field>
        <Field label="Categorie"><Select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{SUGGESTION_CATEGORIES.map((c) => <option key={c}>{c}</option>)}</Select></Field>
        <Field label="Samenvatting" className="col-span-2"><Textarea rows={3} value={f.summary || ""} onChange={(e) => setF({ ...f, summary: e.target.value })} /></Field>
      </div>
    </Dialog>
  );
}
