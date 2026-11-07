"use client";

import Link from "next/link";
import { Suspense } from "react";
import { usePathname } from "next/navigation";
import { useAppState } from "@/components/app-state";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/intake", label: "Find trials" },
  { href: "/results", label: "Results" },
  { href: "/compare", label: "Compare" },
  { href: "/saved", label: "Saved" },
  { href: "/about", label: "Methodology" },
];

export function SiteNav() {
  return (
    <header className="border-b border-rule bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-baseline gap-2 text-ink" aria-label="TrialMatch AI home">
          <Mark />
          <span className="font-serif text-lg font-semibold tracking-tight">TrialMatch</span>
          <span className="text-sm text-ink-soft">AI</span>
        </Link>
        <Suspense fallback={<NavLinks path={null} />}>
          <ActiveNavLinks />
        </Suspense>
      </div>
    </header>
  );
}

function ActiveNavLinks() {
  return <NavLinks path={usePathname()} />;
}

function NavLinks({ path }: { path: string | null }) {
  const { compare, saved, hydrated } = useAppState();
  return (
        <nav aria-label="Primary" className="-mx-2 flex flex-wrap gap-1 text-sm">
          {LINKS.map((l) => {
            const active = !!path && (path === l.href || path.startsWith(l.href + "/"));
            const count = l.href === "/compare" ? compare.length : l.href === "/saved" ? saved.length : 0;
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded px-2 py-1.5 text-ink-soft hover:bg-mist hover:text-ink",
                  active && "bg-mist font-medium text-ink",
                )}
              >
                {l.label}
                {hydrated && count > 0 && <span className="tabular ml-1 text-xs text-teal">({count})</span>}
              </Link>
            );
          })}
        </nav>
  );
}

/* A stylized eligibility checklist: two ticks and one open box. */
function Mark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" className="translate-y-[3px]">
      <rect x="1" y="1" width="16" height="16" rx="3" fill="#13294B" />
      <path d="M4 5.5l1.4 1.4L8 4.3" stroke="#5EEAD4" strokeWidth="1.5" fill="none" strokeLinecap="round" />
      <path d="M4 10l1.4 1.4L8 8.8" stroke="#5EEAD4" strokeWidth="1.5" fill="none" strokeLinecap="round" />
      <rect x="4" y="12.6" width="3.6" height="2.4" rx=".5" stroke="#F1F4F8" strokeWidth="1" fill="none" />
      <path d="M10 5.6h4M10 10h4M10 13.8h4" stroke="#F1F4F8" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}
