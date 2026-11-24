import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Search, Sparkles, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { useAiAction } from "./AiAction";
import { JobProgress, useJob } from "./Job";
import { Dialog } from "./ui/overlay";
import { Button, Field, Input, Notice, Switch } from "./ui/primitives";

/** Naam invullen → opzoeken → officiële website doorzoeken → importeren → (optioneel) analyseren. */
export function AddByNameDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [name, setName] = React.useState("");
  const [analyze, setAnalyze] = React.useState(true);
  const [jobId, setJobId] = React.useState<number | null>(null);
  const [done, setDone] = React.useState<any>(null);
  const job = useJob(jobId, (j) => {
    setJobId(null);
    setDone(j);
    ["providers", "provider", "products", "documents", "dashboard", "premiums", "matrix", "findings"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  });
  const action = useAiAction("/ai/add-by-name", { onDone: (r: any) => setJobId(r.job_id) });
  React.useEffect(() => { if (open && !jobId) { setDone(null); } }, [open]); // eslint-disable-line
  const reset = () => { setDone(null); setName(""); };
  const r = done?.result;

  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="lg"
      title={<span className="flex items-center gap-2"><Search className="h-4 w-4 text-accent" /> Aanbieder opzoeken en verwerken</span>}
      description="Vul alleen een naam in. De app zoekt de officiële website, haalt producten en polisvoorwaarden op en zet alles klaar om te beoordelen."
      footer={done ? (
        <>
          <Button variant="ghost" onClick={reset}>Nog een opzoeken</Button>
          {r?.provider_id && <Button variant="primary" onClick={() => { onOpenChange(false); nav(`/concurrenten/${r.provider_id}`); }}>Openen</Button>}
        </>
      ) : jobId ? (
        <Button variant="ghost" onClick={() => onOpenChange(false)}>Op de achtergrond laten doorgaan</Button>
      ) : (
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Annuleren</Button>
          <Button variant="primary" icon={<Sparkles className="h-3.5 w-3.5" />} loading={action.busy} disabled={name.trim().length < 2} onClick={() => action.start({ name: name.trim(), analyze })}>Opzoeken</Button>
        </>
      )}>
      {jobId ? (
        <JobProgress job={job} title={`${name} wordt opgezocht en verwerkt`} />
      ) : done ? (
        done.status === "fout" ? (
          <Notice tone="caution" icon={<AlertTriangle />} title="Niet gelukt">{done.error}</Notice>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-[15px] font-semibold"><CheckCircle2 className="h-5 w-5 text-positive" /> {r.provider_name} is verwerkt</div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {Object.entries({ Producten: r.created.products, Documenten: r.created.documents, Premies: r.created.premiums, Calculators: r.created.calculators }).map(([k, v]) => (
                <div key={k} className="rounded-xl bg-surface px-3 py-2.5"><div className="text-[11px] text-ink-muted">{k}</div><div className="text-[20px] font-semibold tabular">{v as number}</div></div>
              ))}
            </div>
            {r.analysis?.length > 0 && (
              <div className="space-y-1">
                <div className="text-[13px] font-medium">AI-analyse van polisvoorwaarden</div>
                {r.analysis.map((a: any, i: number) => <div key={i} className="flex items-center gap-2 text-[12.5px]">{a.ok ? <CheckCircle2 className="h-3.5 w-3.5 text-positive" /> : <XCircle className="h-3.5 w-3.5 text-negative" />}<span className="truncate">{a.title}</span><span className="text-ink-muted">{a.ok ? `${a.created} bevindingen` : a.error}</span></div>)}
              </div>
            )}
            {r.errors?.length > 0 && <Notice tone="caution" icon={<AlertTriangle />} title="Niet alles gelukt">{r.errors.slice(0, 6).map((e: string) => <div key={e} className="truncate">{e}</div>)}</Notice>}
            <Notice tone="info">Alles staat op ‘te beoordelen’. Controleer de aanbieder, producten en bevindingen voordat je ze gebruikt.</Notice>
          </div>
        )
      ) : (
        <div className="space-y-4">
          <Field label="Naam van de aanbieder" hint="Bijvoorbeeld een verzekeraar, volmacht of tussenpersoon.">
            <Input id="provider-name" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Bijv. Kuiper Verzekeringen" onKeyDown={(e) => { if (e.key === "Enter" && name.trim().length > 1) action.start({ name: name.trim(), analyze }); }} />
          </Field>
          <Switch checked={analyze} onCheckedChange={setAnalyze} label="Polisvoorwaarden direct laten analyseren met AI" description="Vult de voorwaardenvergelijker in met bronverwijzingen. Kost per document ongeveer € 0,05 – € 0,50." />
          <ol className="space-y-1 text-[12.5px] text-ink-muted">
            <li>1. Officiële website en type aanbieder opzoeken</li>
            <li>2. Website doorzoeken op producten, polisvoorwaarden en gepubliceerde premies</li>
            <li>3. PDF's ophalen en verwerken, logo ophalen</li>
            <li>4. {analyze ? "Polisvoorwaarden analyseren met AI" : "(analyse overgeslagen)"}</li>
          </ol>
        </div>
      )}
      {action.dialog}
    </Dialog>
  );
}
