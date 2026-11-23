import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Printer, ShieldCheck, ShieldAlert, Swords, MessageCircleQuestion, TrendingUp, FileText, GitCompare, Calculator, ListChecks, Flag } from "lucide-react";
import { api } from "@/lib/api";
import { cn, date, pct } from "@/lib/utils";
import { MODULES, tileStyle } from "@/lib/modules";
import { ProviderLogo } from "./common";
import { Badge, Button, Card, EmptyState, Loading } from "./ui/primitives";

/* ------------------------------------------------------------------ Concurrentiekaart */
export function Battlecard({ providerId, print }: { providerId: number; print?: boolean }) {
  const { data } = useQuery({ queryKey: ["battlecard", providerId], queryFn: () => api.get(`/insights/battlecard/${providerId}`) });
  if (!data) return <Loading />;
  const p = data.provider;
  return (
    <div className="space-y-6">
      {!print && (
        <div className="flex items-center justify-between">
          <p className="max-w-2xl text-[13px] text-ink-muted">Eén overzicht voor adviseurs en sales. {data.note}</p>
          <a href={`/concurrenten/${providerId}/kaart`} target="_blank" rel="noreferrer"><Button icon={<Printer className="h-4 w-4" />}>Afdrukken of opslaan als PDF</Button></a>
        </div>
      )}
      <div className="relative overflow-hidden rounded-3xl border border-line bg-white p-7 shadow-soft print-page">
        <div aria-hidden className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full opacity-60 blur-3xl" style={{ background: "radial-gradient(circle, rgba(10,124,255,0.18), transparent 65%)" }} />
        <div className="relative flex flex-wrap items-center gap-4">
          <ProviderLogo name={p.name} logoUrl={p.logo_url} id={p.id} isReference={p.is_reference} size={52} />
          <div className="flex-1">
            <div className="text-[12px] font-semibold uppercase tracking-wide" style={{ color: MODULES.concurrenten.color }}>Concurrentiekaart</div>
            <h2 className="text-[26px] font-semibold tracking-tightest">{p.name}</h2>
            <div className="text-[12.5px] text-ink-muted">{p.provider_type} · opgesteld {date(data.generated_at, true)}{data.last_change && ` · laatste voorwaardenwijziging ${date(data.last_change.created_at)}`}</div>
          </div>
        </div>
        {(p.strengths || p.weaknesses) && (
          <div className="relative mt-5 grid grid-cols-1 gap-3 md:grid-cols-2">
            {p.strengths && <div className="rounded-2xl bg-surface p-4 text-[13px]"><div className="mb-1 font-semibold">Gedocumenteerde sterke punten</div><p className="whitespace-pre-wrap text-ink-soft">{p.strengths}</p></div>}
            {p.weaknesses && <div className="rounded-2xl bg-surface p-4 text-[13px]"><div className="mb-1 font-semibold">Gedocumenteerde zwakke punten</div><p className="whitespace-pre-wrap text-ink-soft">{p.weaknesses}</p></div>}
          </div>
        )}
      </div>
      {data.products.length === 0 && <Card><EmptyState title="Nog geen producten" description="Voeg producten toe om een concurrentiekaart op te stellen." /></Card>}
      {data.products.map((c: any) => (
        <div key={c.product.id} className="print-page space-y-4 break-inside-avoid-page">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-[18px] font-semibold tracking-tight">{c.product.name}</h3>
            <span className="text-[12.5px] text-ink-muted">{c.vetera_product ? `vergeleken met ${c.vetera_product.name}` : "geen Vetera-product in deze categorie"}{c.risk_carrier && ` · risicodrager ${c.risk_carrier}`} · {c.known_features} kenmerken vastgesteld</span>
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Panel icon={<TrendingUp />} color={MODULES.premielab.color} title="Prijsniveau">
              {c.price.avg_diff_pct === null ? <p className="text-[12.5px] text-ink-muted">Geen vergelijkbare premies met Vetera vastgelegd.</p> : (
                <>
                  <div className="text-[28px] font-semibold tracking-tightest tabular">{pct(c.price.avg_diff_pct)}</div>
                  <div className="text-[12.5px] text-ink-soft">gemiddeld {c.price.level}</div>
                  <ul className="mt-2 space-y-0.5 text-[11.5px] text-ink-muted">{c.price.observations.map((o: any) => <li key={o.profile}>{o.profile}: {pct(o.diff_pct)}{!o.comparable && " (beperkt vergelijkbaar)"}</li>)}</ul>
                </>
              )}
            </Panel>
            <Panel icon={<ShieldCheck />} color="#1f7a3a" title={`Waar ${p.name} sterker is`}>
              {c.strengths.length ? <ul className="space-y-1.5 text-[12.5px]">{c.strengths.slice(0, 7).map((s: any, i: number) => <li key={i}><b className="font-medium">{s.feature}</b><div className="text-ink-muted">{short(s.text)}</div></li>)}{c.strengths.length > 7 && <li className="text-ink-faint">+ {c.strengths.length - 7} meer</li>}</ul> : <p className="text-[12.5px] text-ink-muted">Geen aantoonbare punten vastgesteld.</p>}
            </Panel>
            <Panel icon={<ShieldAlert />} color="#b3261e" title={`Waar ${p.name} beperkter is`}>
              {c.weaknesses.length ? <ul className="space-y-1.5 text-[12.5px]">{c.weaknesses.slice(0, 7).map((s: any, i: number) => <li key={i}><b className="font-medium">{s.feature}</b><div className="text-ink-muted">{short(s.text)}</div></li>)}{c.weaknesses.length > 7 && <li className="text-ink-faint">+ {c.weaknesses.length - 7} meer</li>}</ul> : <p className="text-[12.5px] text-ink-muted">Geen aantoonbare punten vastgesteld.</p>}
            </Panel>
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.4fr_1fr]">
            <Panel icon={<Swords />} color={MODULES.advies.color} title="Beste tegenargumenten">
              {c.arguments.length ? (
                <ol className="space-y-2.5 text-[12.5px]">
                  {c.arguments.map((a: any, i: number) => (
                    <li key={i} className="flex gap-2.5"><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white" style={{ background: MODULES.advies.color }}>{i + 1}</span><div><div className="font-medium">{a.fact}</div><div className="text-ink-muted">{a.sales_argument}</div></div></li>
                  ))}
                </ol>
              ) : <p className="text-[12.5px] text-ink-muted">Nog geen aantoonbare voordelen van Vetera ten opzichte van dit product.</p>}
              {c.unknown_count > 0 && <p className="mt-3 text-[11.5px] text-ink-faint">{c.unknown_count} kenmerk(en) onbekend en niet meegewogen.</p>}
            </Panel>
            <Panel icon={<MessageCircleQuestion />} color={MODULES.voorwaarden.color} title="Vragen voor het klantgesprek">
              <ul className="space-y-1 text-[12.5px] text-ink-soft">{c.advisor_questions.map((q: string) => <li key={q}>• {q}</li>)}</ul>
            </Panel>
          </div>
        </div>
      ))}
    </div>
  );
}

