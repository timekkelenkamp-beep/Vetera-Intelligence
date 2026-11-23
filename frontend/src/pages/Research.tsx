import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search, Sparkles, FileText, AlertTriangle, ShieldCheck, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { eur } from "@/lib/utils";
import { useAiAction, useAiStatus } from "@/components/AiAction";
import { SourceRef } from "@/components/common";
import { Badge, Button, Card, CardHeader, EmptyState, Loading, Notice, PageHeader } from "@/components/ui/primitives";

export default function Research() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const q = params.get("q") || "";
  const [input, setInput] = React.useState(q);
  const [result, setResult] = React.useState<any>(null);
  const ai = useAiStatus();
  const ask = useAiAction("/ai/ask", { onDone: setResult });
  const local = useQuery({ queryKey: ["search", q], queryFn: () => api.get<any[]>("/search", { q }), enabled: q.length > 1 });
  React.useEffect(() => setInput(q), [q]);
  React.useEffect(() => setResult(null), [q]);

  const ans = result?.answer;
  const items = result?.context_items || {};
  const val = result?.validation;

  const Ref = ({ r }: { r: string }) => {
    const it = items[r];
    if (!it) return <Badge tone="negative">{r} · onbekend</Badge>;
    if (it.document_version_id) return <SourceRef versionId={it.document_version_id} page={it.page_number} label={r} />;
    if (it.type === "premium") return <button onClick={() => nav("/premielab")} className="text-[11.5px] font-medium text-accent hover:underline">{r}</button>;
    return <span className="text-[11.5px] text-ink-muted">{r}</span>;
  };

  return (
    <div>
      <PageHeader eyebrow="AI-onderzoeksassistent" title="Onderzoek" subtitle="Antwoorden worden uitsluitend gebaseerd op de gegevens in deze applicatie, met bronverwijzingen en expliciete onzekerheden." />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (input.trim()) setParams({ q: input.trim() });
        }}
        className="mb-8 flex gap-2"
      >
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Wat wil je onderzoeken?" className="h-11 w-full rounded-xl border border-line-strong bg-white pl-10 pr-3 text-[14.5px] focus:outline-none focus:border-accent focus:shadow-ring" />
        </div>
        <Button type="submit" size="lg" variant="secondary">Zoeken</Button>
      </form>

      {q && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_380px]">
          <div className="space-y-6">
            {!result && (
              <Card className="p-6">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <div className="text-[15px] font-semibold">“{q}”</div>
                    <p className="mt-1 text-[13px] text-ink-muted">
                      {ai.data?.available ? "Laat AI deze vraag beantwoorden op basis van de vastgelegde bevindingen, premies en documenten." : ai.data?.message}
                    </p>
                  </div>
                  <Button variant="primary" icon={<Sparkles className="h-4 w-4" />} loading={ask.busy} onClick={() => ask.start({ question: q })}>
                    Analyseer met AI
                  </Button>
                </div>
              </Card>
            )}
            {ans && (
              <>
                <Card className="p-6">
                  <div className="mb-2 flex items-center gap-2 text-[12px] font-medium text-ink-muted"><Sparkles className="h-3.5 w-3.5 text-accent" /> Kort antwoord</div>
                  <p className="text-[16px] leading-relaxed text-ink">{ans.short_answer}</p>
                  <div className="mt-4 flex flex-wrap items-center gap-2 text-[12px] text-ink-muted">
                    {val?.ok && !val?.unknown_inline_refs?.length ? (
                      <Badge tone="positive"><ShieldCheck className="h-3 w-3" /> Bronnen gecontroleerd</Badge>
                    ) : (
                      <Badge tone="caution"><AlertTriangle className="h-3 w-3" /> Niet alle bronnen verifieerbaar</Badge>
                    )}
                    <span>Kosten ≈ {eur(result.cost_eur)}</span>
                  </div>
                </Card>
                <Section title="Belangrijkste bevindingen" list={ans.key_findings?.map((f: any) => (
                  <span>{f.text} <span className="ml-1 inline-flex flex-wrap gap-1">{f.refs?.map((r: string) => <Ref key={r} r={r} />)}</span></span>
                ))} />
                {ans.comparison?.length > 0 && (
                  <Card>
                    <CardHeader title="Vergelijking" />
                    <div className="divide-y divide-line px-5 pb-3">
                      {ans.comparison.map((c: any, i: number) => (
                        <div key={i} className="py-3 text-[13.5px]">
                          <div className="font-medium">{c.subject}</div>
                          <div className="mt-0.5 text-ink-soft">{c.details}</div>
                          <div className="mt-1 flex flex-wrap gap-1">{c.refs?.map((r: string) => <Ref key={r} r={r} />)}</div>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}
                <Section title="Gevolgen voor Vetera" list={ans.implications_for_vetera} />
                <Card>
                  <CardHeader title="Bronnen" subtitle="Iedere verwijzing is gecontroleerd tegen de lokale gegevens" />
                  <ul className="divide-y divide-line px-5 pb-3">
                    {(val?.sources || []).map((s: any, i: number) => (
                      <li key={i} className="flex items-start justify-between gap-3 py-2.5 text-[13px]">
                        <div className="min-w-0">
                          <Ref r={s.ref} />
                          {ans.sources?.[i]?.quote && <div className="mt-1 text-[12.5px] italic text-ink-muted">“{ans.sources[i].quote}”</div>}
                        </div>
                        {!s.exists ? <Badge tone="negative">Bron bestaat niet</Badge> : s.quote_verified === false ? <Badge tone="caution">Citaat niet gevonden</Badge> : s.quote_verified ? <Badge tone="positive">Citaat geverifieerd</Badge> : null}
                      </li>
                    ))}
                  </ul>
                </Card>
                <Section title="Onzekerheden" list={ans.uncertainties} tone="caution" />
                <Section title="Ontbrekende gegevens" list={ans.missing_data} />
                <Section title="Mogelijke vervolgstappen" list={ans.next_steps} />
              </>
            )}
          </div>
          <div>
            <Card>
              <CardHeader title="Gevonden in documenten" subtitle="Lokale zoekopdracht, zonder AI" />
              {local.isLoading ? (
                <Loading />
              ) : !local.data?.length ? (
                <EmptyState icon={<FileText />} title="Geen passages gevonden" description="Probeer andere zoektermen, bijvoorbeeld een dekking of clausule." />
              ) : (
                <ul className="divide-y divide-line px-5 pb-3">
                  {local.data.map((h) => (
                    <li key={h.page_id} className="py-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-[12.5px] font-medium">{h.provider_name || "–"} · {h.document_title}</span>
                        <SourceRef versionId={h.version_id} page={h.page_number} />
                      </div>
                      <p className="mt-1 text-[12.5px] leading-relaxed text-ink-muted" dangerouslySetInnerHTML={{ __html: escapeSnippet(h.snippet) }} />
                      {!h.is_current && <Badge tone="neutral" className="mt-1">eerdere versie</Badge>}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}
      {!q && (
        <EmptyState icon={<Search />} title="Stel een onderzoeksvraag" description="Bijvoorbeeld: “Welke concurrenten bieden een collectiepolis?”" action={<Button variant="ghost" onClick={() => nav("/")}>Terug naar dashboard <ArrowRight className="h-3.5 w-3.5" /></Button>} />
      )}
      {ask.dialog}
    </div>
  );
}

function escapeSnippet(s: string) {
  const e = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return e.replace(/\[\[/g, '<mark class="mark-hit">').replace(/\]\]/g, "</mark>");
}

function Section({ title, list, tone }: { title: string; list?: React.ReactNode[]; tone?: "caution" }) {
  if (!list?.length) return null;
  return tone === "caution" ? (
    <Notice tone="caution" title={title} icon={<AlertTriangle />}>
      <ul className="mt-1 space-y-1">{list.map((x, i) => <li key={i}>• {x}</li>)}</ul>
    </Notice>
  ) : (
    <Card>
      <CardHeader title={title} />
      <ul className="space-y-2 px-5 pb-5 text-[13.5px] leading-relaxed text-ink-soft">{list.map((x, i) => <li key={i} className="flex gap-2"><span className="text-ink-faint">•</span><span>{x}</span></li>)}</ul>
    </Card>
  );
}
