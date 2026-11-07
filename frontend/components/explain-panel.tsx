"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CitedText } from "@/components/ledger";
import { api, ApiError } from "@/lib/api";
import type { CriterionResult, ExplainResponse, PatientProfile } from "@/lib/types";
import { cn } from "@/lib/utils";

type Mode = "patient" | "clinical";

export function ExplainPanel({ nctId, sessionId, profile, criteria }: {
  nctId: string; sessionId?: string; profile?: PatientProfile; criteria: CriterionResult[];
}) {
  const [mode, setMode] = useState<Mode>("patient");
  const [cache, setCache] = useState<Partial<Record<Mode, ExplainResponse>>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const data = cache[mode];

  async function load(m: Mode) {
    setMode(m);
    if (cache[m]) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.explain(nctId, m, sessionId, profile);
      setCache((c) => ({ ...c, [m]: res }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The explanation could not be generated.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="explain-h" className="rounded-md border border-rule bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="explain-h" className="text-xl text-ink">Explain this trial</h2>
        <div role="radiogroup" aria-label="Explanation style" className="inline-flex rounded-md border border-rule p-0.5 text-sm">
          {(["patient", "clinical"] as Mode[]).map((m) => (
            <button key={m} role="radio" aria-checked={mode === m} onClick={() => (data || cache[m] ? setMode(m) : load(m))}
              className={cn("rounded px-3 py-1", mode === m ? "bg-ink text-white" : "text-ink-soft hover:text-ink")}>
              {m === "patient" ? "Patient-friendly" : "Detailed clinical"}
            </button>
          ))}
        </div>
      </div>

      {!data && !loading && (
        <div className="mt-3">
          <p className="max-w-prose text-sm text-ink-soft">
            A plain-language summary of what the study is testing, why it might fit, and what still needs checking. It uses
            only this study&apos;s record and your profile.
          </p>
          <Button className="mt-3" onClick={() => load(mode)}>Explain this trial</Button>
        </div>
      )}
      {loading && <p className="mt-4 flex items-center gap-2 text-sm text-ink-soft"><Loader2 className="size-4 animate-spin" aria-hidden="true" /> Writing the explanation…</p>}
      {error && <p role="alert" className="mt-3 text-sm text-brick">{error}</p>}

      {data && !loading && (
        <div className="mt-5 grid gap-6 lg:grid-cols-[1fr_18rem]">
          <div className="grid gap-5">
            {data.sections.map((s) => (
              <div key={s.heading}>
                <h3 className="text-lg text-ink">{s.heading}</h3>
                <p className="mt-1 max-w-prose leading-relaxed text-ink"><CitedText text={s.body} criteria={criteria} /></p>
              </div>
            ))}
            {data.questions_for_team.length > 0 && (
              <div>
                <h3 className="text-lg text-ink">Questions for the research team</h3>
                <ul className="mt-1 list-disc pl-5 text-ink">{data.questions_for_team.map((q) => <li key={q}>{q}</li>)}</ul>
              </div>
            )}
            <p className="text-xs text-ink-soft">
              {data.source === "claude" ? "Written by Claude and checked against the study record." : "Built from the study record by rules (AI explanation unavailable)."}{" "}
              {data.disclaimer}
            </p>
            {data.validation_notes.length > 0 && (
              <p className="text-xs text-amber">Validation: {data.validation_notes.join(" ")}</p>
            )}
          </div>
          {Object.keys(data.glossary).length > 0 && (
            <aside className="rounded bg-mist p-4">
              <h3 className="text-base text-ink">Terms in this study</h3>
              <dl className="mt-2 grid gap-3 text-sm">
                {Object.entries(data.glossary).map(([term, def]) => (
                  <div key={term}><dt className="font-medium capitalize text-ink">{term}</dt><dd className="text-ink-soft">{def}</dd></div>
                ))}
              </dl>
            </aside>
          )}
        </div>
      )}
    </section>
  );
}
