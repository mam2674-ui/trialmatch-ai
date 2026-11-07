import type { Metadata } from "next";
import { SystemStats } from "@/components/system-stats";

export const metadata: Metadata = { title: "Methodology and limitations" };

const H = "scroll-mt-6 text-2xl text-ink";

export default function AboutPage() {
  return (
    <div className="mx-auto grid max-w-6xl gap-12 px-4 py-10 sm:px-6 lg:grid-cols-[1fr_20rem]">
      <article className="grid max-w-prose gap-10 leading-relaxed text-ink">
        <header>
          <h1 className="text-3xl">Methodology and limitations</h1>
          <p className="mt-3 text-ink-soft">
            How TrialMatch finds studies, how it compares a profile with eligibility criteria, and where it can be wrong.
          </p>
        </header>

        <section>
          <h2 className={H} id="data">Data source</h2>
          <p className="mt-3">
            All study information comes from the official ClinicalTrials.gov API (version 2), maintained by the U.S. National
            Library of Medicine. Searches run live; records are cached for 24 hours and search results for 6 hours, and every
            page shows when the data was retrieved. If the API cannot be reached and nothing is cached, TrialMatch shows an
            error rather than old or simulated studies. Titles, criteria, contacts and site locations are copied from the
            record; nothing is filled in when a field is missing.
          </p>
        </section>

        <section>
          <h2 className={H} id="search">How studies are found and ranked</h2>
          <p className="mt-3">
            The profile&apos;s condition and positive biomarkers are turned into a focused and a broad ClinicalTrials.gov query,
            filtered by recruitment status and, when a location and travel distance are given, by distance. Candidate records
            are split into sections (title and conditions, summary, interventions, inclusion and exclusion criteria) and embedded
            with a biomedical sentence model (PubMedBERT fine-tuned on MS MARCO), stored in PostgreSQL with pgvector.
          </p>
          <p className="mt-3">
            Search relevance is a weighted average of visible parts: condition match, semantic similarity, keyword (BM25) overlap,
            biomarker mentions, subtype and stage terms, treatment history, recruitment status and distance. A study whose title
            names the opposite biomarker status (for example HER2-negative for a HER2-positive profile) has its relevance reduced.
            Relevance measures topic match only. It is never a probability of eligibility, and studies with an identified
            blocker are always listed below studies without one.
          </p>
        </section>

        <section>
          <h2 className={H} id="eligibility">How eligibility is assessed</h2>
          <p className="mt-3">Three layers, in this order:</p>
          <ol className="mt-3 list-decimal space-y-2 pl-5">
            <li>
              <span className="font-medium">Deterministic rules</span> check clear-cut requirements: age limits, sex, recruitment
              status, explicit biomarker requirements, named prior therapies, disease stage, ECOG score and pregnancy. Rules only
              give a definite answer when the criterion is unambiguous: no alternatives, exceptions, time windows, or
              subgroup-only conditions.
            </li>
            <li>
              <span className="font-medium">Claude</span> reads every criterion and labels it met, not met, unknown or not
              applicable, quoting the criterion and the profile facts it relied on. For exclusion criteria, &ldquo;met&rdquo;
              means the exclusion is present, which is a potential blocker.
            </li>
            <li>
              <span className="font-medium">A validator</span> then checks every claim: the study ID must match a retrieved
              record, cited criteria must exist, quotes must appear verbatim in the record, and every patient fact must exist in
              the profile. Unsupported claims are downgraded to unknown; if many fail, all AI output for that study is withheld.
              Rule results always override the model.
            </li>
          </ol>
          <p className="mt-3">Each study then receives one of four categories:</p>
          <dl className="mt-3 grid gap-2">
            <div><dt className="inline font-medium text-teal">Potential match: </dt><dd className="inline">no blockers identified; final eligibility is unverified.</dd></div>
            <div><dt className="inline font-medium text-amber">Needs more information: </dt><dd className="inline">key requirements can&apos;t be checked yet, or the criteria were not analyzed.</dd></div>
            <div><dt className="inline font-medium text-violet">Requires clinical review: </dt><dd className="inline">a key criterion depends on ambiguous wording or professional interpretation.</dd></div>
            <div><dt className="inline font-medium text-brick">Potentially ineligible: </dt><dd className="inline">at least one documented criterion appears incompatible.</dd></div>
          </dl>
          <p className="mt-3">
            Missing information is always treated as unknown, never as meeting a requirement. Without Claude, TrialMatch still
            shows retrieved studies and rule-based checks, labels the remaining criteria &ldquo;not analyzed,&rdquo; and never
            invents an AI assessment.
          </p>
        </section>

        <section>
          <h2 className={H} id="limitations">Limitations</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5">
            <li>This is a portfolio research tool. It has not been clinically validated, and its evaluation uses fictional cases.</li>
            <li>Eligibility text is free-form. About 2% of records lack clear inclusion/exclusion headings, so some criteria are left unclassified.</li>
            <li>Distances use the city-level coordinates ClinicalTrials.gov publishes and are approximate.</li>
            <li>Site-level recruitment status can lag behind reality. Always confirm with the study contact.</li>
            <li>Language models can misread criteria. Validation reduces but does not remove this risk.</li>
          </ul>
        </section>

        <section>
          <h2 className={H} id="privacy">Privacy and safety</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5">
            <li>No account is needed and names, birthdates or record numbers are never requested. Please don&apos;t enter them.</li>
            <li>Descriptions are processed in memory and not stored or logged. Server logs record only the route, status and timing.</li>
            <li>Match results are kept in an anonymous session that is deleted automatically after 60 minutes, or immediately when you choose &ldquo;Delete my data now.&rdquo;</li>
            <li>Your profile stays in this browser tab&apos;s session storage and is cleared when the tab closes. Saved studies keep only study numbers and titles.</li>
            <li>Only the structured clinical facts needed for screening are sent to Anthropic&apos;s API, and only your city or postal code is sent to the geocoder (OpenStreetMap Nominatim).</li>
            <li>Study text and patient descriptions are treated as untrusted data, so instructions hidden inside them are ignored.</li>
            <li>
              TrialMatch does not claim HIPAA compliance. A real clinical deployment would need further security, privacy, legal
              and compliance review, including whether HIPAA applies and appropriate agreements with service providers.
            </li>
          </ul>
        </section>
      </article>
      <aside className="lg:sticky lg:top-6 lg:self-start">
        <SystemStats />
      </aside>
    </div>
  );
}
