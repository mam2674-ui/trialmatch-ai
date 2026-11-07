import type { Metadata } from "next";
import { Suspense } from "react";
import { IntakeFlow } from "@/components/intake-flow";

export const metadata: Metadata = { title: "Patient profile" };

export default function IntakePage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <h1 className="text-3xl text-ink">Patient profile</h1>
      <p className="mt-2 max-w-prose text-ink-soft">
        Describe the situation in your own words, then check the structured profile below before searching. Anything left
        blank stays unknown and is never counted as meeting a requirement.
      </p>
      <Suspense fallback={<p className="mt-8 text-ink-soft">Loading…</p>}>
        <IntakeFlow />
      </Suspense>
    </div>
  );
}
