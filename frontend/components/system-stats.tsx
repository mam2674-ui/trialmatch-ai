"use client";

import { useEffect, useState } from "react";
import { api, API_CONNECTED } from "@/lib/api";
import type { Health, MethodologyStats } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export function SystemStats() {
  const [stats, setStats] = useState<MethodologyStats | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    if (!API_CONNECTED) return;
    Promise.all([api.stats(), api.health()])
      .then(([s, h]) => { setStats(s); setHealth(h); })
      .catch(() => setDown(true));
  }, []);

  if (!API_CONNECTED) {
    return (
      <p className="rounded bg-mist p-4 text-sm text-ink-soft">
        Live system status appears here when the matching service is connected. This deployment is a website-only
        preview.
      </p>
    );
  }
  if (down) return <p className="rounded bg-brick-wash p-4 text-sm text-brick">The TrialMatch API is not reachable right now.</p>;
  if (!stats || !health) return <p className="text-sm text-ink-soft">Loading system status…</p>;

  const rows: [string, string][] = [
    ["ClinicalTrials.gov", health.clinicaltrials_gov === "ok" ? "Reachable" : "Unreachable"],
    ["Registry data as of", formatDateTime(health.clinicaltrials_gov_data_timestamp)],
    ["Last successful refresh", formatDateTime(stats.last_successful_refresh)],
    ["Studies cached", String(stats.cached_trials)],
    ["Embedded text sections", String(stats.embedded_chunks)],
    ["Live searches / failures", `${stats.live_refreshes} / ${stats.failed_refreshes}`],
    ["AI criteria analysis", stats.ai_model ? stats.ai_model : "Not configured"],
    ["Embedding model", stats.embedding_model ?? "Disabled"],
    ["Active anonymous sessions", String(stats.active_sessions)],
    ["Session retention", `${stats.session_ttl_minutes} minutes`],
  ];
  return (
    <div className="rounded-md border border-rule bg-white p-5">
      <h2 className="text-lg text-ink">System status</h2>
      <dl className="tabular mt-3 grid gap-2.5 text-sm">
        {rows.map(([k, v]) => (
          <div key={k}><dt className="text-ink-soft">{k}</dt><dd className="break-words text-ink">{v}</dd></div>
        ))}
      </dl>
      <h3 className="mt-5 text-base text-ink">Relevance weights</h3>
      <dl className="tabular mt-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
        {Object.entries(stats.relevance_weights).map(([k, w]) => (
          <div key={k} className="contents"><dt className="text-ink-soft">{k.replace(/_/g, " ")}</dt><dd className="text-right text-ink">{w.toFixed(2)}</dd></div>
        ))}
      </dl>
    </div>
  );
}
