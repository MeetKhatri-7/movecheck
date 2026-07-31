# Biomechanical Assessment System — Conventional Deadlift & Romanian Deadlift (RDL)

A computer-vision–friendly scoring framework parallel to the barbell-squat assessment document. All thresholds are intended for video-based analysis via MediaPipe Pose, with explicit safety overrides reflecting the deadlift's elevated lumbar injury risk profile.

---

## Table of Contents

1. Required Camera Angles
2. Conventional vs Romanian Deadlift: Key Differences
3. Sagittal (Side) View Metrics
4. Frontal (Front) View Metrics
5. Posterior (Rear) View Metrics
6. Tempo & Control Metrics
7. Composite Scoring System
8. Grade & Label Mapping
9. Alternative Naming Schemes
10. Worked Example
11. Practical Notes & Caveats
12. MediaPipe Pose Implementation Guide
13. Appendix — Metric Summary Table

---

## 1. Required Camera Angles

The deadlift is dominated by sagittal-plane mechanics (hip hinge, bar path, torso angle, hip–shoulder timing) but secondary frontal/posterior cues are essential for safety screening (lumbar deviation, knee tracking, bar tilt). A two-camera setup (sagittal + frontal) is the practical minimum; a three-camera setup adds posterior coverage.

### 1.1 Views

