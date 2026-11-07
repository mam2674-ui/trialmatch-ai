"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, Info, Loader2, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAppState } from "@/components/app-state";
import { ProfileEditor } from "@/components/profile-editor";
import { api, ApiError } from "@/lib/api";
import { cleanProfile, emptyProfile } from "@/lib/profile";

const MATCH_STAGES = [
  "Searching ClinicalTrials.gov for live study records",
  "Ranking candidates with biomedical semantic and keyword search",
  "Checking age, sex, recruitment status and clear-cut criteria",
  "Analyzing inclusion and exclusion criteria with Claude",
  "Verifying every cited criterion and patient fact",
];

export function IntakeFlow() {
  const router = useRouter();
  const params = useSearchParams();
  const { narrative, setNarrative, parse, setParse, profile, setProfile, setMatch, hydrated } = useAppState();
  const [parsing, setParsing] = useState(false);
  const [matching, setMatching] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [aiConfigured, setAiConfigured] = useState<boolean | null>(null);
  const autoParsed = useRef(false);

  useEffect(() => {
    api.health().then((h) => setAiConfigured(h.ai === "configured")).catch(() => setAiConfigured(null));
  }, []);
  const stages = MATCH_STAGES.filter((s) => aiConfigured !== false || !s.includes("Claude") && !s.includes("Verifying"));

  async function runParse() {
    setError(null);
    setParsing(true);
    try {
      const res = await api.parse(narrative);
      setParse(res);
      setProfile(res.profile);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The description could not be read.");
    } finally {
      setParsing(false);
    }
  }

  useEffect(() => {
    if (hydrated && params.get("parse") === "1" && !autoParsed.current && narrative.trim().length >= 10 && !parse) {
      autoParsed.current = true;
      void runParse();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated]);

  async function runMatch() {
    if (!profile) return;
    setError(null);
    setMatching(true);
    setStage(0);
    const timer = setInterval(() => setStage((s) => Math.min(s + 1, stages.length - 1)), 6000);
    try {
      const res = await api.match(cleanProfile(profile));
      setMatch(res);
      setProfile(res.profile_used);
      router.push("/results");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Matching failed.");
    } finally {
      clearInterval(timer);
      setMatching(false);
    }
  }

  const conditionMissing = profile && !profile.diagnosis.primary_condition.value;

  return (
    <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,22rem)_1fr]">
      <aside className="lg:sticky lg:top-6 lg:self-start">
        <label htmlFor="narrative" className="font-serif text-lg font-semibold text-ink">Description</label>
        <Textarea id="narrative" value={narrative} maxLength={4000} onChange={(e) => setNarrative(e.target.value)}
          className="mt-2 min-h-48 bg-white leading-relaxed" aria-describedby="privacy-note"
          placeholder="Diagnosis, stage, test results, treatments, location and travel distance." />
        <p id="privacy-note" className="mt-2 flex gap-1.5 text-xs text-ink-soft">
          <ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-amber" aria-hidden="true" />
          Avoid identifying details. The text is processed in memory and not stored.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button onClick={runParse} disabled={parsing || narrative.trim().length < 10}>
            {parsing && <Loader2 className="animate-spin" aria-hidden="true" />}
            {profile ? "Read description again" : "Build profile from description"}
          </Button>
          {!profile && (
            <Button variant="outline" onClick={() => { setProfile(emptyProfile()); setParse(null); }}>Fill in the form instead</Button>
          )}
        </div>
        {profile?.is_demo && (
          <p className="mt-4 rounded bg-violet-wash p-3 text-sm text-violet">
            Fictional demo patient. The profile was pre-filled; searches still use live ClinicalTrials.gov data.
          </p>
        )}
      </aside>

      <section aria-live="polite">
        {error && (
          <div role="alert" className="mb-6 flex gap-2 rounded border border-brick/30 bg-brick-wash p-3 text-sm text-brick">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> {error}
          </div>
        )}
        {parsing && <p className="flex items-center gap-2 text-ink-soft"><Loader2 className="size-4 animate-spin" aria-hidden="true" /> Reading the description…</p>}
        {!profile && !parsing && (
          <div className="rounded-md border border-dashed border-rule p-8 text-ink-soft">
            Your structured profile will appear here. Build it from the description, or fill in the form directly.
          </div>
        )}
        {profile && !parsing && (
          <>
            {parse && !profile.is_demo && (
              <div className="mb-6 grid gap-2 text-sm">
                <p className="flex gap-2 text-ink-soft">
                  <Info className="mt-0.5 size-4 shrink-0 text-link" aria-hidden="true" />
                  {parse.extraction_method === "claude"
                    ? "Extracted by Claude. Each value shows the phrase it came from. Please check them."
                    : "Extracted with conservative text rules. Please review carefully and fill in anything missing."}
                </p>
                {parse.warnings.map((w) => <p key={w} className="rounded bg-amber-wash p-2 text-amber">{w}</p>)}
                {parse.dropped_unverified.length > 0 && (
                  <details className="rounded bg-mist p-2 text-ink-soft">
                    <summary className="cursor-pointer">{parse.dropped_unverified.length} extracted value(s) were discarded because they could not be traced to your words</summary>
                    <ul className="mt-2 list-disc pl-5">{parse.dropped_unverified.map((d) => <li key={d}>{d}</li>)}</ul>
                  </details>
                )}
              </div>
            )}
            {profile.conflicts.length > 0 && (
              <div className="mb-6 rounded border border-amber/30 bg-amber-wash p-3 text-sm text-amber">
                <p className="font-medium">Conflicting information to resolve</p>
                <ul className="mt-1 list-disc pl-5">{profile.conflicts.map((c) => <li key={c.field + c.description}>{c.description}</li>)}</ul>
                <button className="mt-2 underline" onClick={() => setProfile({ ...profile, conflicts: [] })}>I&apos;ve corrected these</button>
              </div>
            )}
            <ProfileEditor profile={profile} onChange={setProfile} />
            <div className="sticky bottom-0 mt-8 border-t border-rule bg-background/95 py-4 backdrop-blur">
              {matching ? (
                <div role="status" className="grid gap-1.5 text-sm">
                  {stages.map((s, i) => (
                    <p key={s} className={i < stage ? "text-teal" : i === stage ? "flex items-center gap-2 font-medium text-ink" : "text-ink-soft/60"}>
                      {i === stage && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}{s}
                    </p>
                  ))}
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-3">
                  <Button className="h-11 px-5 text-base" onClick={runMatch} disabled={!!conditionMissing}>Search for matching trials</Button>
                  {aiConfigured === false && (
                    <span className="text-sm text-ink-soft">AI criteria analysis is off; results will show rule-based checks only.</span>
                  )}
                  {conditionMissing && <span className="text-sm text-brick">Enter a primary condition to search.</span>}
                </div>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
