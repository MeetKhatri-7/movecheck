import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { AssessmentType } from '@/data/registry';
import { ensureSession, pushResult, type SessionData } from '@/services/session';
import { warmUpApi } from '@/config';
import {
  loadDemoIndex, loadDemoReport, isDemoMode, setDemoMode, FLAGSHIP_DEMO,
} from '@/services/demo';

type ReportsBuckets = {
  mobility: Record<string, any>;
  strength: Record<string, any>;
};

export interface UserProfile {
  tibiaLengthCm?:    number;     // mobility — zero-setup px/cm calibration
  athleteHeightCm?:  number;     // strength — pull-up fallback calibration
  plateSizeKg?:      number;     // strength — bar plate diameter calibration
}

/** Per-exercise inputs (variant, load, reps, etc.). Keyed by exercise slug. */
export type ExerciseInputs = Record<string, Record<string, string | number>>;

/**
 * The live result of the most recent analysis, tagged with the exercise it
 * belongs to. The tag lets ResultPage ignore a stale value when the user
 * lands on a *different* exercise's result URL via browser history — an
 * untagged global result used to render exercise A's data on exercise B's page.
 */
export interface LiveResult {
  type: AssessmentType;
  slug: string;
  result: any;
}

interface AppContextType {
  sessionId: string | null;
  sessionLoading: boolean;

  uploads: Record<string, File>;
  setUpload: (key: string, file: File) => void;

  reports: ReportsBuckets;
  saveReport: (type: AssessmentType, slug: string, result: any) => Promise<void>;

  apiResult: LiveResult | null;
  setApiResult: (r: LiveResult | null) => void;

  completed: { mobility: Set<string>; strength: Set<string> };

  profile: UserProfile;
  updateProfile: (patch: Partial<UserProfile>) => void;

  exerciseInputs: ExerciseInputs;
  setExerciseInput: (slug: string, key: string, value: string | number) => void;

  /* ── Demo mode ──────────────────────────────────────────────
     Real pre-computed analyzer output, served from the CDN, so the
     app is fully explorable without uploading a video or waking the
     CV container. See services/demo.ts. */
  demoMode: boolean;
  demoAvailable: { mobility: Set<string>; strength: Set<string> };
  /** Turn demo mode on and preload the flagship report. */
  enterDemoMode: () => Promise<void>;
  /** Turn it off and drop every demo-sourced report from state. */
  exitDemoMode: () => void;
  /** Lazily fetch one sample report into `reports`. */
  loadDemo: (type: AssessmentType, slug: string) => Promise<any | null>;
}

const AppContext = createContext<AppContextType | null>(null);

const LEGACY_REPORTS_KEY = 'mobilityai_reports_v1';
const LOCAL_REPORTS_KEY  = 'mobilityai_reports_v2';
const PROFILE_KEY        = 'mobilityai_profile_v1';
const INPUTS_KEY         = 'mobilityai_exercise_inputs_v1';

function loadProfile(): UserProfile {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}
function saveProfile(p: UserProfile) {
  try { localStorage.setItem(PROFILE_KEY, JSON.stringify(p)); } catch {}
}

