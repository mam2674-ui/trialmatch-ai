import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function titleCase(s?: string | null) {
  if (!s) return "Unknown";
  return s.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}

export function formatPhases(phases: string[]) {
  if (!phases?.length) return "Phase not applicable";
  return phases.map((p) => p.replace("EARLY_PHASE1", "Early phase 1").replace(/^PHASE(\d)$/, "Phase $1").replace("NA", "N/A")).join(" / ");
}

export function formatDate(iso?: string | null) {
  if (!iso) return "unknown";
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(iso?: string | null) {
  if (!iso) return "unknown";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function siteLabel(s: { facility?: string | null; city?: string | null; state?: string | null; country?: string | null }) {
  return [s.facility, [s.city, s.state, s.country].filter(Boolean).join(", ")].filter(Boolean).join(" — ");
}
