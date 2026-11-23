import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, ShieldAlert, PlayCircle, PenLine, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { date } from "@/lib/utils";
import { ObservationForm } from "@/pages/PremiumLab";
import { useProviders } from "./forms";
import { Dialog } from "./ui/overlay";
import { Badge, Button, Card, EmptyState, Field, Input, Notice, Select, Textarea } from "./ui/primitives";

const PERM: Record<string, { label: string; tone: any }> = {
  onbekend: { label: "Onbekend", tone: "neutral" }, in_onderzoek: { label: "In onderzoek", tone: "info" },
  toegestaan: { label: "Expliciet toegestaan", tone: "positive" }, niet_toegestaan: { label: "Niet toegestaan", tone: "negative" },
};

export function Calculators() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["calculators"], queryFn: () => api.get<any[]>("/calculators") });
  const [edit, setEdit] = React.useState<any>(null);
  const [manual, setManual] = React.useState<any>(null);
  const run = async (c: any) => {
    try { await api.post(`/calculators/${c.id}/run`); } catch (e: any) { toast.message("Geen automatische berekening", { description: e.message }); }
    qc.invalidateQueries({ queryKey: ["calculators"] });
  };
  return (
    <div className="space-y-5">
      <Notice tone="caution" icon={<ShieldAlert />} title="Optionele module — alleen met toestemming">
        Automatische proefberekeningen worden uitsluitend per bron gebouwd wanneer geautomatiseerd gebruik aantoonbaar is toegestaan. Er worden nooit echte aanvragen ingediend, geen fictieve identiteiten of contactgegevens gebruikt, geen CAPTCHA's of beveiligingen omzeild en geen proxies ingezet. Er is geen garantie dat verkeer niet herleidbaar is. Zonder connector gebruik je de handmatige workflow: voer de berekening zelf uit met een rekenprofiel en leg het resultaat vast.
      </Notice>
      <div className="flex justify-end"><Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setEdit({})}>Calculator registreren</Button></div>
      {!data?.length ? <Card><EmptyState title="Nog geen calculators geregistreerd" description="Registreer openbare premiecalculators met hun gebruiksvoorwaarden en toestemmingsstatus." /></Card> : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {data.map((c) => (
            <Card key={c.id} className="p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-[15px] font-semibold">{c.name}</div>
                  <div className="text-[12.5px] text-ink-muted">{c.provider_name || "Aanbieder onbekend"}</div>
                </div>
                <Badge tone={PERM[c.permission_status].tone}>{PERM[c.permission_status].label}</Badge>
              </div>
              <div className="mt-3 space-y-1 text-[12.5px] text-ink-soft">
                {c.url && <a href={c.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-accent hover:underline">Calculator <ExternalLink className="h-3 w-3" /></a>}
                {c.terms_url && <a href={c.terms_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-accent hover:underline">Gebruiksvoorwaarden <ExternalLink className="h-3 w-3" /></a>}
                <div>Voorwaarden gecontroleerd: {date(c.terms_checked_at)}</div>
                <div>Connector: {c.implemented ? "beschikbaar" : "niet gebouwd"}</div>
                {c.permission_evidence && <div className="text-ink-muted">Onderbouwing: {c.permission_evidence}</div>}
              </div>
              <div className="mt-4 flex gap-2">
                <Button size="sm" variant="primary" icon={<PenLine className="h-3.5 w-3.5" />} onClick={() => setManual(c)}>Handmatig vastleggen</Button>
                <Button size="sm" icon={<PlayCircle className="h-3.5 w-3.5" />} onClick={() => run(c)}>Automatisch</Button>
                <Button size="sm" variant="ghost" onClick={() => setEdit(c)}>Bewerken</Button>
              </div>
              {c.log?.length > 0 && (
                <details className="mt-3 text-[12px]">
                  <summary className="cursor-pointer text-ink-muted">Controlelogboek ({c.log.length})</summary>
                  <ul className="mt-2 space-y-1">{c.log.map((l: any) => <li key={l.id} className="text-ink-soft"><span className="text-ink-faint">{date(l.at, true)}</span> · {l.action}: {l.message}</li>)}</ul>
                </details>
              )}
            </Card>
          ))}
        </div>
      )}
      <CalcForm open={!!edit} onOpenChange={(v) => !v && setEdit(null)} initial={edit?.id ? edit : undefined} />
      {manual && <ObservationForm open={!!manual} onOpenChange={(v) => !v && setManual(null)} endpoint={`/calculators/${manual.id}/manual`} defaults={{ provider_id: manual.provider_id, observation_type: "proefberekening" }} />}
    </div>
  );
}

function CalcForm({ open, onOpenChange, initial }: { open: boolean; onOpenChange: (v: boolean) => void; initial?: any }) {
  const qc = useQueryClient();
  const providers = useProviders();
  const [f, setF] = React.useState<any>({});
  React.useEffect(() => { if (open) setF(initial || { permission_status: "onbekend" }); }, [open, initial]);
  const set = (k: string) => (e: any) => setF((x: any) => ({ ...x, [k]: e.target.value }));
  const save = async () => {
    try {
      const body = { ...f, provider_id: f.provider_id ? Number(f.provider_id) : null };
      if (initial?.id) await api.patch(`/calculators/${initial.id}`, body);
      else await api.post("/calculators", body);
      qc.invalidateQueries({ queryKey: ["calculators"] });
      onOpenChange(false);
    } catch (e: any) { toast.error(e.message); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="lg" title={initial ? "Calculator bewerken" : "Calculator registreren"}
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Annuleren</Button><Button variant="primary" onClick={save}>Opslaan</Button></>}>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Naam"><Input value={f.name || ""} onChange={set("name")} /></Field>
        <Field label="Aanbieder"><Select value={f.provider_id || ""} onChange={set("provider_id")}><option value="">–</option>{providers.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
        <Field label="URL calculator"><Input value={f.url || ""} onChange={set("url")} /></Field>
        <Field label="URL gebruiksvoorwaarden"><Input value={f.terms_url || ""} onChange={set("terms_url")} /></Field>
        <Field label="Toestemmingsstatus"><Select value={f.permission_status} onChange={set("permission_status")}>{Object.entries(PERM).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</Select></Field>
        <Field label="Voorwaarden gecontroleerd op"><Input type="date" value={f.terms_checked_at || ""} onChange={set("terms_checked_at")} /></Field>
        <Field label="Onderbouwing toestemming" className="col-span-2" hint="Verplicht bij ‘toegestaan’: citeer de voorwaarden of verwijs naar schriftelijke toestemming."><Textarea rows={3} value={f.permission_evidence || ""} onChange={set("permission_evidence")} /></Field>
        <Field label="Notities" className="col-span-2"><Textarea rows={2} value={f.notes || ""} onChange={set("notes")} /></Field>
      </div>
    </Dialog>
  );
}
