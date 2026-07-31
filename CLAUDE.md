# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Starting the stack

```bash
./start.sh          # starts all three servers concurrently
```

Individual servers:

```bash
# Python processor (port 5001)
cd processor && source venv/bin/activate && python app.py

# Node.js backend (port 3001)
cd backend && node server.js

# React frontend (port 5173)
cd frontend && npm run dev
```

Frontend commands:

```bash
cd frontend
npm run build       # tsc -b && vite build
npm run lint        # eslint .
npm run preview     # preview the production build
```

There are no automated tests in this repo. The Python environment is a local venv (`processor/venv/`) with no `requirements.txt` — dependencies are pre-installed in the venv.

---

## Architecture

Three processes, each with a strict role:

```
React/Vite :5173
    │  POST /api/assessments/:type/:slug/analyse  (multipart, returns jobId)
    │  GET  /api/jobs/:jobId                      (polling)
    ▼
Node/Express :3001   (backend/server.js)
    │  - Owns the job queue (in-memory Map — lost on restart)
    │  - Owns session persistence (backend/sessions/*.json)
    │  - Forwards video files to Python via multipart
    │  POST /process
    ▼
Python/Flask :5001   (processor/app.py)
    - MediaPipe + OpenCV video analysis
    - Returns a result dict — never touches sessions
```

The frontend talks only to Node. Node proxies to Python. Python is stateless (no session awareness).

---

## Assessment types and exercise slugs

Two assessment tracks are registered in `backend/server.js` and `processor/analyzer_router.py`:

**Mobility** (10 exercises — integer IDs 1–10 for legacy compat):
`knee-to-wall-test`, `seated-hip-rotation-test`, `thoracic-extension`, `quadruped-rotation`, `shoulder-rotation-90-90`, `single-leg-glute-bridge`, `dead-bug`, `hollow-body-hold`, `plank-shoulder-tap`, `prone-y-t-w-raise`

**Strength** (5 exercises — note their frontend `id` numbers overlap with mobility's 1–10, which is why upload-slot keys are namespaced by `type::slug::uploadId` in `frontend/src/data/uploadKeys.ts`, never by numeric id):
`back-squat`, `deadlift`, `bench-press`, `pull-up`, `overhead-press`

The slug is the stable key everywhere — in URLs (`/api/assessments/:type/:slug/analyse`), session JSON, localStorage, and the Python router.

---

## Adding a new analyzer

1. Create `processor/analyzers/<type>/<slug_underscored>.py` with an `analyse(files, **kwargs)` function.
2. Register it in `processor/analyzer_router.py` under `ANALYZERS[type][slug]`.
3. Add the slug to `backend/server.js` (`MOBILITY_SLUG_TO_ID` or `STRENGTH_SLUGS`).
4. Add the exercise definition to `frontend/src/assessments/<type>/exercises.ts`.

The router uses `inspect.signature` to pass only the kwargs each analyzer's `analyse()` actually declares — there is no need to add `**kwargs` to analyzers, and unknown params are silently dropped.

---

## Python CV pipeline patterns

### Result shape

Every analyzer must return a dict matching the `ExerciseResult` TypeScript interface (`frontend/src/data/types.ts`):

```python
{
  'status': 'GOOD' | 'NEEDS IMPROVEMENT' | 'RESTRICTED',
  'score': int,           # 0-100
  'summary': str,
  'stats': { 'validReps': str, 'confidence': str, 'sides': str, 'cameraView': str },
  'metrics': [ build_metric(...) ],
  'bilateral': [ build_bilateral(...) ],
  'coaching': [ str ],
  'annotated_frames': [ ... ],   # optional
  'per_rep': [ ... ],            # optional
}
```

Use `build_result()`, `build_metric()`, `build_bilateral()` from `utils/scoring.py`. Use `classify()` for threshold-based status (higher_is_better flag matters). Use `classify_range()` for ROM targets with a minimum acceptable range.

### Rep detection

`utils/rep_detection.py` operates on a scalar time-series signal (e.g. angle at each frame):
- `detect_reps(signal, expected_reps, fps)` — finds peaks including plateau-holds; returns `{peak_frame, start_frame, end_frame, peak_value}` per rep.
- `detect_reps_minima(...)` — same but for signals where lower = peak movement.
- `detect_holds(signal, threshold, fps)` — for timed-hold exercises.
- `detect_taps(wrist_y_signal, fps)` — legacy helper, currently unused: the plank shoulder tap analyzer detects taps with `detect_reps` over a wrist-elevation signal instead.

Always scan **all frames within a rep's `[start_frame, end_frame]` range** for the true max/min value — do not rely solely on `peak_frame`, which is the smoothed-signal peak.

### Landmark access

`utils/landmarks.py` exports `LM` (dict of landmark name → MediaPipe index), `extract_all_landmarks(video_path)` (returns `{frames, fps, width, height}`), `get_landmark_px(landmarks, idx, w, h)` (returns `(x, y)` in pixels or `None`).

### Annotated frames

Use helpers from `utils/frame_annotator.py`: `extract_frame_at`, `draw_skeleton`, `draw_angle_arc`, `draw_distance_line`, `draw_reference_line`, `draw_callout`, `draw_metric_overlay`, `draw_legend`, `frame_to_base64`. Return annotated frames as `{'label', 'image_base64', 'rep_num', 'side', 'is_best', 'metrics_shown'}` dicts.

---

## Session and state persistence

Sessions are dual-persisted:
- **Server-side**: `backend/sessions/<sessionId>.json` — written atomically (temp-file rename) with a per-session mutex to prevent concurrent write races. This is the source of truth on load.
- **Client-side**: `localStorage` key `mobilityai_reports_v2` — used as a fast local cache. On app boot, `AppContext` fetches the session from the server and merges it into local state.

A legacy migration path exists for the old integer-keyed `mobilityai_reports_v1` format — it runs once and then removes the old key.

The job queue in `backend/server.js` is a plain `Map` — it does not survive server restarts. Jobs auto-clean their temp upload directory 5 seconds after completion.

---

## Frontend state (AppContext)

`frontend/src/context/AppContext.tsx` is the single provider. Key state:
- `uploads` — `Record<string, File>` populated by `InstructionPage`, consumed by `ProcessingPage`.
- `reports` — `{ mobility: Record<slug, result>, strength: Record<slug, result> }`, persisted to both server and localStorage.
- `apiResult` — the live result from the most recent job; `ResultPage` falls back to `reports[type][slug]` if null. Must be cleared via `setApiResult(null)` on navigation.
- `profile` — `{ tibiaLengthCm?, athleteHeightCm?, plateSizeKg? }` — user calibration constants passed as analyzer params.
- `exerciseInputs` — per-exercise form values (variant, load, reps, etc.), persisted to localStorage.

---

## Analyzer params passthrough

Calibration and config values travel from the frontend profile/form → Node API → Python:

| Frontend key | Form field | Python param |
|---|---|---|
| `tibiaLengthCm` | `tibiaLengthCm` | `tibia_length_cm` |
| `athleteHeightCm` | `athleteHeightCm` | `athlete_height_cm` |
| `plateSizeKg` | `plateSizeKg` | `plate_size_kg` |

Node whitelists these in `passthroughFields`; Python converts them in `app.py`. Any analyzer that doesn't declare the param in its signature simply won't receive it.

---

## Spec documents

Measurement thresholds, target ranges, and camera angles for every exercise are defined in:
- `AI_Metrics_Specification-Mobility.md` — all 10 mobility exercises
- `AI_Metrics_Specification-Strength.md` — all 5 strength exercises

When editing analyzer thresholds or scoring, these are the authoritative source.
