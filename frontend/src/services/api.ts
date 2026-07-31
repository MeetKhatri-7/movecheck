import axios from 'axios';
import type { AssessmentType } from '@/data/registry';
import { API_BASE_URL } from '@/config';

const api = axios.create({ baseURL: API_BASE_URL });

export interface AnalyseResponse {
  jobId: string;
}

export interface JobStatus {
  status: 'processing' | 'complete' | 'error';
  progress?: number;
  stage?: string;
  result?: Record<string, unknown>;
  error?: string;
  assessmentType?: AssessmentType;
  slug?: string;
  sessionId?: string | null;
}

/**
 * Per-analyzer parameters forwarded as plain form fields. The Node API
 * passes through a fixed allow-list to the Python processor.
 */
export interface AnalyseParams {
  // Mobility
  tibiaLengthCm?: number;        // knee-to-wall calibration constant

  // Strength — shared
  plateSizeKg?: number;          // bar-plate diameter for px/cm calibration
  loadKg?:      number;          // working load on the bar (for 1RM est.)
  weightMax?:   number;          // 1RM-set weight for Epley/Brzycki estimate
  repsMax?:     number;          // reps performed at weightMax
  targetReps?:  number;          // 3 / 5 / 10 etc. (legacy single-cam)
  variant?:     string;          // e.g. 'back-squat' | 'bodyweight' | 'conventional' | 'sumo'

  // Strength — per-exercise
  inclineDeg?:        number;    // bench press
  backrestDeg?:       number;    // overhead press (seated DB) — 75 / 80 / 85 / 90
  stance?:            string;    // overhead press (military) — military_true | strict
  style?:             string;    // bench press / pull-up style
  paused?:            string;    // bench press — paused | tng
  grip?:              string;    // pull-up
  athleteHeightCm?:   number;    // pull-up px/cm fallback
  targetRepsSide?:      number;  // back squat — side-cam rep count
  targetRepsFront?:     number;  // back squat — front-cam rep count
  targetRepsSagittal?:  number;  // bench press, pull-up, OHP — sagittal video rep count
  targetRepsOverhead?:  number;  // bench press — overhead video rep count
  targetRepsHeadEnd?:   number;  // bench press — head-end video rep count
  targetRepsFrontal?:   number;  // pull-up, OHP — frontal video rep count
  targetRepsPosterior?: number;  // pull-up, OHP — posterior video rep count
  targetRepsOblique?:   number;  // bench press, pull-up, OHP — oblique video rep count
}

/** Upload videos for analysis. Returns a `jobId` you should poll. */
export async function uploadAndAnalyse(
  type: AssessmentType,
  slug: string,
  files: Record<string, File>,
  sessionId?: string,
  params?: AnalyseParams,
): Promise<AnalyseResponse> {
  const formData = new FormData();
  Object.entries(files).forEach(([k, file]) => formData.append(k, file));
  if (sessionId) formData.append('sessionId', sessionId);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v != null && v !== '') formData.append(k, String(v));
    }
  }

  const url = `/assessments/${type}/${slug}/analyse${sessionId ? `?sessionId=${encodeURIComponent(sessionId)}` : ''}`;
  const { data } = await api.post<AnalyseResponse>(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
  });
  return data;
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const { data } = await api.get<JobStatus>(`/jobs/${jobId}`);
  return data;
}

export async function cleanupJob(jobId: string): Promise<void> {
  await api.delete(`/jobs/${jobId}`);
}
