import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ExternalLink, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { normalizeForSearch } from "@/lib/text";
import { Sheet } from "./ui/overlay";
import { Button, Loading, Notice, Segmented } from "./ui/primitives";

type Target = { versionId: number; page: number; quote?: string };
const Ctx = React.createContext<{ open: (t: Target) => void }>({ open: () => {} });
export const useSourceViewer = () => React.useContext(Ctx);

function highlight(text: string, quote?: string) {
  if (!quote) return [text];
  // Zoek het citaat tolerant voor witruimte; markeer het in de originele tekst.
  const words = normalizeForSearch(quote).split(" ").filter(Boolean);
  if (words.length < 2) return [text];
  const pattern = words.slice(0, 40).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("[\\s\\W]{1,6}");
  try {
    const re = new RegExp(pattern, "i");
    const m = re.exec(text);
    if (!m) return [text];
    return [text.slice(0, m.index), <mark key="h" className="mark-hit">{m[0]}</mark>, text.slice(m.index + m[0].length)];
  } catch {
    return [text];
  }
}

export function SourceViewerProvider({ children }: { children: React.ReactNode }) {
  const [target, setTarget] = React.useState<Target | null>(null);
  const [page, setPage] = React.useState(1);
  const [mode, setMode] = React.useState<"beide" | "pdf" | "tekst">("beide");
  const open = React.useCallback((t: Target) => {
    setTarget(t);
    setPage(t.page || 1);
  }, []);
  const version = useQuery({ queryKey: ["version", target?.versionId], queryFn: () => api.get(`/document-versions/${target!.versionId}`), enabled: !!target });
  const pages = useQuery({ queryKey: ["pages", target?.versionId], queryFn: () => api.get<any[]>(`/document-versions/${target!.versionId}/pages`), enabled: !!target });
  const current = pages.data?.find((p) => p.page_number === page);
  const total = version.data?.page_count || pages.data?.length || 1;
  const fileUrl = target ? `/api/document-versions/${target.versionId}/file#page=${page}&view=FitH` : "";
  const textRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    textRef.current?.querySelector("mark")?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [current, target?.quote]);

  return (
    <Ctx.Provider value={{ open }}>
      {children}
      <Sheet
        open={!!target}
        onOpenChange={(v) => !v && setTarget(null)}
        title={version.data?.document?.title || "Bron"}
        subtitle={
          version.data
            ? `${version.data.document?.provider_name || "Aanbieder onbekend"} · versie ${version.data.version_label || "–"} · ${total} pagina's`
            : undefined
        }
        width="min(1180px, 96vw)"
      >
        {!version.data ? (
          <Loading />
        ) : (
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between gap-3 border-b border-line px-6 py-2.5">
              <div className="flex items-center gap-1.5">
                <Button size="icon" variant="ghost" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} aria-label="Vorige pagina">
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-[13px] tabular text-ink-soft">
                  Pagina {page} van {total}
                </span>
                <Button size="icon" variant="ghost" onClick={() => setPage((p) => Math.min(total, p + 1))} disabled={page >= total} aria-label="Volgende pagina">
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <Segmented value={mode} onChange={setMode} options={[{ value: "beide", label: "Naast elkaar" }, { value: "pdf", label: "PDF" }, { value: "tekst", label: "Tekst" }]} />
                <a href={fileUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[12.5px] text-accent hover:underline">
                  Openen <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            </div>
            <div className="flex flex-1 min-h-0">
              {mode !== "tekst" && (
                <div className={mode === "beide" ? "w-[58%] border-r border-line bg-surface" : "w-full bg-surface"}>
                  <iframe key={fileUrl} title="PDF" src={fileUrl} className="h-full w-full" />
                </div>
              )}
              {mode !== "pdf" && (
                <div ref={textRef} className="flex-1 overflow-y-auto px-6 py-5">
                  <div className="mb-3 text-[11.5px] font-medium uppercase tracking-wide text-ink-faint">Geëxtraheerde tekst</div>
                  {current?.quality === "onbetrouwbaar" && (
                    <Notice tone="caution" icon={<AlertTriangle />} className="mb-4">
                      Tekstextractie van deze pagina is onbetrouwbaar (mogelijk gescand). Controleer de PDF.
                    </Notice>
                  )}
                  {target?.quote && (
                    <div className="mb-4 rounded-xl bg-surface px-4 py-3 text-[12.5px] text-ink-soft">
                      <span className="font-medium text-ink">Gezocht citaat:</span> “{target.quote.slice(0, 400)}”
                    </div>
                  )}
                  <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-ink">{current ? highlight(current.text, target?.quote) : "Geen tekst beschikbaar."}</pre>
                </div>
              )}
            </div>
          </div>
        )}
      </Sheet>
    </Ctx.Provider>
  );
}
