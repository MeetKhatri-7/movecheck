# MobilityAI — Project State Summary

Last regenerated: **2026-05-20**.

This document is a snapshot of what's in the repo today: architecture, exercises supported, the rewrite work completed across the strength analyzers, the scoring system, and the data contract that ties Python → Node → React together.

---

## 1. What the project is

MobilityAI is a video-based form-grading tool for two assessment tracks:

- **Mobility** (10 exercises) — passive / bodyweight movements like knee-to-wall, thoracic extension, glute bridge, dead bug.
- **Strength** (5 exercises) — the big-five barbell / bodyweight lifts: Back Squat, Deadlift, Bench Press, Pull-Up, Overhead Press.

The athlete records videos, the app extracts MediaPipe pose, computes biomechanical metrics from the per-frame landmarks, and emits a composite score, per-metric breakdown, annotated frames, and coaching cues.

---

## 2. Architecture (3 processes)

```
React/Vite :5173                    Node/Express :3001              Python/Flask :5001
─────────────────                   ─────────────────               ─────────────────
InstructionPage                     server.js                       app.py
  · upload videos                     · in-memory job queue          · param conversion
  · enter form params                 · session JSON store           · analyzer_router
ProcessingPage                       · multer .any() upload          · MediaPipe + OpenCV
  · poll /api/jobs/:id                · POST /api/analyse          analyzers/strength/*.py
ResultPage                           · proxy → :5001               analyzers/mobility/*.py
  · render composite +               · param passthrough whitelist   utils/
    annotated frames                                                  · landmarks, angles, scoring
                                                                      · bar_tracker, rep_detection
                                                                      · muscle_inference, frame_annotator
```

- **Frontend** talks ONLY to Node. Node proxies to Python. Python is stateless.
- **Sessions** are dual-persisted: `backend/sessions/<id>.json` (atomic write, per-session mutex) is the source of truth; `localStorage` is a fast cache.
- **Job queue** lives in a `Map` and does NOT survive Node restarts. Temp uploads auto-clean 5 s after completion.

Start it all: `./start.sh`.

---

## 3. Exercises currently registered

### 3.1 Mobility (10)
Slug-keyed everywhere: `knee-to-wall-test`, `seated-hip-rotation-test`, `thoracic-extension`, `quadruped-rotation`, `shoulder-rotation-90-90`, `single-leg-glute-bridge`, `dead-bug`, `hollow-body-hold`, `plank-shoulder-tap`, `prone-y-t-w-raise`.

Analyzer files in [processor/analyzers/mobility/](processor/analyzers/mobility/). These use the older, simpler scoring scheme (GOOD/NEEDS IMPROVEMENT/RESTRICTED via `utils/scoring.py`). They have NOT been rewritten in this session.

### 3.2 Strength (5)
Slugs: `back-squat`, `deadlift`, `bench-press`, `pull-up`, `overhead-press`.

| Lift             | Analyzer lines | Rewrite status                                         |
|------------------|----------------|--------------------------------------------------------|
| Back Squat       | ~1,920         | (not rewritten this session — older doc-driven build)  |
| Deadlift         | ~1,830         | **Rewritten** to spec, 4-cam, geometric composite      |
| Bench Press      | ~2,270         | **Rewritten** to spec, 4-cam, PL/BB style, geometric   |
| Pull-Up          | ~1,920         | **Rewritten** to spec, 4-cam, 6 styles, dual-extreme   |
| Overhead Press   | ~2,200         | **Rewritten** to spec, 4-cam, push-press classifier    |

---

## 4. The 4-camera, multi-extreme scoring system

Four of the five strength lifts now share a common scoring scaffold layered on top of lift-specific physics. This was built up incrementally across the rewrite sessions and is now the de facto standard for new analyzers.

### 4.1 4-camera capture

Every rewritten lift requires four videos uploaded with field names:
- `sagittal` — primary view (90° to the athlete)
- `frontal` / `overhead` — secondary, lift-specific (overhead for bench, frontal for deadlift/pull-up/OHP)
- `posterior` / `headEnd` — third view (posterior for deadlift/pull-up/OHP; headEnd for bench)
- `oblique` (45°) — backup / occlusion fallback

