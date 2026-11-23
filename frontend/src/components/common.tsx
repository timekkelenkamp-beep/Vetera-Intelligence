import * as React from "react";
import { FileText, ShieldCheck, ShieldAlert } from "lucide-react";
import { cn, initials } from "@/lib/utils";
import { FINDING_STATUS } from "@/lib/labels";
import { Badge, Tip } from "./ui/primitives";
import { useSourceViewer } from "./SourceViewer";

export function ProviderLogo({ name, logoUrl, size = 36, className }: { name: string; logoUrl?: string | null; size?: number; className?: string }) {
  const [failed, setFailed] = React.useState(false);
  if (logoUrl && !failed) {
    return (
      <div className={cn("flex items-center justify-center shrink-0", className)} style={{ width: size * 2.2, height: size }}>
        <img src={logoUrl} alt={`Logo ${name}`} onError={() => setFailed(true)} className="max-h-full max-w-full object-contain" />
      </div>
    );
  }
  // Nette tekstweergave zolang er geen goedgekeurd officieel logo is (geen nagemaakt logo).
  return (
    <div
      className={cn("flex items-center justify-center shrink-0 rounded-[10px] bg-surface text-ink-soft font-semibold tracking-tight", className)}
      style={{ width: size, height: size, fontSize: size * 0.36 }}
      aria-label={name}
    >
      {initials(name) || "?"}
    </div>
  );
}

export function FindingStatus({ status, compact }: { status?: string | null; compact?: boolean }) {
  if (!status) return <span className="text-[12px] text-ink-faint">Geen gegevens</span>;
  const s = FINDING_STATUS[status] || { label: status, short: status, tone: "neutral" as const };
  return (
    <Badge tone={s.tone} dot>
      {compact ? s.short : s.label}
    </Badge>
  );
}

export function SourceRef({ versionId, page, quote, article, label, className }: { versionId?: number | null; page?: number | null; quote?: string | null; article?: string | null; label?: string; className?: string }) {
  const viewer = useSourceViewer();
  if (!versionId) return null;
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        viewer.open({ versionId, page: page || 1, quote: quote || undefined });
      }}
      className={cn("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11.5px] font-medium text-accent hover:bg-accent-soft transition-colors", className)}
    >
      <FileText className="h-3 w-3" />
      {label || (page ? `p. ${page}${article ? ` · art. ${article}` : ""}` : "document")}
    </button>
  );
}

export function VerifiedMark({ verified }: { verified?: boolean | null }) {
  if (verified === null || verified === undefined) return null;
  return verified ? (
    <Tip content="Citaat teruggevonden in de geëxtraheerde brontekst">
      <ShieldCheck className="h-3.5 w-3.5 text-positive" />
    </Tip>
  ) : (
    <Tip content="Citaat niet teruggevonden in de brontekst — controle nodig">
      <ShieldAlert className="h-3.5 w-3.5 text-caution" />
    </Tip>
  );
}

export function OriginBadge({ origin, review }: { origin: string; review?: string }) {
  const map: Record<string, string> = { handmatig: "Handmatig", ai: "AI", lokaal: "Passagezoeker" };
  const reviewed = review === "goedgekeurd" || review === "gecorrigeerd";
  return (
    <span className={cn("text-[11px]", reviewed ? "text-positive" : "text-ink-faint")}>
      {map[origin] || origin}
      {reviewed ? " · gecontroleerd" : origin !== "handmatig" ? " · ongecontroleerd" : ""}
    </span>
  );
}

export function useDebounced<T>(value: T, ms = 250) {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