function loadInputs(): ExerciseInputs {
  try {
    const raw = localStorage.getItem(INPUTS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}
function saveInputs(v: ExerciseInputs) {
  try { localStorage.setItem(INPUTS_KEY, JSON.stringify(v)); } catch {}
}

function loadLocalReports(): ReportsBuckets {
  try {
    const raw = localStorage.getItem(LOCAL_REPORTS_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return { mobility: {}, strength: {} };
}

/**
 * Strip heavyweight payloads (base64 annotated frames) before caching.
 * A single session's results can exceed 9 MB while localStorage quota is
 * ~5 MB — writing the full payload failed silently and left the cache
 * permanently stale. The server session file keeps the full result; the
 * cache only needs the scores/metrics for fast boot.
 */
function stripHeavyFields(result: any): any {
  if (result && Array.isArray(result.annotated_frames) && result.annotated_frames.length > 0) {
    return { ...result, annotated_frames: [] };
  }
  return result;
}

function slimReports(r: ReportsBuckets): ReportsBuckets {
  const slim = (bucket: Record<string, any>) =>
    Object.fromEntries(
      Object.entries(bucket)
        // Demo reports are never cached: they're static CDN assets that can be
        // re-fetched instantly, and persisting them stripped of their annotated
        // frames would leave permanently image-less entries after a reload.
        .filter(([, v]) => !v?._isDemo)
        .map(([k, v]) => [k, stripHeavyFields(v)]),
    );
  return { mobility: slim(r.mobility), strength: slim(r.strength) };
}

function saveLocalReports(r: ReportsBuckets) {
  try {
    localStorage.setItem(LOCAL_REPORTS_KEY, JSON.stringify(slimReports(r)));
  } catch (e) {
    console.warn('Local report cache write failed (results are still on the server):', e);
  }
}

/** Slug map for migrating legacy id-keyed reports → slug-keyed. */
const LEGACY_ID_TO_SLUG: Record<number, string> = {
  1: 'knee-to-wall-test',
  2: 'seated-hip-rotation-test',
  3: 'thoracic-extension',
  4: 'quadruped-rotation',
  5: 'shoulder-rotation-90-90',
  6: 'single-leg-glute-bridge',
  7: 'dead-bug',
  8: 'hollow-body-hold',
  9: 'plank-shoulder-tap',
  10: 'prone-y-t-w-raise',
};

function migrateLegacyReports(): Record<string, any> | null {
  try {
    const raw = localStorage.getItem(LEGACY_REPORTS_KEY);
    if (!raw) return null;
    const old = JSON.parse(raw) as Record<string, any>;
    const out: Record<string, any> = {};
    for (const [key, value] of Object.entries(old)) {
      const id = Number(key);
      const slug = LEGACY_ID_TO_SLUG[id];
      if (slug) out[slug] = value;
    }
    localStorage.removeItem(LEGACY_REPORTS_KEY);
    return out;
  } catch { return null; }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [uploads, setUploads] = useState<Record<string, File>>({});
  const [reports, setReports] = useState<ReportsBuckets>(() => loadLocalReports());
  const [apiResult, setApiResult] = useState<LiveResult | null>(null);
  const [profile, setProfile] = useState<UserProfile>(() => loadProfile());
  const [exerciseInputs, setExerciseInputs] = useState<ExerciseInputs>(() => loadInputs());
  const [demoMode, setDemoModeState] = useState<boolean>(() => isDemoMode());
  const [demoAvailable, setDemoAvailable] = useState<{
    mobility: Set<string>; strength: Set<string>;
  }>({ mobility: new Set(), strength: new Set() });

  useEffect(() => { saveProfile(profile); }, [profile]);
  useEffect(() => { saveInputs(exerciseInputs); }, [exerciseInputs]);

  // Discover which sample reports exist (cheap — a ~4 KB index) and start
  // warming the API container in parallel, so a user who does choose to
  // upload isn't paying the full cold-start penalty when they get there.
  useEffect(() => {
    let cancelled = false;
    warmUpApi();
    loadDemoIndex()
      .then(idx => {
        if (cancelled) return;
        const next = { mobility: new Set<string>(), strength: new Set<string>() };
        for (const r of idx.reports) {
          if (r.assessmentType === 'mobility' || r.assessmentType === 'strength') {
            next[r.assessmentType].add(r.slug);
          }
        }
        setDemoAvailable(next);
      })
      .catch(() => { /* demo assets missing — the live flow still works */ });
    return () => { cancelled = true; };
  }, []);

  const updateProfile = (patch: Partial<UserProfile>) =>
    setProfile(prev => ({ ...prev, ...patch }));
  const setExerciseInput = (slug: string, key: string, value: string | number) =>
    setExerciseInputs(prev => ({ ...prev, [slug]: { ...(prev[slug] || {}), [key]: value } }));

  // Bootstrap session + hydrate from server (with localStorage migration)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const session: SessionData = await ensureSession();
        if (cancelled) return;
        setSessionId(session.sessionId);

        const serverReports: ReportsBuckets = {
          mobility: { ...session.assessments.mobility.reports },
          strength: { ...session.assessments.strength.reports },
        };

        // Migrate legacy v1 reports if present and the server has nothing yet
        if (Object.keys(serverReports.mobility).length === 0) {
          const migrated = migrateLegacyReports();
          if (migrated) {
            for (const [slug, result] of Object.entries(migrated)) {
              try { await pushResult(session.sessionId, 'mobility', slug, result); }
              catch (e) { console.warn(`Failed to migrate ${slug}:`, e); }
            }
            serverReports.mobility = { ...migrated };
          }
        }

        // MERGE server state into local state — never replace. The server
        // wins for slugs it has (it holds the full, unstripped results),
        // but local-only results MUST survive: they exist precisely because
        // an earlier server push failed, and replacing wholesale destroyed
        // them permanently on every reload.
        const local = loadLocalReports();
        for (const type of ['mobility', 'strength'] as const) {
          for (const [slug, result] of Object.entries(local[type])) {
            if (!serverReports[type][slug]) {
              // Re-sync the result the server is missing.
              try { await pushResult(session.sessionId, type, slug, result); }
              catch (e) { console.warn(`Failed to re-sync ${type}/${slug}:`, e); }
            }
          }
        }
        if (cancelled) return;
        setReports(prev => ({
          mobility: { ...prev.mobility, ...serverReports.mobility },
          strength: { ...prev.strength, ...serverReports.strength },
        }));
      } catch (e) {
        console.error('Session bootstrap failed:', e);
      } finally {
        if (!cancelled) setSessionLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Persist local cache on every change
  useEffect(() => { saveLocalReports(reports); }, [reports]);

  const setUpload = (key: string, file: File) =>
    setUploads(prev => ({ ...prev, [key]: file }));

  const saveReport = async (type: AssessmentType, slug: string, result: any) => {
    setReports(prev => ({
      ...prev,
      [type]: { ...prev[type], [slug]: result },
    }));
    if (sessionId) {
      try { await pushResult(sessionId, type, slug, result); }
      catch (e) { console.warn('Server-side save failed (local cache still updated):', e); }
    }
  };

  /* ── Demo mode actions ────────────────────────────────────── */

  /**
   * Fetch a sample report and merge it into `reports` so every existing
   * screen (result, dashboard, guide) renders it through the normal path
   * with no special-casing. Demo results are deliberately NOT pushed to
   * the server session — they aren't the user's data.
   */
  const loadDemo = async (type: AssessmentType, slug: string) => {
    try {
      const result = await loadDemoReport(type, slug);
      setReports(prev => ({ ...prev, [type]: { ...prev[type], [slug]: result } }));
      return result;
    } catch (e) {
      console.warn(`Sample report unavailable for ${type}/${slug}:`, e);
      return null;
    }
  };

  const enterDemoMode = async () => {
    setDemoMode(true);
    setDemoModeState(true);
    await loadDemo(FLAGSHIP_DEMO.type, FLAGSHIP_DEMO.slug);
  };

  const exitDemoMode = () => {
    setDemoMode(false);
    setDemoModeState(false);
    // Strip demo-sourced entries so the user's own results are all that's left.
    setReports(prev => {
      const strip = (bucket: Record<string, any>) =>
        Object.fromEntries(Object.entries(bucket).filter(([, v]) => !v?._isDemo));
      return { mobility: strip(prev.mobility), strength: strip(prev.strength) };
    });
    setApiResult(null);
  };

  const completed = {
    mobility: new Set(Object.keys(reports.mobility)),
    strength: new Set(Object.keys(reports.strength)),
  };

  return (
    <AppContext.Provider
      value={{
        sessionId, sessionLoading,
        uploads, setUpload,
        reports, saveReport,
        apiResult, setApiResult,
        completed,
        profile, updateProfile,
        exerciseInputs, setExerciseInput,
        demoMode, demoAvailable, enterDemoMode, exitDemoMode, loadDemo,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext must be used inside <AppProvider>');
  return ctx;
}
