# AGENTS.md

Guidance for AI coding agents (Cursor, Aider, Copilot, Codex, etc.) working in this repository. Claude Code reads `CLAUDE.md`; this file carries the same operational facts in the vendor-neutral AGENTS.md convention so any agent gets the same grounding.

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

There are no automated tests in this repo. The Python environment is a local venv (`processor/venv/`) with no `requirements.txt` beyond `processor/requirements.txt` — dependencies are pre-installed in the venv. There is also a stray `.venv/` at the repo root; the active one used by `start.sh` is `processor/venv/`.

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

**Strength** (5 exercises, no legacy IDs):
`back-squat`, `deadlift`, `bench-press`, `pull-up`, `overhead-press`

The slug is the stable key everywhere — in URLs (`/api/assessments/:type/:slug/analyse`), session JSON, localStorage, and the Python router. Frontend definitions live in `frontend/src/assessments/mobility/exercises.ts` and `frontend/src/assessments/strength/exercises.ts`.

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
- `detect_taps(wrist_y_signal, fps)` — for plank shoulder tap.

Always scan **all frames within a rep's `[start_frame, end_frame]` range** for the true max/min value — do not rely solely on `peak_frame`, which is the smoothed-signal peak.

### Landmark access

`utils/landmarks.py` exports `LM` (dict of landmark name → MediaPipe index), `extract_all_landmarks(video_path)` (returns `{frames, fps, width, height}`), `get_landmark_px(landmarks, idx, w, h)` (returns `(x, y)` in pixels or `None`).

### Annotated frames

Use helpers from `utils/frame_annotator.py`: `extract_frame_at`, `draw_skeleton`, `draw_angle_arc`, `draw_distance_line`, `draw_reference_line`, `draw_callout`, `draw_metric_overlay`, `draw_legend`, `frame_to_base64`. Return annotated frames as `{'label', 'image_base64', 'rep_num', 'side', 'is_best', 'metrics_shown'}` dicts. These base64 JPEGs are currently the *only* imagery the frontend renders that comes from real user data (see Frontend design system below).

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

## Frontend design system

The frontend runs a bespoke design system called **"Editorial Bone + Clay"**, defined in two places that must stay in sync:
- `frontend/src/theme/tokens.ts` — the JS/TS source of truth (`C` colors, `F` fonts, `R` radii, `S` spacing, `Z` z-index, `statusColor()`/`overallStatusColor()` helpers).
- `frontend/src/index.css` — the same palette mirrored as CSS custom properties for Tailwind v4 (`@theme inline` block) plus global type/animation classes (`.display`, `.label-caps`, `.animate-fade-up*`).

Palette: warm bone/cream surfaces (`#F4EFE6` / `#FAF7F0`), ink text (`#2A2520`), terracotta clay accent (`#B9573A`), sage/amber/rust for good/warn/bad status. Typography: DM Serif Display for headlines, Inter for body. Most page components use inline `style={}` objects built from `T` (`const { C, F, R, S } = T`) rather than Tailwind classes — Tailwind is present (shadcn primitives live under `frontend/@/components/ui/`) but the app's own pages don't lean on it. New page-level UI should follow the inline-style-from-tokens pattern already established in `src/pages/*.tsx`, not introduce a third styling approach.

**Known tech debt an agent should be aware of before touching UI:**
- `frontend/src/components/shared/{AnalysisPhotoGallery,MuscleMap,RadarChart}.tsx` are dead code from an earlier dark-neon design iteration (`'Space Grotesk'` font, `#00e5b0`/`#4488ff`/`#ff4466` hex colors) and are not imported anywhere — safe to delete, don't extend them.
- `frontend/src/components/shared/PerRepAccordion.tsx` is **live** (used in `ResultPage.tsx`) but still hard-coded to that same dark-neon palette instead of `theme/tokens.ts` — it visibly clashes with the bone/clay page around it. Needs restyling, not replication.
- The `color` field on exercise entries in both `frontend/src/assessments/*/exercises.ts` files is a leftover neon hex from the same old iteration and is not consumed by any current component.
- No real photography exists yet: `frontend/public/images/exercises/` is empty and `hero-athlete.jpg` doesn't exist, so `ImageSlot` (the graceful-degradation image component) always renders its placeholder state on the landing page and all 15 exercise-guide cards. `frontend/public/images/README.md` documents the exact filenames/specs expected — drop matching files in and placeholders resolve automatically, no code changes needed.
- `frontend/src/assets/hero.png` is an orphaned, unreferenced asset.
- Score-gauge SVG math is duplicated between `ResultPage.tsx`'s `ScoreBadge` and `Dashboard.tsx`'s `OverallGauge`; report-summary card markup is duplicated across `Dashboard.tsx`, `SessionsPage.tsx`, and `ResultPage.tsx`. Prefer extracting a shared component over adding a fourth copy.
- `framer-motion` is installed and used meaningfully only in `MuscleBody.tsx`; everywhere else motion is CSS keyframes (`animate-fade-up` etc.) or manual `useState`-driven inline transitions. Match whichever pattern the surrounding file already uses.

## Spec documents

Measurement thresholds, target ranges, and camera angles for every exercise are defined in:
- `AI_Metrics_Specification-Mobility.md` — all 10 mobility exercises
- `AI_Metrics_Specification-Strength.md` — all 5 strength exercises

When editing analyzer thresholds or scoring, these are the authoritative source.