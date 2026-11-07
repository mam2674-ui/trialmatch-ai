"use client";

import { Fragment } from "react";
import type { CriterionResult } from "@/lib/types";
import { criterionTone } from "@/components/status";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const CITE = /\[([IEU]\d{1,3}|AGE|SEX|STATUS)\]/g;

/** Renders model or rule text, turning [I2]-style citations into references that reveal the verbatim criterion. */
export function CitedText({ text, criteria, className }: { text: string; criteria: CriterionResult[]; className?: string }) {
  const byId = new Map(criteria.map((c) => [c.criterion_id, c]));
  const parts = text.split(CITE);
  return (
    <span className={className}>
      {parts.map((part, i) => {
        if (i % 2 === 0) return <Fragment key={i}>{part}</Fragment>;
        const c = byId.get(part);
        if (!c) return <Fragment key={i}>[{part}]</Fragment>;
        return <CriterionRef key={i} c={c} />;
      })}
    </span>
  );
}

export function CriterionRef({ c }: { c: CriterionResult }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={<a href={`#crit-${c.criterion_id}`} />}
        className="mx-0.5 rounded-sm px-0.5 font-medium text-link underline decoration-dotted underline-offset-2"
      >
        [{c.criterion_id}]
      </TooltipTrigger>
      <TooltipContent className="max-w-sm whitespace-pre-line text-left text-xs leading-snug">
        {c.kind === "structured" ? "" : `${c.kind === "exclusion" ? "Exclusion" : "Inclusion"} criterion: `}
        {c.criterion_text.length > 400 ? c.criterion_text.slice(0, 400) + "…" : c.criterion_text}
      </TooltipContent>
    </Tooltip>
  );
}

/** Three-column criteria ledger: appears met / possible blockers / to confirm. */
export function Ledger({ criteria, limit = 4, compact = false }: { criteria: CriterionResult[]; limit?: number; compact?: boolean }) {
  const relevant = criteria.filter((c) => !(c.kind === "structured" && c.assessment === "NOT_APPLICABLE"));
  const met = relevant.filter((c) => criterionTone(c) === "ok" && (c.kind !== "structured" || !compact));
  const blockers = relevant.filter((c) => criterionTone(c) === "blocker");
  const unknown = relevant
    .filter((c) => criterionTone(c) === "unknown")
    .sort((a, b) => (a.impact === b.impact ? 0 : a.impact === "high" ? -1 : 1));
  const cols = [
    { title: "Appears met", items: met, tone: "text-teal", empty: "Nothing confirmed yet" },
    { title: "Possible blockers", items: blockers, tone: "text-brick", empty: "None identified" },
    { title: "To confirm", items: unknown, tone: "text-amber", empty: "Nothing outstanding" },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {cols.map((col) => (
        <div key={col.title} className="min-w-0">
          <p className={cn("mb-1.5 text-sm font-medium", col.tone)}>
            {col.title} <span className="tabular font-normal text-ink-soft">({col.items.length})</span>
          </p>
          {col.items.length === 0 ? (
            <p className="text-sm text-ink-soft">{col.empty}</p>
          ) : (
            <ul className="grid gap-1.5">
              {col.items.slice(0, limit).map((c) => (
                <li key={c.criterion_id} className="text-sm leading-snug text-ink">
                  <CriterionRef c={c} />{" "}
                  {col.title === "Possible blockers" || c.source !== "not_assessed" ? c.explanation : shorten(c.criterion_text)}
                </li>
              ))}
              {col.items.length > limit && (
                <li className="text-xs text-ink-soft">and {col.items.length - limit} more in the full breakdown</li>
              )}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

function shorten(s: string, n = 110) {
  const one = s.split("\n")[0];
  return one.length > n ? one.slice(0, n) + "…" : one;
}
