import type { Metadata } from "next";
import { ResultsView } from "@/components/results-view";

export const metadata: Metadata = { title: "Matching results" };

export default function ResultsPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <ResultsView />
    </div>
  );
}
