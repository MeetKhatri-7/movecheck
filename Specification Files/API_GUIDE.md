# MobilityAI — API Guide

The system is split across **two services**:

| Service           | Port | URL                       | Role                                                     |
| ----------------- | ---- | ------------------------- | -------------------------------------------------------- |
| Node/Express API  | 3001 | `http://localhost:3001`   | Public-facing API. Sessions, uploads, job state.         |
| Python Processor  | 5001 | `http://localhost:5001`   | Internal CV pipeline. Called by the Node API.            |

The frontend talks **only** to the Node API (proxied via `/api`).

There are **two assessment tracks**:

| Track    | URL prefix                          | Status                                       |
| -------- | ----------------------------------- | -------------------------------------------- |
| Mobility | `/api/assessments/mobility/...`     | Live — 10 exercises analysed via MediaPipe.  |
| Strength | `/api/assessments/strength/...`     | Scaffolded — `barbell-back-squat` placeholder. |

Each session can hold results from **both** tracks; they're persisted side-by-side in one JSON file per session.

---

## Sessions

A **session** is an anonymous, per-device container for a user's results. It is created on the first frontend load (no auth) and its `sessionId` lives in `localStorage('mobilityai_session_id')`. The server stores one JSON file per session at `backend/sessions/<sessionId>.json`.

### `POST /api/sessions` — Create a new session

**Request:**
```
POST /api/sessions
```

**Response — `200 OK`:**
```json
{
  "sessionId": "8c1d1f2c-...",
  "session": {
    "sessionId": "8c1d1f2c-...",
    "createdAt": "2026-05-10T12:34:56.000Z",
    "updatedAt": "2026-05-10T12:34:56.000Z",
    "assessments": {
      "mobility": { "reports": {}, "completedAt": null },
      "strength": { "reports": {}, "completedAt": null }
    }
  }
}
```

### `GET /api/sessions/:sessionId` — Read a session

Returns the full session JSON (same shape as `session` above with whatever results have been appended). Returns `404` if not found.

### `GET /api/sessions/:sessionId/report` — Aggregated report

Convenience endpoint for the dashboard — flattens both assessment buckets into a single `results[]` array.

```json
{
  "sessionId": "8c1d1f2c-...",
  "createdAt": "...",
  "updatedAt": "...",
  "totalCompleted": 3,
  "results": [
    { "assessmentType": "mobility", "slug": "knee-to-wall-test", "result": { ... } },
    { "assessmentType": "mobility", "slug": "dead-bug",         "result": { ... } },
    { "assessmentType": "strength", "slug": "barbell-back-squat","result": { ... } }
  ],
  "assessments": { ... }
}
```

### `POST /api/sessions/:sessionId/results` — Manually push a result

Usually you don't need this — when an `analyse` job completes the server auto-persists the result into the session. Use this only to seed migrated data or correct state.

**Request:**
```json
{
  "assessmentType": "mobility",
  "slug": "knee-to-wall-test",
  "result": { ...ExerciseResult }
}
```

**Response:** `{ "ok": true, "session": { ... } }`

---

## Analyse — upload videos

### `POST /api/assessments/:type/:slug/analyse` — Start a job

The unified analyse endpoint.  `:type` is `mobility` or `strength`, `:slug` is the exercise slug. Returns immediately with a `jobId`; analysis runs **asynchronously** on the backend.

**Request:**
```
POST /api/assessments/mobility/knee-to-wall-test/analyse?sessionId=<id>
Content-Type: multipart/form-data
```

| Field          | Type   | Required | Notes                                                       |
| -------------- | ------ | -------- | ----------------------------------------------------------- |
| `<upload-id>`  | File   | ✅        | One file per upload slot. Field name = the upload's `id`.   |
| `sessionId`    | string | ⚠️ recommended | If present (query OR form field), result is auto-persisted to that session's JSON. |

**Per-exercise field names:**

