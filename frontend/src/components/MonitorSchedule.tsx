import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Select } from "./ui/primitives";

export const SCHEDULE_OPTIONS = [
  { value: "handmatig", label: "Alleen handmatig" },
  { value: "30", label: "Automatisch: elke maand" },
  { value: "91", label: "Automatisch: elk kwartaal" },
  { value: "182", label: "Automatisch: elk half jaar" },
  { value: "365", label: "Automatisch: elk jaar" },
];

export function scheduleLabel(mode?: string, days?: number) {
  if (mode !== "automatisch") return "Alleen handmatig";
  return SCHEDULE_OPTIONS.find((o) => o.value === String(days))?.label.replace("Automatisch: e", "E") || `Elke ${days} dagen`;
}

/** Eén keuzelijst voor hoe vaak bronnen gecontroleerd worden. Standaard: alleen handmatig. */
export function MonitorScheduleSelect({ mode, days, className }: { mode?: string; days?: number; className?: string }) {
  const qc = useQueryClient();
  const value = mode === "automatisch" ? String(days) : "handmatig";
  const opts = SCHEDULE_OPTIONS.some((o) => o.value === value) ? SCHEDULE_OPTIONS : [...SCHEDULE_OPTIONS, { value, label: `Automatisch: elke ${days} dagen` }];
  const change = async (v: string) => {
    try {
      await api.patch("/settings", v === "handmatig" ? { monitor_mode: "handmatig" } : { monitor_mode: "automatisch", monitor_interval_days: Number(v) });
      ["monitor-status", "settings", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      toast.success(v === "handmatig" ? "Bronnen worden alleen gecontroleerd als je daar zelf om vraagt" : `Bronnen worden automatisch gecontroleerd: ${opts.find((o) => o.value === v)?.label.replace("Automatisch: ", "")}`);
    } catch (e: any) { toast.error(e.message); }
  };
  return (
    <Select value={value} onChange={(e) => change(e.target.value)} className={className} aria-label="Hoe vaak controleren">
      {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </Select>
  );
}
