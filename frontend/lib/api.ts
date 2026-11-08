import type {
  CompareResponse, DemoProfile, ExplainResponse, FollowUpQuestion, Health, MatchResponse, MatchResult,
  MethodologyStats, ParseResponse, PatientProfile, Trial,
} from "./types";

// In development the API defaults to the local backend. A production build with no NEXT_PUBLIC_API_URL is a
// website-only preview: requests fail fast with an explanation instead of calling the visitor's own localhost.
export const API_BASE: string | null =
  process.env.NEXT_PUBLIC_API_URL || (process.env.NODE_ENV === "development" ? "http://localhost:8010" : null);
export const API_CONNECTED = API_BASE !== null;
export const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL || null;
export const PREVIEW_MESSAGE =
  "Search isn't connected in this preview: the matching service isn't hosted yet.";

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE) throw new ApiError(0, PREVIEW_MESSAGE, "not_connected");
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "The TrialMatch API could not be reached. Check that the backend is running.");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      throw new ApiError(res.status, detail.message, detail.error);
    }
    if (Array.isArray(detail)) {
      throw new ApiError(res.status, detail.map((d: { msg: string }) => d.msg).join("; "));
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : `Request failed (${res.status})`);
  }
  return body as T;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/api/health"),
  stats: () => request<MethodologyStats>("/api/methodology/stats"),
  demos: () => request<DemoProfile[]>("/api/demo/profiles"),
  parse: (narrative: string, demo = false) => post<ParseResponse>("/api/patients/parse", { narrative, demo }),
  answer: (profile: PatientProfile, question: FollowUpQuestion, answer: string, value?: string | number) =>
    post<PatientProfile>("/api/patients/answer", { profile, question, answer, value }),
  match: (profile: PatientProfile, maxResults = 25) =>
    post<MatchResponse>("/api/trials/match", { profile, max_results: maxResults }),
  trial: (nctId: string) =>
    request<{ trial: Trial; data_source: string; refreshed_at: string | null }>(`/api/trials/${nctId}`),
  sessionResult: (sessionId: string, nctId: string) =>
    request<MatchResult>(`/api/sessions/${sessionId}/results/${nctId}`),
  assess: (nctId: string, sessionId: string, profile: PatientProfile) =>
    post<MatchResult>(`/api/trials/${nctId}/assess`, { session_id: sessionId, profile }),
  explain: (nctId: string, mode: "patient" | "clinical", sessionId?: string, profile?: PatientProfile) =>
    post<ExplainResponse>(`/api/trials/${nctId}/explain`, { mode, session_id: sessionId, profile }),
  compare: (nctIds: string[], sessionId?: string) =>
    post<CompareResponse>("/api/trials/compare", { nct_ids: nctIds, session_id: sessionId }),
  deleteSession: (sessionId: string) => request<void>(`/api/sessions/${sessionId}`, { method: "DELETE" }),
};