The backend whitelist forwards every upload via `multer.any()` so any new field name "just works" without server changes. The InstructionPage now also collects **per-camera rep counts** (`targetRepsSagittal`, `targetRepsFrontal`, `targetRepsOverhead`, `targetRepsHeadEnd`, `targetRepsPosterior`, `targetRepsOblique`) so each video's rep detector trusts a user-supplied N.

### 4.2 5-tier sub-scoring (spec §7.1)

Every metric maps to a 0–100 sub-score via three primitives that live in each analyzer:

- `score_one_sided(x, very_good, good, yellow, bad, higher_is_better)` — four thresholds; linearly interpolates inside each tier (90–100 VG / 75–89 G / 60–74 Y / 40–59 B / 0–39 VB), and decays past Bad into Very Bad over one extra band-width.
- `score_two_sided(x, ideal, tolerances)` — symmetric tent around an ideal point with four half-widths.
- `score_ranged(x, vg_lo, vg_hi, g_lo, g_hi, y_lo, y_hi, b_lo, b_hi)` — flat Very Good band with asymmetric tails (used where the spec's Very Good band is a range, e.g. touch point 70–95% torso for PL bench).

### 4.3 Geometric composite (spec §7.3)

```
Composite = S_safety^w_s · S_technique^w_t · S_performance^w_p
```

Weak Safety drags the composite harder than the arithmetic mean would — chosen for screening intent. Verified: `(30, 80, 80)` → 49–66 depending on category weights, vs an arithmetic 63.

Per-lift category weights:

| Lift           | Safety | Technique | Performance |
|----------------|:------:|:---------:|:-----------:|
| Deadlift       | 0.50   | 0.35      | 0.15        |
| Bench Press    | 0.40   | 0.35      | 0.25        |
| Pull-Up        | 0.20   | 0.45      | 0.35        |
| Overhead Press | 0.45   | 0.35      | 0.20        |

### 4.4 Hard-fail safety overrides

Each analyzer carries a list of override predicates. When any rep trips one, the composite is capped at the override's cap (lowest cap wins). The override list is variant-aware (e.g. pull-up's `kipping_on_strict` is suppressed when style=kipping; OHP's `hip_thrust_kipping` is replaced by `unsafe_asymmetry` for seated DB).

| Lift           | Overrides |
|----------------|:---------:|
| Deadlift       | 9         |
| Bench Press    | 10        |
| Pull-Up        | 6–7 (style-dependent) |
| Overhead Press | 5 per variant |

### 4.5 DNC / reclassification handling

Failed reps are excluded from the set average, not just penalised:

- **Pull-Up**: hand-release / mid-rep fall → `dnc=True`, shown as separate `DNC: N` count
- **Overhead Press**: push-press detected (knee bend > 8° or hip-X > 4 cm before bar rises 5 cm) → `push_press=True`, shown as separate `PP: N` count. Bar/DB frame-exit at lockout → `dnc=True` with reason "bar/DB exited frame at lockout".

### 4.6 Set aggregation (spec §7.5)

Across valid reps: mean (headline) / worst / last-3, plus a deteriorating-rep flag for any rep > 15 pts below mean. Surfaced in the `composite_score.aggregation` payload.

### 4.7 Extreme positions per rep

Each rep is anchored on one or more extreme frames:

| Lift           | Extremes per rep                                  | Diagrams per camera |
|----------------|---------------------------------------------------|:-------------------:|
| Deadlift       | Lockout (top)                                     | 1                   |
| Bench Press    | Touch (bottom of eccentric)                       | 1                   |
| Pull-Up        | Dead-hang (bottom) + Chin-over-bar (top)          | 2                   |
| Overhead Press | Setup (rack) + Sticking Point + Lockout (top)     | 3                   |

For each lift, the **rich rep filter**: best + worst valid rep get all 4 cameras × all extremes; middle reps get sagittal-only × all extremes. DNC / push-press reps get no annotated frames.

---

## 5. Variant / style routing per lift

Each rewritten lift exposes form fields that route the analyzer to the matching threshold column. The frontend stores them on `exerciseInputs[exerciseId]`; the backend whitelists them in `passthroughFields`; the Python `app.py` `_str`/`_int`/`_float` calls convert them to analyzer kwargs.

| Lift           | Variants                                  | Extra form fields                                                |
|----------------|-------------------------------------------|------------------------------------------------------------------|
| Deadlift       | conventional / romanian                   | —                                                                |
| Bench Press    | flat / incline                            | `style` (powerlifting / bodybuilding), `paused` (paused / tng), `inclineDeg` |
| Pull-Up        | pronated / supinated / neutral / wide     | `style` (strict / kipping / butterfly / sternum / c2b / tactical) |
| Overhead Press | military / seated-db                      | `stance` (military_true / strict), `backrestDeg` (75 / 80 / 85 / 90) |

### 5.1 Special routing logic

- **Bench Press PL vs BB**: the `style` flag selects different threshold columns for grip width, arch, elbow flare, and touch point. Incline forces BB-style (spec §11.6).
- **Pull-Up style**: kipping and butterfly suppress the `kipping_detection` override and add `hollow_arch_transition` / `cycle_continuity` metrics. Sternum chin-up inverts the body-lean threshold (45–70° posterior is Very Good).
- **Pull-Up grip**: 4 grip categories shift elbow-at-top and elbow-flare thresholds (e.g. supinated VG ≤ 50°, wide VG ≤ 80°).
- **OHP backrest validation**: if backrest_deg < 70 on seated DB, the analyzer **refuses to score** and returns a banner telling the user to re-upload under Bench Press (Incline). 75°–90° routes to threshold columns and adjusts the torso-lean baseline.
- **OHP push-press gate**: a per-rep classifier check BEFORE scoring. Seated DB is exempted (no kinetic chain).
- **OHP anthropometry**: long-arm lifters (forearm > 0.16 × height) get S5 bar-horizontal thresholds relaxed by 20% (spec §11.1).

---

## 6. Frontend

### 6.1 Pages
[Dashboard.tsx](frontend/src/pages/Dashboard.tsx), [SessionsPage.tsx](frontend/src/pages/SessionsPage.tsx), [LandingPage.tsx](frontend/src/pages/LandingPage.tsx), [ExerciseGuide.tsx](frontend/src/pages/ExerciseGuide.tsx), [InstructionPage.tsx](frontend/src/pages/InstructionPage.tsx) (~620 lines), [ProcessingPage.tsx](frontend/src/pages/ProcessingPage.tsx), [ResultPage.tsx](frontend/src/pages/ResultPage.tsx) (~940 lines).

### 6.2 AppContext state
`uploads: Record<string, File>` keyed by `<exerciseId>-<uploadId>` — populated by InstructionPage, consumed by ProcessingPage. `reports.{mobility, strength}` persists to server + localStorage. `apiResult` carries the live result; ResultPage falls back to `reports[type][slug]` if null. `profile` holds calibration constants (`tibiaLengthCm`, `athleteHeightCm`, `plateSizeKg`).

### 6.3 The composite-breakdown UI
A new block [`CompositeBreakdown`](frontend/src/pages/ResultPage.tsx#L302-L455) renders when `result.composite_score` is present (i.e. only the rewritten lifts). It shows:

- Grade letter card (A–E) + composite headline + variant label
- Override banner (red) only when triggered
- Category bars (Safety / Technique / Performance) with dynamic weights (40/35/25 for bench, 50/35/15 for deadlift, 20/45/35 for pull-up, 45/35/20 for OHP)
- Aggregation pills: Mean / Worst / Last 3 / deteriorating-rep count
- Two lowest sub-scores with corrective cues (spec §11.4)

The existing single-score hero and metric grid remain untouched, so older analyzers (mobility, back squat) still render correctly without `composite_score`.

### 6.4 Result types
Added in [types.ts:96-138](frontend/src/data/types.ts#L96-L138):

```ts
CompositeScore {
  composite: number;
  grade: 'A'|'B'|'C'|'D'|'E';
  label: 'Very Good'|'Good'|'Yellow Flag'|'Bad'|'Very Bad';
  composite_method: 'geometric' | 'arithmetic';
  categories: CategoryScore[];        // {name, weight, score}
  overrides: SafetyOverride[];        // {condition, cap, triggered, ...}
  active_cap?: number | null;
  lowest_sub_scores: CorrectiveCue[]; // {metric, sub_score, cue}
  aggregation: SetAggregation;        // {mean, worst, last_three, deteriorating_rep_nums}
  variant?: string;
}
```

Older analyzers that emit only `score`/`status`/`metrics` continue rendering unchanged because `composite_score` is optional.

---

## 7. Python utilities (shared across analyzers)

All in [processor/utils/](processor/utils/):

| File              | Purpose                                                                 |
|-------------------|-------------------------------------------------------------------------|
| `landmarks.py`    | MediaPipe extraction; `LM` index dict; smoothing (1-Euro / SG)          |
| `angles.py`       | 3-point joint angles, multipoint spine curvature, distance helpers      |
| `scoring.py`      | Legacy `build_metric`/`build_result`/`classify` (older 3-tier scheme)   |
| `rep_detection.py`| Peak / minima detection on scalar signals with plateau holds            |
| `bar_tracker.py`  | KCF + HoughCircles plate centroid tracking; px-per-cm calibration       |
| `frame_annotator.py` | All the `draw_*` overlay primitives (~900 lines)                     |
| `muscle_inference.py` | Kinematic-to-muscle-activation maps per lift                        |
| `signal_filters.py` | 1-Euro filter, Savitzky-Golay                                         |
| `camera_view.py`  | Heuristic camera-view classifier (front / side / etc)                   |
| `dtw_templates.py`| Older rep-template library (dropped in the new rewrites)                |

Note: the rewritten analyzers (deadlift, bench, pull-up, OHP) carry their own 5-tier scoring helpers inline rather than using `scoring.classify` — the older 3-tier helpers remain for back-compat with mobility + back-squat.

---

## 8. Per-lift rewrite highlights

### 8.1 Deadlift — [processor/analyzers/strength/deadlift.py](processor/analyzers/strength/deadlift.py)
- 4-view processing (sagittal primary, frontal, posterior, oblique fallback)
- Conventional + Romanian phase machines (RDL is eccentric-first)
- All 32 spec metrics, 5-tier scoring
- Bar tracker = plate centroid + wrist-centre weighted blend (spec §12.5.3)
- 9 hard-fail overrides; geometric composite 0.50 / 0.35 / 0.15

### 8.2 Bench Press — [processor/analyzers/strength/bench_press.py](processor/analyzers/strength/bench_press.py)
- 4-view processing (sagittal primary + overhead + headEnd + oblique)
- Touch frame (extreme position) via bench-relative wrist-Y minimum + chest-proximity gate
- Bench angle calibration via form input with auto-detect fallback; rotates coordinates so "up off bench" is always +Y
- Style-aware thresholds: separate columns for flat-PL, flat-BB, incline-BB
- Paused vs touch-and-go handling
- 10 hard-fail overrides; geometric composite 0.40 / 0.35 / 0.25

### 8.3 Pull-Up — [processor/analyzers/strength/pull_up.py](processor/analyzers/strength/pull_up.py)
- 4-view processing; bar is fixed → wrist landmarks are the (near-)stationary reference
- **Dual-extreme detection**: Schmitt-trigger state machine picks BOTH dead-hang frame AND chin-over-bar frame per rep
- 4 grip categories + 6 styles, each routing to different rubrics
- Strict-style 7 overrides incl. `kipping_on_strict`; kipping/butterfly suppress the kipping cap and add `hollow_arch_transition` / `cycle_continuity` / `symmetric_cycle` metrics
- Sternum chin-up INVERTS the body-lean threshold (45–70° posterior is Very Good)
- DNC handling for hand-release / fall (excluded from set average)
- 33 spec metrics; geometric composite 0.20 / 0.45 / 0.35

### 8.4 Overhead Press — [processor/analyzers/strength/overhead_press.py](processor/analyzers/strength/overhead_press.py)
- **Triple-extreme detection**: Setup (bar at clavicle) + Sticking Point (velocity minimum mid-press) + Lockout (top, arms by ears)
- **Push-press hard classifier**: per-rep check BEFORE scoring; if knee bend > 8° or hip-X > 4 cm before bar rises 5 cm, the rep is tagged `push_press=True` and excluded from set aggregation
- **Backrest validation** (seated DB): refuses to score if backrest < 70°; routes 75°/80°/85°/90° to threshold columns and adjusts torso-lean baseline
- **Anthropometry adjustment** (long-arm lifters): S5 bar-horizontal thresholds relaxed 20%
- Variant-specific weight tables (Military vs Seated DB) — both sum to 100 ✓
- 38 spec metrics; geometric composite 0.45 / 0.35 / 0.20

---

## 9. The data contract (Python → Node → Frontend)

Every rewritten analyzer returns:

```python
{
  # Standard fields (compatible with older mobility / back-squat)
  'status': 'GOOD' | 'NEEDS IMPROVEMENT' | 'RESTRICTED',
  'score': int,                         # composite headline 0..100
  'summary': str,
  'stats': dict,                        # banner pills (validReps, confidence, ...)
  'metrics': list[Metric],              # flat list for legacy grid
  'bilateral': list,                    # mostly unused in new rewrites
  'coaching': list[str],                # override banners + lowest-sub-score cues

  # Optional extras (rewritten lifts only)
  'annotated_frames': list[AnnotatedFrame],   # base64-PNG diagrams
  'per_rep': list[PerRepMetric],
  'muscle_activation': MuscleActivationData,
  'meta': ResultMeta,
  'composite_score': CompositeScore,    # the spec UI payload
}
```

The frontend `CompositeBreakdown` block keys on `composite_score`; absence means "older analyzer", render the legacy hero only.

---

## 10. Specifications / reference docs in the repo

| File                                   | Purpose                                              |
|----------------------------------------|------------------------------------------------------|
| `AI_Metrics_Specification-Mobility.md` | Mobility threshold spec (10 exercises)               |
| `AI_Metrics_Specification-Strength.md` | Strength threshold spec (5 exercises, older)         |
| `compass_artifact_wf-*.md`             | Deadlift biomechanical spec (drove deadlift rewrite) |
| `bench-press-rewrite.md`               | Bench press biomechanical spec                        |
| `pullups.md`                           | Pull-up biomechanical spec                            |
| `Overhead-press-rewrite.md`            | OHP biomechanical spec                                |
| `barbell_squat_assessment_system.md`   | Back squat biomechanical spec (not yet rewritten)     |
| `CLAUDE.md`                            | Build / start commands, architecture notes           |
| `API_GUIDE.md`                         | (Older) API contract                                  |

---

## 11. What's NOT done yet

- **Back Squat** — still on the older doc-driven build. Has its own dual-cam (side + front) pattern from before the 4-cam standard.
- **Mobility analyzers** — all 10 still use the older 3-tier (`GOOD`/`NEEDS IMPROVEMENT`/`RESTRICTED`) scoring. They don't emit `composite_score`, so the new CompositeBreakdown UI doesn't render for them.
- **DTW rep-template library** — present in `utils/dtw_templates.py` but explicitly dropped in the new rewrites (replaced by the spec's CV%-based consistency metric).
- **Code-splitting** — Vite build emits a ~590 kB chunk; Vite warns about >500 kB.
- **Automated tests** — none in the repo (note in CLAUDE.md).
- **Job-queue persistence** — Node's `Map` doesn't survive restarts.

---

## 12. Quick reference — how to add a new strength analyzer

1. Drop a new file in `processor/analyzers/strength/<slug>.py` with an `analyse(files, **kwargs)` entry point.
2. Register it in `processor/analyzer_router.py` under `ANALYZERS['strength'][slug]`.
3. Add the slug to `backend/server.js` `STRENGTH_SLUGS`.
4. Add the exercise definition to `frontend/src/assessments/strength/exercises.ts` with the 4-camera uploads (`sagittal` / `frontal` / `posterior` / `oblique` — or `overhead` / `headEnd` per lift convention).
5. If new form fields are needed: add them to `InstructionPage.tsx` form definition, the `passthroughFields` whitelist in `server.js`, and the `_str/_int/_float` conversions in `processor/app.py`.
6. Implement the 5-tier scoring helpers + category weights + geometric composite + override list (the 4 rewritten analyzers are the templates).
7. Emit `composite_score` in the result dict so the new UI block renders automatically.
