import { LayoutGrid, Building2, Columns3, Calculator, Radar, Lightbulb, FileBarChart, FolderOpen, Settings, Compass, type LucideIcon } from "lucide-react";

// Elke module heeft een eigen, rustige kleur (zoals de app-iconen in macOS-instellingen).
export type ModuleKey = "dashboard" | "concurrenten" | "voorwaarden" | "advies" | "premielab" | "marktmonitor" | "verbeterradar" | "rapportages" | "bronnen" | "instellingen";
export const MODULES: Record<ModuleKey, { label: string; to: string; icon: LucideIcon; color: string; end?: boolean }> = {
  dashboard: { label: "Dashboard", to: "/", icon: LayoutGrid, color: "#1f6f5f", end: true },
  concurrenten: { label: "Concurrenten", to: "/concurrenten", icon: Building2, color: "#0a7cff" },
  voorwaarden: { label: "Voorwaardenvergelijker", to: "/voorwaarden", icon: Columns3, color: "#1aa3b8" },
  advies: { label: "Adviestool", to: "/advies", icon: Compass, color: "#e8476a" },
  premielab: { label: "Premielab", to: "/premielab", icon: Calculator, color: "#f08a00" },
  marktmonitor: { label: "Marktmonitor", to: "/marktmonitor", icon: Radar, color: "#e5493a" },
  verbeterradar: { label: "Verbeterradar", to: "/verbeterradar", icon: Lightbulb, color: "#e0a800" },
  rapportages: { label: "Rapportages", to: "/rapportages", icon: FileBarChart, color: "#a14fd6" },
  bronnen: { label: "Bronnen & documenten", to: "/bronnen", icon: FolderOpen, color: "#5856d6" },
  instellingen: { label: "Instellingen", to: "/instellingen", icon: Settings, color: "#8e8e93" },
};
export const NAV_ORDER: ModuleKey[] = ["dashboard", "concurrenten", "voorwaarden", "advies", "premielab", "marktmonitor", "verbeterradar", "rapportages", "bronnen", "instellingen"];

export function tileStyle(color: string) {
  return { background: `linear-gradient(180deg, color-mix(in srgb, ${color} 82%, white) 0%, ${color} 100%)` };
}
