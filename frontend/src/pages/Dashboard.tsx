import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { Search, ArrowRight, Building2, Package, FileCheck2, Activity, TrendingUp, Lightbulb, FlaskConical, CheckCircle2, Circle, AlarmClock, Bell } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, pct, relative } from "@/lib/utils";
import { NOTIF_TYPE } from "@/lib/labels";
import { Badge, Button, Card, CardHeader, EmptyState, Loading, Notice, Stat } from "@/components/ui/primitives";

const EXAMPLES = [
  "Waarin heeft Vetera betere voorwaarden dan GIO?",
  "Welke concurrent biedt de ruimste dekking voor klassieke motorfietsen?",
  "Vergelijk de eigen risico's van alle onderzochte aanbieders.",
  "Welke kansen liggen er voor Vetera in de oldtimermarkt?",
  "Welke relevante polisvoorwaarden zijn recent gewijzigd?",
];

export default function Dashboard() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [q, setQ] = React.useState("");
  const { data, isLoading } = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get("/dashboard") });
  const catchUp = useMutation({
    mutationFn: () => api.post("/monitor/run", { trigger: "inhaal" }),
    onSuccess: () => {
      toast.success("Inhaalcontrole gestart. Resultaten verschijnen in de Marktmonitor.");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["dashboard"] }), 3000);
    },
    onError: (e: any) => toast.error(e.message),
  });
  const submit = (text: string) => text.trim() && nav(`/onderzoek?q=${encodeURIComponent(text.trim())}`);

  if (isLoading || !data) return <Loading />;
  const c = data.counts;
  const ob = data.onboarding;
  const obSteps = [
    { done: ob.vetera_product, label: "Leg het huidige Vetera-product vast", to: "/concurrenten" },
    { done: ob.competitors, label: "Voeg concurrenten toe of laad de startlijst", to: "/concurrenten" },
    { done: ob.documents, label: "Importeer polisvoorwaarden (PDF)", to: "/bronnen" },
    { done: ob.premiums, label: "Leg premies vast of importeer een Excel-onderzoek", to: "/premielab" },
    { done: ob.ai, label: "Optioneel: koppel een Anthropic API-sleutel voor AI-analyses", to: "/instellingen" },
  ];
  const obDone = obSteps.filter((s) => s.done).length;

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="pt-6 pb-10 text-center">
        <h1 className="text-[44px] font-semibold tracking-tightest text-ink leading-none">Vetera Intelligence</h1>
        <p className="mt-3 text-[16px] text-ink-muted">Concurrentie-inzicht voor klassieke auto's, motorfietsen en bromfietsen</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(q);
          }}
          className="mx-auto mt-9 max-w-2xl"
        >
          <div className="group relative flex items-center rounded-2xl border border-line-strong bg-white shadow-soft transition-shadow focus-within:shadow-lift focus-within:border-accent/40">
            <Search className="ml-5 h-5 w-5 text-ink-faint" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Wat wil je onderzoeken?"
              className="h-14 flex-1 bg-transparent px-4 text-[16px] text-ink placeholder:text-ink-faint focus:outline-none"
              aria-label="Onderzoeksvraag"
            />
            <Button type="submit" variant="primary" size="md" className="mr-2" disabled={!q.trim()}>
              Onderzoek <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </form>
        <div className="mx-auto mt-4 flex max-w-3xl flex-wrap justify-center gap-2">
          {EXAMPLES.map((e) => (
            <button key={e} onClick={() => submit(e)} className="rounded-full border border-line bg-white px-3 py-1.5 text-[12.5px] text-ink-soft transition-colors hover:border-line-strong hover:text-ink">
              {e}
            </button>
          ))}
        </div>
        {!data.ai.configured && <p className="mt-4 text-[12px] text-ink-faint">AI is niet gekoppeld — vragen worden beantwoord zodra een API-sleutel is ingesteld. Alle andere functies werken lokaal.</p>}
      </motion.div>

      {data.monitor.overdue && data.monitor.monitored_sources > 0 && (
        <Notice tone="caution" icon={<AlarmClock />} title="Broncontrole gemist" className="mb-6 items-center">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>{data.monitor.message}</span>
            <Button size="sm" variant="outline" onClick={() => catchUp.mutate()} loading={catchUp.isPending}>Inhaalcontrole starten</Button>
          </div>
        </Notice>
      )}

      {obDone < obSteps.length && (
        <Card className="mb-8 p-6">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div className="max-w-md">
              <h2 className="text-[17px] font-semibold">Aan de slag</h2>
              <p className="mt-1 text-[13px] text-ink-muted leading-relaxed">
                Deze installatie bevat nog geen concurrentiegegevens. Er worden bewust geen voorbeeldpremies of fictieve voorwaarden getoond: alles wat je hier ziet komt uit je eigen, herleidbare bronnen.
              </p>
              <div className="mt-4 h-1.5 w-56 rounded-full bg-surface overflow-hidden">
                <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${(obDone / obSteps.length) * 100}%` }} />
              </div>
              <div className="mt-1.5 text-[12px] text-ink-muted">{obDone} van {obSteps.length} stappen</div>
            </div>
            <ul className="flex-1 min-w-[280px] space-y-1">
              {obSteps.map((s) => (
                <li key={s.label}>
                  <button onClick={() => nav(s.to)} className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-[13.5px] hover:bg-surface">
                    {s.done ? <CheckCircle2 className="h-[18px] w-[18px] text-positive" /> : <Circle className="h-[18px] w-[18px] text-ink-faint" />}
                    <span className={cn(s.done && "text-ink-muted line-through decoration-ink-faint")}>{s.label}</span>
                    {!s.done && <ArrowRight className="ml-auto h-3.5 w-3.5 text-ink-faint" />}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Onderzochte concurrenten" value={c.competitors} icon={<Building2 />} hint={c.providers_to_review ? `${c.providers_to_review} te beoordelen` : "actieve aanbieders"} onClick={() => nav("/concurrenten")} />
        <Stat label="Verzekeringsproducten" value={c.products} icon={<Package />} hint="zonder dubbele distributie" onClick={() => nav("/voorwaarden")} />
        <Stat label="Gecontroleerde polisdocumenten" value={c.documents} icon={<FileCheck2 />} hint="verwerkte documentversies" onClick={() => nav("/bronnen")} />
        <Stat label="Marktontwikkelingen" value={c.developments_30d} icon={<Activity />} hint="documentwijzigingen, 30 dagen" onClick={() => nav("/marktmonitor")} />
        <Stat label="Premiewaarnemingen" value={c.premiums} icon={<TrendingUp />} hint={`${data.premium_differences.length} recente verschillen t.o.v. Vetera`} onClick={() => nav("/premielab")} />
        <Stat label="Nieuwe verbetersuggesties" value={c.suggestions_new} icon={<Lightbulb />} hint="in de Verbeterradar" onClick={() => nav("/verbeterradar")} />
        <Stat label="Lopende onderzoeken" value={c.research_ongoing} icon={<FlaskConical />} hint="onderzoeken · interessant · uitwerken" onClick={() => nav("/verbeterradar")} />
        <Stat label="Nieuwe meldingen" value={c.notifications_new} icon={<Bell />} hint={data.monitor.last_run_at ? `laatste controle ${relative(data.monitor.last_run_at)}` : "nog geen broncontrole"} onClick={() => nav("/marktmonitor")} />
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Recente premieverschillen" subtitle="Ten opzichte van Vetera, per rekenprofiel" actions={<Button size="sm" variant="ghost" onClick={() => nav("/premielab")}>Premielab</Button>} />
          {data.premium_differences.length === 0 ? (
            <EmptyState icon={<TrendingUp />} title="Nog geen vergelijkbare premies" description="Leg voor één profiel zowel een Vetera-premie als een concurrentpremie vast om verschillen te zien." />
          ) : (
            <ul className="divide-y divide-line px-5 pb-2">
              {data.premium_differences.map((d: any, i: number) => (
                <li key={i} className="flex items-center justify-between gap-4 py-3 text-[13px]">
                  <div className="min-w-0">
                    <div className="font-medium text-ink truncate">{d.provider}</div>
                    <div className="text-[12px] text-ink-muted truncate">{d.profile}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    {!d.comparable && <Badge tone="caution">beperkt vergelijkbaar</Badge>}
                    <span className={cn("tabular font-semibold", d.diff_pct > 0 ? "text-ink" : "text-accent")}>{pct(d.diff_pct)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <CardHeader title="Laatste meldingen" actions={<Button size="sm" variant="ghost" onClick={() => nav("/marktmonitor")}>Alle meldingen</Button>} />
          {data.notifications.length === 0 ? (
            <EmptyState icon={<Bell />} title="Geen meldingen" description="Meldingen verschijnen bij documentwijzigingen, nieuwe aanbieders en relevante premieverschillen." />
          ) : (
            <ul className="divide-y divide-line px-5 pb-2">
              {data.notifications.map((n: any) => (
                <li key={n.id} className="py-3">
                  <button className="w-full text-left" onClick={() => nav(n.link || "/marktmonitor")}>
                    <div className="flex items-center gap-2">
                      {n.status === "nieuw" && <span className="h-1.5 w-1.5 rounded-full bg-accent" />}
                      <span className="text-[13px] font-medium text-ink truncate">{n.title}</span>
                    </div>
                    <div className="mt-0.5 text-[12px] text-ink-muted">{NOTIF_TYPE[n.type] || n.type} · {relative(n.created_at)}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
