import Link from "next/link";
import { AlertTriangle, CheckCircle2, CircleHelp, ExternalLink, ListChecks, Scale } from "lucide-react";
import { HeroIntake } from "@/components/hero-intake";

export default function Home() {
  return (
    <>
      <section className="border-b border-rule bg-white">
        {/* Mobile order: headline, then the input, then the reassurances. Desktop: text left, input right. */}
        <div className="mx-auto grid max-w-6xl gap-8 px-4 pb-14 pt-10 sm:px-6 md:pt-16 lg:grid-cols-[1.05fr_1fr] lg:grid-rows-[auto_1fr] lg:gap-x-14 lg:gap-y-10">
          <div className="max-w-xl lg:col-start-1 lg:row-start-1">
            <h1 className="text-[2.4rem] leading-[1.08] text-ink [text-wrap:balance] sm:text-[3.2rem]">
              Find trials worth asking your doctor about.
            </h1>
            <p className="mt-4 text-base leading-relaxed text-ink-soft sm:mt-5 sm:text-lg">
              We search current studies on ClinicalTrials.gov and show, for each one, which requirements you appear to meet
              and what still needs checking.
            </p>
          </div>

          <div className="lg:col-start-2 lg:row-span-2 lg:row-start-1">
            <HeroIntake />
          </div>

          <ul className="grid max-w-md content-start gap-5 text-[0.95rem] lg:col-start-1 lg:row-start-2">
            <li className="flex gap-3">
              <ExternalLink className="mt-1 size-4 shrink-0 text-teal" aria-hidden="true" />
              <p className="text-ink-soft">
                <span className="font-medium text-ink">Studies from the official registry.</span> Every result links to
                its ClinicalTrials.gov listing and its study contacts.
              </p>
            </li>
            <li className="flex gap-3">
              <ListChecks className="mt-1 size-4 shrink-0 text-teal" aria-hidden="true" />
              <p className="text-ink-soft">
                <span className="font-medium text-ink">Requirements you can check yourself.</span> Each finding points to
                the exact wording in the study.
              </p>
            </li>
            <li className="flex gap-3">
              <Scale className="mt-1 size-4 shrink-0 text-teal" aria-hidden="true" />
              <p className="text-ink-soft">
                <span className="font-medium text-ink">Never a final answer.</span> Only a study&apos;s research team can
                decide who takes part.
              </p>
            </li>
          </ul>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
        <h2 className="text-2xl text-ink">What you&apos;ll get</h2>
        <ol className="mt-8 grid gap-8 md:grid-cols-4">
          {[
            ["Describe", "Write what you know about the diagnosis and treatments. You don't need every detail."],
            ["Check what we understood", "We turn your words into a short profile. Correct anything that's wrong before we search."],
            ["See studies that may fit", "Each study shows what appears to match, what might rule it out, and what's still unknown."],
            ["Take questions to your doctor", "Leave with the specific questions to ask your care team or the study's contacts."],
          ].map(([title, body], i) => (
            <li key={title} className="border-t border-ink pt-4">
              <span className="font-serif text-sm text-ink-soft">Step {i + 1}</span>
              <h3 className="mt-1 text-lg text-ink">{title}</h3>
              <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-soft">{body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-t border-rule bg-white">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[1fr_1.3fr]">
          <div>
            <h2 className="text-2xl text-ink">Read the requirements, not a score</h2>
            <p className="mt-4 max-w-prose leading-relaxed text-ink-soft">
              TrialMatch never shows &ldquo;92% eligible.&rdquo; Each study gets one of four plain labels, and its
              requirements are sorted into three groups: what appears met, what might rule you out, and what still needs
              confirming. A reference like <span className="font-medium text-ink">[I2]</span> means the study&apos;s
              second inclusion requirement, so you can read its exact wording.
            </p>
          </div>
          <LedgerSpecimen />
        </div>
      </section>

      <section aria-labelledby="built-h" className="border-t border-rule">
        <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
          <h2 id="built-h" className="text-lg text-ink">How it&apos;s built</h2>
          <p className="mt-2 max-w-3xl text-[0.95rem] leading-relaxed text-ink-soft">
            Live ClinicalTrials.gov API v2 records, ranked with biomedical sentence embeddings (PubMedBERT in pgvector) and
            keyword search. Clear-cut requirements are checked by deterministic rules; the rest are read by Claude, and a
            validator downgrades any claim it can&apos;t trace to the study&apos;s text or the profile.{" "}
            <Link href="/about" className="text-link underline">Methodology, evaluation and limitations</Link>
          </p>
        </div>
      </section>
    </>
  );
}

/* A static, clearly labeled illustration of the requirements view (fictional patient and study). */
function LedgerSpecimen() {
  return (
    <figure className="rounded-md border border-rule bg-paper p-5">
      <figcaption className="mb-4 text-sm text-ink-soft">
        Example with a fictional patient: lung cancer with an EGFR mutation, previously treated with osimertinib
      </figcaption>
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-sm font-medium text-teal">
            <CheckCircle2 className="size-4" aria-hidden="true" /> Appears met
          </p>
          <p className="text-sm leading-snug text-ink"><span className="font-medium">[I1]</span> Advanced lung cancer with an EGFR mutation</p>
        </div>
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-sm font-medium text-brick">
            <AlertTriangle className="size-4" aria-hidden="true" /> Might rule you out
          </p>
          <p className="text-sm text-ink-soft">None found</p>
        </div>
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-sm font-medium text-amber">
            <CircleHelp className="size-4" aria-hidden="true" /> Still to confirm
          </p>
          <p className="text-sm leading-snug text-ink"><span className="font-medium">[I2]</span> Cancer grew after an EGFR inhibitor. Osimertinib was taken, but growth wasn&apos;t mentioned.</p>
        </div>
      </div>
    </figure>
  );
}
