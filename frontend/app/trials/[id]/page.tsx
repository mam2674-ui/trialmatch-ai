import type { Metadata } from "next";
import { Suspense } from "react";
import { TrialDetail } from "@/components/trial-detail";

export async function generateMetadata({ params }: PageProps<"/trials/[id]">): Promise<Metadata> {
  const { id } = await params;
  return { title: id.toUpperCase() };
}

export default function TrialPage({ params }: PageProps<"/trials/[id]">) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <Suspense fallback={<p className="text-ink-soft">Loading study…</p>}>
        <TrialFromParams params={params} />
      </Suspense>
    </div>
  );
}

async function TrialFromParams({ params }: { params: PageProps<"/trials/[id]">["params"] }) {
  const { id } = await params;
  return <TrialDetail nctId={id.toUpperCase()} />;
}
