import { AlertTriangle, CheckCircle2, CircleHelp, Stethoscope, XCircle, MinusCircle } from "lucide-react";
import type { Assessment, Category, CriterionResult } from "@/lib/types";
import { cn } from "@/lib/utils";

export const CATEGORY_STYLE: Record<Category, { label: string; text: string; wash: string; bar: string; Icon: typeof CheckCircle2; blurb: string }> = {
  POTENTIAL_MATCH: {
    label: "Potential match", text: "text-teal", wash: "bg-teal-wash", bar: "bg-teal", Icon: CheckCircle2,
    blurb: "No blockers identified. Final eligibility is still unverified.",
  },
  NEEDS_MORE_INFORMATION: {
    label: "Needs more information", text: "text-amber", wash: "bg-amber-wash", bar: "bg-amber", Icon: CircleHelp,
    blurb: "Not enough information for a meaningful assessment yet.",
  },
  REQUIRES_CLINICAL_REVIEW: {
    label: "Requires clinical review", text: "text-violet", wash: "bg-violet-wash", bar: "bg-violet", Icon: Stethoscope,
    blurb: "Depends on wording or tests that need a clinician's interpretation.",
  },
  POTENTIALLY_INELIGIBLE: {
    label: "Potentially ineligible", text: "text-brick", wash: "bg-brick-wash", bar: "bg-brick", Icon: XCircle,
    blurb: "One or more documented criteria appear incompatible with the profile.",
  },
};

export function CategoryBadge({ category, className }: { category: Category; className?: string }) {
  const s = CATEGORY_STYLE[category];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-sm font-medium", s.text, s.wash, className)}>
      <s.Icon className="size-4" aria-hidden="true" />
      {s.label}
    </span>
  );
}

export function criterionTone(c: CriterionResult) {
  if (c.is_blocker) return "blocker";
  if (c.assessment === "NOT_APPLICABLE") return "na";
  if (c.assessment === "UNKNOWN") return "unknown";
  return "ok"; // inclusion MET or exclusion NOT_MET
}

export function AssessmentLabel({ c }: { c: CriterionResult }) {
  const tone = criterionTone(c);
  const map = {
    ok: { Icon: CheckCircle2, cls: "text-teal", text: c.kind === "exclusion" ? "Exclusion appears absent" : "Appears met" },
    blocker: { Icon: AlertTriangle, cls: "text-brick", text: c.kind === "exclusion" ? "Exclusion appears present" : "Appears not met" },
    unknown: { Icon: CircleHelp, cls: "text-amber", text: c.source === "not_assessed" ? "Not analyzed" : "Unknown" },
    na: { Icon: MinusCircle, cls: "text-ink-soft", text: "Not applicable" },
  }[tone];
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-medium", map.cls)}>
      <map.Icon className="size-3.5" aria-hidden="true" /> {map.text}
    </span>
  );
}

export const ASSESSMENT_WORD: Record<Assessment, string> = {
  MET: "Met", NOT_MET: "Not met", UNKNOWN: "Unknown", NOT_APPLICABLE: "Not applicable",
};

export function RecruitStatus({ status }: { status?: string | null }) {
  const open = status === "RECRUITING" || status === "NOT_YET_RECRUITING" || status === "ENROLLING_BY_INVITATION";
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm", open ? "text-teal" : "text-ink-soft")}>
      <span aria-hidden="true" className={cn("inline-block size-2 rounded-full", open ? "bg-teal" : "bg-ink-soft/50")} />
      {(status ?? "Unknown status").replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase())}
    </span>
  );
}