// "X biedt … een ruimere regeling (gedekt tegenover voorwaardelijk bij Vetera)." → alleen het deel tussen haakjes
function short(t: string) {
  const m = t.match(/\((.*)\)/);
  return m ? m[1] : t;
}

function Panel({ icon, color, title, children }: { icon: React.ReactNode; color: string; title: string; children: React.ReactNode }) {
  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center gap-2.5">
        <span className="flex h-7 w-7 items-center justify-center rounded-[8px] text-white [&_svg]:h-3.5 [&_svg]:w-3.5" style={tileStyle(color)}>{icon}</span>
        <span className="text-[13.5px] font-semibold">{title}</span>
      </div>
      {children}
    </Card>
  );
}

/* ------------------------------------------------------------------ Tijdlijn */
const EV: Record<string, { label: string; icon: any; color: string }> = {
  wijziging: { label: "Voorwaardenwijziging", icon: GitCompare, color: MODULES.marktmonitor.color },
  document: { label: "Document", icon: FileText, color: MODULES.bronnen.color },
  premie: { label: "Premie", icon: Calculator, color: MODULES.premielab.color },
  bevinding: { label: "Bevinding", icon: ListChecks, color: MODULES.voorwaarden.color },
  status: { label: "Status", icon: Flag, color: "#8e8e93" },
};

export function Timeline({ providerId }: { providerId: number }) {
  const nav = useNavigate();
  const { data } = useQuery({ queryKey: ["timeline", providerId], queryFn: () => api.get(`/insights/timeline/${providerId}`) });
  const [off, setOff] = React.useState<string[]>([]);
  if (!data) return <Loading />;
  const events = data.events.filter((e: any) => !off.includes(e.type));
  let lastMonth = "";
  return (
    <div>
      <div className="mb-5 flex flex-wrap gap-1.5">
        {Object.entries(EV).map(([k, v]) => {
          const on = !off.includes(k);
          const n = data.events.filter((e: any) => e.type === k).length;
          return (
            <button key={k} onClick={() => setOff((o) => (on ? [...o, k] : o.filter((x) => x !== k)))} className={cn("inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] transition-colors", on ? "border-transparent text-white" : "border-line text-ink-muted")} style={on ? { background: v.color } : undefined}>
              <v.icon className="h-3 w-3" /> {v.label} <span className="opacity-75 tabular">{n}</span>
            </button>
          );
        })}
      </div>
      {events.length === 0 ? <Card><EmptyState title="Nog geen gebeurtenissen" description="Documenten, wijzigingen, premies en bevindingen voor deze aanbieder verschijnen hier op volgorde." /></Card> : (
        <div className="relative pl-8">
          <div className="absolute bottom-2 left-[13px] top-2 w-px bg-line" />
          {events.map((e: any, i: number) => {
            const m = new Date(e.date).toLocaleDateString("nl-NL", { month: "long", year: "numeric" });
            const head = m !== lastMonth ? m : null;
            lastMonth = m;
            const t = EV[e.type];
            return (
              <React.Fragment key={i}>
                {head && <div className="relative -ml-8 mb-2 mt-5 first:mt-0 pl-8 text-[12px] font-semibold capitalize text-ink-muted">{head}</div>}
                <div className="relative mb-2.5">
                  <span className="absolute -left-8 top-2.5 flex h-[26px] w-[26px] items-center justify-center rounded-full ring-4 ring-white" style={tileStyle(t.color)}><t.icon className="h-3 w-3 text-white" /></span>
                  <button disabled={!e.link} onClick={() => e.link && nav(e.link)} className="block w-full rounded-xl border border-line bg-white px-4 py-2.5 text-left shadow-soft transition-colors enabled:hover:bg-surface/60">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-[13px] font-medium">{e.title}</span>
                      <span className="shrink-0 text-[11.5px] text-ink-faint">{date(e.date)}</span>
                    </div>
                    {e.detail && <div className="mt-0.5 text-[12px] text-ink-muted">{e.detail}{e.historical && <Badge className="ml-2">historisch</Badge>}</div>}
                  </button>
                </div>
              </React.Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
}
