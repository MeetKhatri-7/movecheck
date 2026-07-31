# Architecture &amp; Analysis Pipeline — Deep Dive

This document explains **how the system actually works** under the hood: the full
request lifecycle, the computer-vision/ML techniques each analyzer uses, what every
important library is doing and why it was chosen, and how each of the 15 exercises
turns a raw video into a scored report. Read [README.md](README.md) first for the
high-level map; this document goes underneath it.

---

## Table of contents

1. [End-to-end request lifecycle](#1-end-to-end-request-lifecycle)
2. [The pose-estimation pipeline (MediaPipe)](#2-the-pose-estimation-pipeline-mediapipe)
3. [Signal processing layer](#3-signal-processing-layer)
4. [Calibration — converting pixels to real-world units](#4-calibration--converting-pixels-to-real-world-units)
5. [Rep detection](#5-rep-detection)
6. [Camera-view classification](#6-camera-view-classification)
7. [Barbell tracking](#7-barbell-tracking)
8. [DTW template matching](#8-dtw-template-matching)
9. [The scoring system](#9-the-scoring-system)
10. [Muscle-activation inference](#10-muscle-activation-inference)
11. [Frame annotation / visualization](#11-frame-annotation--visualization)
12. [How each mobility exercise works](#12-how-each-mobility-exercise-works)
13. [How each strength lift works](#13-how-each-strength-lift-works)
14. [Node backend internals](#14-node-backend-internals)
15. [Frontend state &amp; rendering](#15-frontend-state--rendering)
16. [Library reference table](#16-library-reference-table)

---

## 1. End-to-end request lifecycle

```
 User (browser)                Node/Express :3001              Python/Flask :5001
 ──────────────                ──────────────────              ──────────────────
 InstructionPage
   collects File objects
   into AppContext.uploads
        │
        │ POST /api/assessments/:type/:slug/analyse
        │  (multipart: video files + calibration params
        │   + optional sessionId)
        ▼
                                jobId = uuid()
                                jobs.set(jobId, {status:'processing'})
                                respond 200 {jobId}   ◀── returned immediately;
                                                            processing continues async
                                        │
                                        │ builds a FormData with the same files
                                        │ + whitelisted passthrough params
                                        │ POST http://localhost:5001/process
                                        ▼
                                                                request.files saved to
                                                                a tempfile.mkdtemp() dir,
                                                                keyed by UPLOAD FIELD NAME
                                                                (not original filename —
                                                                 avoids collisions)
                                                                        │
                                                                        │ analyzer_router.route_analysis(
                                                                        │   assessment_type, slug, files, params)
                                                                        ▼
                                                                importlib reloads any
                                                                changed utils/*.py or
                                                                analyzers/*.py source
                                                                (hot-reload for a
                                                                 long-running server),
                                                                then calls the matching
                                                                analyse(files, **kwargs)
                                                                        │
                                                                        ▼
                                                                [see §2–§13 below]
                                                                        │
                                                                        ▼
                                                                returns a result dict
                                                                        │
                                                                shutil.rmtree(temp_dir)
                                                                _sanitize_for_json()
                                                                strips numpy types
                                                                        ▼
                                jobs.set(jobId, {status:'complete',
                                                  result})
                                if sessionId:
                                  sessionStore.appendResult()
                                  (atomic write to
                                   backend/sessions/<id>.json)
        │
        │ ProcessingPage polls
        │ GET /api/jobs/:jobId  every ~N ms
        ▼
 ResultPage renders result.metrics,
   .bilateral, .coaching, .annotated_frames
```

Key properties of this design:

- **The upload is fire-and-forget from the client's perspective.** The `POST .../analyse`
  handler (`backend/server.js`) assigns a `jobId`, responds `200 {jobId}` synchronously,
  and does the actual multipart forward to Python inside an unawaited async IIFE. This
  is why the frontend has to poll `GET /api/jobs/:jobId` rather than get the result on
  the original request — a full pose-estimation pass over a multi-minute video would
  otherwise hold the HTTP connection open past most proxy/browser timeouts.
- **Python never sees a session and never persists anything.** It is a pure function:
  `files in → result dict out`. All state (job status, session history) lives in Node.
  This keeps the CV service horizontally stateless and restart-safe.
- **Hot module reload in `analyzer_router.py`.** Every request re-checks the mtimes of
  every already-imported `utils.*` / `analyzers.*` module and calls `importlib.reload()`
  on anything that changed on disk, *before* reloading the target analyzer module (so its
  `from utils.x import y` re-binds against the fresh code). This means analyzer/utils
  edits take effect on the next request without restarting the Flask process — useful
  during iterative threshold tuning, but it also means the server is doing a directory
  stat sweep on every single request.
- **Params are whitelisted twice.** `frontend/src/services/api.ts`'s `AnalyseParams`
  interface, Node's `passthroughFields` array, and Python's `_float/_int/_str` calls in
  `app.py` all name the same fixed set of calibration/config fields (`tibiaLengthCm`,
  `plateSizeKg`, `targetRepsSagittal`, etc.). Nothing free-form crosses the Node→Python
  boundary. On the Python side, `inspect.signature(fn)` further filters `params` down to
  only the kwargs the specific analyzer's `analyse()` actually declares — so a new
  analyzer doesn't need `**kwargs`, and old analyzers silently ignore params added later
  for newer ones.

---

## 2. The pose-estimation pipeline (MediaPipe)

Every analyzer's first step is `utils.landmarks.extract_all_landmarks(video_path)`. This
is the single most important shared primitive in the codebase — all 15 analyzers build
on top of its output.

**What it does, frame by frame:**

1. Opens the video with **OpenCV** (`cv2.VideoCapture`) and reads frames sequentially.
2. If the frame's long side exceeds `MAX_INFERENCE_DIM` (1920 px), downsamples it with
   `cv2.INTER_AREA` before running pose inference — MediaPipe's model consumes a small
   fixed-size input internally and returns *normalized* `[0,1]` coordinates, so feeding
   it native 4K frames only costs CPU (`cvtColor` + tensor prep on 8-megapixel images)
   without any accuracy benefit. All downstream pixel math (`get_landmark_px`, angle
   calculations) multiplies normalized coords back out against the **original** frame
   dimensions, so this optimization is coordinate-system-transparent.
3. Converts BGR → RGB (OpenCV's native channel order vs. what MediaPipe expects).
4. Runs **MediaPipe Pose** (`model_complexity=2`, the "heavy" model —
   `pose_landmarker_heavy.task`, auto-downloaded on first run if missing) to get 33 body
   landmarks per frame, each as `(x, y, z, visibility)` — x/y normalized to `[0,1]`, z a
   relative depth estimate, visibility a confidence score in `[0,1]`.
5. The module supports **both** of MediaPipe's pose APIs at import time: the legacy
   `mp.solutions.pose` (pre-0.10.14) and the newer Tasks-based `PoseLandmarker` API
   (0.10.14+), auto-detecting which is installed. This is why `landmarks.py` has two
   near-duplicate extraction loops guarded by `MP_LEGACY`.
6. **Smooths every landmark's x/y/z trajectory** with a per-coordinate **1-Euro filter**
   (see §3) before returning — this is the default (`smooth=True`); the pre-smoothing
   trajectory is preserved separately as `raw_frames` for debugging.

**Output:** `{frames, raw_frames, fps, total_frames, width, height}` where `frames` is a
list of `{frame_idx, time_sec, landmarks}` — `landmarks` is the 33-tuple list or `None`
if no person was detected in that frame.

**Landmark indices** (`LM` dict in `landmarks.py`) follow MediaPipe's canonical 33-point
skeleton: nose, ears, mouth corners, shoulders, elbows, wrists, fingers, hips, knees,
ankles, heels, and foot indices (big-toe knuckle). Analyzers reference these by name
(`LM['LEFT_KNEE']`) rather than by raw index.

**Accessors built on top of the raw tuples** (all in `landmarks.py`):

| Function | Returns | Visibility gate |
|---|---|---|
| `get_landmark_px(lm, idx, w, h)` | `(x_px, y_px)` or `None` | `visibility < 0.3` → `None` (legacy default) |
| `get_landmark_norm(lm, idx)` | `(x, y)` normalized | same 0.3 gate |
| `get_lm(lm, idx, w, h)` | `(x_px, y_px, visibility)` | `visibility < 0.5` (stricter — used by newer strength analyzers that need per-metric confidence) |
| `midpoint_px` / `midpoint_norm` | midpoint of two landmarks | either missing → `None` |
| `confidence_score(frames)` | 0–100 | fraction of frames with *any* detected person |
| `landmark_quality(lm, idxs)` / `window_landmark_quality(...)` | mean visibility over a landmark set / frame window | feeds per-metric `confidence` (§9) |

Every geometry helper downstream (`None`-propagates): if a required landmark wasn't
visible, the function returns `None` rather than raising, and callers treat `None` as
"skip this frame/rep" rather than crashing the whole analysis on one bad frame.

---

## 3. Signal processing layer

`processor/utils/signal_filters.py` centralizes three different smoothing techniques,
each suited to a different kind of noise:

### 3a. One-Euro filter — landmark trajectories

Applied to **every x/y/z coordinate of every landmark, every frame**, immediately after
MediaPipe inference (inside `extract_all_landmarks`). It's a low-pass filter whose cutoff
frequency adapts to velocity (Casiez et al. 2012): slow-moving landmarks get heavily
smoothed (kills MediaPipe's frame-to-frame jitter), but fast-moving landmarks get less
smoothing (avoids lag during, e.g., the top of a fast rep). One `OneEuroFilter` instance
is created per `(landmark_index, axis)` pair (33 landmarks × 3 axes) so each coordinate's
filter state (previous value, previous derivative) is independent.

Parameters `min_cutoff=1.0, beta=0.007` are the library defaults; analyzers generally
don't override them at this layer.

### 3b. Savitzky–Golay smoothing — derived 1-D signals

Once an analyzer has computed a scalar signal from the landmarks (e.g. knee angle at
every frame, bar-Y position, trunk lean), `savgol_series()` applies a **polynomial
least-squares smoother** (`scipy.signal.savgol_filter`) over a small time window
(`window_sec=0.25` default → ~7–8 frames at 30fps). Unlike a moving average, Savitzky-
Golay preserves peak shape and higher-order derivatives better, which matters when the
next step is finding local maxima/minima (rep detection) or differentiating for
velocity. `None` gaps (landmark dropouts) are linearly interpolated before filtering and
restored as `None` afterward so downstream missing-data handling is unaffected. Falls
back to a plain moving average if `scipy` isn't importable or the window is too short.

### 3c. Kalman 1-D — bar position &amp; velocity

`kalman_1d()` / `kalman_velocity()` run a constant-velocity **Kalman filter**
(`filterpy.kalman.KalmanFilter`, state = `[position, velocity]`) over the bar-tracker's
raw centroid series. This is specifically used where a *clean derivative* matters — bar
velocity for rep-phase segmentation (`detect_reps_velocity`) and mean concentric
velocity reporting — because a Kalman filter's velocity state is a proper model-based
estimate rather than a noisy frame-difference. Falls back to Savitzky-Golay + central
difference if `filterpy` isn't available.

**Why three different filters instead of one?** Landmark jitter (sub-pixel noise, high
frequency, every joint) needs adaptive real-time smoothing → 1-Euro. A derived angle
signal that will be peak-detected needs shape-preserving smoothing → Savitzky-Golay. A
position signal that will be *differentiated* for velocity needs a filter with an
explicit velocity state → Kalman. Using the wrong one in each context was a documented
source of past bugs (comments throughout the codebase reference specific failure modes
each choice fixed).

---

## 4. Calibration — converting pixels to real-world units

MediaPipe gives you pixel and normalized coordinates, not centimeters. Every analyzer
that reports a physical distance (heel lift in cm, knee travel in cm, bar path drift in
cm) needs a **pixel-per-centimeter** conversion, and the codebase uses a different known
"ruler" per context — always a body segment or object of known/assumed real-world size,
never a physical marker the user has to place in frame:

| Context | Known constant | Computation |
|---|---|---|
| Knee-to-wall (mobility) | User's tibia length (cm), optional profile field | `px_per_cm = median(knee↔ankle px distance across the first ~15% of frames) / tibia_length_cm` (`knee_to_wall._calibrate_px_per_cm`) |
| Any mobility test without a better constant | Assumed athlete height (170 cm default) | `estimate_px_per_cm(height_px) = (height_px * 0.75) / assumed_body_height_cm` — assumes the body fills ~75% of frame height (`angles.estimate_px_per_cm`) |
| Barbell lifts (squat/deadlift/bench/OHP) | Loaded plate's real diameter | `utils/bar_tracker.py`'s `PLATE_DIAM_MM` table (25 kg→450 mm … 1.25 kg→160 mm); `calibrate_px_per_cm()` runs `cv2.HoughCircles` on frame 0 to find the plate, then `px_per_cm = measured_radius_px * 2 / plate_diameter_cm`. Falls back to a 20 kg-plate assumption if the user didn't specify `plateSizeKg`. |
| Pull-up | User's height (cm), optional profile field | `athlete_height_cm` fallback when no plate is visible on the pull-up bar setup |

**Body-segment normalization** (`angles.body_segment_lengths`) is a second, complementary
technique: it computes median pixel lengths of tibia/femur/torso/upper-arm/forearm across
a sampled window, used both to normalize movement thresholds to the individual's body
proportions and as an input to the camera-view classifier (§6).

Every calibration function returns a `calibration_mode` tag (`'tibia-calibrated'` vs
`'fallback-estimate'`) that gets surfaced back to the user as a coaching note — "provide
your tibia length in profile for ±0.3 cm accurate measurements" — so users understand
when they're getting the more accurate, personalized calibration vs. the generic
fallback.

---

## 5. Rep detection

`processor/utils/rep_detection.py` implements repetition/hold segmentation purely from
1-D signals (an angle, a position, an elevation) — no separate ML model, just classical
signal processing:

- **`detect_reps(signal, expected_reps, fps)`** — the core algorithm. Smooths the signal
  with a moving average, then walks it looking for rising edges that plateau and then
  fall (this plateau-aware logic is what lets it detect both sharp peaks *and* held
  positions, e.g. a 3-second isometric hold at the top of a rep, as a single rep rather
  than many micro-reps from signal noise at the plateau). Detected peaks closer together
  than `min_hold_sec` are merged (keeping the higher-value one). If more peaks than
  `expected_reps` survive, it keeps the `expected_reps` highest-value ones and re-sorts
  by time — this guards against false positives from noise while trusting the user-
  reported rep count as ground truth.
- **`detect_reps_minima`** — same algorithm on a sign-inverted signal, for movements
  where the "peak" of interest is a minimum (e.g. squat depth = minimum hip Y).
- **`detect_holds(signal, threshold, fps, min_hold_sec)`** — for timed-hold exercises
  (hollow body, thoracic extension): finds contiguous runs where the signal stays above
  a threshold for at least `min_hold_sec`, reporting start/end/duration/average.
- **`detect_reps_multi(signals, ...)`** — fuses peak detection across *multiple*
  independent signals (e.g. both wrists' elevation) via a windowed majority vote,
  returning a `signal_agreement` confidence per detected rep. Used where a single signal
  alone is an unreliable proxy for "did a rep happen."
- **`detect_reps_velocity(bar_y, fps, ...)`** — the strength-analyzer-specific variant:
  Kalman-smooths bar Y, computes velocity, and finds rep boundaries from **velocity zero-
  crossings** rather than position peaks. This naturally segments each rep into descent /
  bottom / ascent / top phases and additionally locates the **sticking point** (first
  local velocity minimum during the concentric phase after a grace period) — the
  biomechanically hardest point of a lift, reported as a fault-timing anchor.

A recurring pattern across analyzers: **`detect_reps` operates on a *smoothed* signal, so
its `peak_frame` output lags the true extreme.** Every analyzer therefore re-scans the
*raw* per-frame values within `[start_frame, end_frame]` to find the actual maximum/
minimum before reading out any metric — this is called out explicitly as a rule in
`CLAUDE.md` and is visible in `knee_to_wall.py`'s `peak = max(range(seg_start, seg_end),
key=lambda i: shin_lean[i])`.

---

## 6. Camera-view classification

Strength analyzers require a specific camera angle per lift (sagittal/side vs. frontal),
and scoring from the wrong angle silently produces garbage metrics. `utils/camera_view.py`
gates every strength analyzer with a **pure-geometry classifier** (no ML model) that
votes across three independent measurements, sampled from the *middle 50%* of the
recording (skipping setup/warm-up motion):

1. **Shoulder-spread ÷ torso-length ratio** — a front-on view shows both shoulders
   fully spread (ratio ≈ 0.5–1.0×torso); a side view has one shoulder occluded behind
   the other (ratio ≈ 0.1–0.25×).
2. **Left/right ankle z-depth differential** — MediaPipe's z-channel is noisy per-frame
   but consistently shows a large left/right depth gap in a side view and near-zero in a
   front view.
3. **Landmark-visibility asymmetry** — a side view occludes one whole side of the body
   (visibility ~0.4 vs ~0.9); a front view keeps both sides symmetric (~0.7+ each).

Each measurement casts one vote for `'side'` or `'front'` (or abstains if it falls in an
ambiguous middle band); the majority wins, ties or all-abstain results in `'three_quarter'`
(rejected — a 45° angle is unusable for these metrics) or `'unknown'`. `confidence` is a
function of vote count and how far past each measurement's decision boundary the medians
fell. `assign_video_roles()` uses this to auto-assign uploaded files to roles (sagittal,
frontal, etc.) by classified view rather than trusting upload order/naming — important
because users sometimes upload camera angles in the wrong upload slot.

---

## 7. Barbell tracking

`utils/bar_tracker.py` is the strength-analyzer analog of pose tracking, but for the
**loaded plate** rather than the body:

1. **Detection** (`detect_plate`): `cv2.HoughCircles` on a median-blurred grayscale
   frame, searching a radius window derived either from a size hint or a fraction of
   frame height. The largest detected circle is assumed to be the plate (smaller circles
   are usually the plate's center pin-hole or background lights).
2. **Calibration** (`calibrate_px_per_cm`): the detected plate's pixel radius, combined
   with the real-world diameter looked up from `PLATE_DIAM_MM` by the user-supplied
   `plateSizeKg`, gives `px_per_cm`.
3. **Per-frame tracking** (`track_bar_path`): seeds an OpenCV **KCF tracker**
   (`cv2.TrackerKCF_create`) on the frame-0 detection, then updates it every frame. Every
   `fps` frames (≈once per second), it re-runs `HoughCircles` in a small ROI around the
   tracker's current estimate to correct drift — if the two disagree by more than one
   plate radius, the Hough detection wins and re-seeds the tracker. Each frame's centroid
   is tagged with a `quality` score: `1.0` (Hough-verified), `0.5` (tracker-only),
   `0.35` (tracker running but Hough couldn't confirm), or `0.0` (fully lost, inherits
   the previous frame's position). `median_quality` across the video is surfaced as an
   overall bar-tracking confidence.
4. **Derived signals**: `bar_velocity_series` (Kalman-smoothed, m/s, sign-corrected so
   positive = "up" in world space), `mean_concentric_velocity`, `bar_path_rms_x` / 
   `bar_path_horizontal_drift_cm` (bar-path straightness — a core lifting-technique
   metric), and `estimate_1rm` (Epley and Brzycki formulas from a working set's load and
   rep count).

---

## 8. DTW template matching

`utils/dtw_templates.py` answers "does this specific rep look like a *normal* rep for
this lift, or is it an outlier (kipping, mid-rep dump, wildly different tempo)?" — used
to **downweight** anomalous reps in set aggregation rather than let one bad rep skew the
whole session score.

- Each lift has a canonical template: a 100-point, magnitude- and time-normalized
  average "ideal" rep signal (e.g. hip-Y for squat, bar-Y for deadlift/bench/OHP,
  shoulder-to-wrist elevation for pull-up), loaded from `processor/templates/<lift>.json`.
  If no template file exists yet, a synthetic half-sine "descent→bottom→ascent" shape is
  used as a reasonable fallback.
- `template_similarity(rep_signal, lift_slug)` resamples the candidate rep to the same
  100-point grid, then computes similarity via **Dynamic Time Warping distance**
  (`dtaidistance.dtw.distance_fast`, with pruning for speed) — DTW is the right distance
  metric here because two real reps of the same movement rarely take exactly the same
  time in each phase; a naive point-by-point comparison would be dominated by tempo
  differences rather than shape differences. If `dtaidistance` isn't installed, falls
  back to normalized cross-correlation.
- `flag_outlier_reps()` returns indices of reps below a similarity floor (default 0.5),
  which callers use to exclude/deprioritize those reps from the "does not count" (DNC)
  bucket described in the strength spec docs (e.g. pull-up kipping/hand-release reps).

---

## 9. The scoring system

`processor/utils/scoring.py` is the single place every analyzer converts a raw
measurement into the tri-state clinical classification and, ultimately, a 0–100 score.

### Classification functions

- **`classify(value, good_thresh, needs_thresh, higher_is_better)`** — simple threshold
  classifier for metrics with one "better direction" (e.g. ankle dorsiflexion: higher is
  better; heel lift: lower is better).
- **`classify_range(value, good_min, good_max, needs_min, needs_max)`** — for
  range-of-motion metrics where *exceeding* the target is still fine (more mobility is
  never bad) — `GOOD` is simply `value >= good_min`.
- **`classify_band(value, good_min, good_max, needs_min, needs_max)`** — for *form*
  metrics with a genuine two-sided target (e.g. a "T" raise 40° past perpendicular is a
  formation error, not extra credit) — `GOOD` requires being *inside* `[good_min,
  good_max]`.

All three collapse to one of `'GOOD' | 'NEEDS IMPROVEMENT' | 'RESTRICTED'`.

### Building a metric

`build_metric(name, value_str, raw, target, max_val, classification, confidence=None,
n_reps=None, fault_timing=None)` packages a classification into the frontend-facing
`Metric` shape (`frontend/src/data/types.ts`), including:

- a binary `status` (`'good'`/`'bad'`) for simple UI coloring, alongside the full
  tri-state `classification`;
- an optional **`confidence`** in `[0,1]` — when a metric's underlying landmark
  visibility was low, this is set from `landmark_quality`/`window_landmark_quality`, and
  the frontend shows a confidence pill (`high`/`medium`/`low` tiers at 0.7/0.4 cutoffs);
- optional `n_reps` (how many reps contributed to an aggregated metric) and
  `fault_timing` (`{rep, start_phase_pct, message}` — *when in the rep* a fault appeared,
  surfaced as a UI chip and drawn on annotated frames via
  `frame_annotator.draw_fault_timing_strip`).

### Composite scoring

`compute_overall_score(metrics)` maps each metric's tier to a base score (`GOOD=100`,
`NEEDS IMPROVEMENT=60`, `RESTRICTED=25`; legacy binary `good`/`bad` metrics map to
`100`/`35`), then computes a **confidence-weighted average**: a metric's contribution is
weighted by its `confidence` (floored at 0.3, so a low-confidence metric still counts,
just less) — this keeps one badly-occluded metric from either dominating or being
completely thrown away. `overall_status(score)` buckets the final 0–100 score back into
`GOOD` (≥80) / `NEEDS IMPROVEMENT` (≥55) / `RESTRICTED` (below).

### Newer strength analyzers: 5-tier linear scoring

The rewritten strength analyzers (back squat, bench press, deadlift, OHP, pull-up) layer
a more granular system on top: each metric is scored 0–100 via **linear interpolation
between named tier anchors** (`very_good=100, good=90, yellow_flag=75, bad=60,
very_bad=40→0`, per the spec docs' §7.1), using either a `one_sided` mode (further in one
direction is strictly better/worse, anchors run best→worst raw value) or a `tent` mode
(there's an ideal value and deviation in *either* direction is penalized, anchors are
`|raw − ideal|` half-widths). These per-metric sub-scores then roll up into weighted
**Safety / Technique / Performance** category scores, combined into a composite via a
**geometric mean** (e.g. deadlift: `S_safety^0.50 · S_tech^0.35 · S_perf^0.15`) — a
geometric mean means a catastrophically bad safety score can't be fully offset by a great
technique score, unlike an arithmetic mean. On top of that, a fixed list of **hard-fail
safety overrides** (spec §7.4, e.g. lumbar flexion beyond a hard limit) can cap the
composite regardless of the weighted score. Per-rep composites aggregate to a set score
as mean/worst/last-3, with "deteriorating rep" flags when a rep's composite falls >15
points below the set mean (fatigue/form-decay signal).

### Aggregation helper

`aggregate_per_rep(rep_metrics, keys=None)` takes a list of per-rep metric dicts and
computes, per numeric key, `{mean, std, decay_slope, n, values}` — `decay_slope` is a
simple linear-regression slope of the metric against rep index, so a consistently
worsening metric across a set (e.g. valgus getting worse rep-over-rep) is flagged
quantitatively rather than just eyeballed from a chart.

### Coaching notes

`generate_coaching_notes(metrics, bilateral, exercise_name)` auto-generates plain-English
notes: flags metrics with `status='bad'`, flags bilateral asymmetries over 5 units, and
falls back to a positive note if nothing failed. Individual analyzers layer additional,
exercise-specific coaching on top (e.g. knee-to-wall's "FALSE POSITIVE: ARCH COLLAPSE"
callout when a user cheats knee travel by pronating the foot instead of truly
dorsiflexing).

---

## 10. Muscle-activation inference

`utils/muscle_inference.py` estimates **per-muscle activation percentages** from
kinematic measurements already computed by the analyzer (trunk-tibia angle, elbow flare,
grip width ratio, variant, etc.) — explicitly labeled to the user as "Estimated from
kinematics · Not EMG" since these are not real electromyography readings, just published
EMG-correlation heuristics (e.g. `infer_squat`: trunk-tibia angle > 10° → hip-dominant
pattern → glute/hamstring-biased activation numbers; < -10° → knee-dominant → quad-
biased). One inference function exists per lift (`infer_squat`, `infer_deadlift`,
`infer_bench_press`, `infer_pull_up`, `infer_overhead_press`), each returning a
`{exercise, dominance, muscles: [...]}` structure consumed by the frontend's `MuscleMap` /
`MuscleBody` components, which render activation onto an SVG body diagram (muscle slugs
in `ALL_MUSCLES` must match `frontend/src/components/shared/muscle-paths.ts` SVG path
IDs).

---

## 11. Frame annotation / visualization

`utils/frame_annotator.py` (~900 lines) is a small drawing DSL built entirely on **OpenCV
primitives** (`cv2.line`, `cv2.ellipse`, `cv2.putText`, `cv2.rectangle`, alpha-blended
overlays) for turning a raw video frame + computed metrics into an annotated screenshot.
Every analyzer extracts specific frames (the true rep extreme, best/worst rep, etc.) via
`extract_frame_at(video_path, frame_idx)` and layers on:

- `draw_skeleton` — the pose connections (which bones to draw is analyzer-specific — see
  e.g. `knee_to_wall.py`'s `LEG_CONNECTIONS`).
- `draw_angle_arc` — a colored arc at a joint showing the measured angle, colored by
  pass/warn/fail status.
- `draw_distance_line` / `draw_reference_line` — measured distances (knee travel, bar
  drift) and fixed reference lines (a detected wall edge, a floor baseline).
- `draw_callout` — a labeled pointer to a specific landmark (e.g. "HEEL LIFT 2.1cm").
- `draw_metric_overlay` / `draw_info_panel` — a metrics table/panel rendered directly
  onto the frame.
- `draw_title_strip`, `draw_phase_label`, `draw_top_phase_banner`,
  `draw_top_right_rep_pill`, `draw_confidence_pill`, `draw_legend` — chrome/labeling.
- `draw_fault_timing_strip` — a timeline strip showing *when* in the rep a fault fired.
- `draw_hip_height_trace` — a small inline sparkline of a tracked signal (e.g. hip
  height across the rep) burned into the frame.
- `draw_valgus_callout` — a specialized knee-valgus indicator.

The finished frame is JPEG-encoded and base64'd by `frame_to_base64()` (downscaled to a
`max_width` cap to keep the JSON payload size sane) into the result's `annotated_frames`
list, each entry shaped `{label, image_base64, rep_num, side, is_best, metrics_shown}`.
The frontend's `AnalysisPhotoGallery` component renders these directly as `<img
src="data:image/jpeg;base64,...">`.

> **Payload-size note:** these base64 frames are the heavyweight part of a result. The
> frontend explicitly strips `annotated_frames` before writing results into `localStorage`
> (`AppContext.stripHeavyFields`) — a single session's results could exceed the ~5MB
> localStorage quota otherwise — while the **server-side** session JSON keeps the full,
> unstripped payload as the source of truth.

---

## 12. How each mobility exercise works

All 10 live in `processor/analyzers/mobility/`. Each returns the standard result shape
via `build_result()`; camera setup and rep protocol are documented in each file's module
docstring. Ankle-to-body-part angle math draws on `utils/angles.py`; timing on
`utils/rep_detection.py`.

| # | Exercise | Camera(s) | What's actually measured |
|---|---|---|---|
| 1 | **Knee-to-Wall Test** (`knee_to_wall.py`) | Side (L+R, required) + front (optional) | Ankle dorsiflexion via **shin lean from vertical** (not the naive knee-ankle-toe angle, which the code notes under-reports on textbook reps). Tibia-length calibration (§4). **Heel lift** via a dual check: geometric Y-displacement *and* a 10×10px "ghost heel" MSE patch comparison between the resting and peak frame (catches heel roll-off even when the landmark itself barely moves). **Wall touch** via automated wall-edge detection: Canny edge detection + `HoughLinesP` finds near-vertical lines across the first 5 frames, then picks the one the knee is actually travelling toward. Front-view adds **knee valgus** (`180 − angle(hip,knee,ankle)`) and an **arch-collapse "cheat checker"** — ankle-vs-toe medial drift that flags when knee travel was achieved by pronating the foot rather than true dorsiflexion. |
| 2 | **Seated Hip Rotation Test** (`seated_hip_rotation.py`) | Front, L+R | Hip internal/external rotation from the lower-leg lever-arm swing angle. IR/ER is labeled from the **sign of the foot's deviation** at each rep (not rep order), so it's correct regardless of which rotation direction the athlete starts with. |
| 3 | **Thoracic Extension** (`thoracic_extension.py`) | Side, 1× 30s hold | Shoulder-to-hip angle relative to horizontal (clinical convention: shoulder physically below the hip line = extension) plus a shoulder→ear "head release" angle, held over the sustained-hold window via `detect_holds`. |
| 4 | **Quadruped Rotation / Thread the Needle** (`quadruped_rotation.py`) | Side, L+R | Thoracic rotation ROM from the rotating-arm elbow's distance off the spine baseline (hip-midpoint→shoulder-midpoint line). |
| 5 | **90/90 Shoulder Rotation** (`shoulder_rotation.py`) | Axial (down the humeral axis), L+R | IR/ER angle of the forearm from vertical, assigned by **temporal order** (protocol is fixed: IR→neutral→ER×3 alternating) rather than sign, since the axial camera view makes sign ambiguous. |
| 6 | **Single-Leg Glute Bridge** (`glute_bridge.py`) | Side, L+R | Peak hip-extension angle, a **hold-stability** metric (standard deviation of hip angle across a clamped post-peak hold window), and pelvic drop/rotation (bilateral hip Y-difference/tilt during the hold). |
| 7 | **Dead Bug** (`dead_bug.py`) | Side, 1 clip (8 movements) | Arm+leg extension angle (deviation from horizontal) at the true extreme of each of 8 alternating movements, assigned to left/right by fixed temporal order (movements 0,2,4,6 = one side, 1,3,5,7 = the other). |
| 8 | **Hollow Body Hold** (`hollow_body.py`) | Side, 3× ~10s holds | Ankle-elevation-above-floor as the hold-detection signal (a documented earlier version used an inverted signal that scored rest periods as holds — see the file's docstring for the fix rationale); metrics measured at the highest-elevation frame within each detected hold. |
| 9 | **Plank Shoulder Tap** (`plank_shoulder_tap.py`) | Front-side, 16 taps (8/side) | Anti-rotation quality at each tap's peak wrist-elevation frame — the moment the raised hand is furthest from the floor, i.e. the hardest anti-rotation instant. |
| 10 | **Prone Y-T-W Raise** (`ytw_raise.py`) | Overhead + foot-side, 6 clips (Y/T/W × 2 angles, 3 reps each) | Per-shape raise angle from the body's longitudinal axis (overhead cam) plus a **shrug-compensation** check (ear→shoulder distance decrease, foot-side cam) and elevation-angle confirmation. Returns both a flat `metrics` list and a `metric_sections` breakdown by shape (`Y`/`T`/`W`/`combined`) for the frontend's sectioned UI. |

Every mobility analyzer follows the same skeleton: extract landmarks → build a per-frame
scalar signal → `detect_reps`/`detect_holds` → re-scan the true extreme within each
segment → compute geometry at that frame → `classify`/`classify_range` each metric →
`build_bilateral` for L/R comparisons → `compute_overall_score` → 
`generate_coaching_notes` (+ exercise-specific coaching) → annotated frames via
`frame_annotator`.

---

## 13. How each strength lift works

The 5 strength analyzers (`processor/analyzers/strength/`) are substantially larger and
more sophisticated than the mobility ones (1,900–2,400 lines each vs. 250–900) — each is
a from-scratch implementation of a detailed biomechanical spec document (see
`Specification Files/*-rewrite.md` and `*_assessment_system.md`). Common structure across
all five:

1. **Multi-camera resolution.** Each lift accepts up to 4 simultaneous camera angles
   (sagittal/side is always primary; frontal, posterior, oblique are supporting/fallback
   views), each independently pose-extracted since they can have different fps and rep
   counts (`target_reps_sagittal`, `target_reps_frontal`, etc., passed per-view from the
   frontend form).
2. **Camera-view gating** (§6) — refuses to score a view that doesn't match what the
   lift needs, with a clear UI message instead of silently producing wrong metrics.
3. **Phase/extreme-frame detection specific to the lift's mechanics** — e.g. deadlift
   finds LIFTOFF (bar leaves floor) and LOCKOUT (top, body fully extended) using bar
   height *combined with* body-extension signals so lockout is never mis-anchored on a
   still-bent frame; bench press finds the touch frame (bar/wrist at its lowest,
   bench-relative) with different logic for paused vs. touch-and-go reps (last stationary
   frame vs. exact velocity zero-crossing); pull-up tracks *two* extremes per rep
   (dead-hang bottom and chin-over-bar top) via a Schmitt-trigger state machine; overhead
   press tracks *three* (setup, sticking point, lockout) and additionally runs a **hard
   push-press classifier** (knee bend > 8° or hip translation > 4cm before the bar rises)
   that excludes reclassified reps from the strict-press average entirely, not just
   penalizes them.
4. **20–40 metrics per lift**, each scored via the 5-tier linear-interpolation system
   (§9), with **style/variant-aware threshold columns** — e.g. back squat uses different
   thresholds for `low-bar` vs `high-bar` style; bench press for powerlifting vs.
   bodybuilding style and paused vs. touch-and-go; pull-up has **five separate rubrics**
   (strict/kipping/butterfly/sternum/c2b/tactical) since scoring a kipping athlete
   against the strict-form rubric is simply the wrong question, not a penalized one;
   overhead press has completely different active-metric sets for standing military press
   vs. seated dumbbell press (including a backrest-angle gate that refuses to score under
   the OHP rubric at all below 70° incline, redirecting to bench press).
5. **Category aggregation** — metrics roll up into Safety/Technique/Performance weighted
   sub-scores, combined via **geometric mean** into a per-rep composite, with hard-fail
   safety overrides able to cap the composite regardless of the weighted math (§9).
6. **DTW outlier flagging** (§8) — anomalous reps are identified against the lift's
   canonical template and excluded/flagged rather than allowed to distort the set
   average.
7. **Set aggregation** — mean (headline score), worst rep, last-3-reps (fatigue window),
   with deteriorating-rep flags (>15pt drop from set mean) and a `DNC` (does-not-count)
   bucket for reps excluded by fault classifiers (hand-release, push-press, kipping).
8. **Muscle activation** (§10) and **annotated frames** (§11) — typically best-rep and
   worst-rep get full multi-camera annotation; middle reps get a lighter single-view
   annotation to control payload size.
9. **1RM estimation** where a working set + load is supplied — Epley and Brzycki formulas
   (`bar_tracker.estimate_1rm`).

Per-lift specifics:

- **Back Squat** (`back_squat.py`) — 18 metrics across sagittal/frontal (rear view is
  intentionally folded into the frontal-view fallback rather than requesting a 3rd
  camera). Style column (`low-bar`/`high-bar`) picks between the spec's "Normal Squat"
  and "Deep Squat" threshold sets. Uses plate-based calibration and bar tracking for
  depth/bar-path metrics, `infer_squat` for muscle activation.
- **Deadlift** (`deadlift.py`) — 32 metrics, conventional/sumo/trap-bar/RDL variant
  awareness (feeds `infer_deadlift`'s dominance labeling). Bar position on the sagittal
  view is a weighted blend of plate-centroid tracking and wrist-centre position (spec
  §12.5.3) rather than either alone, since the plate can be briefly occluded by the
  lifter's hands/body at lockout.
- **Bench Press** (`bench_press.py`) — 32 metrics across 4 camera roles (sagittal,
  overhead, head-end, oblique). Rotates landmark coordinates by the bench's incline angle
  so "up off the bench" becomes a clean positive-Y axis regardless of whether the bench
  is flat or inclined — `incline_deg` from the form is cross-validated against the
  auto-detected shoulder-hip line at setup.
- **Overhead Press** (`overhead_press.py`) — 38 metrics, the most branchy of the five:
  separate active-metric sets and safety-override lists for standing military press
  (full kinetic-chain overrides active) vs. seated dumbbell press (bench-contact and
  independently-tracked-DB symmetry metrics instead), plus an anthropometry adjustment
  that relaxes one threshold by 20% for long-armed lifters (forearm length > 0.16×
  height).
- **Pull-Up** (`pull_up.py`) — 33 metrics, grip-aware (pronated/supinated/neutral/wide →
  4 threshold categories feeding `infer_pull_up`), with an explicit fallback chain for
  chin-over-bar detection because MediaPipe's face landmarks frequently get occluded by
  the bar itself at lockout.

---

## 14. Node backend internals

`backend/server.js` is a single-file Express app with three concerns:

- **Job queue** — a plain in-memory `Map<jobId, jobState>`. No database, no Redis — jobs
  do not survive a server restart by design (this is called out explicitly in
  `CLAUDE.md`). Terminal jobs (`complete`/`error`) are pruned after a 30-minute TTL via an
  `unref()`'d `setTimeout` so the timer never keeps the process alive and the map can't
  grow unboundedly if a client stops polling.
- **Session persistence** (`backend/lib/sessionStore.js`) — one JSON file per session at
  `backend/sessions/<sessionId>.json`. Writes are **atomic** (write to a
  `<file>.<pid>.<timestamp>.tmp` then `rename()`, which is atomic on POSIX filesystems)
  and **serialized per-session** via an in-memory promise-chain mutex (`withLock`) so two
  near-simultaneous result-appends for the same session can't race and clobber each
  other's writes. `sessionId` is validated against a strict regex before ever touching
  the filesystem, preventing path traversal.
- **Proxy to Python** — `analyseHandler` builds a `FormData` (via the `form-data` npm
  package) re-streaming the uploaded files plus whitelisted params, and posts it to
  `http://localhost:5001/process` with `axios` (5-minute timeout, unlimited body/content
  length since videos can be large). Multer (`multer.diskStorage`) writes uploads to
  `backend/temp_uploads/<jobId>/` first — filenames are derived from the multipart field
  name plus a timestamp, not the browser-supplied original filename, specifically so two
  camera angles exported with an identical name (e.g. `IMG_0001.MOV`) can't overwrite
  each other in the shared per-job directory. That directory is deleted 5 seconds after
  the job settles (success or failure).
- **Error diagnostics** — the catch block in `analyseHandler` unpacks the axios error
  into a human-readable message depending on its shape: a structured `{error, detail}`
  body from Python's own 500 handler, a raw non-JSON body, `ECONNREFUSED` (processor not
  running), `ECONNRESET` (processor crashed mid-request), or a timeout — so the frontend
  surfaces something more actionable than "Network Error."
- **Legacy aliases** — `POST /api/analyse` (old exerciseId-based clients) and
  `GET /api/status/:jobId` / `DELETE /api/cleanup/:jobId` (old route names) are kept as
  thin re-dispatches to the current handlers "for one cycle," per the code comments.

Slugs are the stable identifier everywhere (`resolveSlug`, `MOBILITY_SLUG_TO_ID`,
`STRENGTH_SLUGS`); the numeric `exerciseId` only exists for backward compatibility with
the original Python router's id-based dispatch and is derived from the slug, never the
reverse.

---

## 15. Frontend state &amp; rendering

**Routing** (`App.tsx`, `react-router-dom`) is fully parametrized by `:type` (`mobility`
| `strength`) and `:slug`, validated against the exercise registry
(`frontend/src/data/registry.ts`) on every route — an invalid type/slug redirects home
rather than rendering a broken page. Route-level wrapper components (`GuideRoute`,
`InstructionRoute`, `ProcessingRoute`, `ResultRoute`, `DashboardRoute`) pull params via
`useParams()` and wire the relevant `AppContext` slices into the presentational page
components.

**`AppContext`** (`frontend/src/context/AppContext.tsx`) is the single global state
provider:

- `uploads: Record<string, File>` — populated on `InstructionPage`, keyed by a
  **namespaced upload key** (`uploadKeys.ts`: `` `${type}::${slug}::${uploadId}` ``) —
  this exists specifically because mobility and strength exercise IDs overlap (both
  tracks number 1–10/1–5), so an id-only key would let a video uploaded for one
  exercise's "front" slot silently satisfy a different exercise's "front" slot in the
  other track. The `::` separator is safe because slugs/upload-ids are always kebab-case.
- `reports: {mobility, strength}` — the durable per-exercise results, **dual-persisted**:
  written to `localStorage` (`mobilityai_reports_v2`, heavy `annotated_frames` stripped
  first — see §11) for instant boot, and pushed to the Node session store for the
  full-fidelity source of truth. On boot, `AppContext` fetches the server session and
  **merges** it into local state rather than replacing it outright — local-only results
  (e.g. from a server push that failed earlier) survive a reload and get re-synced to the
  server instead of being silently dropped. A one-time migration path
  (`migrateLegacyReports`) upgrades the old integer-id-keyed `mobilityai_reports_v1`
  format to slug keys, then deletes the old key.
- `apiResult` — the just-completed job's live result, tagged with `{type, slug}` so
  `ResultPage` can tell whether the live result actually belongs to the exercise the user
  is currently viewing (reachable-by-back-button protection against rendering exercise
  A's live result on exercise B's result page); explicitly cleared via `setApiResult(null)`
  on most navigations.
- `profile` — calibration constants (`tibiaLengthCm`, `athleteHeightCm`, `plateSizeKg`),
  persisted to `localStorage` only (not session-scoped — these are properties of the
  user, not a specific assessment run).
- `exerciseInputs` — per-exercise form state (variant, load, target reps, style, etc.),
  persisted to `localStorage`, read by `InstructionPage` and forwarded as `AnalyseParams`
  on submit.

**`services/api.ts`** wraps the three Node endpoints (`uploadAndAnalyse`,
`getJobStatus`, `cleanupJob`) behind a typed `AnalyseParams` interface that mirrors Node's
`passthroughFields` allowlist field-for-field. **`services/session.ts`** handles session
bootstrap (`ensureSession`) and result push (`pushResult`).

**Result rendering** (`ResultPage` + `components/shared/*`) fans the result dict out into
purpose-built widgets: `RadarChart` (multi-metric overview), `MetricHistogram`,
`PerRepAccordion` (per-rep breakdown for strength sets), `MuscleMap`/`MuscleBody` (SVG
muscle-activation diagram), `AnalysisPhotoGallery` (the base64 annotated frames).

---

## 16. Library reference table

### Python (`processor/`)

| Library | Role in this project |
|---|---|
| **Flask** + **flask-cors** | The `/process` and `/health` HTTP endpoints. `CORS(app)` lets the Node backend (different origin/port) call it directly during dev. |
| **MediaPipe** | Core pose-estimation engine — 33-landmark body pose per frame, via either the legacy `solutions.pose` API or the newer Tasks `PoseLandmarker` API (auto-detected). Every single analyzer is built on its output. |
| **OpenCV** (`opencv-python` + `opencv-contrib-python`) | Video I/O (`VideoCapture`, frame reads), image preprocessing (resize, color conversion, blur), classical CV for barbell-plate detection (`HoughCircles`), object tracking (`TrackerKCF` — requires `opencv-contrib-python`), edge/line detection for wall-mapping (`Canny` + `HoughLinesP`), and all frame annotation drawing primitives. |
| **NumPy** | Vector math throughout — angle calculations (`angle_3pt` via dot products), array-based signal manipulation, resampling for DTW template comparison. |
| **SciPy** | `scipy.signal.savgol_filter` — Savitzky-Golay smoothing for derived 1-D signals (angles, positions) ahead of peak/rep detection. |
| **filterpy** | `KalmanFilter` — constant-velocity 1-D Kalman smoothing for bar position, used specifically where a clean velocity derivative is needed (rep-phase segmentation, concentric velocity reporting). |
| **scikit-learn** | Listed for regression / future fault-classifier work (`requirements.txt` comment: "Regression / future fault classifiers") — the ML-based extension point for the strength pipeline. |
| **dtaidistance** | Fast Dynamic Time Warping (`dtw.distance_fast`) for comparing a rep's motion signal against a lift's canonical template, to flag outlier reps for exclusion from set aggregation. |
| **PyYAML** | Parses the `eval/annotations/<lift>/*.yaml` ground-truth files used by the evaluation harness (`eval/run_eval.py`) to compute precision/recall/F1 against hand-labeled faults. |

### Node (`backend/`)

| Library | Role in this project |
|---|---|
| **express** | The API server — job/session/analyse routes. |
| **multer** | Multipart file upload handling; configured with `diskStorage` writing straight to `temp_uploads/<jobId>/` rather than buffering in memory (videos can be large). |
| **axios** | Outbound HTTP client for the Node→Python `/process` proxy call. |
| **form-data** | Builds the multipart body Node re-streams to Python (re-wrapping Multer's saved files as readable streams). |
| **cors** | Restricts the API to the known frontend origin (`http://localhost:5173`) in dev. |
| **uuid** | Generates `jobId`s. |

### Frontend (`frontend/`)

| Library | Role in this project |
|---|---|
| **React 19** + **react-dom** | UI runtime. |
| **react-router-dom 7** | Client-side routing, param-driven (`:type`/`:slug`) route tree. |
| **Vite** | Dev server + build tool; proxies `/api/*` to Node in dev (`vite.config.ts`) so the SPA and API appear same-origin to the browser. |
| **TypeScript** | Static typing across the app, including the `ExerciseResult`/`Metric`/`BilateralComparison` shapes that mirror the Python result dict contract. |
| **Tailwind CSS 4** (`@tailwindcss/vite`) + **tailwind-merge** + **tw-animate-css** | Utility-first styling and animation utilities. |
| **radix-ui** | Unstyled, accessible primitive components underlying the custom UI kit. |
| **class-variance-authority** + **clsx** | Variant-driven className composition for the component library. |
| **framer-motion** | Page/element transition animations. |
| **lucide-react** | Icon set. |
| **axios** | HTTP client for all Node API calls (`services/api.ts`, `services/session.ts`). |
| **@fontsource-variable/geist** | Self-hosted variable font. |

### Evaluation-only

| Tool | Role |
|---|---|
| `processor/eval/sample_harness.py` | Caches extracted MediaPipe landmarks to disk (keyed by file size+mtime) so analyzer logic can be re-run against a sample video in milliseconds instead of re-running pose estimation (which takes minutes on 4K footage) on every iteration. |
| `processor/eval/run_eval.py` | Reads YAML ground-truth fault annotations, runs the matching analyzer, and reports per-fault precision/recall/F1 plus fault-timing mean-absolute-error — the accuracy gate referenced by spec docs' "≥95%" claims. |
| `processor/eval/tune_thresholds.py`, `synthetic_tests.py`, `run_all_samples.py` | Supporting tools for threshold tuning and batch sample runs. |
