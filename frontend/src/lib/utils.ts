import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const eurFmt = new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR", maximumFractionDigits: 2 });
const eur0 = new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
export const eur = (v?: number | null, decimals = true) => (v === null || v === undefined ? "–" : (decimals ? eurFmt : eur0).format(v));
export const num = (v?: number | null) => (v === null || v === undefined ? "–" : new Intl.NumberFormat("nl-NL").format(v));
export const pct = (v?: number | null) => (v === null || v === undefined ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(1).replace(".", ",")}%`);

export function date(v?: string | null, withTime = false) {
  if (!v) return "–";
  const d = new Date(v);
  if (isNaN(d.getTime())) return v;
  return d.toLocaleDateString("nl-NL", { day: "numeric", month: "short", year: "numeric", ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}) });
}

export function relative(v?: string | null) {
  if (!v) return "nooit";
  const diff = (Date.now() - new Date(v).getTime()) / 1000;
  if (diff < 60) return "zojuist";
  if (diff < 3600) return `${Math.floor(diff / 60)} min geleden`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} uur geleden`;
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)} dagen geleden`;
  return date(v);
}

export function initials(name: string) {
  return name.replace(/[^A-Za-zÀ-ÿ0-9 ]/g, " ").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
}
