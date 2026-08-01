import axios from 'axios';
import type { AssessmentType } from '@/data/registry';
import { API_BASE_URL } from '@/config';
import { compressVideo } from '@/services/videoCompress';

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

/**
 * Largest single request the API host will accept. Cloud Run's hard cap is
 * 32 MiB; the margin covers multipart framing and header overhead.
 * This is why videos are uploaded one per request — see uploadAndAnalyse.
 */
const MAX_REQUEST_MB = 30;
const MAX_REQUEST_BYTES = MAX_REQUEST_MB * 1024 * 1024;

/** Per-file progress while preparing and sending an assessment. */
export interface UploadProgress {
  /** Upload slot currently being handled, e.g. 'left' or 'y-overhead'. */
  field: string;
  /** 1-based position and total, for "Video 2 of 6". */
  index: number;
  total: number;
  phase: 'compressing' | 'uploading' | 'done';
  /** 0..1 within the current phase. */
  ratio: number;
}

/**
 * Upload videos for analysis. Returns a `jobId` you should poll.
 *
 * Each video is compressed to 1080p and sent as its OWN request, rather than
 * batching everything into one multipart body. That matters because managed
 * hosts cap request size (Cloud Run: 32 MiB) — and exercises need up to six
 * camera angles, so a combined upload blows the cap no matter how well each
 * clip is compressed. One request per file makes the ceiling depend on the
 * largest single clip instead of the sum.
 *
 * Analysis is then triggered by reference to the staged upload.
 */
export async function uploadAndAnalyse(
  type: AssessmentType,
  slug: string,
  files: Record<string, File>,
  sessionId?: string,
  params?: AnalyseParams,
  onProgress?: (p: UploadProgress) => void,
): Promise<AnalyseResponse> {
  const entries = Object.entries(files);
  const total = entries.length;

  // 1. Open a staging area.
  const { data: staging } = await api.post<{ uploadId: string }>('/uploads');
  const uploadId = staging.uploadId;

  try {
    // 2. Compress + send each clip individually, in sequence. Sequential is
    //    deliberate: parallel re-encodes compete for the same CPU and make
    //    every file slower, while giving the user no clearer feedback.
    for (let i = 0; i < entries.length; i++) {
      const [field, original] = entries[i];

      const prepared = await compressVideo(original, ({ ratio }) =>
        onProgress?.({ field, index: i + 1, total, phase: 'compressing', ratio }),
      );

      // compressVideo degrades to the original file whenever it can't run
      // (old browser, blocked autoplay, unreadable codec). If that original is
      // still oversized the host rejects it at the edge with a bare 413 and no
      // CORS header, which reaches the user as "Network Error". Fail here
      // instead, with something they can actually act on.
      if (prepared.size > MAX_REQUEST_BYTES) {
        const mb = (prepared.size / 1024 / 1024).toFixed(0);
        throw new Error(
          `"${original.name}" is ${mb} MB — too large to upload (limit ${MAX_REQUEST_MB} MB). ` +
          `Your browser couldn't shrink it automatically. Record at 1080p instead of 4K ` +
          `(iPhone: Settings → Camera → Record Video → 1080p HD at 30 fps), or trim the clip shorter.`,
        );
      }

      const form = new FormData();
      form.append('file', prepared, prepared.name);

      await api.post(`/uploads/${uploadId}?field=${encodeURIComponent(field)}`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 600000,
        onUploadProgress: (e) => {
          const ratio = e.total ? e.loaded / e.total : 0;
          onProgress?.({ field, index: i + 1, total, phase: 'uploading', ratio });
        },
      });

      onProgress?.({ field, index: i + 1, total, phase: 'done', ratio: 1 });
    }

    // 3. Trigger analysis against the staged files (JSON — no bodies to cap).
    const body: Record<string, unknown> = { uploadId };
    if (sessionId) body.sessionId = sessionId;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v != null && v !== '') body[k] = v;
      }
    }

    const url = `/assessments/${type}/${slug}/analyse${sessionId ? `?sessionId=${encodeURIComponent(sessionId)}` : ''}`;
    const { data } = await api.post<AnalyseResponse>(url, body, { timeout: 60000 });
    return data;
  } catch (err) {
    // Don't leave orphaned files occupying the server's (RAM-backed) /tmp.
    try { await api.delete(`/uploads/${uploadId}`); } catch { /* best effort */ }
    throw err;
  }
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const { data } = await api.get<JobStatus>(`/jobs/${jobId}`);
  return data;
}

export async function cleanupJob(jobId: string): Promise<void> {
  await api.delete(`/jobs/${jobId}`);
}