| Track    | Slug                          | Required field names                                              |
| -------- | ----------------------------- | ----------------------------------------------------------------- |
| mobility | `knee-to-wall-test`           | `left`, `right`                                                   |
| mobility | `seated-hip-rotation-test`    | `left`, `right`                                                   |
| mobility | `thoracic-extension`          | `all`                                                             |
| mobility | `quadruped-rotation`          | `left`, `right`                                                   |
| mobility | `shoulder-rotation-90-90`     | `left`, `right`                                                   |
| mobility | `single-leg-glute-bridge`     | `left`, `right`                                                   |
| mobility | `dead-bug`                    | `all`                                                             |
| mobility | `hollow-body-hold`            | `hold`                                                            |
| mobility | `plank-shoulder-tap`          | `all`                                                             |
| mobility | `prone-y-t-w-raise`           | `y-overhead`, `y-footside`, `t-overhead`, `t-footside`, `w-overhead`, `w-footside` |
| strength | `barbell-back-squat`          | `all` (placeholder)                                               |

**Constraints:** each file ≤ 2 GB.

**Response — `200 OK`:** `{ "jobId": "..." }`

**Response — `400`:** `{ "error": "Unknown assessment: ..." }`

**Example — cURL:**
```bash
curl -X POST "http://localhost:3001/api/assessments/mobility/knee-to-wall-test/analyse?sessionId=$SID" \
  -F 'left=@./left_side.mp4' \
  -F 'right=@./right_side.mp4'
```

**Example — JavaScript (frontend):**
```ts
const fd = new FormData();
fd.append('left',  leftFile);
fd.append('right', rightFile);

const res = await fetch(
  `/api/assessments/mobility/knee-to-wall-test/analyse?sessionId=${sessionId}`,
  { method: 'POST', body: fd },
);
const { jobId } = await res.json();
```

---

## Jobs — poll for completion

### `GET /api/jobs/:jobId`

Poll once per second until `status` is `complete` or `error`.

**Response — `200 OK` (in progress):**
```json
{
  "status": "processing",
  "progress": 35,
  "stage": "Sending to processor",
  "assessmentType": "mobility",
  "slug": "knee-to-wall-test",
  "sessionId": "8c1d1f2c-..."
}
```

**Response — `200 OK` (complete):**
```json
{
  "status": "complete",
  "progress": 100,
  "stage": "Complete",
  "assessmentType": "mobility",
  "slug": "knee-to-wall-test",
  "sessionId": "8c1d1f2c-...",
  "result": {
    "status": "RESTRICTED",
    "score": 62,
    "summary": "...",
    "stats":   { ... },
    "metrics": [ ... ],
    "bilateral": [ ... ],
    "coaching": [ "..." ],
    "annotated_frames": [ ... ],
    "per_rep": [ ... ]
  }
}
```

When `status === "complete"` and `sessionId` was supplied, the result is **already persisted** to `backend/sessions/<sessionId>.json` — no extra round-trip needed.

**Response — `404`:** `{ "error": "Job not found" }`

### `DELETE /api/jobs/:jobId`

Optional cleanup — removes the job from in-memory state and any leftover upload files. Uploads auto-clean 5 s after a job completes, so calling this is only useful if you abandon a job mid-flight.

---

## Result schema

Stored under `result` in `GET /api/jobs/:jobId` and under `assessments[type].reports[slug]` in the session JSON.

```ts
interface ExerciseResult {
  status: 'GOOD' | 'NEEDS IMPROVEMENT' | 'RESTRICTED' | 'ADEQUATE' | 'PASS';
  score:  number;            // 0-100 composite
  summary: string;
  stats: {
    validReps:  string;
    confidence: string;
    sides:      string;
    cameraView: 'OK' | 'UNKNOWN';
    passRate?:  string;
  };
  metrics: Array<{
    name: string; value: string; raw: number;
    target: string; max: number; status: 'good' | 'bad';
  }>;
  bilateral: Array<{
    name: string; left: number; right: number;
    unit: string; max: number; asymmetry: number;
  }>;
  coaching: string[];
  annotated_frames: Array<{
    label: string; image_base64: string;
    rep_num: number; side: string; is_best: boolean;
    metrics_shown: string[];
  }>;
  per_rep: Array<{
    rep: number; side: string;
    metrics: Record<string, number | string>;
  }>;
}
```