| View | Primary purpose | Priority |
|---|---|---|
| Sagittal (side, lifter's strong side) | Torso/hip/knee/shin angles, bar path, hip–shoulder timing, lockout, lumbar flexion proxy | **Required** |
| Frontal (front, ~2.5–3 m away) | Stance width, foot/toe angle, knee valgus/varus, bar tilt, lateral hip shift, grip width | **Required** |
| Posterior (rear) | Spinal lateral deviation, shoulder/scapular symmetry, hip asymmetry, bar tilt cross-check | Recommended |
| Oblique (45°) | Backup view if sagittal occluded by plates; useful for sumo cross-check; not primary | Optional |

### 1.2 Camera setup recommendations

| Parameter | Recommendation | Rationale |
|---|---|---|
| Frame rate | **60 fps** minimum; 120 fps for advanced velocity tracking | Escamilla et al. (2000), using 60-Hz video at the U.S. national powerlifting championship, reported a total deadlift lift time of 4.08 ± 0.86 s for masters lifters at ≈100% 1RM; 30 fps is acceptable but loses bar-velocity and stripper-timing fidelity |
| Resolution | 1080p (1920×1080) min; 4K preferred for long shots | Pose landmark stability degrades below 720p |
| Lens height | Hip-height (~90–110 cm), tripod-mounted | Centring on the lifter–bar centre of mass reduces parallax |
| Distance | 3–4 m sagittal; 2.5–3 m frontal; 3 m posterior | Full body + bar must fit in frame at start and lockout |
| Lighting | Even, diffuse, ≥500 lux, no backlight | Backlight collapses contrast and crushes landmark detection |
| Background | Plain, contrasting | Avoid pose-detector false positives from mirrors/posters |
| Camera | Static tripod; no zoom, no panning | Per Topend Sports video-analysis convention |
| Calibration | A known-length reference (Olympic plate edge = 45 cm) in view | Enables metric distance estimation |

### 1.3 Which angle captures which metrics

| Metric | Sagittal | Frontal | Posterior |
|---|:---:|:---:|:---:|
| Torso angle | ✓ | | |
| Hip hinge depth | ✓ | | |
| Knee flexion at start | ✓ | | |
| Shin angle | ✓ | | |
| Bar path / horizontal drift | ✓ | | |
| Bar-to-shin / bar-to-thigh distance | ✓ | | |
| Hip–shoulder timing ("stripper") | ✓ | | |
| Lumbar flexion approximation | ✓ | | ✓ |
| Lockout completion | ✓ | | |
| Heel contact | ✓ | (✓) | |
| Stance width | | ✓ | ✓ |
| Foot/toe angle | | ✓ | |
| Grip width | | ✓ | |
| Bar tilt | | ✓ | ✓ |
| Knee valgus/varus | | ✓ | |
| Lateral hip shift | | ✓ | ✓ |
| Spinal lateral deviation | | | ✓ |
| Shoulder symmetry | | (✓) | ✓ |
| Pull symmetry (L/R) | | ✓ | ✓ |

---

## 2. Conventional vs Romanian Deadlift: Key Differences

| Dimension | Conventional Deadlift | Romanian Deadlift (RDL) |
|---|---|---|
| Starting position | Bar on the floor, dead stop; lifter bent at hips and knees | Bar at hip/thigh height, lifter standing tall; movement starts with eccentric (lowering) |
| Direction of first phase | Concentric (lift from floor) | Eccentric (hinge down) |
| Hip joint angle at start | ~67–72° (Escamilla et al. 2000 measured 72 ± 12°; McGuigan & Wilson 1996 measured 67 ± 5°) | Hip extended (≈170–180°) at top; flexes to hamstring-limited depth at bottom |
| Knee joint angle at liftoff / bottom | ~120–124° (Escamilla et al. 2000: 124 ± 9°) — i.e., ~55–60° of flexion | Knee held at ~15° flexion per Piper & Waller (2001) coaching standard; Lee et al. (2018, PMC6323186) measured 15–33° of knee flexion in trained RDL subjects asked to descend to the floor |
| Knee angle change during lift | Knees extend ~37° from liftoff to knee-pass (Escamilla 2000) | Knees do not change angle significantly |
| Bar contact with body | Bar slides up shins, knees, thighs to hip lockout | Bar slides down thighs to mid-shin and back up |
| Bar position at start | Over mid-foot, ~1 inch (2.5 cm) in front of vertical shin (Rippetoe / *Starting Strength* canonical position) | At hip/upper-thigh height |
| Stance width | 32 ± 8 cm (Escamilla et al. 2000), ≈80 ± 16 % of biacromial width — hip-width or narrower | Hip-width, similar to conventional |
| Range of motion | Floor → standing (vertical bar travel 44.4 ± 5.7 cm, or 26.0 ± 2.3 % of body height per Escamilla et al. 2000) | Top → mid-shin (~50–70 % of conventional ROM, hamstring-limited) |
| Primary muscle emphasis | Whole posterior chain + quads (knee extension contribution) | Hamstrings + glutes + erectors (no significant quad demand) |
| Trunk angle at bottom | 24 ± 10° above horizontal at liftoff (Escamilla et al. 2000) | Often near-parallel to floor at bottom (hamstring-flexibility dependent) |
| Spine cue | Neutral; some inevitable lumbar flexion under heavy load — Cholewicki & McGill (J Biomech 25(1):17–28, 1992) reported elite powerlifters "accomplished their lifts with an amount of lumbar flexion between 1.5 and 13 degrees less than they demonstrated during full flexion" | Strict neutral; spinal flexion ends the rep |
| Eccentric quality | Optional; many lifters drop bar | Mandatory slow, controlled eccentric — defines the lift |
| "Good form" signature | Vertical bar path over mid-foot; hips and shoulders rise together; lockout = full hip + knee extension with glutes squeezed | Knees frozen at ~15° bend; hips travel back, not down; bar grazes thighs; stops at hamstring-stretch endpoint, not the floor |

---

## 3. Sagittal (Side) View Metrics

Scoring tiers: **Very Good (90–100)**, **Good (75–89)**, **Yellow Flag (60–74)**, **Bad (40–59)**, **Very Bad (0–39)**.

Where Conventional and RDL differ, separate columns are given. "Trunk angle above horizontal" = 0° flat parallel to floor, 90° fully upright.

### 3.1 Torso angle at start (relative to horizontal floor)

| Tier | Conventional | RDL (at bottom of eccentric) |
|---|---|---|
| Very Good | 20°–35° above horizontal | 5°–25° above horizontal (deep hinge, neutral spine) |
| Good | 15°–20° or 35°–45° | 25°–35° or 0°–5° |
| Yellow Flag | 10°–15° or 45°–55° | 35°–45° |
| Bad | <10° (too horizontal) or 55°–65° | 45°–55° |
| Very Bad | <5° (parallel-to-floor) or >65° (squat-like) | >55° (collapsed) or torso lifted prematurely |

Anchor: Escamilla et al. (2000) measured 24 ± 10° trunk angle (above horizontal) at liftoff in 12 conventional masters powerlifters at the U.S. national championship; McGuigan & Wilson (J Strength Cond Res 10(4):250–255, 1996) measured 17 ± 7° on regional New Zealand competitors.

### 3.2 Torso angle at lockout (relative to vertical)

| Tier | Both lifts |
|---|---|
| Very Good | 0° ± 3° (true vertical, ribs stacked over pelvis) |
| Good | 0° ± 5° |
| Yellow Flag | Forward lean 5°–10° **or** backward lean 3°–7° |
| Bad | Backward lean 7°–15° (hyperextension) **or** incomplete (>10° forward) |
| Very Bad | Backward lean >15° (clear hyperextension) or torso never reaches vertical |

### 3.3 Bar path horizontal deviation

Maximum horizontal drift from the start-frame mid-foot reference, normalised to lifter height.

| Tier | Conventional | RDL |
|---|---|---|
| Very Good | <2% of lifter height (≤≈3.5 cm for a 175 cm lifter) | Bar stays in contact with thighs/shins throughout |
| Good | 2%–4% | Bar within 2 cm of legs |
| Yellow Flag | 4%–6% | Bar 2–5 cm from legs |
| Bad | 6%–9% | Bar 5–10 cm from legs |
| Very Bad | >9% (bar swings out, looping pattern) | Bar >10 cm from legs (RDL turning into stiff-leg good-morning hybrid) |

Escamilla et al. (2000) reported bar motion in the conventional deadlift "primarily occurred in the vertical direction"; no peer-reviewed cm-value for "acceptable drift" exists, so these are coaching-derived thresholds.

### 3.4 Bar-to-shin distance at start (conventional only)

| Tier | Conventional |
|---|---|
| Very Good | 1–3 cm from shin (Rippetoe / *Starting Strength* canonical position) |
| Good | 0 cm (touching shin) or 3–5 cm |
| Yellow Flag | 5–8 cm |
| Bad | 8–12 cm |
| Very Bad | >12 cm (bar over toes) |

### 3.5 Bar-to-thigh proximity throughout pull

| Tier | Both lifts |
|---|---|
| Very Good | Continuous contact / dragging the bar up the legs |
| Good | <1 cm gap throughout |
| Yellow Flag | 1–4 cm gap at some point |
| Bad | 4–8 cm gap |
| Very Bad | >8 cm gap (bar visibly orbits the legs) |

### 3.6 Hip–shoulder timing (stripper-deadlift detection; conventional only)

Define R = ΔHip_y / ΔShoulder_y over the first 100 ms after liftoff. R = 1.0 means hips and shoulders rise together; R > 1 means hips rise faster ("stripper").

| Tier | Conventional |
|---|---|
| Very Good | R = 0.9–1.1 (synchronous rise) |
| Good | R = 0.8–0.9 or 1.1–1.3 |
| Yellow Flag | R = 1.3–1.6 |
| Bad | R = 1.6–2.2 (clear stripper) |
| Very Bad | R > 2.2 (hips fully rise before bar leaves floor) |

### 3.7 Knee flexion angle at start (conventional)

Knee joint angle, 180° = full extension.

| Tier | Conventional |
|---|---|
| Very Good | 115°–130° knee angle (matches Escamilla et al. 2000's 124 ± 9° at liftoff) |
| Good | 105°–115° or 130°–140° |
| Yellow Flag | 95°–105° or 140°–150° |
| Bad | 85°–95° (too squat-like) or 150°–160° |
| Very Bad | <85° (full squat depth) or >160° (stiff-leg style with bar on floor) |

### 3.8 Knee flexion at bottom of RDL

| Tier | RDL |
|---|---|
| Very Good | 15°–25° flexion held constant from top to bottom |
| Good | 10°–15° or 25°–35° |
| Yellow Flag | 5°–10° (locking into stiff-leg) or 35°–45° |
| Bad | 0°–5° (fully locked) or 45°–60° (squatting the weight down) |
| Very Bad | Hyperextended knees at top **or** >60° flexion at bottom |

Anchor: Piper & Waller (Strength Cond J 23(3):66–73, 2001) coaching standard of ~15° knee flexion; Lee et al. (J Exerc Sci Fit; PMC6323186, 2018) measured 15°–33° in their crossover RDL/CD study at 70 % of RDL 1RM.

### 3.9 Shin angle from vertical at start (conventional)

| Tier | Conventional |
|---|---|
| Very Good | 5°–15° forward of vertical (Escamilla et al. 2000 reported shank 76 ± 5° from horizontal ≈ 14° forward of vertical) |
| Good | 0°–5° or 15°–20° forward |
| Yellow Flag | 20°–28° forward |
| Bad | 28°–35° forward (knees over bar) |
| Very Bad | >35° (squat shin angle) or shins behind vertical |

### 3.10 Lumbar spine flexion / rounding under load

MediaPipe cannot track the lumbar spine directly. The approximation uses the deviation of the shoulder-hip-knee triangle angle from the reference neutral established at the start frame; progressive curving (mid-back moves anteriorly relative to the shoulder–hip line) is flagged.

| Tier | Both lifts (Δ deviation from start-frame neutral) |
|---|---|
| Very Good | ≤3° deviation; spine visibly straight throughout |
| Good | 3°–7° deviation (within the range of normal trained-lifter lumbar accommodation) |
| Yellow Flag | 7°–12° deviation (mild visible rounding, particularly thoracic) |
| Bad | 12°–20° deviation (clear lumbar flexion under load) |
| Very Bad | >20° deviation or visible "buckling" / cat-back during the rep |

Context: Vigotsky et al. (PeerJ 3:e708, 2015) measured exactly 28° lumbar flexion at peak hip flexion (95% CI = 26–29°) in 15 trained males (age 24.6 ± 5.3 yr; 8.6 ± 5.5 yr lifting experience) during the good morning at 50% 1RM, and observed no significant change as load was incremented to 90% 1RM — i.e., non-zero lumbar flexion is the trained-lifter norm. This metric therefore flags **progressive worsening under load** rather than absolute lumbar position. **Hard-fail safety override** — see §7.4.

### 3.11 Thoracic spine position

| Tier | Both lifts |
|---|---|
| Very Good | Neutral thoracic curve; chest "tall," scapulae set |
| Good | Slight kyphosis (5°–10° above neutral) — acceptable in heavy lifters |
| Yellow Flag | Moderate kyphosis (10°–20°), shoulders visibly forward |
| Bad | 20°–30° thoracic flexion; visible upper-back rounding |
| Very Bad | >30° thoracic rounding (turtle-back) |

### 3.12 Neck / head position

| Tier | Both lifts (cervical–torso continuation angle) |
|---|---|
| Very Good | ±5° of torso continuation; eyes on a spot 3–5 m ahead |
| Good | ±10° |
| Yellow Flag | 10°–20° flexion (chin to chest) or extension (looking up) |
| Bad | 20°–35° |
| Very Bad | >35° (extreme chin tuck or "stargazing") |

### 3.13 Hip extension completion at lockout

Hip joint angle, 180° = full extension.

| Tier | Both lifts |
|---|---|
| Very Good | 175°–182° (slight glute squeeze, no hyperextension) |
| Good | 170°–175° or 182°–186° |
| Yellow Flag | 165°–170° (short of lockout) or 186°–192° (mild hyperextension) |
| Bad | 155°–165° or 192°–200° |
| Very Bad | <155° (clearly not standing tall) or >200° (gross hyperextension/lean-back) |

### 3.14 Knee extension completion at lockout

| Tier | Both lifts |
|---|---|
| Very Good | 175°–182° |
| Good | 170°–175° |
| Yellow Flag | 165°–170° (soft knees) |
| Bad | 155°–165° |
| Very Bad | <155° (knees clearly bent at "lockout") |

### 3.15 Heel contact throughout

| Tier | Both lifts |
|---|---|
| Very Good | Heels fully grounded for 100% of rep |
| Good | Heels grounded ≥98% of rep duration |
| Yellow Flag | Brief heel lift (<200 ms) during transition |
| Bad | Heel lift 200–500 ms (clear weight shift to forefoot) |
| Very Bad | Heels off ground >500 ms or during loaded portion |

### 3.16 Range of motion for RDL (lowest bar height)

| Tier | RDL |
|---|---|
| Very Good | Bar descends to mid-shin / just below knee, hamstring-limited stop with neutral spine |
| Good | Just above knee (~10–20 cm below start position) |
| Yellow Flag | Above knee — short ROM that may indicate hamstring tightness |
| Bad | Bar barely moves (<10 cm) — quasi-isometric pseudo-RDL |
| Very Bad | Bar descends to floor with lumbar flexion (form failure) **or** bar descends below mid-shin with visible lumbar rounding |

---

## 4. Frontal (Front) View Metrics

### 4.1 Stance width relative to hip / shoulder width

| Tier | Both lifts |
|---|---|
| Very Good | 80%–110% of biacromial (shoulder) width — matches Escamilla et al. (2000)'s 80 ± 16% in conventional powerlifters |
| Good | 70%–80% or 110%–125% |
| Yellow Flag | 60%–70% or 125%–145% |
| Bad | 50%–60% or 145%–170% |
| Very Bad | <50% (feet touching) or >170% (semi-sumo width in a conventional lift) |

### 4.2 Foot / toe-out angle

| Tier | Both lifts |
|---|---|
| Very Good | 7°–15° toe-out (matches Escamilla et al. 2000's 14 ± 6° for conventional) |
| Good | 0°–7° or 15°–22° |
| Yellow Flag | 22°–30° or feet asymmetric ±5° L/R |
| Bad | 30°–40° (excessive flare) or asymmetric ±10° |
| Very Bad | >40° or feet pointed inward (pigeon-toed) or asymmetric ±15° |

### 4.3 Grip width

| Tier | Conventional | RDL |
|---|---|---|
| Very Good | Hands just outside thighs, arms hanging vertically (≈55 ± 10 cm hand width per Escamilla et al. 2000) | Slightly wider than hip width, ~shoulder width |
| Good | ±5 cm from neutral | ±5 cm |
| Yellow Flag | Hands brushing thighs, or 10–15 cm wider than neutral | 10–15 cm offset |
| Bad | Hands collide with thighs **or** snatch-grip wide (without intent) | Asymmetric grip ±5 cm |
| Very Bad | Grip prevents arm–knee clearance and forces knee valgus | Grip clearly asymmetric (>5 cm one side) |

### 4.4 Bar tilt (one side higher than the other)

| Tier | Both lifts |
|---|---|
| Very Good | <2° tilt across entire rep |
| Good | 2°–4° |
| Yellow Flag | 4°–7° tilt at any frame |
| Bad | 7°–12° tilt |
| Very Bad | >12° tilt sustained for >300 ms |

### 4.5 Lateral hip shift

| Tier | Both lifts (max hip-centre lateral displacement, % of stance width) |
|---|---|
| Very Good | <3% |
| Good | 3%–6% |
| Yellow Flag | 6%–10% |
| Bad | 10%–15% |
| Very Bad | >15% (gross weight-shift onto one leg) |

### 4.6 Knee tracking (valgus / varus, frontal-plane projection angle FPPA)

| Tier | Both lifts |
|---|---|
| Very Good | Knees track over 2nd–3rd toe, FPPA <5° |
| Good | FPPA 5°–10° |
| Yellow Flag | FPPA 10°–15° |
| Bad | FPPA 15°–22° |
| Very Bad | FPPA >22° (clear valgus collapse) or visible varus bowing |

### 4.7 Symmetry of pull (left vs right shoulder rise timing)

| Tier | Both lifts |
|---|---|
| Very Good | <30 ms timing difference; <2° angular difference at any phase |
| Good | 30–80 ms or 2°–5° |
| Yellow Flag | 80–150 ms or 5°–10° |
| Bad | 150–300 ms or 10°–18° |
| Very Bad | >300 ms or >18° (visible side-rise / hitching on one side) |

---

## 5. Posterior (Rear) View Metrics

### 5.1 Spinal alignment (lateral deviation)

| Tier | Both lifts (max midline deviation, % torso length) |
|---|---|
| Very Good | <2% |
| Good | 2%–4% |
| Yellow Flag | 4%–7% |
| Bad | 7%–11% |
| Very Bad | >11% (clear S-curve / lateral lean) |

### 5.2 Shoulder symmetry

| Tier | Both lifts |
|---|---|
| Very Good | Shoulder line within 2° of horizontal |
| Good | 2°–4° |
| Yellow Flag | 4°–7° |
| Bad | 7°–12° |
| Very Bad | >12° |

### 5.3 Hip symmetry during pull (hip-line tilt)

| Tier | Both lifts |
|---|---|
| Very Good | Hip line stays ≤2° from horizontal |
| Good | 2°–4° |
| Yellow Flag | 4°–7° |
| Bad | 7°–12° |
| Very Bad | >12° (visible hip hike) |

### 5.4 Bar tilt cross-check

Same thresholds as §4.4. Posterior view confirms frontal-view tilt and detects bar rotation (windmilling).

---

## 6. Tempo & Control Metrics

### 6.1 Setup time / pre-pull tension

Time from bar grip to bar liftoff.

| Tier | Conventional |
|---|---|
| Very Good | 2–5 s of deliberate setup, visible "slack pull" |
| Good | 1–2 s or 5–8 s |
| Yellow Flag | <1 s (rushed) or 8–15 s (overlong) |
| Bad | 15–25 s or instantaneous grip-and-yank |
| Very Bad | >25 s (CNS fatigue / hesitation) |

(RDL: setup = bar unrack + brace; same thresholds with rack-walkout excluded.)

### 6.2 Concentric tempo (floor to lockout)

| Tier | Conventional | RDL (up-phase) |
|---|---|---|
| Very Good | 1.0–2.5 s for working sets (Escamilla et al. 2000 measured 4.08 ± 0.86 s at near-1RM; faster for sub-max) | 1.0–2.0 s |
| Good | 0.7–1.0 s or 2.5–3.5 s | 0.7–1.0 s or 2.0–3.0 s |
| Yellow Flag | 3.5–5 s (slow grinder) | 3.0–4.0 s |
| Bad | 5–8 s | 4.0–6.0 s |
| Very Bad | >8 s | >6.0 s |

### 6.3 Eccentric tempo

| Tier | Conventional (return to floor) | RDL (hinge down) |
|---|---|---|
| Very Good | Controlled 1.5–3 s with bar contact on legs; or training-deliberate drop | 2–4 s controlled descent |
| Good | 1.0–1.5 s | 1.5–2.0 s or 4–5 s |
| Yellow Flag | Bar dropped from lockout (touch-and-go with bounce) | 1.0–1.5 s (rushed) |
| Bad | Dropped from above hip with no control | <1 s (free-fall) |
| Very Bad | Dropped from lockout with body collapse | Bar slams thighs, lumbar flexion on descent |

### 6.4 Lockout hold quality

| Tier | Both lifts |
|---|---|
| Very Good | ≥0.5 s stable lockout, glutes squeezed, no hyperextension, no soft knees |
| Good | 0.3–0.5 s stable |
| Yellow Flag | <0.3 s; momentary lockout before descent |
| Bad | Lockout not held (immediate descent); or knees re-bend before descent |
| Very Bad | Lockout never reached / leg-tremor / lean-back to claim lockout |

### 6.5 Rep-to-rep consistency

Coefficient of variation (CV) across torso angle peak, hip angle at lockout, and bar-path drift.

| Tier | Both lifts |
|---|---|
| Very Good | CV < 5% on all key metrics |
| Good | 5%–8% |
| Yellow Flag | 8%–12% |
| Bad | 12%–18% |
| Very Bad | >18% (form drifts visibly through the set) |

### 6.6 Bar speed / sticking points

Mean concentric velocity (MCV) of the bar.

| Tier | Conventional (working sets, ~60–85% 1RM) |
|---|---|
| Very Good | MCV ≥ 0.5 m/s, single smooth velocity peak |
| Good | MCV 0.4–0.5 m/s |
| Yellow Flag | MCV 0.3–0.4 m/s; sticking-point <30% slowdown |
| Bad | MCV 0.2–0.3 m/s; sticking-point 30–60% slowdown |
| Very Bad | MCV <0.2 m/s; sticking-point >60% slowdown or velocity reaches zero mid-rep (true grinder) |

---

## 7. Composite Scoring System

### 7.1 Step 1 — Raw metric → 0–100 sub-score

Linearly interpolate within tier bands:
- Very Good → 90–100
- Good → 75–89
- Yellow Flag → 60–74
- Bad → 40–59
- Very Bad → 0–39

Worked sub-step (torso angle at start, conventional): if measured = 28° (Very Good 20–35° band), distance from band centre 27.5° = 0.5°; map to ≈ 95.

For two-sided bands ("X°–Y° or A°–B°"), interpolate against the closest in-band edge. Apply asymmetric penalties where one side is clinically worse (lean-back at lockout is worse than forward lean).

### 7.2 Step 2 — Category weights

| Category | Weight | Rationale |
|---|---|---|
| **Safety** | **50%** | Cholewicki et al. (Med Sci Sports Exerc 23(10):1179–1186, 1991) estimated L4/L5 compressive loads up to 17,192 N and L4/L5 net moments up to 1,071 N·m during 1RM deadlift in male powerlifters — the deadlift's primary injury risk profile is lumbar |
| Technique | 35% | Defines efficient, repeatable execution |
| Performance | 15% | Velocity / consistency / tempo (only meaningful once safety and technique pass) |

#### 7.2.1 Safety metric weights (sum to 100 within category)

| Metric | Conventional | RDL |
|---|:---:|:---:|
| Lumbar flexion / rounding | 30 | 35 |
| Thoracic spine position | 10 | 12 |
| Hip extension at lockout (hyperextension cap) | 12 | 12 |
| Spinal lateral deviation (posterior) | 10 | 10 |
| Knee valgus / FPPA | 10 | 8 |
| Hip–shoulder timing ("stripper") | 13 | — (re-allocate to lumbar) |
| Bar drift away from body | 10 | 13 |
| Heel contact | 5 | 5 |
| Lateral hip shift | — | 5 |

#### 7.2.2 Technique metric weights (sum to 100)

| Metric | Conventional | RDL |
|---|:---:|:---:|
| Torso angle at start / bottom | 15 | 18 |
| Knee flexion at start / RDL constant bend | 12 | 15 |
| Shin angle (conventional only) | 8 | — |
| Bar-to-thigh proximity | 15 | 18 |
| Bar path deviation | 12 | 10 |
| Neck/head position | 4 | 4 |
| Stance width | 8 | 8 |
| Foot/toe angle | 5 | 5 |
| Grip width | 5 | 6 |
| Symmetry of pull (L/R) | 8 | 8 |
| Bar tilt | 5 | 5 |
| Range of motion (RDL only) | — | 3 |
| Knee extension at lockout | 3 | — |

#### 7.2.3 Performance metric weights (sum to 100)

| Metric | Conventional | RDL |
|---|:---:|:---:|
| Concentric tempo / bar speed | 30 | 25 |
| Eccentric tempo / control | 20 | 35 |
| Setup time / pre-pull tension | 15 | 10 |
| Lockout hold quality | 15 | 15 |
| Rep-to-rep consistency | 20 | 15 |

### 7.3 Step 3 — Composite computation

Category sub-score: **S_cat = Σ (w_metric × score_metric) / 100**

Overall composite (weighted arithmetic mean, default):

  **Composite = 0.50 · S_safety + 0.35 · S_technique + 0.15 · S_performance**

Geometric-mean alternative (penalises any one-category collapse harder):

  **Composite_geo = S_safety^0.50 · S_technique^0.35 · S_performance^0.15**

Use geometric mean for safety-critical screening (rehab return-to-lift, novice triage); arithmetic mean for general training feedback.

### 7.4 Step 4 — Hard-fail safety overrides

Each override caps the composite regardless of other scores.

| Override condition | Composite cap |
|---|---|
| Visible lumbar rounding (deviation >20° from neutral; §3.10 Very Bad) | **40** (D / Bad) |
| Progressive lumbar worsening across the set | **30** (E / Very Bad) |
| Bar drift away from body in Very Bad band (>9% of height) | **45** |
| Hip–shoulder timing R > 2.2 (stripper) for conventional | **45** |
| Hyperextension at lockout >15° backward lean | **50** |
| Knee valgus FPPA >22° at any frame | **50** |
| Heel lift sustained >500 ms during loaded portion | **55** |
| Pull asymmetry >18° L/R | **55** |
| Bar drop from above hip with body collapse (no controlled descent) | **45** |
| Composite spinal lateral deviation + bar tilt both in Bad+ tiers | **50** |

If multiple overrides trigger, the lowest cap applies. Override engagement is **always surfaced** to the user with the triggering metric named.

### 7.5 Step 5 — Per-set aggregation

For an N-rep set:
- **Mean**: average composite across reps (default).
- **Worst**: minimum composite (safety screening).
- **Last-3**: average composite of the final 3 reps (fatigue-resistance).

Recommended display: all three; flag any rep falling >15 points below the set mean as a "deteriorating rep."

---

## 8. Grade & Label Mapping

| Composite | Letter | Label |
|---|:---:|---|
| 90–100 | A | Very Good |
| 75–89 | B | Good |
| 60–74 | C | Yellow Flag |
| 40–59 | D | Bad |
| 0–39 | E | Very Bad |

---

## 9. Alternative Naming Schemes

| Composite | Traffic light | Sports tier | Coaching | Medical / PT | Risk | Tier list | Belt | Stars | Olympic | Descriptive | Percentile | Academic | Quality |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 90–100 | Green | Elite | Master | Optimal | Safe | S | Black | 5★ | Gold | Pristine | Top 10% | A | Excellent |
| 75–89 | Light Green | Advanced | Skilled | Functional | Cleared | A | Brown | 4★ | Silver | Polished | 70–90 | B | Proficient |
| 60–74 | Yellow | Intermediate | Developing | Compensated | Caution | B | Blue | 3★ | Bronze | Passable | 40–70 | C | Acceptable |
| 40–59 | Orange | Novice | Needs Work | Dysfunctional | Warning | C | Green | 2★ | (none) | Problematic | 15–40 | D | Deficient |
| 0–39 | Red | Beginner | Critical | Pathological | Stop | D | White | 1★ | (none) | Perilous | Bottom 15% | F | Poor |

Additional one-off schemes worth considering: Weather (Sunny / Partly Cloudy / Cloudy / Storm / Severe), Animals (Lion / Wolf / Dog / Cat / Mouse), Heat (Forge / Furnace / Warm / Cool / Frozen).

---

## 10. Worked Example

Lifter performs a single conventional deadlift at ~75% 1RM, captured from sagittal + frontal cameras.

### 10.1 Raw measurements and sub-scores

| Metric | Measured | Tier | Sub-score |
|---|---|---|---|
| Torso angle at start | 22° above horizontal | Very Good (20–35°) | 96 |
| Torso angle at lockout | 3° behind vertical | Yellow Flag (3–7° back) | 70 |
| Bar path deviation | 3.2% lifter height | Good (2–4%) | 82 |
| Bar-to-shin at start | 2 cm | Very Good | 95 |
| Bar-to-thigh proximity | <1 cm contact | Good | 88 |
| Hip–shoulder timing (R) | 1.55 | Yellow Flag (1.3–1.6) | 62 |
| Knee flexion at start | 122° | Very Good (115–130°) | 94 |
| Shin angle | 12° forward of vertical | Very Good (5–15°) | 92 |
| Lumbar flexion deviation | 8° | Yellow Flag (7–12°) | 67 |
| Thoracic position | 8° kyphosis | Good (5–10°) | 80 |
| Neck position | 5° flexion | Very Good | 92 |
| Hip extension at lockout | 178° | Very Good | 95 |
| Knee extension at lockout | 177° | Very Good | 94 |
| Heel contact | 100% | Very Good | 100 |
| Stance width | 95% biacromial | Very Good | 94 |
| Foot angle | 12° | Very Good | 93 |
| Grip width | hands just outside thighs | Very Good | 95 |
| Bar tilt | 3° | Good | 80 |
| Lateral hip shift | 4% | Good | 80 |
| Knee FPPA | 7° | Good | 81 |
| Symmetry of pull | 60 ms / 3° | Good | 82 |
| Spinal lateral dev. | 2.5% | Good | 85 |
| Shoulder symmetry | 3° | Good | 82 |
| Hip symmetry | 3° | Good | 82 |
| Setup time | 3 s | Very Good | 95 |
| Concentric tempo | 2.0 s | Very Good | 93 |
| Eccentric tempo | controlled drop | Good | 80 |
| Lockout hold | 0.4 s | Good | 82 |
| Consistency | n/a single rep — default 80 | — | 80 |
| Bar speed (MCV) | 0.45 m/s | Good | 80 |

### 10.2 Category sub-scores

**Safety (conventional weights):**
- Lumbar (30 × 67)/100 = 20.1
- Thoracic (10 × 80)/100 = 8.0
- Hip ext at lockout (12 × 95)/100 = 11.4
- Spinal lat dev (10 × 85)/100 = 8.5
- Knee valgus (10 × 81)/100 = 8.1
- Hip–shoulder timing (13 × 62)/100 = 8.06
- Bar drift (10 × 82)/100 = 8.2
- Heel contact (5 × 100)/100 = 5.0
- **S_safety = 77.4**

**Technique:**
- Torso start (15 × 96)/100 = 14.4
- Knee flexion start (12 × 94)/100 = 11.3
- Shin angle (8 × 92)/100 = 7.4
- Bar-thigh prox (15 × 88)/100 = 13.2
- Bar path (12 × 82)/100 = 9.8
- Neck (4 × 92)/100 = 3.7
- Stance (8 × 94)/100 = 7.5
- Foot angle (5 × 93)/100 = 4.7
- Grip (5 × 95)/100 = 4.8
- Symmetry (8 × 82)/100 = 6.6
- Bar tilt (5 × 80)/100 = 4.0
- Knee ext lockout (3 × 94)/100 = 2.8
- **S_technique = 90.2**

**Performance:**
- Concentric (30 × 93)/100 = 27.9
- Eccentric (20 × 80)/100 = 16.0
- Setup (15 × 95)/100 = 14.25
- Lockout hold (15 × 82)/100 = 12.3
- Consistency (20 × 80)/100 = 16.0
- **S_performance = 86.5**

### 10.3 Composite

Composite = 0.50 × 77.4 + 0.35 × 90.2 + 0.15 × 86.5
       = 38.7 + 31.57 + 12.98
       = **83.3**

Geometric: 77.4^0.50 × 90.2^0.35 × 86.5^0.15 ≈ **84.0**

### 10.4 Override checks

- Lumbar = Yellow Flag, not Very Bad → no override
- Bar drift = Good → no override
- Hip–shoulder R = 1.55 (Yellow) → no override
- Lockout lean = 3° back (Yellow) → no override
- FPPA = 7° → no override

**Final composite = 83.3 → Grade B (Good / Polished / Silver / Cleared).**

### 10.5 Two lowest sub-scores (feedback)

1. **Hip–shoulder timing (62)** — "Hips are rising ~1.5× faster than shoulders out of the floor. Focus on leg-driving the floor away rather than hinging early. Consider lowering the hips ~5 cm in setup and re-engaging the quads on the lift-off cue."
2. **Lumbar flexion deviation (67)** — "Mild visible rounding in the upper lumbar region. Reset cues: chest up, brace harder before pulling slack out; consider dropping intensity ~10% for one session to re-pattern."

---

## 11. Practical Notes & Caveats

### 11.1 Anthropometry effects

- **Long-femur / short-torso lifters** sit with hips higher and torso more horizontal. Conventional thresholds in §3.1 should be widened by ~10° on the horizontal-tolerance side for these lifters; alternatively, recommend sumo or hex-bar variant.
- **Short-femur / long-torso lifters** can pull with hips deep and torso closer to vertical (40°–50° above horizontal). They naturally sit *inside* the Very Good range.
- **Long arms** lower the starting torso angle (you can stand more upright). Do not penalise a lifter for being more vertical than average if hip and knee angles still meet the criteria.
- **Hip-socket depth and acetabular orientation** vary individually; foot angle and stance width are highly personal — apply §4.2 thresholds as guidelines, not absolutes.

### 11.2 Continuous tracking vs single-frame

Sample at the camera frame rate (60+ fps) and report each metric (a) at the canonical event frame (liftoff, knee-pass, lockout) **and** (b) the worst value across the rep. For lumbar flexion, hip–shoulder timing, and knee valgus, always use worst-case.

### 11.3 Calibration

Place a known-length object (a 45 cm Olympic plate edge-on) in the calibration frame to convert pixel distances to cm. Without calibration, all distance thresholds default to "% of lifter height" or "% of inter-landmark reference," which is unit-free but less interpretable.

### 11.4 Always surface the reason behind the grade

The user-facing report must always state:
- Composite score and grade
- Override (if any) triggered
- The two lowest sub-scores in plain language
- A specific corrective cue tied to those sub-scores

Never display the composite alone.

### 11.5 Style-specific scoring

**Never apply conventional thresholds to RDL.** Lift selection must be specified at the start of the session, and the threshold tables in §§3–6 switched accordingly. RDL must not be penalised for shallow knee flexion at "start"; conventional must not be penalised for substantial knee flexion. Hip–shoulder timing (§3.6) is conventional-only.

### 11.6 Minimum-viable metric priority list

If compute or camera setup is constrained, retain in this order:

1. Lumbar flexion / rounding (safety #1)
2. Bar path deviation
3. Hip–shoulder timing (conventional only)
4. Torso angle at start
5. Hip extension at lockout (hyperextension cap)
6. Knee flexion at start (conventional) / constant knee bend (RDL)
7. Bar-to-thigh proximity
8. Knee valgus / FPPA
9. Concentric tempo / bar speed
10. Stance width

Anything below this is "nice-to-have." A working assessment with #1–#7 covers most clinical and coaching value.

### 11.7 Frame-rate tradeoffs

- 30 fps → coarse hip–shoulder timing (±33 ms resolution); workable for technique but unreliable for stripper detection at the boundary.
- 60 fps → adequate for all metrics including timing.
- 120 fps → necessary only for bar-speed/velocity analysis at maximal loads or for sticking-point profiling.

---

## 12. MediaPipe Pose Implementation Guide

### 12.1 MediaPipe Pose landmark reference

The MediaPipe Pose Landmarker outputs 33 landmarks per frame.

| Idx | Name | Idx | Name | Idx | Name |
|---|---|---|---|---|---|
| 0 | NOSE | 11 | LEFT_SHOULDER | 22 | RIGHT_THUMB |
| 1 | LEFT_EYE_INNER | 12 | RIGHT_SHOULDER | 23 | LEFT_HIP |
| 2 | LEFT_EYE | 13 | LEFT_ELBOW | 24 | RIGHT_HIP |
| 3 | LEFT_EYE_OUTER | 14 | RIGHT_ELBOW | 25 | LEFT_KNEE |
| 4 | RIGHT_EYE_INNER | 15 | LEFT_WRIST | 26 | RIGHT_KNEE |
| 5 | RIGHT_EYE | 16 | RIGHT_WRIST | 27 | LEFT_ANKLE |
| 6 | RIGHT_EYE_OUTER | 17 | LEFT_PINKY | 28 | RIGHT_ANKLE |
| 7 | LEFT_EAR | 18 | RIGHT_PINKY | 29 | LEFT_HEEL |
| 8 | RIGHT_EAR | 19 | LEFT_INDEX | 30 | RIGHT_HEEL |
| 9 | MOUTH_LEFT | 20 | RIGHT_INDEX | 31 | LEFT_FOOT_INDEX |
| 10 | MOUTH_RIGHT | 21 | LEFT_THUMB | 32 | RIGHT_FOOT_INDEX |

**Deadlift-relevant landmarks (highlighted):**
- Shoulders: 11, 12 (torso top)
- Elbows: 13, 14 (arm-hang check; not critical)
- **Wrists: 15, 16 — the bar proxy** (hands grip the bar, so wrist centre is the closest reliable bar position estimate)
- Hips: 23, 24
- Knees: 25, 26
- Ankles: 27, 28
- Heels: 29, 30
- Foot indexes: 31, 32

**Image vs world landmarks (from official MediaPipe documentation):**
- `pose_landmarks` (image landmarks): normalised x,y ∈ [0,1] relative to image width/height; z is depth relative to the hip midpoint, also normalised. Useful for 2D overlay and pixel-based metrics.
- `pose_world_landmarks` (POSE_WORLD_LANDMARKS): x,y,z in **metres**, with origin at the midpoint of the hips. The MediaPipe documentation states the output contains "both normalized coordinates (Landmarks) and world coordinates (WorldLandmarks) for each landmark" with WorldLandmarks expressed in metres relative to the hip-midpoint origin. This is the recommended input for angle computation.

### 12.2 Derived reference points

| Composite point | Formula |
|---|---|
| Hip centre | (LEFT_HIP + RIGHT_HIP) / 2 |
| Shoulder centre | (LEFT_SHOULDER + RIGHT_SHOULDER) / 2 |
| **Wrist centre (bar proxy)** | (LEFT_WRIST + RIGHT_WRIST) / 2 |
| Knee centre | (LEFT_KNEE + RIGHT_KNEE) / 2 |
| Ankle centre | (LEFT_ANKLE + RIGHT_ANKLE) / 2 |
| Heel centre | (LEFT_HEEL + RIGHT_HEEL) / 2 |
| Foot centre | (LEFT_FOOT_INDEX + RIGHT_FOOT_INDEX) / 2 |
| Mid-foot reference | (heel_centre + foot_index_centre) / 2 |
| Torso vector | shoulder_centre − hip_centre |
| Shin vector (one side) | knee − ankle |
| Thigh vector (one side) | hip − knee |
| Foot vector (one side) | foot_index − heel |
| Spine vector | shoulder_centre − hip_centre (same as torso) |
| Vertical reference | (0, 1, 0) in world coords (gravity along +y) |

**Critical deadlift-specific note**: in the squat, the bar sits on the shoulders/upper back, so shoulder centre approximates bar position. **In the deadlift the bar is held in the hands — wrist centre is the only valid bar proxy.** Using shoulder centre for bar path in the deadlift produces systematically wrong drift values.

### 12.3 General computational principles

**Visibility filtering.** Each landmark has a `visibility` ∈ [0,1]. Reject any landmark with visibility < 0.5 for that frame's computation; if a required landmark is rejected, propagate NaN and exclude from temporal aggregation.

**Side selection.** For sagittal-view metrics, select the side closer to the camera based on average z-coordinate of the LEFT vs RIGHT hip/shoulder/ankle group. Use that side's landmarks; mirror indices if RIGHT.

**Coordinate-space choice.** Use **world landmarks** for joint-angle metrics (torso, knee, shin), because they are in metric units and roughly gravity-aligned. Use **image landmarks** for bar-path drift (relative-to-image, unit-free).

**Temporal smoothing.** Apply a Savitzky-Golay filter (window 5, order 2) or 1€ filter to landmark trajectories before computing derivatives (e.g., for hip-shoulder timing).

**Phase detection for deadlift** (based on wrist-centre vertical position W_y(t)):
- **Setup**: W_y ≈ constant near floor (conventional) or near hip (RDL); pre-liftoff frames
- **Liftoff (LO)**: first frame where dW_y/dt > 0 and W_y leaves setup baseline (conventional only)
- **Pull / concentric**: W_y rising
- **Knee-pass (KP)**: W_y crosses knee_y level
- **Lockout**: W_y reaches maximum and dW_y/dt ≈ 0; hip angle ≥ 170° and knee angle ≥ 170°
- **Eccentric**: W_y descending
- **Reset / bottom**: W_y returns to setup baseline (conventional) or hamstring-stretch endpoint (RDL)

For RDL the phase order is: Setup → Eccentric → Bottom → Concentric → Lockout.

**Frame of interest.** Static metrics are evaluated at the canonical event frame; dynamic metrics tracked across the rep and reported worst-case.

**Normalisation.** Report bar-path drift as "% of lifter height," with lifter height = y-distance between foot-midpoint and nose at the standing-upright start; fallback to torso length × 2.5.

**2D vs 3D.** MediaPipe's image-landmark `z` is depth only and not gravity-aligned; world landmarks are. Use world landmarks for angles; 2D image landmarks suffice for purely sagittal-projection metrics when the camera is well-positioned. Bar-tilt (frontal) requires 2D processing of the frontal-camera frame.

### 12.4 Foundational math operations

```text
# Angle between two vectors u and v, in degrees
angle(u, v) = degrees( acos( clamp( (u·v) / (|u|·|v|), -1, 1 ) ) )

# Angle of vector v from vertical reference (0, 1, 0) in 2D sagittal (x, y):
angle_from_vertical(v) = degrees( atan2( v.x, v.y ) )

# Three-point joint angle at point B with neighbours A and C:
joint_angle(A, B, C) = angle(A - B, C - B)
# (e.g., knee angle = joint_angle(HIP, KNEE, ANKLE))

# Signed lateral deviation of point P from line through P1, P2 (frontal view):
signed_lat(P, P1, P2) = cross_z( (P2 - P1), (P - P1) ) / |P2 - P1|

# Euclidean distance between landmarks p1 and p2:
dist(p1, p2) = sqrt( (p1.x - p2.x)^2 + (p1.y - p2.y)^2 + (p1.z - p2.z)^2 )
```

### 12.5 Per-metric computation guide

For each metric: **L** = landmarks used, **V** = vectors formed, **C** = computation, **T** = temporal tracking, **Caveats**.

#### 12.5.1 Torso angle at start
- L: 11/12, 23/24
- V: torso = shoulder_centre − hip_centre
- C: torso_angle_horizontal = 90° − angle_from_vertical(torso)
- T: LO frame (conventional) or bottom-of-eccentric frame (RDL)
- Caveats: requires gravity-aligned coords; verify with a standing-upright calibration frame.

#### 12.5.2 Torso angle at lockout
- L: 11/12, 23/24
- C: angle from vertical (positive = forward lean, negative = backward = hyperextension)
- T: lockout frame
- Caveats: needs the world-landmark frame for true vertical reference.

#### 12.5.3 Bar path deviation (wrist-centre proxy)
- L: 15, 16, 27/28, 31/32
- C: drift_x(t) = wrist_centre.x(t) − mid_foot.x(t_start). max_drift = max |drift_x|; normalise by lifter_height.
- T: every frame; report max
- Caveats: hands rotate slightly around the bar during the lift; wrist landmark is offset from the bar by hand thickness (~3–5 cm). For comparative scoring this is acceptable; for absolute bar metrics, train a YOLO-style bar detector alongside.

#### 12.5.4 Bar-to-shin distance at start (conventional)
- L: 15/16, 25/26, 27/28, 31/32
- C: at LO frame, distance_x = wrist_centre.x − shin.x at bar height (linear interp from knee/ankle)
- T: single LO frame
- Caveats: ~3 cm of systematic error from wrist offset; threshold bands accommodate this.

#### 12.5.5 Bar-to-thigh proximity throughout pull
- L: 15/16, 23/24, 25/26
- C: at each frame, closest distance from wrist_centre to thigh segment (hip→knee)
- T: track min/max
- Caveats: use world landmarks for true 3D distance.

#### 12.5.6 Hip–shoulder timing ("stripper deadlift" detector)
- L: 11/12, 23/24
- V: hip_centre.y(t), shoulder_centre.y(t)
- C: compute dHip_y/dt and dShoulder_y/dt via finite differences over 100 ms post-LO. R = (dHip_y/dt) / (dShoulder_y/dt). R > 1 means hips rising faster.
- T: window = first 100 ms post-LO
- Caveats: smoothing essential; sign convention — y decreases as lifter rises in image coords, so flip sign explicitly. Conventional only — RDL has no liftoff phase.

#### 12.5.7 Lumbar flexion approximation
- L: 11/12, 23/24, 25/26
- V: torso vector at start frame (reference), torso vector at frame t
- C: MediaPipe cannot resolve the lumbar spine. Compute the shoulder-hip-knee joint angle (SHK) at the start frame as reference; at each subsequent frame, Δ_SHK = SHK(t) − SHK(reference). Increased lumbar flexion manifests as decreasing SHK; use −Δ_SHK as lumbar-flexion proxy.
- T: track worst Δ_SHK
- Caveats: approximation only. Vigotsky et al. (PeerJ 3:e708, 2015) found 28° lumbar flexion at peak hip flexion (95% CI = 26–29°) in trained males during the good morning at 50% 1RM, with no significant change up to 90% 1RM — so non-zero lumbar flexion is the norm; the metric flags *progressive worsening under load*. Posterior-camera pairing helps but MediaPipe's 11-12 vs 23-24 span is vertebrally non-specific.

#### 12.5.8 Knee flexion angle at start
- L: 23, 25, 27 (or right side)
- C: knee_angle = joint_angle(hip, knee, ankle) (180° = straight)
- T: LO frame
- Caveats: camera-near side; visibility filter.

#### 12.5.9 Knee flexion at bottom of RDL
- Same landmarks and computation as 12.5.8
- T: evaluate at bottom-of-eccentric frame (W_y minimum)

#### 12.5.10 Shin angle from vertical
- L: 25/26, 27/28
- V: shin = knee − ankle
- C: angle_from_vertical(shin)
- T: LO frame (conventional)
- Caveats: world landmarks; gravity reference.

#### 12.5.11 Hip extension at lockout
- L: 11, 23, 25
- C: hip_angle = joint_angle(shoulder, hip, knee)
- T: lockout frame
- Caveats: hyperextension shows as >180°.

#### 12.5.12 Knee extension at lockout
- L: 23, 25, 27
- C: knee_angle (180° = straight)
- T: lockout frame.

#### 12.5.13 Heel contact
- L: 29/30, 31/32
- V: heel_y(t) vs floor_ref = min heel_y across rep
- C: heel_lift(t) = heel_y(t) − floor_ref; flag lift > 1.5 cm. Compute fraction of rep with heel up.
- T: continuous
- Caveats: small detection errors ~1 cm; use 1.5 cm threshold.

#### 12.5.14 Range of motion for RDL
- L: 15/16
- C: ROM = W_y_max − W_y_min (metres via world landmarks)
- T: across full rep.

#### 12.5.15 Stance width
- L: 27/28, 11/12 (frontal view)
- C: stance_x = |left_ankle.x − right_ankle.x|; biacromial_x = |left_shoulder.x − right_shoulder.x|; ratio = stance_x / biacromial_x.
- Caveats: frontal camera only.

#### 12.5.16 Foot / toe-out angle
- L: 29, 31 (one side at a time)
- V: foot_vector = foot_index − heel
- C: angle from forward direction in top-down projection
- T: start frame
- Caveats: foot-index landmark is noisy — smooth across the setup period.

#### 12.5.17 Grip width
- L: 15, 16
- C: |left_wrist.x − right_wrist.x| at start frame; report cm and relative to biacromial.

#### 12.5.18 Lateral hip shift
- L: 23/24, 27/28
- C: hip_centre.x(t) relative to ankle_centre.x; report max shift / stance_width.
- T: across rep, frontal camera.

#### 12.5.19 Bar tilt
- L: 15, 16
- C: angle = degrees(atan2(left_wrist.y − right_wrist.y, left_wrist.x − right_wrist.x)) — frontal view
- T: track throughout rep; report max |tilt|.

#### 12.5.20 Knee tracking / FPPA
- L: 23, 25, 27 (one side)
- C: FPPA = signed_lat(knee, hip, ankle) projected onto frontal plane; report degrees
- Caveats: per-side; report worst.

#### 12.5.21 Spinal lateral deviation (posterior)
- L: 11/12, 23/24, posterior view
- C: lateral midline = vertical through hip centre; track max lateral offset of shoulder centre.

#### 12.5.22 Shoulder symmetry
- L: 11, 12
- C: angle from horizontal; |angle| reported across the rep.

#### 12.5.23 Tempo metrics
- L: 15/16 → W_y(t)
- C: LO_time = first frame dW_y/dt > 0; lockout_time = frame at max W_y. Concentric = lockout_time − LO_time. Eccentric symmetrically.
- T: frame-indexed; convert to seconds via frame rate.

#### 12.5.24 Consistency
- Per-rep composite; CV% = std/mean across reps in the set.

### 12.6 Sample pipeline (conceptual flow)

```
[1] Capture video (sagittal + frontal) → write to file
[2] Per-frame: MediaPipe Pose Landmarker
    → image_landmarks (33×3 with visibility)
    → world_landmarks (33×3 in metres)
[3] Smooth landmark trajectories (Savitzky-Golay or 1€)
[4] Detect side closer to sagittal camera (z-mean comparison)
[5] Compute W_y(t) from wrist centre
    (image landmarks for frontal-view bar-tilt; world landmarks for sagittal bar-path)
[6] Phase detection:
    - Identify setup, LO, KP, lockout, eccentric-end frames
[7] Compute per-metric values:
    - Static metrics at canonical frames
    - Dynamic metrics across the rep (min/max)
[8] Apply visibility mask
[9] Map raw values → sub-scores (0–100) via linear interpolation
[10] Apply category weights → S_safety, S_technique, S_performance
[11] Composite = 0.50·S_safety + 0.35·S_technique + 0.15·S_performance
[12] Apply hard-fail overrides; cap composite as needed
[13] Aggregate per-set (mean / worst / last-3)
[14] Surface grade + two lowest sub-scores + corrective cues
[15] Render annotated video overlay (optional): joint angles, bar-path trace, override flags
```

### 12.7 Known limitations of MediaPipe for deadlift assessment

1. **No bar detection.** MediaPipe tracks the human only; the bar is inferred from wrist landmarks, which carry a 3–5 cm systematic offset from the true bar. Acceptable for comparative scoring; for absolute bar metrics, train a YOLO-style bar detector (see Ko et al. 2024, IEEE Access, which combines YOLOv5 + MediaPipe in a powerlifting form-check system).
2. **No lumbar spine tracking.** The single most consequential limitation, because the lumbar spine is the highest-risk structure. The shoulder-hip-knee deviation proxy (§12.5.7) can detect catastrophic rounding but not subtle changes. Markerless 3D pose-estimation accuracy is bounded by what is published: Mercadal-Baudart et al. (Heliyon 10(6):e27596, 2024, Trinity College Dublin) validated their 3D pose model against VICON motion capture and reported root mean square angle errors "within 10°" for shin angle, knee varus/valgus, hip flexion, trunk angle, and spinal flexion across squats and deadlifts, with errors up to 15° only for shoulder flexion and ASIS asymmetry in front squats and drop-jumps. Lumbar-flexion scoring must therefore use conservative (wide) bands and be supplemented by human review in high-stakes contexts.
3. **Limited 3D accuracy.** World landmarks are estimates; depth resolution is the weakest dimension. Sagittal-plane angles (the deadlift's primary plane) are most reliable; frontal-plane metrics (valgus, lateral shift) are less reliable.
4. **Occlusion sensitivity.** The bar and plates occlude the lifter's hips and wrists from the sagittal view, especially at the bottom. A 2026 clinical validation study (Healthcare, MDPI 14(4):482) using MediaPipe Pose across a 30-participant independent validation cohort reported **96.4% baseline pose accuracy for the deadlift** with a **−4.3% occlusion effect during torso blockage (ICC = 0.89 vs. expert assessment)**.
5. **Frame-rate dependence.** Stripper-detection requires ≥60 fps; the pose model itself runs at 24–30 FPS on a 13th-Gen Intel Core i7-1355U CPU per the SiriwanIm et al. (GitHub, 2024) deadlift-correction system, while Google's own BlazePose benchmark (Bazarevsky et al., CV4ARVR @ CVPR 2020) reports up to 31 FPS on a Pixel 2 (Lite model, ≤6.9 MFLOPs). Adequate hardware (modern desktop GPU or M-series Apple silicon) sustains 60 fps capture.
6. **No load awareness.** MediaPipe cannot see the plates or read the weight. The user must input intensity, or the system must infer from bar speed (lower MCV → likely higher %1RM).
7. **Calibration drift.** Without a known-length reference, distance metrics are unit-free. If the camera position changes between sets, calibration must be re-acquired. Place a 45 cm Olympic plate edge-on at the back of the platform every session.

---

## 13. Appendix — Metric Summary Table

| # | Metric | Primary view | Type | Default weight (within category) | Conv | RDL |
|---|---|---|---|---|:---:|:---:|
| 1 | Torso angle at start | Sagittal | Continuous | Technique 15/18 | ✓ | ✓ |
| 2 | Torso angle at lockout | Sagittal | Continuous | — (override-gated) | ✓ | ✓ |
| 3 | Bar path deviation | Sagittal | Continuous | Tech 12/10 | ✓ | ✓ |
| 4 | Bar-to-shin at start | Sagittal | Continuous | Tech 8/— | ✓ | — |
| 5 | Bar-to-thigh proximity | Sagittal | Continuous | Tech 15/18 | ✓ | ✓ |
| 6 | Hip–shoulder timing | Sagittal | Continuous | Safety 13/— | ✓ | — |
| 7 | Knee flexion at start | Sagittal | Continuous | Tech 12/— | ✓ | — |
| 8 | Knee flexion (RDL constant) | Sagittal | Continuous | —/15 | — | ✓ |
| 9 | Shin angle | Sagittal | Continuous | Tech 8/— | ✓ | — |
| 10 | Lumbar flexion proxy | Sagittal | Continuous | Safety 30/35 | ✓ | ✓ |
| 11 | Thoracic position | Sagittal | Continuous | Safety 10/12 | ✓ | ✓ |
| 12 | Neck / head | Sagittal | Continuous | Tech 4/4 | ✓ | ✓ |
| 13 | Hip extension at lockout | Sagittal | Continuous | Safety 12/12 | ✓ | ✓ |
| 14 | Knee extension at lockout | Sagittal | Continuous | Tech 3/— | ✓ | ✓ |
| 15 | Heel contact | Sagittal | Continuous (% time) | Safety 5/5 | ✓ | ✓ |
| 16 | RDL bottom ROM | Sagittal | Continuous | Tech —/3 | — | ✓ |
| 17 | Stance width | Frontal | Continuous (ratio) | Tech 8/8 | ✓ | ✓ |
| 18 | Foot / toe angle | Frontal | Continuous | Tech 5/5 | ✓ | ✓ |
| 19 | Grip width | Frontal | Continuous | Tech 5/6 | ✓ | ✓ |
| 20 | Bar tilt | Frontal/Posterior | Continuous | Tech 5/5 | ✓ | ✓ |
| 21 | Lateral hip shift | Frontal | Continuous | Safety —/5 | ✓ | ✓ |
| 22 | Knee valgus / FPPA | Frontal | Continuous | Safety 10/8 | ✓ | ✓ |
| 23 | Pull symmetry | Frontal | Two-sided | Tech 8/8 | ✓ | ✓ |
| 24 | Spinal lateral deviation | Posterior | Continuous | Safety 10/10 | ✓ | ✓ |
| 25 | Shoulder symmetry | Posterior | Continuous | (within symmetry) | ✓ | ✓ |
| 26 | Hip symmetry | Posterior | Continuous | (within symmetry) | ✓ | ✓ |
| 27 | Setup time / pre-pull tension | Sagittal | Continuous (s) | Perf 15/10 | ✓ | ✓ |
| 28 | Concentric tempo | Sagittal | Continuous (s) | Perf 30/25 | ✓ | ✓ |
| 29 | Eccentric tempo | Sagittal | Continuous (s) | Perf 20/35 | ✓ | ✓ |
| 30 | Lockout hold quality | Sagittal | Continuous (s) | Perf 15/15 | ✓ | ✓ |
| 31 | Rep-to-rep consistency | Multi-rep | CV% | Perf 20/15 | ✓ | ✓ |
| 32 | Bar speed (MCV) | Sagittal | Continuous (m/s) | (within concentric tempo) | ✓ | ✓ |

Category overall weights: **Safety 50%, Technique 35%, Performance 15%.**

---

*End of document.*