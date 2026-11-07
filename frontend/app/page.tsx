import Link from "next/link";
import { HeroIntake } from "@/components/hero-intake";

export default function Home() {
  return (
    <>
      <section className="border-b border-rule bg-white">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 pb-14 pt-12 sm:px-6 md:pt-16 lg:grid-cols-[1.05fr_1fr] lg:gap-14">
          <div className="max-w-xl">
            <h1 className="text-[2.6rem] leading-[1.05] text-ink sm:text-[3.4rem]">Clinical research, matched to you.</h1>
            <p className="mt-5 text-lg leading-relaxed text-ink-soft">
              Discover clinical trials based on your medical profile, understand the eligibility criteria, and explore
              opportunities for research participation.
            </p>
            <dl className="mt-8 grid max-w-md gap-4 text-sm">
              <div className="border-l-2 border-teal pl-3">
                <dt className="font-medium text-ink">Live registry data</dt>
                <dd className="text-ink-soft">Every study comes from ClinicalTrials.gov and links to its official listing.</dd>
              </div>
              <div className="border-l-2 border-teal pl-3">
                <dt className="font-medium text-ink">Criteria you can check</dt>
                <dd className="text-ink-soft">Each assessment cites the exact inclusion or exclusion criterion it relies on.</dd>
              </div>
              <div className="border-l-2 border-teal pl-3">
                <dt className="font-medium text-ink">Never a verdict</dt>
                <dd className="text-ink-soft">Results are preliminary. Only a study&apos;s research team decides eligibility.</dd>
              </div>
            </dl>
          </div>
          <HeroIntake />
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
        <h2 className="text-2xl text-ink">How a match is built</h2>
        <ol className="mt-8 grid gap-8 md:grid-cols-4">
          {[
            ["Describe", "Write the diagnosis, treatments so far, and where you can travel. Skip names and birthdates."],
            ["Review your profile", "Check what was understood. Every value shows where it came from; correct anything that's wrong."],
            ["Search and rank", "Live ClinicalTrials.gov search, then biomedical semantic and keyword ranking of the candidates."],
            ["Check the criteria", "Rules and Claude compare the profile with each criterion, then a validator verifies every cited fact."],
          ].map(([title, body], i) => (
            <li key={title} className="border-t border-ink pt-4">
              <span className="tabular font-serif text-sm text-ink-soft">Step {i + 1}</span>
              <h3 className="mt-1 text-lg text-ink">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-soft">{body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-t border-rule bg-white">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[1fr_1.3fr]">
          <div>
            <h2 className="text-2xl text-ink">Read the criteria, not a score</h2>
            <p className="mt-4 max-w-prose leading-relaxed text-ink-soft">
              TrialMatch never shows &ldquo;92% eligible.&rdquo; Each study is sorted into one of four plain categories, and
              its criteria are laid out in three columns: what appears met, what may block participation, and what still
              needs confirming. Bracketed references like <span className="font-medium text-ink">[I2]</span> point to the
              exact criterion in the study record.
            </p>
            <Link href="/about" className="mt-6 inline-block text-link underline">How eligibility is assessed</Link>
          </div>
          <LedgerSpecimen />
        </div>
      </section>
    </>
  );
}

/* A static, clearly-labeled illustration of the criteria ledger (fictional example, not a real study). */
function LedgerSpecimen() {
  return (
    <figure className="rounded-md border border-rule bg-paper p-5">
      <figcaption className="mb-4 text-sm text-ink-soft">
        Illustration with a fictional patient and study, based on the EGFR example in our methodology
      </figcaption>
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <p className="mb-2 text-sm font-medium text-teal">Appears met</p>
          <p className="text-sm leading-snug text-ink"><span className="font-medium">[I1]</span> Advanced NSCLC with an activating EGFR mutation</p>
        </div>
        <div>
          <p className="mb-2 text-sm font-medium text-brick">Possible blockers</p>
          <p className="text-sm text-ink-soft">None identified</p>
        </div>
        <div>
          <p className="mb-2 text-sm font-medium text-amber">To confirm</p>
          <p className="text-sm leading-snug text-ink"><span className="font-medium">[I2]</span> Progression after an EGFR inhibitor: osimertinib was taken, but progression wasn&apos;t stated</p>
        </div>
      </div>
    </figure>
  );
}
