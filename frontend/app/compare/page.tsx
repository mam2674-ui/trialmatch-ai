"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ExternalLink, Loader2, X } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { useAppState } from "@/components/app-state";
import { api, ApiError } from "@/lib/api";
import type { CompareResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function ComparePage() {
  const { compare, toggleCompare, match, hydrated } = useAppState();
  const [data, setData] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const key = compare.join(",");

  useEffect(() => {
    if (!hydrated || compare.length < 2) return;
    let cancelled = false;
    /* eslint-disable-next-line react-hooks/set-state-in-effect -- loading indicator for an external fetch */
    setLoading(true);
    api.compare(compare, match?.session_id)
      .then((d) => { if (!cancelled) { setData(d); setError(null); } })
      .catch((e) => { if (!cancelled) setError(e instanceof ApiError ? e.message : "Comparison failed."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, key]);

  const titles = (data?.rows.find((r) => r.field === "Study title")?.values ?? {}) as Record<string, string>;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <h1 className="text-3xl text-ink">Compare studies</h1>
      <p className="mt-2 max-w-prose text-ink-soft">
        Side-by-side study characteristics and preliminary eligibility. Studies are not ranked by expected effectiveness,
        and nothing here suggests one treatment is better than another.
      </p>

      {hydrated && compare.length < 2 ? (
        <div className="mt-8 rounded-md border border-dashed border-rule p-8">
          <p className="text-ink">Select two to four studies to compare.</p>
          <p className="mt-1 text-sm text-ink-soft">Use the Compare checkbox on any result. {compare.length === 1 && "One study is selected so far."}</p>
          <Link href="/results" className={cn(buttonVariants({ variant: "outline" }), "mt-4")}>Go to results</Link>
        </div>
      ) : loading && !data ? (
        <p className="mt-8 flex items-center gap-2 text-ink-soft"><Loader2 className="size-4 animate-spin" aria-hidden="true" /> Building comparison…</p>
      ) : error ? (
        <p role="alert" className="mt-8 rounded bg-brick-wash p-4 text-brick">{error}</p>
      ) : data ? (
        <div className="mt-8 overflow-x-auto rounded-md border border-rule bg-white">
          <table className="w-full min-w-[44rem] border-collapse text-sm">
            <caption className="sr-only">Comparison of {data.nct_ids.length} studies</caption>
            <thead>
              <tr className="border-b border-rule bg-mist text-left align-bottom">
                <th scope="col" className="w-44 p-3 font-medium text-ink-soft">Study</th>
                {data.nct_ids.map((id) => (
                  <th key={id} scope="col" className="p-3 font-normal">
                    <div className="flex items-start justify-between gap-2">
                      <Link href={`/trials/${id}`} className="font-serif text-base font-semibold leading-snug text-ink hover:underline">
                        {titles[id] ?? id}
                      </Link>
                      <button aria-label={`Remove ${id} from comparison`} onClick={() => toggleCompare(id)} className="text-ink-soft hover:text-brick">
                        <X className="size-4" />
                      </button>
                    </div>
                    <span className="tabular text-ink-soft">{id}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.filter((r) => r.field !== "Study title").map((row) => (
                <tr key={row.field} className="border-b border-rule align-top last:border-0">
                  <th scope="row" className="p-3 text-left font-medium text-ink">{row.field}</th>
                  {data.nct_ids.map((id) => {
                    const v = row.values[id];
                    return (
                      <td key={id} className="p-3 text-ink">
                        {v == null ? <span className="text-ink-soft">Not available</span>
                          : row.field === "Official study link" ? (
                            <a href={v as string} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-link underline">
                              ClinicalTrials.gov <ExternalLink className="size-3.5" aria-hidden="true" />
                            </a>
                          ) : Array.isArray(v) ? (
                            <ul className="grid gap-1">{v.map((x, i) => <li key={i}>{x}</li>)}</ul>
                          ) : v}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-rule p-3 text-xs text-ink-soft">{data.note}</p>
        </div>
      ) : null}
    </div>
  );
}
