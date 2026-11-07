"use client";

/*
  Client-side app state.
  Privacy: the narrative, profile and match results live only in this browser tab's sessionStorage
  (cleared when the tab closes). "Saved trials" keep only NCT ids and titles in localStorage, never
  medical details.
*/

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { MatchResponse, ParseResponse, PatientProfile } from "@/lib/types";

export interface SavedTrial {
  nct_id: string;
  title: string;
  saved_at: string;
}

interface AppState {
  narrative: string;
  setNarrative: (s: string) => void;
  parse: ParseResponse | null;
  setParse: (p: ParseResponse | null) => void;
  profile: PatientProfile | null;
  setProfile: (p: PatientProfile | null) => void;
  match: MatchResponse | null;
  setMatch: (m: MatchResponse | null) => void;
  compare: string[];
  toggleCompare: (nct: string) => void;
  clearCompare: () => void;
  saved: SavedTrial[];
  toggleSaved: (nct: string, title: string) => void;
  isSaved: (nct: string) => boolean;
  clearAll: () => void;
  hydrated: boolean;
}

const Ctx = createContext<AppState | null>(null);
const SESSION_KEY = "trialmatch.session.v1";
const SAVED_KEY = "trialmatch.saved.v1";

function readJSON<T>(storage: () => Storage, key: string, fallback: T): T {
  try {
    const raw = storage().getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJSON(storage: () => Storage, key: string, value: unknown) {
  try {
    storage().setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable (private mode, quota): state simply isn't persisted */
  }
}

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [hydrated, setHydrated] = useState(false);
  const [narrative, setNarrative] = useState("");
  const [parse, setParse] = useState<ParseResponse | null>(null);
  const [profile, setProfile] = useState<PatientProfile | null>(null);
  const [match, setMatch] = useState<MatchResponse | null>(null);
  const [compare, setCompare] = useState<string[]>([]);
  const [saved, setSaved] = useState<SavedTrial[]>([]);

  useEffect(() => {
    const s = readJSON(() => sessionStorage, SESSION_KEY, {} as Partial<{
      narrative: string; parse: ParseResponse; profile: PatientProfile; match: MatchResponse; compare: string[];
    }>);
    /* eslint-disable react-hooks/set-state-in-effect -- one-time hydration from browser storage */
    setNarrative(s.narrative ?? "");
    setParse(s.parse ?? null);
    setProfile(s.profile ?? null);
    setMatch(s.match ?? null);
    setCompare(s.compare ?? []);
    setSaved(readJSON(() => localStorage, SAVED_KEY, [] as SavedTrial[]));
    setHydrated(true);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  useEffect(() => {
    if (hydrated) writeJSON(() => sessionStorage, SESSION_KEY, { narrative, parse, profile, match, compare });
  }, [hydrated, narrative, parse, profile, match, compare]);

  useEffect(() => {
    if (hydrated) writeJSON(() => localStorage, SAVED_KEY, saved);
  }, [hydrated, saved]);

  const toggleCompare = useCallback((nct: string) => {
    setCompare((c) => (c.includes(nct) ? c.filter((x) => x !== nct) : c.length >= 4 ? c : [...c, nct]));
  }, []);
  const toggleSaved = useCallback((nct: string, title: string) => {
    setSaved((s) => (s.some((x) => x.nct_id === nct) ? s.filter((x) => x.nct_id !== nct)
      : [...s, { nct_id: nct, title, saved_at: new Date().toISOString() }]));
  }, []);
  const clearAll = useCallback(() => {
    setNarrative(""); setParse(null); setProfile(null); setMatch(null); setCompare([]);
    try { sessionStorage.removeItem(SESSION_KEY); } catch { /* ignore */ }
  }, []);

  const value = useMemo<AppState>(() => ({
    narrative, setNarrative, parse, setParse, profile, setProfile, match, setMatch, compare, toggleCompare,
    clearCompare: () => setCompare([]), saved, toggleSaved, isSaved: (n) => saved.some((x) => x.nct_id === n),
    clearAll, hydrated,
  }), [narrative, parse, profile, match, compare, toggleCompare, saved, toggleSaved, clearAll, hydrated]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppState() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAppState must be used inside AppStateProvider");
  return v;
}
