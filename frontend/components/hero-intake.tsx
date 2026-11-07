"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAppState } from "@/components/app-state";
import { api } from "@/lib/api";
import type { DemoProfile } from "@/lib/types";

export function HeroIntake() {
  const router = useRouter();
  const { narrative, setNarrative, setParse, setProfile, setMatch } = useAppState();
  const [demos, setDemos] = useState<DemoProfile[]>([]);

  useEffect(() => {
    api.demos().then(setDemos).catch(() => setDemos([]));
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
    <div className="rounded-md border border-rule bg-paper p-5 sm:p-6">
      <label htmlFor="hero-narrative" className="font-serif text-lg font-semibold text-ink">
        Describe the medical situation
      </label>
      <p id="hero-hint" className="mt-1 text-sm text-ink-soft">
        Diagnosis, stage or subtype, test results you know, treatments so far, and how far you can travel.
      </p>
      <Textarea
        id="hero-narrative"
        aria-describedby="hero-hint hero-privacy"
        value={narrative}
        maxLength={4000}
        onChange={(e) => setNarrative(e.target.value)}
        placeholder="Example: 58-year-old with metastatic non-small cell lung cancer, EGFR exon 19 deletion, previously treated with osimertinib. Lives near Chicago and can travel 300 miles."
        className="mt-3 min-h-36 bg-white text-base leading-relaxed"
      />
      <p id="hero-privacy" className="mt-2 flex items-start gap-1.5 text-xs text-ink-soft">
        <ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-amber" aria-hidden="true" />
        Don&apos;t include names, birthdates, addresses, or record numbers. Your description isn&apos;t stored.
      </p>
      <Button onClick={start} disabled={narrative.trim().length < 10} className="mt-4 h-11 w-full px-5 text-base sm:w-auto">
        Find Clinical Trials
      </Button>

      {demos.length > 0 && (
        <div className="mt-6 border-t border-rule pt-4">
          <p className="text-sm font-medium text-ink">Or try a fictional demo patient</p>
          <ul className="mt-2 grid gap-1.5">
            {demos.map((d) => (
              <li key={d.id}>
                <button
                  onClick={() => pickDemo(d)}
                  className="w-full rounded px-2 py-1.5 text-left text-sm hover:bg-mist"
                  title={d.challenge}
                >
                  <span className="text-link underline-offset-2 hover:underline">{d.title}</span>
                  <span className="block text-xs text-ink-soft">{d.challenge}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