---

## Session JSON file shape

`backend/sessions/<sessionId>.json`:

```json
{
  "sessionId": "8c1d1f2c-...",
  "createdAt": "2026-05-10T12:34:56.000Z",
  "updatedAt": "2026-05-10T13:00:00.000Z",
  "assessments": {
    "mobility": {
      "reports": {
        "knee-to-wall-test": { /* ExerciseResult */ },
        "dead-bug":          { /* ExerciseResult */ }
      },
      "completedAt": null
    },
    "strength": {
      "reports": {
        "barbell-back-squat": { /* ExerciseResult */ }
      },
      "completedAt": null
    }
  }
}
```

Writes are atomic (temp file + rename) and serialised per-session via an in-memory mutex, so rapid back-to-back result appends don't corrupt the file.

---

## Lifecycle of a request

```
Frontend                     Node API (3001)              Python (5001)            Disk
────────                     ──────────────               ─────────────            ────
[boot]
GET /api/sessions/:id  ──►   404 (or session JSON)
POST /api/sessions     ──►   200 { sessionId }      ─────────────────────────►  sessions/<id>.json

[analyse a video]
POST /api/assessments/
   mobility/<slug>/analyse
   ?sessionId=<id>     ──►   200 { jobId }
                             │ (async)
                             ▼
                             POST /process       ───────►   (CV runs, ~30-120s)
GET /api/jobs/:jobId   ──►   { processing, … }       │
                                                     ▼
                             ◄──────────── result JSON ────
                             │  appendResult(...)        ────────────────────►  sessions/<id>.json (updated)
GET /api/jobs/:jobId   ──►   { complete, result }
```

---

## Legacy aliases (back-compat)

Old endpoints still work for one release cycle so any in-flight client code doesn't break:

| Legacy                              | Equivalent (new)                                            |
| ----------------------------------- | ----------------------------------------------------------- |
| `POST /api/analyse` + `exerciseId`  | `POST /api/assessments/mobility/<resolved-slug>/analyse`    |
| `GET  /api/status/:jobId`           | `GET  /api/jobs/:jobId`                                     |
| `DELETE /api/cleanup/:jobId`        | `DELETE /api/jobs/:jobId`                                   |

The Node layer maps the legacy `exerciseId` (1–10) back to the corresponding mobility slug internally.

---

## Health

### `GET /health` (Python processor — `:5001`)

Internal sanity check:
```json
{ "status": "ok", "cv_available": true, "exercises": [1,…,10] }
```

---

## Internal — Python processor (`:5001`)

You should not call this from the frontend.

### `POST /process`

Same multipart contract as the public `analyse` endpoint, but **synchronous** (blocks for up to 5 minutes while CV runs). Returns the `result` body directly with no `jobId`.

Form fields the processor reads:
- `assessmentType` — `mobility` | `strength`
- `slug` — exercise slug
- `exerciseId` — legacy fallback (mobility only) if `slug` is missing

The processor's [`analyzer_router.py`](processor/analyzer_router.py) maps `(assessmentType, slug)` to the right Python module via a registry — see `ANALYZERS` in that file to wire a new exercise.

---

## Frontend service module

The frontend calls the API through:

- [src/services/api.ts](frontend/src/services/api.ts) — `uploadAndAnalyse`, `getJobStatus`, `cleanupJob`
- [src/services/session.ts](frontend/src/services/session.ts) — `ensureSession`, `getStoredSessionId`, `pushResult`, `resetSession`

Use `ensureSession()` once on app boot (already done in [`AppContext`](frontend/src/context/AppContext.tsx)). All subsequent `uploadAndAnalyse` calls automatically attach the current `sessionId`.
