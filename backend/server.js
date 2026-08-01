const express = require('express');
const cors = require('cors');
const multer = require('multer');
const { v4: uuidv4 } = require('uuid');
const axios = require('axios');
const path = require('path');
const fs = require('fs');
const FormData = require('form-data');

const sessionStore = require('./lib/sessionStore');

const app = express();

/* ── Environment-driven config ────────────────────────────────
   Every deployment-specific value is an env var with a local-dev
   default, so the same image runs locally, in docker-compose, and
   on the hosted container with no code changes.               */
const PORT        = Number(process.env.PORT || 3001);
const PYTHON_URL  = process.env.PYTHON_URL || 'http://localhost:5001';
const UPLOAD_DIR  = process.env.UPLOAD_DIR || path.join(__dirname, 'temp_uploads');
// Max upload size per file. Phone 4K clips run 80-150 MB, so the default is
// generous; lower it via env on a memory-constrained host.
const MAX_UPLOAD_MB = Number(process.env.MAX_UPLOAD_MB || 512);
// How long to wait on the Python processor. Pose extraction over a multi-
// minute 4K clip on a shared vCPU can legitimately take several minutes.
const PROCESS_TIMEOUT_MS = Number(process.env.PROCESS_TIMEOUT_MS || 15 * 60 * 1000);
// Optional: serve the built React app from this directory (single-container
// deploys). Unset in the split Vercel + API deployment.
const SERVE_STATIC_DIR = process.env.SERVE_STATIC_DIR || null;

if (!fs.existsSync(UPLOAD_DIR)) fs.mkdirSync(UPLOAD_DIR, { recursive: true });

/* CORS — a comma-separated allowlist. The browser calls this API from the
   Vercel-hosted frontend, which is a different origin, so the deployed
   origin MUST be listed here (via CORS_ORIGIN) or every request fails
   preflight. `*` is accepted for a fully public demo API. */
const CORS_ORIGINS = (process.env.CORS_ORIGIN || 'http://localhost:5173,http://localhost:4173')
  .split(',')
  .map(s => s.trim())
  .filter(Boolean);

app.use(cors({
  origin(origin, cb) {
    // Non-browser clients (curl, server-to-server) send no Origin header.
    if (!origin) return cb(null, true);
    if (CORS_ORIGINS.includes('*') || CORS_ORIGINS.includes(origin)) return cb(null, true);
    // Allow any Vercel deployment URL (production + per-branch previews), so
    // preview builds aren't broken by an exact-match allowlist.
    if (/^https:\/\/[a-z0-9-]+\.vercel\.app$/.test(origin)) return cb(null, true);
    // Reject by simply NOT emitting the CORS header — the browser blocks the
    // response. Passing an Error here instead would surface as a noisy 500.
    return cb(null, false);
  },
}));
app.use(express.json({ limit: '150mb' }));

/* ── Slug → exerciseId map (back-compat with the Python id-based router) ── */
const MOBILITY_SLUG_TO_ID = {
  'knee-to-wall-test':         1,
  'seated-hip-rotation-test':  2,
  'thoracic-extension':        3,
  'quadruped-rotation':        4,
  'shoulder-rotation-90-90':   5,
  'single-leg-glute-bridge':   6,
  'dead-bug':                  7,
  'hollow-body-hold':          8,
  'plank-shoulder-tap':        9,
  'prone-y-t-w-raise':        10,
};
const MOBILITY_ID_TO_SLUG = Object.fromEntries(
  Object.entries(MOBILITY_SLUG_TO_ID).map(([k, v]) => [v, k])
);

const STRENGTH_SLUGS = new Set([
  'back-squat',
  'deadlift',
  'bench-press',
  'pull-up',
  'overhead-press',
]);

const VALID_TYPES = new Set(['mobility', 'strength']);

function resolveSlug(type, slug) {
  if (type === 'mobility') return MOBILITY_SLUG_TO_ID[slug] ? slug : null;
  if (type === 'strength') return STRENGTH_SLUGS.has(slug) ? slug : null;
  return null;
}

/* ── In-memory job store ─────────────────────────────────────── */
const jobs = new Map();

// Prune terminal jobs after a TTL so the Map can't grow unboundedly on a
// long-running server. 30 min leaves plenty of margin for a client that
// stopped polling and comes back. unref() so the timer never holds the
// process open.
const JOB_TTL_MS = 30 * 60 * 1000;
function scheduleJobPrune(jobId) {
  const t = setTimeout(() => jobs.delete(jobId), JOB_TTL_MS);
  if (typeof t.unref === 'function') t.unref();
}

