/**
 * Session service — anonymous, per-device session bootstrapping.
 *
 * - sessionId is stored in localStorage('mobilityai_session_id').
 * - On first load OR if the server doesn't recognise the stored id,
 *   POST /api/sessions creates a new one.
 * - All subsequent /assessments/.../analyse requests include the sessionId
 *   so the backend can persist results into the right session JSON file.
 */
import axios from 'axios';
import type { AssessmentType } from '@/data/registry';
import { API_BASE_URL } from '@/config';

const api = axios.create({ baseURL: API_BASE_URL });
const SESSION_KEY = 'mobilityai_session_id';

export interface SessionData {
  sessionId: string;
  createdAt: string;
  updatedAt: string;
  assessments: {
    mobility: { reports: Record<string, any>; completedAt: string | null };
    strength: { reports: Record<string, any>; completedAt: string | null };
  };
}

function readStoredId(): string | null {
  try { return localStorage.getItem(SESSION_KEY); } catch { return null; }
}

function writeStoredId(id: string) {
  try { localStorage.setItem(SESSION_KEY, id); } catch {}
}

/** Create a brand-new session on the server. */
async function createSession(): Promise<SessionData> {
  const { data } = await api.post<{ sessionId: string; session: SessionData }>('/sessions');
  return data.session;
}

/** Fetch an existing session. Returns null on 404. */
async function fetchSession(id: string): Promise<SessionData | null> {
  try {
    const { data } = await api.get<SessionData>(`/sessions/${id}`);
    return data;
  } catch (e: any) {
    if (e?.response?.status === 404) return null;
    throw e;
  }
}

/**
 * Boot a session: hydrate the stored one if it still exists on the server,
 * otherwise create a fresh one. Always returns a usable SessionData.
 */
export async function ensureSession(): Promise<SessionData> {
  const stored = readStoredId();
  if (stored) {
    const existing = await fetchSession(stored);
    if (existing) return existing;
  }
  const fresh = await createSession();
  writeStoredId(fresh.sessionId);
  return fresh;
}

/** Get the current sessionId without making a network call. */
export function getStoredSessionId(): string | null {
  return readStoredId();
}

/** Manually push a result into the current session (also auto-saved server-side post-analyse). */
export async function pushResult(
  sessionId: string,
  assessmentType: AssessmentType,
  slug: string,
  result: any,
): Promise<SessionData> {
  const { data } = await api.post<{ ok: boolean; session: SessionData }>(
    `/sessions/${sessionId}/results`,
    { assessmentType, slug, result },
  );
  return data.session;
}

/** Clear the stored sessionId — next ensureSession() will mint a new one. */
export function resetSession(): void {
  try { localStorage.removeItem(SESSION_KEY); } catch {}
}

/** Fetch the latest session JSON from the server (source of truth). */
export async function fetchSessionDetails(sessionId: string): Promise<SessionData | null> {
  if (!sessionId) return null;
  try {
    const { data } = await api.get<SessionData>(`/sessions/${sessionId}`);
    return data;
  } catch (e: any) {
    if (e?.response?.status === 404) return null;
    throw e;
  }
}

/** Fetch the aggregated (flattened) report for the dashboard. */
export interface AggregatedReport {
  sessionId:      string;
  createdAt:      string;
  updatedAt:      string;
  totalCompleted: number;
  results: Array<{
    assessmentType: 'mobility' | 'strength';
    slug:           string;
    result:         any;
  }>;
  assessments: SessionData['assessments'];
}

export async function fetchSessionAggregate(sessionId: string): Promise<AggregatedReport | null> {
  if (!sessionId) return null;
  try {
    const { data } = await api.get<AggregatedReport>(`/sessions/${sessionId}/report`);
    return data;
  } catch (e: any) {
    if (e?.response?.status === 404) return null;
    throw e;
  }
}
