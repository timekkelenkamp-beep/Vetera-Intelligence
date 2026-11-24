import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";

/** Volgt een achtergrondtaak tot die klaar of mislukt is. */
export function useJob(jobId: number | null, onFinish?: (job: any) => void) {
  const finished = React.useRef<number | null>(null);
  const q = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.get(`/ai/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => (query.state.data && ["klaar", "fout"].includes(query.state.data.status) ? false : 1500),
  });
  React.useEffect(() => {
    if (q.data && jobId && ["klaar", "fout"].includes(q.data.status) && finished.current !== jobId) {
      finished.current = jobId;
      onFinish?.(q.data);
    }
  }, [q.data, jobId]); // eslint-disable-line
  return q.data;
}

export function JobProgress({ job, title }: { job: any; title?: string }) {
  const pct = job?.total ? Math.round((job.done / job.total) * 100) : null;
  return (
    <div className="rounded-2xl border border-line p-5">
      <div className="flex items-center gap-2 text-[14px] font-semibold"><Loader2 className="h-4 w-4 animate-spin text-accent" /> {title || "Bezig…"}</div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface">
        {pct === null ? <div className="h-full w-1/3 animate-[indeterminate_1.4s_ease-in-out_infinite] rounded-full bg-accent" /> : <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${pct}%` }} />}
      </div>
      <p className="mt-2 text-[12.5px] text-ink-muted">{job?.step || "Starten…"}</p>
      <p className="mt-1 text-[11.5px] text-ink-faint">Dit kan een paar minuten duren. Je kunt dit venster sluiten; het werk gaat op de achtergrond door.</p>
    </div>
  );
}
