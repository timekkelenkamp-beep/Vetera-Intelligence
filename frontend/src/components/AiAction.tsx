import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles, Send, Lock, Globe } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { eur, num } from "@/lib/utils";
import { Dialog } from "./ui/overlay";
import { Button, Notice } from "./ui/primitives";

export function useAiStatus() {
  return useQuery({ queryKey: ["ai-status"], queryFn: () => api.get("/ai/status"), staleTime: 30_000 });
}

/**
 * Twee-staps AI-actie: eerst een preview (wat wordt er verstuurd, naar wie, geraamde kosten),
 * pas na bevestiging de echte aanroep. Zonder API-sleutel toont de dialoog dat duidelijk.
 */
export function useAiAction<T = any>(endpoint: string, opts?: { onDone?: (r: T) => void; invalidate?: string[][] }) {
  const [preview, setPreview] = React.useState<any>(null);
  const [body, setBody] = React.useState<any>(null);
  const [busy, setBusy] = React.useState(false);
  const qc = useQueryClient();

  const start = async (b: any) => {
    setBusy(true);
    try {
      const r = await api.post(endpoint, { ...b, dry_run: true });
      setBody(b);
      setPreview(r.preview);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  const confirm = async () => {
    setBusy(true);
    try {
      const r = await api.post<T>(endpoint, body);
      setPreview(null);
      opts?.invalidate?.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      qc.invalidateQueries({ queryKey: ["ai-status"] });
      opts?.onDone?.(r);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  const dialog = (
    <AiPreviewDialog preview={preview} onClose={() => setPreview(null)} onConfirm={confirm} busy={busy} />
  );
  return { start, busy, dialog };
}

const KIND_LABEL: Record<string, string> = {
  vraag: "Onderzoeksvraag", extractie: "Voorwaardenanalyse van document", verkoop: "Verkoopargumenten", radar: "Verbeterradar",
  dossier: "Verdiepend onderzoek", productonderzoek: "Automatisch onderzoek van de officiële website", opzoeken: "Aanbieder opzoeken op internet", wijziging: "Analyse van documentwijzigingen", ontdekking: "Concurrentieontdekking (webonderzoek)",
};
const ITEM_LABEL: Record<string, string> = { finding: "bevindingen", premium: "premiewaarnemingen", page: "documentpagina's", text: "overzichten", document_pages: "documentpagina's", wijzigingen: "wijzigingen", bekende_aanbieders: "bekende aanbieders", aanbieder: "aanbieder", naam: "naam" };

export function AiPreviewDialog({ preview, onClose, onConfirm, busy }: { preview: any; onClose: () => void; onConfirm: () => void; busy: boolean }) {
  if (!preview) return null;
  const st = preview.status || {};
  const items = preview.sent?.items || {};
  return (
    <Dialog
      open={!!preview}
      onOpenChange={(v) => !v && onClose()}
      size="lg"
      title={<span className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-accent" /> {KIND_LABEL[preview.kind] || "AI-analyse"}</span>}
      description="Controleer wat er naar de externe AI-dienst wordt verstuurd voordat je doorgaat."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Annuleren</Button>
          <Button variant="primary" icon={<Send className="h-3.5 w-3.5" />} onClick={onConfirm} loading={busy} disabled={!st.available}>
            Versturen en analyseren
          </Button>
        </>
      }
    >
      {!st.available && (
        <Notice tone="caution" icon={<Lock />} title="AI is niet beschikbaar" className="mb-4">
          {st.message || "AI-functies zijn uitgeschakeld in Instellingen."} De preview hieronder laat zien wat er verstuurd zou worden.
        </Notice>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-4">
        <Mini label="Bestemming" value="Anthropic API" />
        <Mini label="Model" value={preview.model} />
        <Mini label="Geraamde tokens" value={num(preview.estimated_input_tokens)} />
        <Mini label="Geraamde kosten" value={`≈ ${eur(preview.estimated_cost_eur)}`} />
      </div>
      <div className="rounded-xl border border-line p-4 text-[13px]">
        <div className="font-medium text-ink mb-2">Wat wordt verstuurd</div>
        <ul className="space-y-1 text-ink-soft">
          {Object.entries(items).map(([k, v]) => (
            <li key={k}>• {String(v)} {ITEM_LABEL[k] || k}</li>
          ))}
          {preview.sent?.document && <li>• Document: {preview.sent.document}</li>}
          <li>• {num(preview.characters)} tekens tekst in totaal</li>
          {preview.web_search && <li className="flex items-center gap-1.5"><Globe className="h-3.5 w-3.5" /> Het model mag het openbare web doorzoeken</li>}
        </ul>
        {preview.sent?.excluded_nonpublic > 0 && (
          <p className="mt-3 text-[12.5px] text-positive">
            {preview.sent.excluded_nonpublic} niet-publieke gegevens zijn uitgesloten en worden niet verstuurd.
          </p>
        )}
        {preview.sent?.nonpublic_included && <p className="mt-3 text-[12.5px] text-negative">Let op: niet-publieke gegevens worden meegestuurd (expliciete toestemming).</p>}
      </div>
      <details className="mt-3 group">
        <summary className="cursor-pointer text-[12.5px] text-accent">Toon voorbeeld van de verzonden tekst</summary>
        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-surface p-3 text-[11.5px] leading-relaxed text-ink-soft">{preview.text_excerpt}…</pre>
      </details>
      <p className="mt-4 text-[12px] text-ink-muted leading-relaxed">
        De applicatie en database draaien lokaal, maar deze AI-aanvraag gaat via internet naar {preview.destination?.split(" — ")[0]}.
        Maandverbruik tot nu toe: {eur(st.month_spend_eur)} van {eur(st.monthly_budget_eur)}.
      </p>
    </Dialog>
  );
}

function Mini({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-surface px-3 py-2.5">
      <div className="text-[11px] text-ink-muted">{label}</div>
      <div className="text-[13px] font-medium text-ink truncate tabular">{value}</div>
    </div>
  );
}
