import type { Metadata } from "next";
import { Public_Sans, Source_Serif_4 } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { AppStateProvider } from "@/components/app-state";
import { PreviewNotice } from "@/components/preview-notice";
import { SiteNav } from "@/components/site-nav";

const publicSans = Public_Sans({ variable: "--font-public-sans", subsets: ["latin"] });
const sourceSerif = Source_Serif_4({ variable: "--font-source-serif", subsets: ["latin"], weight: ["500", "600", "700"] });

export const metadata: Metadata = {
  title: { default: "TrialMatch AI — Find clinical trials that fit your medical profile", template: "%s · TrialMatch AI" },
  description:
    "Discover clinical trials from ClinicalTrials.gov based on your medical profile, understand the eligibility criteria, and see what still needs to be checked.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${publicSans.variable} ${sourceSerif.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
          Skip to content
        </a>
        <AppStateProvider>
          <SiteNav />
          <PreviewNotice />
          <main id="main" className="flex-1">{children}</main>
          <footer className="border-t border-rule bg-white">
            <div className="mx-auto grid max-w-6xl gap-6 px-4 py-8 text-sm text-ink-soft sm:px-6 md:grid-cols-[2fr_1fr]">
              <p className="max-w-prose leading-relaxed">
                TrialMatch AI is an informational screening tool, not medical advice. It never determines eligibility:
                each study&apos;s research team makes that decision. Trial data comes from{" "}
                <a className="text-link underline" href="https://clinicaltrials.gov" target="_blank" rel="noreferrer">
                  ClinicalTrials.gov
                </a>
                , a service of the U.S. National Library of Medicine. Please don&apos;t enter names, birthdates, or record numbers.
              </p>
              <nav aria-label="Footer" className="flex flex-col gap-1.5 md:items-end">
                <Link className="hover:underline" href="/about">Methodology and limitations</Link>
                <Link className="hover:underline" href="/about#privacy">Privacy</Link>
              </nav>
            </div>
          </footer>
        </AppStateProvider>
      </body>
    </html>
  );
}