/* ── Multer config ───────────────────────────────────────────── */
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const jobDir = path.join(UPLOAD_DIR, req.jobId || 'unknown');
    if (!fs.existsSync(jobDir)) fs.mkdirSync(jobDir, { recursive: true });
    cb(null, jobDir);
  },
  filename: (req, file, cb) =>
    cb(null, `${file.fieldname}_${Date.now()}${path.extname(file.originalname)}`),
});
const upload = multer({ storage, limits: { fileSize: MAX_UPLOAD_MB * 1024 * 1024 } });

/* ═════════════════════════════════════════════════════════════════
   Staged uploads — one HTTP request per video
   ═════════════════════════════════════════════════════════════════
   Managed hosts cap request bodies (Cloud Run: 32 MiB). Sending every
   clip in a single multipart request breaks the moment an exercise needs
   several: prone-y-t-w-raise takes 6 videos, the barbell lifts take 4.
   Even well-compressed, that total blows the cap.

   So each file is uploaded on its own request into a staging directory,
   and analysis is triggered afterwards by reference. Per-request size
   then depends on the LARGEST single clip, not the sum — which keeps
   every exercise under the limit no matter how many angles it needs.

   The original all-in-one multipart path still works unchanged, so
   local dev and any older client keep functioning.
   ═════════════════════════════════════════════════════════════════ */

const STAGING_DIR = path.join(UPLOAD_DIR, 'staging');
if (!fs.existsSync(STAGING_DIR)) fs.mkdirSync(STAGING_DIR, { recursive: true });

// uploadId -> { dir, files: { field: absolutePath }, createdAt }
const staged = new Map();
const STAGING_TTL_MS = Number(process.env.STAGING_TTL_MS || 60 * 60 * 1000);

function stagingDirFor(uploadId) {
  return path.join(STAGING_DIR, uploadId);
}

