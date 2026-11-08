"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAppState } from "@/components/app-state";
import { api, API_CONNECTED } from "@/lib/api";
import type { DemoProfile } from "@/lib/types";

const MIN_CHARS = 10;

export function HeroIntake() {
  const router = useRouter();
  const { narrative, setNarrative, setParse, setProfile, setMatch } = useAppState();
  const [demos, setDemos] = useState<DemoProfile[] | null>(null);
  const [demosFailed, setDemosFailed] = useState(false);
  const tooShort = narrative.trim().length < MIN_CHARS;

  useEffect(() => {
    if (!API_CONNECTED) return;
    api.demos().then(setDemos).catch(() => setDemosFailed(true));
  }, []);

  function start() {
    setParse(null);
    setProfile(null);
    setMatch(null);
    router.push("/intake?parse=1");
  }

  function pickDemo(d: DemoProfile) {
    setNarrative(d.narrative);
    setParse({ profile: d.profile, extraction_method: "rules", warnings: [], dropped_unverified: [] });
    setProfile(d.profile);
    setMatch(null);
    router.push("/intake?demo=" + d.id);
  }

  return (
    <div className="rounded-md border border-rule bg-paper p-4 sm:p-6">
      <label htmlFor="hero-narrative" className="font-serif text-xl font-semibold text-ink">
        Describe the diagnosis
      </label>
      <p id="hero-hint" className="mt-1.5 text-[0.95rem] leading-relaxed text-ink-soft">
        The condition, test results, treatments so far, and how far you can travel. Leave out anything you&apos;re
        unsure of; we&apos;ll ask later.
      </p>
      <Textarea
        id="hero-narrative"
        aria-describedby="hero-hint hero-privacy"
        value={narrative}
        maxLength={4000}
        onChange={(e) => setNarrative(e.target.value)}
        placeholder="For example: My husband is 58 and has lung cancer that has spread. He has an EGFR mutation and has been taking osimertinib. We live near Chicago."
        className="mt-3 min-h-36 bg-white text-base leading-relaxed placeholder:text-[#66758b] md:text-base"
      />
      <p id="hero-privacy" className="mt-2 flex items-start gap-1.5 text-sm text-ink-soft">
        <Lock className="mt-[3px] size-3.5 shrink-0" aria-hidden="true" />
        Leave out names, birthdates, addresses and record numbers. Your description isn&apos;t stored.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button onClick={start} disabled={tooShort || !API_CONNECTED} className="h-11 px-5 text-base">
          Find clinical trials
        </Button>
        {!API_CONNECTED ? (
          <span className="text-sm text-ink-soft">Search isn&apos;t connected in this preview.</span>
        ) : tooShort && (
          <span className="text-sm text-ink-soft" aria-live="polite">
            {narrative.trim().length === 0 ? "Start with the diagnosis." : "Add a little more detail to continue."}
          </span>
        )}
      </div>

      <div className="mt-6 border-t border-rule pt-4">
        <p className="text-sm font-medium text-ink">Or start from a fictional example</p>
        {!API_CONNECTED ? (
          <p className="mt-2 text-sm text-ink-soft">
            Examples run a live search, so they need the matching service too.
          </p>
        ) : demosFailed ? (
          <p className="mt-2 text-sm text-ink-soft">Examples couldn&apos;t load right now. You can still describe a diagnosis above.</p>
        ) : !demos ? (
          <p className="mt-2 text-sm text-ink-soft">Loading examples…</p>
        ) : (
          <ul className="mt-1 grid">
            {demos.map((d) => (
              <li key={d.id}>
                <button
                  onClick={() => pickDemo(d)}
                  className="-mx-2 min-h-11 w-[calc(100%+1rem)] rounded px-2 py-2 text-left hover:bg-mist"
                >
                  <span className="text-[0.95rem] text-link underline-offset-2 hover:underline">{d.title}</span>
                  <span className="block text-sm text-ink-soft">{d.summary}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
