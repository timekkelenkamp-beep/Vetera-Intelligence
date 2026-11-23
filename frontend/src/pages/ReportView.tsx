import { useNavigate, useParams, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileDown, Sheet, Printer } from "lucide-react";
import { api } from "@/lib/api";
import { date } from "@/lib/utils";
import { Button, Loading } from "@/components/ui/primitives";

export default function ReportView() {
  const { id } = useParams();
  const nav = useNavigate();
  const loc = useLocation();
  const print = loc.pathname.endsWith("/print");
  const { data: r } = useQuery({ queryKey: ["report", id], queryFn: () => api.get(`/reports/${id}`) });
  if (!r) return <Loading />;
  const c = r.content;
  return (
    <div className={print ? "mx-auto max-w-[900px] bg-white px-12 py-12" : ""}>
      <div className="no-print mb-6 flex items-center justify-between">
        {!print ? <button onClick={() => nav("/rapportages")} className="inline-flex items-center gap-1 text-[13px] text-ink-muted hover:text-ink"><ArrowLeft className="h-3.5 w-3.5" /> Rapportages</button> : <span />}
        <div className="flex gap-2">
          <a href={api.url(`/reports/${r.id}/download`, { fmt: "pdf" })}><Button icon={<FileDown className="h-4 w-4" />}>PDF</Button></a>
          <a href={api.url(`/reports/${r.id}/download`, { fmt: "xlsx" })}><Button icon={<Sheet className="h-4 w-4" />}>Excel</Button></a>
          <Button variant="primary" icon={<Printer className="h-4 w-4" />} onClick={() => (print ? window.print() : window.open(`/rapportages/${r.id}/print`, "_blank"))}>Afdrukken</Button>
        </div>
      </div>
      <article className="print-page rounded-3xl border border-line bg-white px-12 py-12 shadow-soft">
        <div className="flex items-center justify-between border-b border-line pb-5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-[8px] bg-accent"><svg viewBox="0 0 64 64" className="h-3.5 w-3.5"><path d="M14 18l18 30 18-30" fill="none" stroke="#fff" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" /></svg></div>
            <span className="text-[13px] font-semibold">Vetera Intelligence</span>
          </div>
          <span className="text-[12px] text-ink-muted">{c.type_label}</span>
        </div>
        <h1 className="mt-10 text-[34px] font-semibold tracking-tightest leading-tight">{c.title}</h1>
        <div className="mt-2 text-[13px] text-ink-muted">Onderzoeksdatum {date(c.date)}</div>
        {c.products?.length > 0 && <div className="mt-4 text-[13px]"><span className="text-ink-muted">Onderzochte producten: </span>{c.products.join(", ")}</div>}
        <section className="mt-10 rounded-2xl bg-surface px-6 py-5">
          <h2 className="text-[15px] font-semibold">Managementsamenvatting</h2>
          <ul className="mt-2 space-y-1.5 text-[13.5px] leading-relaxed">{(c.management_summary.length ? c.management_summary : ["Geen kernconclusies: onvoldoende gegevens."]).map((s: string, i: number) => <li key={i}>• {s}</li>)}</ul>
        </section>
        {c.sections.map((s: any, i: number) => (
          <section key={i} className="mt-10 break-inside-avoid-page">
            <h2 className="text-[19px] font-semibold tracking-tight">{s.heading}</h2>
            {s.paragraphs?.map((p: string, j: number) => <p key={j} className="mt-2 text-[13.5px] leading-relaxed text-ink-soft">{p}</p>)}
            {s.tables?.map((t: any, j: number) => (
              <div key={j} className="mt-4">
                {t.title && <h3 className="mb-2 text-[13.5px] font-semibold text-accent">{t.title}</h3>}
                <div className="overflow-x-auto rounded-xl border border-line">
                  <table className="w-full text-[11.5px]">
                    <thead className="bg-surface"><tr>{t.columns.map((h: string) => <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>)}</tr></thead>
                    <tbody>{t.rows.length ? t.rows.map((r: any[], k: number) => <tr key={k} className="border-t border-line align-top">{r.map((v, l) => <td key={l} className="px-3 py-2">{v}</td>)}</tr>) : <tr><td className="px-3 py-3 text-ink-muted" colSpan={t.columns.length}>Geen gegevens</td></tr>}</tbody>
                  </table>
                </div>
              </div>
            ))}
          </section>
        ))}
        <section className="mt-12 border-t border-line pt-6">
          <h2 className="text-[15px] font-semibold">Bronverwijzingen</h2>
          {c.sources.length ? <ol className="mt-2 space-y-0.5 text-[11.5px] text-ink-muted">{c.sources.map((s: string, i: number) => <li key={i}>[{i + 1}] {s}</li>)}</ol> : <p className="mt-2 text-[12px] text-ink-muted">Geen documentverwijzingen in dit rapport.</p>}
          <h2 className="mt-6 text-[15px] font-semibold">Beperkingen en onzekerheden</h2>
          <ul className="mt-2 space-y-1 text-[12.5px] text-ink-soft">{c.limitations.map((s: string, i: number) => <li key={i}>• {s}</li>)}</ul>
        </section>
      </article>
    </div>
  );
}
