import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { Check, X, HelpCircle, CircleDashed, RotateCcw, MessageCircleQuestion, ChevronDown } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ProviderLogo, SourceRef } from "@/components/common";
import { Badge, Button, Card, EmptyState, Loading, Notice, PageHeader } from "@/components/ui/primitives";

const VERDICT: Record<string, { label: string; tone: any; ring: string }> = {
  past: { label: "Past goed", tone: "positive", ring: "#1f7a3a" },
  past_mogelijk: { label: "Past mogelijk", tone: "caution", ring: "#c27c00" },
  onvoldoende_gegevens: { label: "Onvoldoende gegevens", tone: "neutral", ring: "#a1a1a6" },
  past_niet: { label: "Past niet", tone: "negative", ring: "#b3261e" },
};
const FIT_ICON: Record<string, { icon: any; cls: string; label: string }> = {
  ja: { icon: Check, cls: "bg-positive-soft text-positive", label: "Ja" },
  mogelijk: { icon: CircleDashed, cls: "bg-caution-soft text-caution", label: "Onder voorwaarden" },
  nee: { icon: X, cls: "bg-negative-soft text-negative", label: "Nee" },
  onbekend: { icon: HelpCircle, cls: "bg-surface text-ink-faint", label: "Onbekend" },
};

export default function Advice() {
  const nav = useNavigate();
  const qs = useQuery({ queryKey: ["advice-questions"], queryFn: () => api.get<any[]>("/insights/advice/questions") });
  const [answers, setAnswers] = React.useState<Record<string, any>>({ vehicle_category: "auto", value: "midden", usage: ["hobby"], activities: [], collection: "nee", second_vehicle: "ja" });
  const result = useQuery({ queryKey: ["advice", answers], queryFn: () => api.post("/insights/advice", { answers }), placeholderData: (p) => p });
  const [open, setOpen] = React.useState<number | null>(null);
  const toggle = (k: string, v: string, multi: boolean) =>
    setAnswers((a) => (multi ? { ...a, [k]: (a[k] || []).includes(v) ? a[k].filter((x: string) => x !== v) : [...(a[k] || []), v] } : { ...a, [k]: v }));

  return (
    <div>
      <PageHeader module="advies" title="Adviestool" subtitle="Beantwoord een paar vragen over de klant. De tool laat zien welke producten aantoonbaar passen en waarom — met bronnen, zonder onbekende onderdelen als ‘niet verzekerd’ te tellen." />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[400px_1fr]">
        <Card className="h-fit p-5 xl:sticky xl:top-6">
          {!qs.data ? <Loading /> : (
            <div className="space-y-5">
              {qs.data.map((q) => (
                <div key={q.key}>
                  <div className="mb-2 text-[13px] font-semibold">{q.label}{q.type === "multi" && <span className="ml-1 font-normal text-ink-faint">(meerdere mogelijk)</span>}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {q.options.map(([v, l]: [string, string]) => {
                      const on = q.type === "multi" ? (answers[q.key] || []).includes(v) : answers[q.key] === v;
                      return (
                        <button key={v} onClick={() => toggle(q.key, v, q.type === "multi")} className={cn("rounded-full border px-3 py-1.5 text-[12.5px] transition-all", on ? "border-transparent text-white shadow-sm" : "border-line text-ink-soft hover:border-line-strong")} style={on ? { background: "#e8476a" } : undefined}>
                          {l}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
              <Button variant="ghost" size="sm" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => setAnswers({ vehicle_category: "auto", value: "midden", usage: ["hobby"], activities: [], collection: "nee", second_vehicle: "ja" })}>Opnieuw beginnen</Button>
            </div>
          )}
        </Card>
        <div className="space-y-4">
          {!result.data ? <Loading /> : result.data.results.length === 0 ? (
            <Card><EmptyState title="Geen actieve producten in deze categorie" description="Voeg producten toe en zet aanbieders op ‘actief’." action={<Button onClick={() => nav("/concurrenten")}>Naar concurrenten</Button>} /></Card>
          ) : (
            <>
              <Notice tone="neutral" icon={<HelpCircle />}>{result.data.note}</Notice>
              {result.data.results.map((r: any, i: number) => {
                const v = VERDICT[r.verdict];
                const isOpen = open === r.id;
                return (
                  <motion.div key={r.id} layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
                    <Card className="overflow-hidden">
                      <button onClick={() => setOpen(isOpen ? null : r.id)} className="flex w-full items-center gap-4 p-5 text-left">
                        <MatchRing value={r.match} color={v.ring} />
                        <ProviderLogo name={r.provider_name} logoUrl={r.logo} id={r.provider_id} isReference={r.is_reference} size={36} />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2"><span className="text-[15px] font-semibold">{r.provider_name}</span>{r.is_reference && <Badge tone="accent">Vetera</Badge>}<Badge tone={v.tone}>{v.label}</Badge></div>
                          <div className="text-[12.5px] text-ink-muted">{r.name} · {r.known_share}% van de wensen vastgesteld{r.blockers ? ` · ${r.blockers} knelpunt(en)` : ""}</div>
                        </div>
                        <div className="hidden gap-1 md:flex">
                          {r.rows.slice(0, 8).map((x: any) => { const f = FIT_ICON[x.fit]; return <span key={x.feature_key} title={`${x.need}: ${f.label}`} className={cn("flex h-6 w-6 items-center justify-center rounded-full", f.cls)}><f.icon className="h-3 w-3" /></span>; })}
                        </div>
                        <ChevronDown className={cn("h-4 w-4 text-ink-faint transition-transform", isOpen && "rotate-180")} />
                      </button>
                      {isOpen && (
                        <div className="border-t border-line">
                          {r.rows.map((x: any) => {
                            const f = FIT_ICON[x.fit];
                            return (
                              <div key={x.feature_key} className="grid grid-cols-[28px_1fr_auto] items-start gap-3 border-b border-line px-5 py-3 last:border-0">
                                <span className={cn("mt-0.5 flex h-6 w-6 items-center justify-center rounded-full", f.cls)}><f.icon className="h-3 w-3" /></span>
                                <div className="min-w-0">
                                  <div className="text-[13px] font-medium">{x.need}</div>
                                  <div className="text-[12px] text-ink-muted">{x.feature}: {x.status_label}{x.value_text ? ` · ${x.value_text}` : ""}</div>
                                </div>
                                {x.finding?.document_version_id && <SourceRef versionId={x.finding.document_version_id} page={x.finding.page_number} article={x.finding.article} quote={x.finding.quote} />}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </Card>
                  </motion.div>
                );
              })}
              <Card className="p-5">
                <div className="mb-2 flex items-center gap-2 text-[14px] font-semibold"><MessageCircleQuestion className="h-4 w-4" style={{ color: "#e8476a" }} /> Vragen om de klant te stellen</div>
                <ul className="space-y-1 text-[13px] text-ink-soft">{result.data.advisor_questions.map((q: string) => <li key={q}>• {q}</li>)}</ul>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function MatchRing({ value, color }: { value: number; color: string }) {
  const r = 18, c = 2 * Math.PI * r;
  return (
    <div className="relative h-12 w-12 shrink-0">
      <svg viewBox="0 0 44 44" className="h-12 w-12 -rotate-90">
        <circle cx="22" cy="22" r={r} fill="none" stroke="#ececef" strokeWidth="4" />
        <circle cx="22" cy="22" r={r} fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" strokeDasharray={`${(value / 100) * c} ${c}`} style={{ transition: "stroke-dasharray .5s ease" }} />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-[11.5px] font-semibold tabular">{value}%</span>
    </div>
  );
}
