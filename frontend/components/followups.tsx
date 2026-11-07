"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAppState } from "@/components/app-state";
import { api, ApiError } from "@/lib/api";
import { cleanProfile } from "@/lib/profile";
import type { FollowUpQuestion } from "@/lib/types";

/** Focused questions about missing information that could change which studies are potential matches. */
export function FollowUps({ questions }: { questions: FollowUpQuestion[] }) {
  const { profile, setProfile, setMatch } = useAppState();
  const [busy, setBusy] = useState<string | null>(null);
  const [answered, setAnswered] = useState<Record<string, string>>({});
  const [numeric, setNumeric] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [rerunning, setRerunning] = useState(false);

  if (!questions.length || !profile) return null;

  async function answer(q: FollowUpQuestion, value: string, input?: string) {
    if (!profile) return;
    setBusy(q.id);
    setError(null);
    try {
      const raw = input === undefined ? undefined : q.patch.input === "number" ? Number(input) : input;
      const next = await api.answer(profile, q, value, raw);
      setProfile(next);
      setAnswered((a) => ({ ...a, [q.id]: value === "not_sure" ? "Not sure (left unknown)" : input ?? (value === "yes" ? "Yes" : "No") }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not record that answer.");
    } finally {
      setBusy(null);
    }
  }

  async function rerun() {
    if (!profile) return;
    setRerunning(true);
    setError(null);
    try {
      const res = await api.match(cleanProfile(profile));
      setMatch(res);
      setProfile(res.profile_used);
      setAnswered({});
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update the results.");
    } finally {
      setRerunning(false);
    }
  }

  const answeredCount = Object.keys(answered).length;

  return (
    <section aria-labelledby="fu-title" className="rounded-md border border-amber/30 bg-amber-wash/60 p-5">
      <h2 id="fu-title" className="text-xl text-ink">Questions that could change these results</h2>
      <p className="mt-1 text-sm text-ink-soft">
        Answer only what you know. &ldquo;Not sure&rdquo; keeps the item unknown; it never counts as meeting a requirement.
      </p>
      <ul className="mt-4 grid gap-4">
        {questions.map((q) => (
          <li key={q.id} className="grid gap-2 md:grid-cols-[1fr_auto] md:items-center">
            <div>
              <p className="font-medium text-ink">{q.question}</p>
              <p className="text-xs text-ink-soft">
                {q.why} Affects {q.affected_trials.length} {q.affected_trials.length === 1 ? "study" : "studies"}.
              </p>
            </div>
            {answered[q.id] ? (
              <p className="text-sm text-teal">Answered: {answered[q.id]}</p>
            ) : q.patch.type === "set_field" ? (
              <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void answer(q, "yes", numeric[q.id]); }}>
                {q.patch.input === "choice" ? (
                  <select aria-label={q.question} className="h-8 rounded-md border border-input bg-white px-2 text-sm"
                    value={numeric[q.id] ?? ""} onChange={(e) => setNumeric({ ...numeric, [q.id]: e.target.value })}>
                    <option value="">Choose</option>
                    {(q.patch.choices as string[]).map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                ) : (
                  <Input aria-label={q.question} type="number" className="h-8 w-24 bg-white" value={numeric[q.id] ?? ""}
                    onChange={(e) => setNumeric({ ...numeric, [q.id]: e.target.value })} />
                )}
                <Button size="sm" type="submit" disabled={!numeric[q.id] || busy === q.id}>Save</Button>
              </form>
            ) : (
              <div className="flex gap-1.5" role="group" aria-label={q.question}>
                {q.options.map((o) => (
                  <Button key={o.value} size="sm" variant={o.value === "not_sure" ? "ghost" : "outline"} className="bg-white"
                    disabled={busy === q.id} onClick={() => answer(q, o.value)}>
                    {o.label}
                  </Button>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
      {error && <p role="alert" className="mt-3 text-sm text-brick">{error}</p>}
      {answeredCount > 0 && (
        <Button className="mt-5" onClick={rerun} disabled={rerunning}>
          {rerunning && <Loader2 className="animate-spin" aria-hidden="true" />}
          Update results with {answeredCount} {answeredCount === 1 ? "answer" : "answers"}
        </Button>
      )}
    </section>
  );
}