function discardStaging(uploadId) {
  const entry = staged.get(uploadId);
  staged.delete(uploadId);
  const dir = entry?.dir || stagingDirFor(uploadId);
  // Guard against a crafted id escaping the staging root.
  if (dir.startsWith(STAGING_DIR) && fs.existsSync(dir)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

function scheduleStagingPrune(uploadId) {
  const t = setTimeout(() => discardStaging(uploadId), STAGING_TTL_MS);
  if (typeof t.unref === 'function') t.unref();
}

// Field names come from the exercise definition (e.g. 'left', 'y-overhead').
const SAFE_FIELD = /^[a-zA-Z0-9_-]{1,64}$/;

const stagingUpload = multer({
  storage: multer.diskStorage({
    destination: (req, _file, cb) => {
      const dir = stagingDirFor(req.params.uploadId);
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
      cb(null, dir);
    },
    // Named after the upload SLOT, never the browser-supplied filename, so
    // two camera angles exported as IMG_0001.MOV can't overwrite each other.
    filename: (req, file, cb) => {
      const field = String(req.query.field || file.fieldname || 'file');
      const ext = path.extname(file.originalname || '') || '.mp4';
      cb(null, `${field}${ext}`);
    },
  }),
  limits: { fileSize: MAX_UPLOAD_MB * 1024 * 1024 },
});

/** Open a staging area. Returns the id the client attaches files to. */
app.post('/api/uploads', (_req, res) => {
  const uploadId = uuidv4();
  const dir = stagingDirFor(uploadId);
  fs.mkdirSync(dir, { recursive: true });
  staged.set(uploadId, { dir, files: {}, createdAt: Date.now() });
  scheduleStagingPrune(uploadId);
  res.json({ uploadId, maxUploadMb: MAX_UPLOAD_MB });
});

/** Attach ONE video to a staging area: POST /api/uploads/:uploadId?field=left */
app.post('/api/uploads/:uploadId', (req, res, next) => {
  const { uploadId } = req.params;
  if (!staged.has(uploadId)) {
    return res.status(404).json({ error: 'Unknown or expired uploadId' });
  }
  const field = String(req.query.field || '');
  if (!SAFE_FIELD.test(field)) {
    return res.status(400).json({ error: `Invalid field name: ${field}` });
  }
  stagingUpload.single('file')(req, res, (err) => {
    if (err) return next(err);
    if (!req.file) return res.status(400).json({ error: 'No file received' });
    const entry = staged.get(uploadId);
    if (!entry) return res.status(404).json({ error: 'Staging area expired mid-upload' });
    entry.files[field] = req.file.path;
    res.json({
      ok: true,
      field,
      bytes: req.file.size,
      received: Object.keys(entry.files),
    });
  });
});

/** Abandon a staging area (client cancelled). */
app.delete('/api/uploads/:uploadId', (req, res) => {
  discardStaging(req.params.uploadId);
  res.json({ ok: true });
});

/* ═════════════════════════════════════════════════════════════════
   Sessions
   ═════════════════════════════════════════════════════════════════ */

app.post('/api/sessions', async (_req, res) => {
  try {
    const session = await sessionStore.create();
    res.json({ sessionId: session.sessionId, session });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/sessions/:sessionId', async (req, res) => {
  try {
    const session = await sessionStore.get(req.params.sessionId);
    res.json(session);
  } catch (e) {
    if (e.code === 'ENOENT') return res.status(404).json({ error: 'Session not found' });
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/sessions/:sessionId/report', async (req, res) => {
  try {
    const report = await sessionStore.aggregate(req.params.sessionId);
    res.json(report);
  } catch (e) {
    if (e.code === 'ENOENT') return res.status(404).json({ error: 'Session not found' });
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/sessions/:sessionId/results', async (req, res) => {
  try {
    const { assessmentType, slug, result } = req.body || {};
    if (!VALID_TYPES.has(assessmentType)) {
      return res.status(400).json({ error: 'Invalid assessmentType' });
    }
    if (!slug || !result) {
      return res.status(400).json({ error: 'slug and result required' });
    }
    const session = await sessionStore.appendResult(
      req.params.sessionId, assessmentType, slug, result
    );
    res.json({ ok: true, session });
  } catch (e) {
    if (e.code === 'ENOENT') return res.status(404).json({ error: 'Session not found' });
    res.status(500).json({ error: e.message });
  }
});

/* ═════════════════════════════════════════════════════════════════
   Analyse — generic per (type, slug)
   ═════════════════════════════════════════════════════════════════ */

function analyseHandler(req, res) {
  const jobId = req.jobId;
  const { type, slug } = req.params;
  const sessionId = req.query.sessionId || req.body.sessionId || null;

  if (!VALID_TYPES.has(type) || !resolveSlug(type, slug)) {
    return res.status(400).json({ error: `Unknown assessment: ${type}/${slug}` });
  }

  // Back-compat exerciseId for the current Python id-dispatch code path
  const exerciseId = type === 'mobility' ? MOBILITY_SLUG_TO_ID[slug] : 0;

  jobs.set(jobId, {
    status: 'processing', progress: 0, stage: 'Uploading',
    assessmentType: type, slug, exerciseId, sessionId,
  });
  res.json({ jobId });

  // Async processing
  (async () => {
    // Files arrive one of two ways: inline as multipart on THIS request
    // (original path), or pre-staged via /api/uploads (used when the total
    // would exceed the host's request-body cap). Normalise both into
    // [{ fieldname, path, originalname }] so the rest is identical.
    const uploadId = req.body?.uploadId || req.query?.uploadId || null;
    let files = [];
    if (uploadId) {
      const entry = staged.get(uploadId);
      if (!entry || !Object.keys(entry.files).length) {
        jobs.set(jobId, {
          status: 'error', progress: 100, stage: 'Failed',
          error: `Upload session ${uploadId} is empty or expired — please re-upload.`,
          assessmentType: type, slug, exerciseId, sessionId,
        });
        scheduleJobPrune(jobId);
        return;
      }
      files = Object.entries(entry.files).map(([field, p]) => ({
        fieldname: field, path: p, originalname: path.basename(p),
      }));
    } else {
      files = req.files || [];
    }

    try {
      jobs.set(jobId, { ...jobs.get(jobId), stage: 'Sending to processor', progress: 10 });

      const form = new FormData();
      form.append('assessmentType', type);
      form.append('slug', slug);
      form.append('exerciseId', String(exerciseId));

      // Forward any analyzer-specific params transparently. Whitelisted so
      // the Python side has a known surface; analyzers ignore params they
      // don't accept (see analyzer_router.route_analysis introspection).
      const passthroughFields = [
        // Mobility
        'tibiaLengthCm',
        // Strength — shared
        'plateSizeKg', 'loadKg', 'targetReps', 'variant', 'weightMax', 'repsMax',
        // Strength — per-exercise
        'inclineDeg',          // bench press
        'backrestDeg',         // overhead press (seated DB) — 75 / 80 / 85 / 90
        'stance',              // overhead press (military) — military_true | strict
        'style',               // bench press — powerlifting | bodybuilding;
                                //   pull-up — strict / kipping / butterfly / sternum / c2b / tactical
        'paused',              // bench press — paused | tng
        'grip',                // pull-up
        'athleteHeightCm',     // pull-up px/cm fallback
        'targetRepsSide',      // back squat — side-cam rep count
        'targetRepsFront',     // back squat — front-cam rep count
        'targetRepsSagittal',  // bench press, pull-up — sagittal video rep count
        'targetRepsOverhead',  // bench press — overhead video rep count
        'targetRepsHeadEnd',   // bench press — head-end video rep count
        'targetRepsFrontal',   // pull-up — frontal video rep count
        'targetRepsPosterior', // pull-up — posterior video rep count
        'targetRepsOblique',   // bench press, pull-up — oblique video rep count
      ];
      for (const fld of passthroughFields) {
        const v = req.body[fld] ?? req.query[fld];
        if (v != null && v !== '') form.append(fld, String(v));
      }

      files.forEach(f => {
        form.append(f.fieldname, fs.createReadStream(f.path), f.originalname);
      });

      const response = await axios.post(`${PYTHON_URL}/process`, form, {
        headers: form.getHeaders(),
        timeout: PROCESS_TIMEOUT_MS,
        maxContentLength: Infinity,
        maxBodyLength: Infinity,
      });

      const result = response.data;
      jobs.set(jobId, {
        status: 'complete', progress: 100, stage: 'Complete',
        result, assessmentType: type, slug, exerciseId, sessionId,
      });
      scheduleJobPrune(jobId);

      // Persist to session JSON file
      if (sessionId) {
        try {
          await sessionStore.appendResult(sessionId, type, slug, result);
        } catch (e) {
          console.error(`Failed to persist result to session ${sessionId}:`, e.message);
        }
      }
    } catch (error) {
      // Pull the real diagnostic from wherever it lives in the axios error.
      // Python returns 500 with {error, detail, status} when route_analysis throws.
      const data = error.response?.data || {};
      const pyError  = data.error || data.message;
      const pyDetail = Array.isArray(data.detail) ? data.detail.join(' | ') : data.detail;
      const httpCode = error.response?.status;
      let finalMsg;
      if (pyError) {
        finalMsg = `Python (${httpCode || 'no-status'}): ${pyError}`;
        if (pyDetail) finalMsg += ` — ${pyDetail}`;
      } else if (typeof data === 'string' && data.length) {
        finalMsg = `Python returned non-JSON ${httpCode}: ${data.slice(0, 240)}`;
      } else if (error.code === 'ECONNREFUSED') {
        finalMsg = `Python processor unreachable at ${PYTHON_URL} — is it running on port 5001?`;
      } else if (error.code === 'ECONNRESET') {
        finalMsg = `Python processor reset the connection — likely crashed mid-request. Check Python logs.`;
      } else if (error.code === 'ETIMEDOUT' || error.code === 'ECONNABORTED') {
        finalMsg = `Python processor timed out after ${Math.round(PROCESS_TIMEOUT_MS / 60000)} min. `
                 + `Videos too large or analyzer stuck.`;
      } else {
        finalMsg = `${error.message} (code=${error.code || 'unknown'})`;
      }
      console.error(`[analyseHandler] ${type}/${slug} FAILED:`);
      console.error(`  ${finalMsg}`);
      if (error.response?.data) {
        console.error(`  Python body:`, JSON.stringify(error.response.data).slice(0, 800));
      }
      jobs.set(jobId, {
        status: 'error', progress: 100, stage: 'Failed',
        error: finalMsg, assessmentType: type, slug, exerciseId, sessionId,
      });
      scheduleJobPrune(jobId);
    } finally {
      const jobDir = path.join(UPLOAD_DIR, jobId);
      if (fs.existsSync(jobDir)) {
        setTimeout(() => {
          fs.rmSync(jobDir, { recursive: true, force: true });
        }, 5000);
      }
      // Staged uploads are consumed by exactly one analysis, so drop them
      // as soon as it settles. Without this they'd linger until the TTL —
      // and on hosts where /tmp is RAM-backed that is memory held hostage.
      if (uploadId) {
        setTimeout(() => discardStaging(uploadId), 5000);
      }
    }
  })();
}

// Pre-assign jobId for any analyse-style endpoint
app.use(['/api/assessments/:type/:slug/analyse', '/api/analyse'], (req, _res, next) => {
  req.jobId = uuidv4();
  next();
});

app.post(
  '/api/assessments/:type/:slug/analyse',
  upload.any(),
  analyseHandler
);

/* ═════════════════════════════════════════════════════════════════
   Jobs
   ═════════════════════════════════════════════════════════════════ */

app.get('/api/jobs/:jobId', (req, res) => {
  const job = jobs.get(req.params.jobId);
  if (!job) return res.status(404).json({ error: 'Job not found' });
  res.json(job);
});

app.delete('/api/jobs/:jobId', (req, res) => {
  const jobDir = path.join(UPLOAD_DIR, req.params.jobId);
  if (fs.existsSync(jobDir)) fs.rmSync(jobDir, { recursive: true, force: true });
  jobs.delete(req.params.jobId);
  res.json({ ok: true });
});

/* ═════════════════════════════════════════════════════════════════
   Legacy aliases — keep old clients working for one cycle
   ═════════════════════════════════════════════════════════════════ */

// Old POST /api/analyse with exerciseId form field → forward through analyseHandler
app.post('/api/analyse', upload.any(), (req, res) => {
  const exerciseId = parseInt(req.body.exerciseId || '1');
  const slug = MOBILITY_ID_TO_SLUG[exerciseId];
  if (!slug) return res.status(400).json({ error: `Unknown exerciseId: ${exerciseId}` });

  // Wire params and re-dispatch
  req.params = { type: 'mobility', slug };
  return analyseHandler(req, res);
});

// Old GET /api/status/:jobId → /api/jobs/:jobId
app.get('/api/status/:jobId', (req, res) => {
  const job = jobs.get(req.params.jobId);
  if (!job) return res.status(404).json({ error: 'Job not found' });
  res.json(job);
});

// Old DELETE /api/cleanup/:jobId → /api/jobs/:jobId
app.delete('/api/cleanup/:jobId', (req, res) => {
  const jobDir = path.join(UPLOAD_DIR, req.params.jobId);
  if (fs.existsSync(jobDir)) fs.rmSync(jobDir, { recursive: true, force: true });
  jobs.delete(req.params.jobId);
  res.json({ ok: true });
});

/* ═════════════════════════════════════════════════════════════════
   Health — used by the platform's health check and by the frontend
   to warm the container before the user uploads anything.
   ═════════════════════════════════════════════════════════════════ */

app.get('/api/health', async (_req, res) => {
  let processor = { reachable: false };
  try {
    const r = await axios.get(`${PYTHON_URL}/health`, { timeout: 10000 });
    processor = { reachable: true, ...r.data };
  } catch (e) {
    processor = { reachable: false, error: e.code || e.message };
  }
  res.json({
    status: processor.reachable ? 'ok' : 'degraded',
    uptimeSec: Math.round(process.uptime()),
    activeJobs: jobs.size,
    processor,
  });
});

/* ═════════════════════════════════════════════════════════════════
   Optional static frontend (single-container deployments only).
   When SERVE_STATIC_DIR is set, this process also serves the built
   React app and falls back to index.html for client-side routes.
   ═════════════════════════════════════════════════════════════════ */

if (SERVE_STATIC_DIR && fs.existsSync(SERVE_STATIC_DIR)) {
  app.use(express.static(SERVE_STATIC_DIR));
  // SPA fallback — anything that isn't an /api route serves index.html so
  // deep links like /assessments/mobility/dead-bug work on a hard refresh.
  app.get(/^\/(?!api\/).*/, (_req, res) => {
    res.sendFile(path.join(SERVE_STATIC_DIR, 'index.html'));
  });
  console.log(`   Serving static frontend from ${SERVE_STATIC_DIR}`);
}

/* ═════════════════════════════════════════════════════════════════ */

// Bind 0.0.0.0 so the process is reachable from outside its container.
app.listen(PORT, '0.0.0.0', () => {
  console.log(`\n🚀 MobilityAI Backend listening on 0.0.0.0:${PORT}`);
  console.log(`   Proxying to Python at ${PYTHON_URL}`);
  console.log(`   CORS allowlist: ${CORS_ORIGINS.join(', ')} (+ *.vercel.app)`);
  console.log(`   Max upload: ${MAX_UPLOAD_MB} MB   Process timeout: ${Math.round(PROCESS_TIMEOUT_MS / 60000)} min`);
  console.log(`   Session storage: ${sessionStore.SESSION_DIR}\n`);
});
