# Athlete Strength Assessment — AI Technical Specification

Complete measurement protocol for computer-vision-based strength scoring on 5 compound lifts. Built to slot into the same 4-screen flow as your Mobility Analyser:

1. **Exercises screen** — grid of 5 cards (mirrors your "10 Exercises" page)
2. **Upload + details screen** — reference library, checklist, calibration, per-side video slots (mirrors Knee-to-Wall)
3. **Per-exercise report** — score, skeleton overlay reps, per-rep breakdown, all-metrics table, bar-path/radar chart, coaching cues (mirrors Seated Hip Rotation report)
4. **Final dashboard** — overall strength grade, "exercises to work on", tips, all 5 reports (mirrors Mobility Dashboard)

Use **MediaPipe Pose (BlazePose, 33 landmarks)** for skeleton tracking + **OpenCV (KCF or MOSSE tracker)** for barbell-plate tracking. All angles in degrees; distances in cm via calibration.

### Strength Analyser vs Mobility Analyser at a glance

| Aspect | Mobility Analyser | Strength Analyser |
|---|---|---|
| Number of exercises | 10 | 5 |
| Primary tracked objects | Body landmarks only | Body landmarks + barbell (OpenCV) |
| Load type | Bodyweight only | Barbell + bodyweight alternatives |
| Key metrics | Range of motion, symmetry, compensation | Joint angles, load tracking, bar velocity, rep count, form quality |
| Critical safety flags | Heel lift, valgus | Lumbar flexion, excessive layback, elbow flare, bar path drift |
| RM / rep type | Not applicable | 3RM / 5RM / 10RM / max reps / bodyweight |
| Barbell detection | Not used | Required for 3 of 5 lifts (Squat, Deadlift, Bench, OHP) |
| Output focus | Mobility restriction identification | Strength proficiency + form quality + injury risk |

### Universal classification cutoffs (apply to every exercise score)
- **GOOD:** 90–100
- **NEEDS IMPROVEMENT:** 70–89
- **RESTRICTED:** < 70

---

## Rules for the user (first-page display, mirrors mobility rules)

- Film in a well-lit space; plain wall behind the rack helps plate-tracking accuracy
- Phone on a **tripod** at the **specified height** for each exercise — never handheld (research shows handheld kills bar-path accuracy)
- Wear **fitted clothing** so hips, knees, shoulders are clearly visible (baggy hoodies destroy hip/spine landmark detection)
- **Calibration object in frame.** Primary: standard circular plates (auto-detected — plate diameter is the px/cm reference). Fallback: place a **standard A4 paper (21.0 × 29.7 cm)** flat against the wall or on the floor in frame. Without one of these, depth/distance metrics fall back to athlete-height inputs.
- Film at **30 fps minimum** (60 fps preferred for tempo and bar-velocity accuracy)
- Film from the **EXACT camera angle** listed per exercise — wrong angle = inaccurate scoring
- Do the **specified rep count** at the **specified load** (3RM / 5RM / 10RM / bodyweight). The system asks the user to enter the load before analysing so it can compute estimated 1RM and velocity zones
- Side-view exercises: film from the **left side** unless stated otherwise (kept consistent for bar-path direction conventions)
- Frame the **whole body + barbell path** end-to-end (don't crop the bar or the feet)
- For bodyweight alternatives, the same camera rules apply

---

## Why Strength Analyser is harder than Mobility (design implications)

A few realities the mobility analyser doesn't have to handle:

1. **The barbell is a separate object to track.** MediaPipe gives you the body; OpenCV trackers (KCF, MOSSE, or plate-edge detection via Hough circles) give you the bar. Both run together — body landmarks for joint angles, plate centroid for bar path / velocity / displacement.
2. **Self-occlusion is severe.** In bench press, the barbell sits over the chest and obscures shoulders. In squats, a back-bar covers C7. Use the **plate-side view** (camera positioned so plates are clearly visible from the side) — this is the convention used by Metric VBT, Vitruve, and Qwik.
3. **Load matters.** Form at 10RM ≠ form at 3RM. The scoring thresholds must be **load-adjusted** (some compensation is acceptable near a true 3RM).
4. **Estimated 1RM is a derived output** the user will want. Formula: Epley `1RM = weight × (1 + reps/30)` or Brzycki `1RM = weight × 36 / (37 - reps)`. Report both — they diverge above 10 reps. Velocity-based estimation (mean concentric velocity at the last rep) is more accurate near failure but optional for v1.
5. **Muscle activation cannot be measured by vision.** Real EMG is impossible from a camera. What you *can* do is **infer muscle bias** from joint-angle ratios — see the per-exercise "Inferred muscle activation bias" sections below. Be honest with users: label it "estimated dominance" not "EMG".

---

## EXERCISE 1 — Back Squat (or Bodyweight Squat alternative)

**Lift variants the user can select:** High-bar back squat / Low-bar back squat / Front squat / Goblet squat / Bodyweight squat (no equipment).
**Load options:** 3RM / 5RM / 10RM / Bodyweight (user selects + enters load in kg). System tracks reps automatically.

**Camera:** **Side view, 90° to athlete, 2.5–3 m distance, hip height** (waist-level on tripod). Frame must include from above-head to below-feet, with **plate side fully visible**. Film from **left side** by default.
**Optional Camera 2 (Front view, knee height):** for knee valgus (cave) detection — same as your mobility analyser's "Front View (optional)" slot.

**Landmarks tracked:**
- SHOULDER (11/12), HIP (23/24), KNEE (25/26), ANKLE (27/28), HEEL (29/30), FOOT INDEX (31/32), EAR (7/8) for head position
- Plate centroid (OpenCV plate-edge / KCF tracker) for bar path

**Rep Details:** User performs the set (3 / 5 / 10 reps + warmups). Upload **one video per working set**. AI auto-counts reps using hip-Y signal: peak (top) → trough (bottom) → peak = 1 rep.

### MediaPipe / OpenCV Metrics

**Primary metric — Squat depth (hip crease vs knee):**
- Depth ratio = HIP_Y at lowest frame compared to KNEE_Y at the same frame
- GOOD (parallel or below): HIP_Y ≥ KNEE_Y (hip crease at or below top of knee)
- Equivalent knee flexion angle at bottom: ≥ 100° (full squat ~106°, parallel ~86°). [Research: ETH Zurich, unrestricted vs restricted squats]
- Report depth as both: (a) hip-to-knee vertical pixel difference in cm and (b) knee flexion angle

**Primary metric — Knee flexion angle (sagittal):**
- Calculate at HIP–KNEE–ANKLE
- Capture peak flexion (deepest point) for each rep

**Primary metric — Hip flexion angle (sagittal):**
- Calculate at SHOULDER–HIP–KNEE
- Peak hip flexion per rep ~95–100° expected

**Primary metric — Trunk inclination (lean):**
- Angle of SHOULDER → HIP vector relative to **vertical**
- Squat-University biomechanics: low-bar ~45° lean, high-bar ~30°, front squat ~10–15°

**Primary metric — Tibia inclination:**
- Angle of KNEE → ANKLE vector relative to **vertical**

**Derived metric — Trunk–Tibia angle (hip vs knee bias):**
- TTA = Trunk_inclination − Tibia_inclination
- **TTA > +10° → hip-dominant squat** (low-bar pattern; posterior chain bias)
- **TTA < −10° → knee-dominant squat** (front-squat pattern; quad bias)
- **−10° ≤ TTA ≤ +10° → balanced/neutral**
- [Source: IJSPT 2024 Biomechanical Review of the Squat — Straub et al.]

**Compensation metric — Heel lift:**
- HEEL Y-coordinate vs baseline floor contact
- Flag if heel lifts > 1.5 cm at any point in eccentric or concentric

**Compensation metric — Butt wink (posterior pelvic tilt at bottom):**
- Measure angle of HIP_LEFT → HIP_RIGHT line vs horizontal at bottom frame compared to standing baseline
- Pelvic tuck > 8° = butt wink flag

**Compensation metric — Knee valgus (front camera only):**
- Vector HIP → KNEE → ANKLE in frontal plane
- Knee medial deviation from foot axis > 10° = valgus flag (already in your mobility spec for knee-to-wall — same logic applies)

**Compensation metric — Bar drift (low-bar squats specifically):**
- Plate centroid horizontal displacement over mid-foot baseline
- Bar should travel in a **vertical line over mid-foot** (~5 cm tolerance)
- Forward drift > 8 cm = "good morning" failure mode

**Tempo metrics:**
- Eccentric time: peak hip-Y to trough hip-Y
- Concentric time: trough hip-Y back to peak hip-Y
- Target: 2–3 sec eccentric, 1–2 sec concentric (recommended for assessment, not 1RM)
- Flag rushed concentric < 0.5 sec (bouncing)

**Bar velocity (from plate tracking):**
- Mean concentric velocity (MCV) = displacement / time during ascent
- Reference VBT zones: ≥ 1.0 m/s (speed strength), 0.75–1.0 m/s (strength-speed), 0.5–0.75 m/s (max strength), < 0.5 m/s (absolute strength / near 1RM)
- Last-rep MCV is the input to 1RM estimation

**Stability metric — Bar path symmetry (front camera):**
- Plate-left vs plate-right horizontal travel difference
- > 3 cm difference = lateral lean / weak-side compensation

### Scoring thresholds (Back Squat, sagittal view)

| Status | Depth | Trunk lean | Bar path | Compensations |
|---|---|---|---|---|
| **GOOD** | At or below parallel (knee flex ≥ 100°) all reps | Consistent across reps (SD < 5°) | Vertical over mid-foot (< 5 cm drift) | No heel lift, no butt wink, no valgus, smooth tempo |
| **NEEDS IMPROVEMENT** | Above parallel by 5–15° on any rep | Lean changes ≥ 5° between reps (fatigue) | 5–8 cm drift | Minor heel lift (1.5–3 cm) OR mild butt wink (5–10°) OR valgus 5–10° |
| **RESTRICTED** | High squat (knee flex < 90°) | Lean changes > 10° rep-to-rep | > 8 cm drift / good-morning collapse | Heel lift > 3 cm OR butt wink > 10° OR valgus > 10° OR rushed tempo with bounce |

### Per-rep weighted scoring (Back Squat, weighted version)
Combined rep score (0–100) = weighted sum:
- **Depth (35%)** — hip-vs-knee at peak depth
- **Knee alignment (25%)** — valgus deviation from HIP–ANKLE axis (GOOD ≤ 1.5 cm, NEEDS IMPROVEMENT 1.5–3 cm, RESTRICTED > 3 cm)
- **Back angle / trunk lean (20%)** — within expected range for chosen variant
- **Knee travel / ankle dorsiflexion proxy (15%)** — KNEE_X − FOOT_INDEX_X at deepest frame (GOOD ≥ 8 cm, NEEDS IMPROVEMENT 4–7 cm, RESTRICTED < 4 cm)
- **Bar path linearity (5%)** — RMS deviation from vertical line over mid-foot

**Exercise final score** = average of valid rep scores.
**Best rep** = highest combined score (used for "BEST REP" badge on the report screen).

**Bilateral symmetry:** Front camera plate-tilt > 3° between left and right = asymmetry flag.

Additional bilateral checks (when front camera supplied):
- **L vs R depth:** > 2 cm hip-to-knee difference between sides
- **L vs R knee valgus:** > 2° deviation difference from HIP–ANKLE axis
- **L vs R knee travel:** > 2 cm horizontal difference KNEE–TOE

### Additional detections (Squat)

- **Heel lift:** HEEL Y-displacement > 1.5 cm flagged as ankle-mobility limitation
- **Butt wink:** posterior pelvic tilt at bottom — angle change between SHOULDER–HIP line and standing baseline. **> 10° = lumbar flexion compensation flag** (clinically defensible threshold)
- **Breathing / Valsalva:** flag exhalation during eccentric/bottom phase (the Valsalva manoeuvre should be maintained — proxy via chest/abdominal landmark expansion)
- **Knee-cave (front camera, frontal plane):** KNEE medial deviation from HIP–ANKLE axis > 3 cm = **CRITICAL flag** (ACL injury risk indicator)

### Inferred muscle activation bias (Squat)
Computed from Trunk–Tibia angle (TTA) — this is the closest you can get without EMG:
- **Quad-dominant (knee bias):** TTA < −10° → high quadriceps emphasis (front squat / high-bar pattern)
- **Glute/hamstring-dominant (hip bias):** TTA > +10° → posterior chain emphasis (low-bar pattern)
- **Balanced:** −10° ≤ TTA ≤ +10° → equal hip and knee extensor demand

### Per-rep breakdown (display logic, mirrors your Seated Hip Rotation report)
For each rep, save:
- Peak knee flexion (°), peak hip flexion (°), depth ratio
- Trunk lean at peak depth (°)
- Eccentric time (s), concentric time (s), MCV (m/s)
- Compensation flags
- Mark "BEST REP" = highest weighted score (depth + alignment + back angle + travel + bar path)

### Bodyweight Squat alternative (when no barbell)
Same camera, same landmarks, **skip bar-path & VBT metrics**. Use 10–20 reps instead. Scoring focuses on depth, trunk lean, knee valgus, tempo.

**Re-weighted scoring formula (bodyweight version):**
- Depth (40%) + Knee alignment (30%) + Back angle (20%) + Knee travel (10%)
- Useful for athletes without equipment access — your "alternate exercises bodyweight" requirement

---

## EXERCISE 2 — Deadlift (Conventional / Trap-Bar) or Romanian Deadlift Bodyweight Hinge

**Lift variants:** Conventional barbell / Sumo / Trap-bar (hex bar) / Romanian deadlift (RDL) / Bodyweight hip-hinge (alternative).
**Load options:** 3RM / 5RM / 10RM / Bodyweight hinge (for technique-only). Sumo and conventional behave very differently — score them with the same metrics but flag the variant.

**Camera:** **Side view, 90° to athlete, 2.5–3 m distance, hip height**. Plates fully visible. Frame from above-head to floor.
**Optional Camera 2 (45° rear-quarter view):** for spine-curvature shading and lat engagement.

**Landmarks tracked:**
- EAR (7/8), SHOULDER (11/12), HIP (23/24), KNEE (25/26), ANKLE (27/28), WRIST (15/16)
- Plate centroid (OpenCV tracker) for bar path

**Rep Details:** 3 / 5 / 10 reps in one set, one video per working set. AI counts reps via plate Y-displacement.

### MediaPipe / OpenCV Metrics

**Phase detection (state machine):**
- **Setup phase:** athlete static, hands at WRIST level, knees bent. Capture setup angles before the bar leaves the floor.
- **Lifting phase:** plate Y rising. Capture knee and hip extension trajectories.
- **Lock-out phase:** plate at peak Y, knees locked, hips fully extended.
- **Descent phase:** plate Y falling.
[Source: SiriwanIm AI Deadlift system on GitHub uses exactly this state machine.]

**Primary metric — Setup hip and knee angle:**
- Knee angle at HIP–KNEE–ANKLE at the moment the bar breaks the floor
  - Conventional: expected 100–110°
  - Sumo: expected 110–125° (more knee bend, more upright torso)
  - Trap-bar: expected 95–105° (more squat-like)
- Hip angle at SHOULDER–HIP–KNEE at break-from-floor
  - Conventional: 70–90°
  - Sumo: 90–110°
  - Trap-bar: 95–115°

**Primary metric — Spinal neutrality (back rounding detection):**
- Calculate **three-point angle** EAR → mid-SHOULDER → mid-HIP. A straight neutral spine = ~170–180° (close to straight line)
- **Lumbar rounding flag:** if angle drops below 160° at any frame during lifting phase = back rounding
- Track this angle across the **entire concentric phase** — record the minimum angle reached (worst spine position)
- Track separately: **cervical position** = EAR angle relative to vertical. Looking up > 20° from neutral = hyperextension flag

**Primary metric — Bar path (plate tracker):**
- Plate horizontal X-position throughout the lift
- **GOOD: bar travels in a near-vertical line, drifting backward toward the lifter by ≤ 5 cm at lockout** (the bar should naturally come back toward the body)
- **BAD: bar drifts forward > 5 cm** as it leaves the floor = quad-dominant pull, hips shoot up
- Conventional research: bar-to-mid-foot horizontal distance should stay within ~5 cm throughout

**Primary metric — Hip vs knee extension sequence ("hips shoot up" fault):**
- Compute the **ratio of hip extension velocity to knee extension velocity** at the start of the concentric phase
- **GOOD:** hip and knee extend at similar rates (ratio 0.8–1.3)
- **BAD ("stripper deadlift"):** knees extend much faster than hips at start (ratio < 0.5) → bar drags up the shins, then hips have to swing through

**Primary metric — Lockout completion:**
- Hip angle at peak plate Y ≥ 170° (near straight body line)
- Knee angle at peak plate Y ≥ 170°
- Shoulders should be **behind** the bar at lockout (SHOULDER X > plate X by 5–10 cm) for conventional; trap-bar: directly over

**Compensation metric — Hyperextension at lockout:**
- Excessive backward lean (SHOULDER–HIP line angle past vertical) > 10° = lumbar hyperextension flag

**Compensation metric — Bar drift at start:**
- Plate X-displacement in the first 0.3 sec of concentric > 8 cm = bar swinging away from body (lat disengagement)

**Compensation metric — Shoulder protraction (lats not engaged):**
- Angle at HIP–SHOULDER–WRIST during setup. Engaged lats: shoulders pulled back, ~85–95°. Disengaged: shoulders rolled forward, < 80°

**Tempo metrics:**
- Concentric time (floor → lockout): target 1.5–3 sec for assessment reps
- Eccentric time (lockout → floor): target 2–3 sec for controlled descent
- Flag dropped reps (eccentric < 0.5 sec) — common in 1RM testing but NOT in assessment

**Bar velocity:**
- MCV across concentric phase
- Same VBT zones as squat. Deadlift typically lifts at lower MCV than squat at equivalent %1RM

### Variant-specific scoring adjustments

**Conventional deadlift:**
- Expect higher trunk lean at setup (more horizontal torso)
- Hip:knee moment ratio in research is ~3.5:1 → hip-dominant
- Stricter spine-neutrality scoring (highest lumbar load)

**Trap-bar deadlift:**
- More upright torso (~10–15° more vertical than conventional)
- More knee flexion at setup
- Hip:knee moment ratio ~1.8:1 → less hip-dominant, more quad involvement
- [Source: Swinton et al; Stronger by Science]
- Lower expected lumbar load — relax spine-neutrality threshold by 5° vs conventional

**Sumo deadlift:**
- Very upright torso (~30–45° less lean than conventional)
- Hip:knee moment ratio ~1:1
- Wider stance → measure FOOT_INDEX width vs HIP width — sumo: feet ≥ 1.5x hip-width

**RDL (Romanian deadlift) / Bodyweight hinge alternative:**
- Knees stay relatively straight (knee angle stays > 140° throughout)
- Hip flexion deeper than conventional setup
- Bar (or hands, for bodyweight) stays in contact with thighs throughout
- This is your bodyweight alternative — purely hip-hinge pattern assessment

### Scoring thresholds (Deadlift)

| Status | Spine angle | Bar path | Hip/knee sequence | Lockout |
|---|---|---|---|---|
| **GOOD** | Min spine angle ≥ 165° all reps | < 5 cm forward drift | Hip:knee velocity ratio 0.8–1.3 (rate difference < 20%) | Hip ≥ 170°, knee ≥ 170°, no hyperextension |
| **NEEDS IMPROVEMENT** | Min 155–164° on any rep | 5–10 cm drift | Ratio 0.5–0.8 (rate difference 20–35%) | Hip 165–170° (slight short lockout) OR mild hyperextension (10–15°) |
| **RESTRICTED** | < 155° (visible rounding) | > 10 cm drift | Ratio < 0.5 / rate difference > 35% / knees lock before hips reach 50% extension (stiff-legged fault) | Incomplete lockout (hip < 165°) OR hyperextension > 15° |

### Per-rep weighted scoring (Deadlift)
Combined rep score (0–100) = weighted sum:
- **Spinal neutrality (35%)** — highest priority because lumbar flexion is the #1 deadlift injury mechanism
- **Bar positioning at setup (20%)** — bar over mid-foot (± 3 cm GOOD, 3–5 cm NEEDS, > 5 cm RESTRICTED)
- **Hip/knee extension sequencing (20%)** — rate-of-extension differential during pull
- **Lockout completion (15%)** — full hip and knee extension at top, shoulders behind/over hips
- **Bar path verticality (10%)** — RMS X-deviation from mid-foot vertical line

### 🚩 Critical red-flag rule (Deadlift only)
**If detected lumbar flexion exceeds 15° at any frame during the concentric phase:**
1. Invalidate the rep (does not count toward valid rep total)
2. Auto-classify rep as **RESTRICTED** regardless of other metrics
3. Display injury-risk warning in coaching panel
4. Surface as a **clinical referral red flag** on the final dashboard

This rule mirrors how your mobility analyser surfaces "sharp pain / severe restriction" red flags — same UI pattern, surfaced from a different signal source.

**Bilateral symmetry (Deadlift):**

| Symmetry check | Calculation | Warning threshold |
|---|---|---|
| L vs R hip height at start | HIP_Y(L) vs HIP_Y(R) at setup | > 1.5 cm difference |
| L vs R lockout height | HIP_Y at top position | > 2 cm difference |
| L vs R knee travel | Horizontal X displacement of each knee | > 2 cm difference |
| L vs R plate tilt | Plate-end Y left vs right at any frame | > 3° tilt = uneven pull |

Common cause of asymmetry: grip imbalance, hip-shift, or unilateral strength deficit.

### Inferred muscle activation bias (Deadlift)
- **Hip-dominant (glute/hamstring/erector):** Conventional or RDL with TTA > +15° at start, hip:knee velocity ratio > 1.2
- **Quad-dominant:** Trap-bar with TTA < 0° and high knee flexion at setup
- **Balanced:** Sumo deadlift, typically 1:1

---

## EXERCISE 3 — Bench Press (Flat / Incline) or Push-Up Bodyweight Alternative

**Lift variants:** Flat barbell bench / Incline barbell bench (30–45°) / Decline / Push-up (bodyweight alternative).
**Load options:** 3RM / 5RM / 10RM / Push-up (bodyweight).

**Camera:** **Side view, 90° to bench, 2.5 m away, chest height of lifter** (not floor — phone elevated on a stack or low tripod). Plates clearly visible from the side. Film from the **left side** of the bench.
- For incline: same side view, framed to include head + bench + bar arc
- The bench-press is the **hardest to assess via 2D vision** — research notes self-occlusion and that the open-source `pose-estimation-for-powerlifting` project explicitly **excluded** bench because of obstruction issues. Spell this out to users: bar tracker + visible elbow are the key signals.

**Optional Camera 2 (foot-end view, head-down):** captures bar tilt, elbow flare symmetry, hand width.

**Landmarks tracked:**
- SHOULDER (11/12), ELBOW (13/14), WRIST (15/16), HIP (23/24), KNEE (25/26), EAR (7/8)
- Plate centroid + plate edge (OpenCV) for bar path and bar tilt

**Rep Details:** 3 / 5 / 10 reps, one video per set. Rep count from plate Y signal.

### MediaPipe / OpenCV Metrics

**Primary metric — Bar path (sagittal):**
- Plate centroid X and Y across the lift
- A correct bench bar path is **a slight diagonal**: at top, bar is over the shoulders; at bottom, bar touches mid-to-lower chest. The bar moves ~10–15 cm horizontally toward the head as it descends (J-curve)
- Measure: plate-X at top vs plate-X at bottom. Expected: bar moves ~10–15 cm toward feet (athlete's head) on descent
- **Vertical-only bar path** (no horizontal travel) = inefficient; usually means insufficient scapular retraction
- **Bar drifts toward face on press** = triceps weakness / wide grip issue

**Primary metric — Elbow angle at bottom (chest touch):**
- Angle at SHOULDER–ELBOW–WRIST at lowest plate-Y frame
- GOOD: 70–90° (full ROM with bar touching chest)
- < 70° = bar bouncing off chest before full press initiates (or short ROM)
- Lockout: 170–180° at top frame (full extension)

**Primary metric — Elbow flare angle:**
- Angle of HUMERUS (SHOULDER → ELBOW) vector relative to **TORSO (SHOULDER–HIP) longitudinal axis** in the frontal plane (or from a 45° camera)
- GOOD: 30–60° (elbows tucked toward 45° to the torso) — current evidence-based recommendation, lat-engaged
- > 70° (elbows wide, perpendicular to body) = shoulder-impingement risk pattern
- < 25° (elbows pinned to body) = tricep-dominant; OK for close-grip but inefficient for max bench
- Sources: Modern Men's Fitness on lat–bar-path link; ATHLEAN-X 75° cue; consensus 30–45° tuck

**Primary metric — Scapular retraction proxy:**
- Direct measurement is impossible from 2D side view, but indirect proxy:
  - Distance from SHOULDER landmark to bench surface (Y-coordinate of SHOULDER relative to elbow at touch): retracted shoulders sit **lower** (closer to bench), protracted shoulders **rise**
  - Compare SHOULDER Y at top vs bottom — if shoulder Y changes > 2 cm during the press, scapulae are **moving** (not locked in retraction)
  - GOOD: ΔSHOULDER_Y < 2 cm rep-to-rep

**Primary metric — Wrist alignment:**
- Angle at ELBOW–WRIST–KNUCKLE (or use the 19/20 INDEX landmark as a proxy)
- Wrist should be stacked over the elbow at bottom (~170–180°, neutral)
- Hyperextended wrist (< 150°) = bar rolling back in palm = lost force transfer

**Compensation metric — Hip lift off bench:**
- HIP Y-coordinate during press
- GOOD: hips stay on bench (HIP_Y stable within ±1 cm)
- BAD: hips rise > 2 cm during press = arching to "cheat" the lift (illegal in competition, common form fault in training)

**Compensation metric — Bar tilt:**
- Plate-end Y on left vs right (from foot-end Camera 2)
- > 2 cm difference at any point = uneven press (strength asymmetry)

**Compensation metric — Touch-and-bounce:**
- Time at chest = duration plate-Y is at minimum (< 1 cm change for ≥ N frames)
- Bouncing bar off chest < 0.1 sec = bouncing fault
- Paused bench (1+ sec hold) = good control rep

**Tempo metrics:**
- Eccentric: 2–3 sec target
- Pause: ≥ 0.5 sec at chest for a paused-bench protocol; 0 sec for touch-and-go
- Concentric: 0.5–2 sec
- Tempo consistency rep-to-rep — SD < 0.5 sec = stable

**Bar velocity:**
- MCV during the press
- Sticking point detection: minimum velocity point along concentric (typically 1/3 of the way up). Fatigue increases sticking-point depth.

**Bilateral comparison (foot-end view):**
- Plate-left Y vs plate-right Y at each frame
- Asymmetric press = one side reaches lockout before the other → strength imbalance flag

### Incline-specific adjustments
- Bench angle: user inputs (30° / 45° / 60°)
- Expected bar path: more vertical (less J-curve) than flat
- Bar touches **upper chest / clavicle area**, not mid-chest
- Elbow flare angle expected slightly tighter (anterior delt emphasis)

### Push-up alternative (bodyweight)
- Same side-camera setup
- Reps: 10–20 max-effort (or AMRAP at strict form)
- Landmarks: SHOULDER, ELBOW, WRIST, HIP, KNEE, ANKLE
- Metrics: elbow flare (same logic), depth (chest within 5 cm of floor), plank-line integrity (hip sag/pike: HIP angle ≥ 170° between SHOULDER-HIP and HIP-ANKLE — already in your mobility analyser Plank-with-Shoulder-Tap)
- No bar path or VBT possible

### Scoring thresholds (Bench Press)

| Status | Bar path J-curve | Elbow flare | Bottom ROM | Compensations |
|---|---|---|---|---|
| **GOOD** | 8–18 cm horizontal travel | 30–60° all reps | Elbow ≤ 90° (chest touch) | No hip lift, no bar tilt > 1 cm, no bounce |
| **NEEDS IMPROVEMENT** | 3–7 cm OR 18–25 cm | 25–30° or 60–70° | Elbow 90–100° (slight short ROM) | Hip lift 1–2 cm OR bar tilt 1–2 cm OR brief touch (0.1–0.3 sec) |
| **RESTRICTED** | < 3 cm (vertical-only) or > 25 cm (face-bar) | < 25° or > 70° (excessive flare = shoulder impingement risk) | Elbow > 100° (short ROM) | Hip lift > 2 cm OR bar tilt > 2 cm OR bouncing OR uneven lockout |

### Per-rep weighted scoring (Bench Press)
Combined rep score (0–100) = weighted sum:
- **Elbow tuck angle (30%)** — primary shoulder-safety metric
- **Bar touch point on chest (20%)** — bar contacts at sternum level ± 3 cm (GOOD), 3–6 cm offset (NEEDS), > 6 cm (RESTRICTED)
- **Shoulder retraction (20%)** — scapular Y-stability across the rep
- **Leg drive / foot stability (15%)** — HEEL/FOOT_INDEX < 1 cm vertical movement, < 2 cm horizontal slide (GOOD)
- **Bar path consistency (15%)** — natural J-curve, rep-to-rep variance

### 🚩 Special combo red flag (Bench Press)
**If elbow flare > 85° AND bar contact > 5 cm off sternum on the same rep:**
- Surface as **elevated shoulder-injury-risk flag** in the report
- This combination is a known shoulder-impingement pattern (anterior glenohumeral stress with poor leverage) — flag it even if other metrics pass

### Additional detections (Bench Press)
- **Grip width:** WRIST_L − WRIST_R distance normalised by biacromial (SHOULDER-SHOULDER) width. Flag if grip > 2× shoulder width OR < shoulder width.
- **Wrist alignment:** Flag wrist extension > 15° beyond neutral (hand bent behind bar rather than stacked over elbow) — drains force, risks wrist tendinopathy
- **Incline bench adjustment:** For incline, raise the chest touch target to clavicle level and reduce expected elbow flare by 5° (tighter tuck)

**Bilateral symmetry (Bench Press):**

| Symmetry check | Calculation | Warning threshold |
|---|---|---|
| L vs R elbow tuck | ELBOW angle left vs right at chest touch | > 10° difference |
| L vs R grip width | Each SHOULDER → WRIST distance | > 3 cm difference |
| L vs R bar contact height | Bar Y-position relative to each pectoral landmark | > 4 cm (uneven pressing) |

### Inferred muscle activation bias (Bench Press)
- **Pec-dominant:** Wide grip (WRIST-WRIST distance ≥ 1.8× biacromial width), elbows flared 60°+, moderate touch on mid-chest
- **Tricep-dominant:** Narrow grip (≤ 1.3× biacromial), elbows tucked < 35°, faster lockout phase
- **Anterior delt-dominant:** Incline angle > 30° with elbows 45°

### Push-up alternative — re-weighted scoring
For bodyweight push-up:
- **Depth (40%)** — chest within 5 cm of floor at bottom
- **Body alignment (30%)** — plank line ≥ 170° at SHOULDER–HIP–ANKLE, no hip sag or pike
- **Elbow angle / flare (20%)** — same 30–60° tuck logic as bench
- **Tempo (10%)** — 2-sec descent, no rushed reps

---

## EXERCISE 4 — Pull-Up (Strict / Chin-up) — Bodyweight + Optional Weighted

**Lift variants:** Wide-grip pronated pull-up / Shoulder-width pronated pull-up / Chin-up (supinated) / Neutral grip / Weighted pull-up (belt + plate or vest).
**Load options:** Max reps (AMRAP) bodyweight, OR 3RM / 5RM / 10RM weighted.

**Camera:** **Front view, 2–2.5 m from the bar, eye-level to the bar (or slightly below)**. Athlete faces camera. Frame from **above head when hanging at top** down to **knees**. The hanging position should put the chest in the middle of the frame.
**Optional Camera 2 (Side view, same height):** captures kipping / body swing / chin-over-bar checkpoint.

**Landmarks tracked:**
- EAR (7/8), MOUTH (9/10), SHOULDER (11/12), ELBOW (13/14), WRIST (15/16), HIP (23/24), KNEE (25/26)
- No bar tracker needed — use WRIST landmarks as the bar anchor

**Rep Details:**
- **Bodyweight (AMRAP):** user does as many reps as possible. AI counts reps + scores form for each
- **Weighted:** 3 / 5 / 10 reps with belt-loaded plate. User enters added load
- One video per attempt

### MediaPipe / OpenCV Metrics

**Primary metric — Chin-over-bar checkpoint (rep validity gate):**
- At peak of each rep, compare **MOUTH Y vs WRIST Y** (wrist = bar position) AND check elbow angle simultaneously
- **VALID rep:** MOUTH_Y above WRIST_Y (chin clears bar) **AND** elbow angle ≤ 110° (demonstrates active pull, not just neck-craning)
- **HALF REP:** chin at bar level (within 2 cm) OR elbow 110–130° at top
- **INCOMPLETE:** chin below bar OR elbow > 130° at top — invalid rep, do not count
- This is the **rep-validity gate** — research-standard chin-over-bar definition combined with elbow-flexion check to prevent neck-stretching from registering as a rep

**Primary metric — Full hang at bottom (dead hang):**
- Elbow angle at SHOULDER–ELBOW–WRIST at lowest position
- **GOOD:** elbow ≥ 165° (near full extension, dead hang)
- **NEEDS IMPROVEMENT:** 150–165° (partial hang, lat tension never released)
- **INVALID:** < 150° (half reps, no full ROM)

**Primary metric — Range of motion (elbow ROM):**
- ΔElbow angle = (elbow at top) − (elbow at bottom)
- Expected: 85–100° absolute ROM [research: 93° pronated, 100° supinated chin-up]
- < 70° = severely shortened ROM

**Primary metric — Scapular control / initiation pattern:**
- Sequential activation research [Youdas 2010] shows healthy pull-ups initiate with **scapular depression** before elbow flexion
- Proxy: at the start of the concentric, watch which moves first — SHOULDER Y (downward) or ELBOW angle (closing)
- If SHOULDER drops 2+ cm **before** elbow flexion crosses 170° = good scapular initiation (lower trap engagement)
- If elbow starts flexing first with no shoulder depression = "elbow-pull" pattern (biceps-dominant, weak scapular control)

**Compensation metric — Kipping / body swing (side camera or front):**
- Track HIP X-displacement throughout the rep
- **GOOD strict pull-up:** HIP X stays within ±5 cm of vertical line below WRIST
- **Kip detected:** HIP X displacement > 10 cm forward-backward = momentum-assisted
- Mark kipping reps separately — don't count them toward strict-pull-up score

**Compensation metric — Body line (hollow vs arched):**
- Angle at SHOULDER–HIP–KNEE
- GOOD strict: 170–180° (straight body) OR slight hollow (160–170°)
- Excessive arch (< 150°) or piked legs (knee bent + hip flexed > 30°) = compensation for upper-body weakness

**Compensation metric — Shoulder elevation / shrug:**
- Distance from EAR to SHOULDER landmark
- Should INCREASE (or stay constant) during the pull (shoulder packed/depressed, ear-shoulder distance grows as shoulder pulls down)
- If EAR-SHOULDER distance DECREASES > 2 cm at the top = shrugging into bar (poor scapular control)

**Tempo metrics:**
- Concentric (pull): 1–2 sec target
- Eccentric (lower): 2–3 sec target for assessment
- Rushed reps < 0.5 sec concentric = kipping or partial reps
- Falling drop (eccentric < 0.5 sec) = dropping vs lowering — flag

**Grip width detection:**
- Distance WRIST_LEFT to WRIST_RIGHT, normalised by SHOULDER-SHOULDER width
- Narrow: ≤ 1.3× shoulder width
- Medium/shoulder: 1.3–1.6×
- Wide: > 1.6×
- System should detect and label the grip used; thresholds shift accordingly (wide grip → lower expected rep count, more lat bias)

**Bilateral symmetry:**
- ELBOW angle left vs right throughout the rep
- > 10° difference = one arm pulling more = strength asymmetry

### Scoring thresholds (Pull-Up)

| Status | Reps (bodyweight) | ROM | Kipping | Chin-over-bar consistency |
|---|---|---|---|---|
| **GOOD** | M: ≥ 10 / F: ≥ 5 strict | Elbow ROM ≥ 85°, full hang ≥ 165° | < 5 cm hip drift | 100% reps clear chin |
| **NEEDS IMPROVEMENT** | M: 5–9 / F: 2–4 | ROM 70–84° OR full hang 150–164° | 5–10 cm hip drift | 70–99% clear chin |
| **RESTRICTED** | M: < 5 / F: < 2 (or unable) | ROM < 70° OR hang < 150° | > 10 cm (kipping) | < 70% clear chin (half-reps) |

(Rep thresholds are general-population estimates; the system should let the user select their training level if needed.)

### Per-rep weighted scoring (Pull-Up)
Form-quality score per rep (0–100) = weighted sum:
- **Shoulder retraction / scapular control (35%)** — packing of shoulders, maintained throughout
- **Swing penalty (25%)** — hip/ankle horizontal SD penalty (inverse: less swing = higher score)
- **Elbow flexion angle at top (25%)** — full ROM (≤ 100° = best)
- **Lockout at bottom (15%)** — dead-hang elbow ≥ 170° before next rep

**Overall pull-up exercise score** = (valid rep count × 10) + (average form-quality across reps), capped at 100. This rewards both volume and form jointly.

### Muscle activation score (Pull-Up, inferred)
Composite activation score (0–100) — proxy for engagement quality without EMG:
- **Shoulder retraction (40%)** — primary lat-engagement indicator
- **Controlled tempo without swing (30%)** — pure strength vs momentum
- **Elbow flexion angle (20%)** — ROM completeness
- **Spinal neutrality (10%)** — core engagement (no excessive arch / pike)

Computed muscle-by-muscle inference table:

| Muscle group | Activation inference method |
|---|---|
| Latissimus dorsi | Early shoulder depression before elbow flexion |
| Biceps brachii | Final elbow flexion angle — smaller angle = more biceps demand (chin-up bias) |
| Rhomboids / middle traps | Scapular retraction maintenance (shoulder-to-spine X distance) |
| Core stabilisers | Minimal hip/ankle X-swing during pull |

### Inferred grip-based muscle bias (Pull-Up)
Based on grip + pattern [Youdas 2010; Edelburg 2017]:
- **Lat-dominant:** Pronated, wide grip, slow eccentric, full hang. Lat EMG peaks 117–130% MVIC
- **Biceps-dominant:** Supinated chin-up (BB EMG 78–96% MVIC, significantly higher than pronated)
- **Lower-trap-dominant:** Pronated grip with strong scapular initiation pattern (lower trap activates first)
- **Mixed:** Neutral grip — balanced lat/bicep activation

**Bilateral symmetry (Pull-Up):**

| Symmetry check | Calculation | Warning threshold |
|---|---|---|
| L vs R elbow angle | ELBOW(13) vs ELBOW(14) at top position | > 15° (uneven pulling) |
| L vs R shoulder height | SHOULDER(11) vs SHOULDER(12) Y-coordinate | > 3 cm (lateral tilt during pull) |

### Bodyweight alternatives if user can't do a pull-up
- **Inverted row** (TRX or barbell in rack): use same elbow ROM and scapular metrics, body more horizontal. Useful for users with < 1 pull-up.
- **Band-assisted pull-up:** record bandwidth; same form metrics; rep count gets scaled. **Swing tolerance relaxed to ≤ 10 cm** (band creates natural rebound that registers as drift but isn't a fault).
- **Lat pulldown machine:** Track elbow angle, shoulder retraction, bar path (should pull vertically to chest). Same form thresholds.
- **Negative-only pull-up:** eccentric-only (jump up, lower slowly). Track only eccentric time and ROM.

---

## EXERCISE 5 — Overhead Press (Standing Strict / Seated)

**Lift variants:** Standing barbell strict press (military) / Seated barbell press / Standing dumbbell press / Push-press (NOT strict — flag if leg drive detected).
**Load options:** 3RM / 5RM / 10RM / Bodyweight pike push-up (alternative if no rack/barbell).

**Camera:** **Side view, 90° to athlete, 2–2.5 m away, chest height** of standing lifter. Frame from **above-arms-extended at top** down to **mid-thigh**. Plates fully visible.
**Optional Camera 2 (Front view, chest height):** for elbow path, bar tilt, asymmetry detection.

**Landmarks tracked:**
- EAR (7/8), SHOULDER (11/12), ELBOW (13/14), WRIST (15/16), HIP (23/24), KNEE (25/26), ANKLE (27/28)
- Plate centroid

**Rep Details:** 3 / 5 / 10 reps, one video per working set.

### MediaPipe / OpenCV Metrics

**Primary metric — Bar path (the critical OHP metric):**
- Plate X-displacement across the lift
- The bar must travel **as vertically as possible** with the head moving **forward-then-back** to allow the bar to clear the face
- Expected pattern: at rack, bar in front of face (plate X = X_face + ~10 cm); at top, bar directly over head/mid-foot (plate X = X_mid-foot ± 3 cm)
- Plate horizontal displacement from rack to lockout: ~10–15 cm BACKWARD (toward the rear)
- **Bar drifts forward at lockout (plate X > shoulder X at top):** classic "press out in front" fault — anterior-delt-dominant, ends in shoulder strain
- **Bar zig-zags around face:** insufficient head movement, hits face

**Primary metric — Lockout position (bar over mid-foot):**
- At peak plate Y, plate X should align vertically with the ANKLE landmark (mid-foot proxy)
- Tolerance: ± 5 cm horizontal
- Also check the **bar-shoulder-hip-ankle stack** at lockout: all four landmarks within a vertical line (each within ± 3 cm of bar X)

**Primary metric — Trunk lean (backward lean):**
- Angle of SHOULDER → HIP vector relative to vertical
- A small backward lean (5–10°) at the start of the press is biomechanically necessary [Resistance.ai, Sumner research]
- **GOOD:** ≤ 10° initial backward lean, becomes vertical at lockout
- **NEEDS IMPROVEMENT:** 10–15° lean throughout (push-press cheating starting)
- **RESTRICTED:** > 15° lean = lift becomes incline bench press, anterior delt only, lumbar stressed

**Primary metric — Lumbar hyperextension (the OHP danger signal):**
- Angle at SHOULDER–HIP–KNEE
- A neutral standing position = ~175–180°; lumbar hyperextension = angle bows backward beyond vertical so SHOULDER X moves **behind** HIP X
- Measure: SHOULDER X relative to HIP X at peak press
- **GOOD:** SHOULDER X within ± 3 cm of HIP X
- **NEEDS IMPROVEMENT:** SHOULDER X behind HIP X by 3–6 cm
- **RESTRICTED:** SHOULDER X behind HIP X by > 6 cm = significant lumbar arching = compensating for poor shoulder mobility or weak overhead strength

**Primary metric — Elbow angle at start (rack position):**
- Elbow under or slightly forward of wrist (good rack): SHOULDER–ELBOW–WRIST ~50–70° flexion with elbow X slightly in front of wrist X
- Elbow far below wrist (elbow X = wrist X, vertical forearm) = poor rack, fingertip grip [Sumner et al. SCJ 2017]

**Primary metric — Lockout completeness:**
- Elbow angle at top: ≥ 170° (full extension)
- Both arms locked simultaneously (compare left elbow vs right elbow angle at top frame — < 5° difference)
- Trapezius slight shrug at top — proxy: SHOULDER Y at top vs SHOULDER Y at rack should rise 2–4 cm (active scapular elevation)

**Compensation metric — Leg drive (push-press tell):**
- KNEE angle should stay ~178–180° (locked straight) for strict press
- **If knee angle drops < 170° at start of concentric** = countermovement (leg drive) → reclassify as push-press, not strict press, OR flag as fault

**Compensation metric — Bar tilt (front camera):**
- Plate-left Y vs plate-right Y
- > 2 cm difference at any point = uneven press, side strength imbalance

**Compensation metric — Bar drift toward face:**
- Plate X relative to NOSE X during pass-through
- Plate must clear the face by ≥ 3 cm horizontally
- Hitting the chin / face = head not retracted enough

**Tempo metrics:**
- Eccentric (down to rack): 2 sec target
- Concentric (rack to lockout): 1–2 sec target
- Pause at rack: ≥ 0.5 sec for strict reps (no bounce)
- Pause at lockout: ≥ 0.5 sec for valid lockout

**Bilateral symmetry:**
- Elbow angle delta L vs R throughout = press asymmetry
- ELBOW Y delta L vs R during press = one arm leading

### Scoring thresholds (Overhead Press)

| Status | Bar path / lockout stack | Lumbar extension (spine angle from vertical) | Trunk lean | Lockout |
|---|---|---|---|---|
| **GOOD** | Bar over mid-foot at top (± 3 cm); stacked shoulder-hip-ankle | ≤ 5° (spine neutral to slight extension) | ≤ 10° backward lean, returns to vertical | Both elbows ≥ 170° simultaneously |
| **NEEDS IMPROVEMENT** | Bar 3–8 cm forward of mid-foot | 5–15° extension | 10–15° lean | One arm 5–10° short of lockout OR mild asymmetry |
| **RESTRICTED** | Bar > 8 cm forward (pressed out front) | > 15° extension (red flag) OR early layback before bar clears head | > 15° lean (incline press) | Incomplete lockout (< 165°) OR > 10° L/R asymmetry OR leg drive detected (knee bend) |

Note: lumbar extension is the stricter clinical threshold here (≤ 5° GOOD). The "Shoulder X vs Hip X" measurement in the implementation section above remains the actual computation — translate it to the spine-angle-from-vertical scale shown in this table.

### Per-rep weighted scoring (OHP)
Combined rep score (0–100) = weighted sum:
- **Lumbar extension (30%)** — highest weight because excessive layback is the #1 OHP injury mechanism
- **Bar path verticality (20%)** — RMS X-deviation from SHOULDER midline
- **Elbow position / stacking (20%)** — elbow X within 2–5 cm vertically below bar at start
- **Lockout completeness (15%)** — elbow ≥ 170°, bar over mid-foot ± 3 cm
- **Head clearance / chin retraction (15%)** — bar clears face by ≥ 5 cm

### 🚩 Critical red-flag rule (OHP)
**If lumbar extension exceeds 15° at any frame during the concentric phase:**
1. Auto-classify the rep as **RESTRICTED**
2. Display **lumbar-injury-risk warning** in coaching panel
3. Surface as a clinical-referral red flag on the final dashboard

Same pattern as the deadlift lumbar-flexion red flag — both are critical spine-stress conditions, different directions of failure.

### Additional detections (OHP)
- **Knee lockout:** knees should remain slightly soft (not fully locked) to protect lower back during heavy pressing
- **Shoulder shrug at lockout:** Some upward shrug is normal (active scapular elevation, 2–4 cm). Flag excessive shrug (EAR-to-SHOULDER distance changes > 5 cm from baseline) as compensation
- **Breath holding:** Valsalva manoeuvre is appropriate for heavy pressing; flag exhalation during concentric
- **Wrist extension:** Flag wrist bent > 15° behind forearm (bar not stacked over forearm = force-transfer loss + wrist strain)

**Bilateral symmetry (OHP):**

| Symmetry check | Calculation | Warning threshold |
|---|---|---|
| L vs R elbow position | ELBOW(13) vs ELBOW(14) horizontal offset | > 5 cm difference |
| L vs R lockout height | ELBOW angle left vs right at top | > 15° difference |
| L vs R bar height | WRIST(15) vs WRIST(16) vertical position | > 4 cm (uneven pressing) |

### Inferred muscle activation bias (OHP)
- **Anterior delt-dominant:** Bar drifts forward, lean > 10°
- **Lateral delt + tricep-balanced:** Good vertical bar path, clean lockout, no lean
- **Tricep-dominant:** Narrow grip (wrists ≤ 1.2× shoulder width) — sticking point near lockout disappears
- **Lat-engaged stable press:** Bar travels straight up, ribs stay down, no rib flare → score this as best pattern

### Bodyweight / Light-weight alternative
- **Pike push-up:** side view, full body. Pike position with hips high (inverted V). Track head Y-position as the "press" indicator, plus elbow angle and hip stability. Useful when no barbell.
- **Dumbbell or band overhead press:** Same metrics apply but use WRIST landmarks in place of bar detection (no plate to track)
- **Seated overhead press:** When back is supported, relax the lumbar extension metric (the bench takes the spine out of the equation) — focus scoring on elbow position and bar path

---

## CROSS-EXERCISE TRACKING (consistent across all 5)

### Barbell / Plate detection pipeline
- Use OpenCV `HoughCircles` to detect the plate's circular edge OR train a YOLOv5 plate-detector (research by Ko, Nasridinov, Park 2024 uses exactly this)
- Initialise a KCF or MOSSE tracker on the detected plate centroid; KCF is more accurate for displacement, MOSSE is faster
- Calibration: known plate diameter (kg → mm map: 25 kg plate = 450 mm, 20 kg = 450 mm, 15 kg = 400 mm, 10 kg = 320 mm, 5 kg = 230 mm) gives the px/cm conversion — same role as your "tibia length 40 cm" fallback in mobility
- User selects plate size on upload screen for accurate calibration

### Rep-counting algorithm (universal)
- Use the **primary movement landmark** for each lift:
  - Squat: HIP Y
  - Deadlift: plate Y
  - Bench: plate Y
  - Pull-up: SHOULDER Y or MOUTH Y
  - OHP: plate Y
- Apply 1D signal smoothing (Savitzky-Golay or moving-average over 5 frames)
- Detect local maxima and minima (peak-finding)
- 1 rep = peak → trough → peak (or trough → peak → trough for pull-up)
- Reject reps where peak-to-trough amplitude < 50% of expected ROM for that lift

### 1RM estimation
Each report shows estimated 1RM using **both** Epley and Brzycki formulas, plus a velocity-based estimate when MCV at last rep is available:
- Epley: `1RM = weight × (1 + reps / 30)`
- Brzycki: `1RM = weight × 36 / (37 − reps)`
- VBT-based (optional, advanced): use load-velocity profile per lift — minimum velocity threshold (MVT) ≈ 0.15 m/s for deadlift, 0.30 for squat, 0.17 for bench

### Tempo consistency score
- For each lift, compute SD of concentric time across reps
- SD < 0.3 sec = consistent (strength expression stable)
- SD > 0.5 sec = fatigue or technical breakdown across reps

### Confidence score per metric
- Average MediaPipe landmark visibility for the relevant joints across the rep
- Visibility < 0.7 → flag low confidence, ask user to refilm
- Plate-tracker IOU stability score across frames

---

## GENERAL AI IMPLEMENTATION NOTES (mirrors mobility spec)

**Minimum frame rate:** 30 fps. **60 fps strongly preferred** for VBT and tempo accuracy (research uses 120 Hz; smartphone 60 fps is acceptable for assessment).

**Calibration requirements:**
- **Primary:** Circular plate auto-detect (plate diameter is the px/cm reference)
- **Fallback:** A4 paper (21.0 × 29.7 cm) placed flat in frame
- **Secondary fallback:** Athlete-height input (height + tibia length improves depth metric accuracy)
- Athlete in fitted clothing (loose shirts destroy hip/shoulder landmarks)
- Plain background ideal but not required (BlazePose handles cluttered scenes reasonably well)
- For squats/deadlifts, ensure plates are in **full side profile**, not angled

**Measurement reliability (BlazePose 2D):**
- Knee/hip/ankle landmarks: MAE ~4–5° in sagittal plane (well-validated)
- Shoulder landmarks: MAE ~6.5° (highest error — bench press most affected)
- Lumbar / mid-spine: NOT directly tracked. Spine angle is inferred from SHOULDER-HIP line — this is a 2-point approximation, not true spine curvature. Be honest in the UI: "spine angle estimate"
- For deadlift spine-rounding detection at competition level, a 3-point EAR-SHOULDER-HIP angle is more reliable than 2-point alone

**Load-aware scoring:**
- Same metric thresholds, but **NEEDS IMPROVEMENT becomes more lenient at 3RM than at 10RM** (some compensation is biologically expected near 1RM)
- Suggested adjustment: widen thresholds by 20% at 3RM, by 10% at 5RM, leave alone at 10RM

### Tempo & duration detection (applies to all lifts)

| Parameter | Method | Target |
|---|---|---|
| Eccentric phase duration | Track descent from start of rep to bottom position | 2–3 sec (bench/squat), 2 sec (OHP) |
| Concentric phase duration | Track ascent from bottom to lockout | 1–2 sec (all exercises) |
| Pause detection | Frame count where joint angles remain static at bottom | ≥ 0.5 sec required for bench/squat |
| Rep rejection threshold | Tempo < 50% of target OR > 200% of target | Flag as "rushed" or "overly slow" |

### Compensation & injury-risk flags (severity-coded)

| Compensation type | Detection method | Severity |
|---|---|---|
| Knee valgus (squat) | KNEE deviation from HIP–ANKLE axis > 3 cm | **Critical** |
| Lumbar flexion (deadlift) | Spine curvature angle > 10° from neutral | **Critical** |
| Excessive elbow flare (bench) | Elbow angle > 85° from torso | **Critical** |
| Lumbar extension > 15° (OHP) | SPINE angle relative to vertical | **Critical** |
| Heel lift (squat) | HEEL vertical displacement > 2 cm | Warning |
| Bar path deviation > 10 cm | Plate X-coordinate SD > 10 cm | Warning |
| Bilateral asymmetry > 20% | L vs R angle difference | Warning |
| Swinging (pull-up) | ANKLE horizontal SD > 5 cm | Warning |
| Hip rise during press (bench) | HIP_Y > 2 cm above baseline | Warning |
| Leg drive (strict OHP) | KNEE flexion < 170° during concentric | Warning |

**Critical flags surface on the final dashboard as red-flag clinical referrals.** Warnings appear as in-report coaching cues but don't gate the score the same way.

**Bilateral comparison:**
- Every lift must compute L vs R asymmetry (mirrors your mobility spec philosophy)
- Output a single "Symmetry index" per lift, 0–100

**Movement validation:**
- Reject reps with poor landmark visibility (< 0.7 avg confidence)
- Reject reps with abnormal tempo (concentric < 0.3 sec — likely a dropped bar)
- Report number of valid reps / total reps (exactly like your mobility "12/12 valid reps")

### Confidence scoring (per metric)

Each computed metric returns alongside a 0–100 confidence score, computed from:
- **Landmark visibility** — occluded joints (bar over chest, hand over face) reduce confidence
- **Camera angle compliance** — deviation from specified angle reduces confidence
- **Calibration reference** — presence/absence of in-frame plate or A4 paper
- **Lighting quality** — uniform vs backlight / shadows

**Confidence tiers:**
- **90–100%:** High reliability — use for clinical/coaching recommendations
- **70–89%:** Moderate reliability — flag in report that manual coach review is recommended
- **< 70%:** Low reliability — do NOT persist results to user history; prompt user to re-record with corrected setup

This mirrors how your mobility analyser shows "100% confidence" on the report cards — same UI element, more sophisticated underlying signal.

### Output format per exercise (mirrors your Seated Hip Rotation report layout)

Visual layout:
1. Header card: score 0–100, grade (A/B/C/D), classification (GOOD / NEEDS IMPROVEMENT / RESTRICTED)
2. Sub-header: camera view OK, confidence %, sides analysed, valid reps, pass rate
3. Analysis photos: skeleton overlay on 3 best-frame stills (e.g., setup, bottom, lockout)
4. Per-rep breakdown: expandable rows with each rep's key metrics, marked BEST REP
5. All-metrics table: metric name, value, target, PASS/FAIL status
6. Performance radar chart: 5–6 axes (depth, lockout, bar path, tempo, symmetry, spine)
7. Bilateral comparison bars: left vs right horizontal bars (where applicable)
8. Coaching & Improvements: 3–4 bullet points, color-coded (important / maintain / fix)

Plain-text export template (for API / coach handoff):
```
EXERCISE NAME — SUBTITLE
[CLASSIFICATION] — [SCORE]
#/# valid reps · XX% confidence

PER-REP BREAKDOWN:
- Rep 1: [classification] — [score]
- Rep 2: [classification] — [score]
- Rep 3: [classification] — [score]

ALL METRICS:
| METRIC              | VALUE   | TARGET     | STATUS |
|---------------------|---------|------------|--------|
| (e.g., Squat Depth) | -2.3 cm | below knee | PASS   |
| (e.g., Knee Valgus) | 2.1 cm  | < 1.5 cm   | FAIL   |
| ...                 |         |            |        |

BILATERAL COMPARISON:
- Metric L: [value] · R: [value] · Difference: [value]° [WARNING if over threshold]

COACHING & IMPROVEMENTS:
- [Specific actionable feedback]
- [Cited references to clinical thresholds where applicable]

→ Redo This Exercise | All Exercises | Dashboard
```

### Overall strength dashboard (mirrors your Mobility Dashboard)

- Composite score across 5 exercises (weighted by completed lifts)
- Identified weakest exercises (priority for training focus) — sorted by lowest score
- Bilateral asymmetry summary (across all lifts)
- Inferred muscle bias profile: e.g., "Hip-dominant + Pec-dominant + Lat-dominant pull"
- Estimated 1RM table for all 5 lifts (Epley + Brzycki)
- Red flags requiring referral (visible lumbar rounding under load, severe asymmetry > 20%, sharp pain markers via text input)

Plain-text dashboard template:
```
STRENGTHAI (your product name)

[#]/5 exercises analysed · [overall status]

OVERALL GRADE: [XX]/100

EXERCISES TO WORK ON:
- [Priority #1 exercise]
- [Priority #2 exercise]
- [Priority #3 exercise]

[Universal coaching tips — camera angle, tempo, hydration, re-test frequency]

ALL STRENGTH EXERCISES · [N] REPORTS

[Exercise 1 name] — [classification] — [score] — [OPEN FULL REPORT]
[Exercise 2 name] — [classification] — [score] — [OPEN FULL REPORT]
[Exercise 3 name] — [classification] — [score] — [OPEN FULL REPORT]
[Exercise 4 name] — [classification] — [score] — [OPEN FULL REPORT]
[Exercise 5 name] — [classification] — [score] — [OPEN FULL REPORT]

OVERALL STRENGTH PROFILE:
- Composite score across 5 exercises
- Identified weakest areas (priority for corrective programming)
- Bilateral asymmetry summary
- Estimated 1RM (Epley + Brzycki) per lift
- Red flags requiring clinical referral (sharp pain, severe restriction, > threshold lumbar flexion/extension)
```

---

## SCREEN-BY-SCREEN MAP (matches your 4 uploaded mockups)

### Screen 1 — Exercises grid (mirrors `mobility.png` "10 Exercises")
5 cards, each with: exercise number (1–5), name, sub-label (movement pattern), short description, body region badge (LOWER / UPPER / FULL BODY), level badge (Beginner / Intermediate / Advanced), expected video count, estimated time, completion checkmark.

Suggested cards:
1. **Back Squat** — Lower Body — Compound knee/hip extension — 1 video (side) + optional front — ~5 min
2. **Deadlift** — Full Body — Hip-dominant pull pattern — 1 video (side) — ~5 min
3. **Bench Press** — Upper Body Push — Horizontal press — 1 video (side) + optional foot-end — ~5 min
4. **Pull-Up** — Upper Body Pull — Vertical pull pattern — 1 video (front) + optional side — ~3 min
5. **Overhead Press** — Upper Body Push — Vertical press — 1 video (side) + optional front — ~3 min

Plus "Dashboard →" button and overall progress bar — identical to mobility.

### Screen 2 — Per-exercise upload (mirrors `knee-to-wall-test.png`)
- Reference library row: HOW-TO video, camera setup diagram, written guide, body-position reference
- Submission checklist: lift-specific bullets ("Plates visible", "Whole body in frame", "Tripod stable", "Side view", etc.)
- Calibration row: detected plate size (auto) OR user-entered fallback (45 cm)
- **Lift-specific input row:** load (kg), reps performed, variant selector (e.g., "Conventional / Sumo / Trap-bar"), grip style for pull-up, bench incline angle, etc.
- Video upload slots: usually 1 video (single side); some lifts get an "optional secondary camera" slot
- "Analyse →" button enabled once all required videos uploaded

### Screen 3 — Per-exercise report (mirrors `seated-hip-rotation-test_result.png`)
- Score card (left): big circular score 0–100 + grade + classification chip
- Summary header: camera view status, confidence %, sides (if applicable), valid reps / total reps, pass rate
- Analysis photos row: 3 skeleton-overlay stills (Setup / Bottom / Lockout for squats; analogous for others)
- Per-rep breakdown: expandable accordion, one row per rep, badge "★ BEST" on best rep
- All Metrics table: 6–8 metrics with value, target, PASS/FAIL
- Performance Radar (right): polygon overlay showing this lift's profile
- Bilateral Comparison bars (where applicable): L vs R horizontal bars with asymmetry % flag
- Coaching & Improvements section: 3–4 cards, color-coded (yellow=important, green=maintain, red=fix)
- Footer card: score recap + Redo / All Exercises / Dashboard / Next Exercise nav buttons

### Screen 4 — Strength dashboard (mirrors `mobility_dashboard.png`)
- Top hero card: overall strength score 0–100, grade letter, "5/5 analysed · N passed"
- 4 small metric cards: total exercises, passed, to improve, strengths
- "Exercises to work on" sorted list (lowest score first)
- Tips & tricks section: 4–6 short tips (warm up, film angle, retest cadence, hydration, breath, rest)
- "All Strength Exercises · N Reports" section: 5 large report cards in 2-column grid (just like mobility), each with score, classification badge, valid reps, best-rep thumbnails, top 2 coaching bullets, "OPEN FULL REPORT →" link
- "Not yet analysed" section at bottom: tags for any incomplete exercises
- Bottom nav: Home / All Exercises

---

## SUMMARY OF CAMERA ANGLES (quick reference for the upload UI)

| Exercise | Primary Camera | Height | Distance | Optional 2nd Camera |
|---|---|---|---|---|
| Back Squat | Side, left | Hip | 2.5–3 m | Front (knee height) for valgus |
| Deadlift | Side, left | Hip | 2.5–3 m | Rear-quarter 45° for spine |
| Bench Press | Side of bench, left | Chest of lifter (elevated) | 2.5 m | Foot-end (overhead-down) |
| Pull-Up | Front (facing athlete) | Bar height or slightly below | 2–2.5 m | Side for kipping detection |
| Overhead Press | Side, left | Chest of standing lifter | 2–2.5 m | Front for bar tilt |

---

## SUMMARY OF METRICS BY LIFT (cheat sheet)

| Exercise | Primary metrics | Compensations watched | Inferred bias |
|---|---|---|---|
| Squat | Depth (hip vs knee), knee angle, hip angle, trunk lean, tibia angle, TTA, bar path | Heel lift, butt wink, knee valgus, bar drift | Quad vs glute (via TTA) |
| Deadlift | Setup angles, spine neutrality (EAR-SHOULDER-HIP), bar path, hip-knee velocity ratio, lockout | Hips shoot up, bar drift, hyperextension, shoulder protraction | Hip vs quad (variant + TTA) |
| Bench Press | Bar path J-curve, elbow flare, bottom ROM (elbow angle), lockout, scapular Y-stability | Hip lift, bar tilt, bouncing, wrist alignment | Pec vs tricep vs anterior delt (via flare + grip) |
| Pull-Up | Chin-over-bar, dead hang, elbow ROM, scapular initiation, hip drift | Kipping, shrugging, body arch | Lat vs bicep vs lower trap (grip + pattern) |
| Overhead Press | Bar path (over mid-foot), lockout stack, trunk lean, lumbar position, elbow lockout L/R | Leg drive, bar drift forward, lumbar hyperextension, bar tilt | Anterior vs lateral delt vs tricep |

### Per-rep weighted scoring summary (formula cheat sheet)

| Exercise | Weighted score formula |
|---|---|
| **Squat** (barbell) | Depth 35% + Knee alignment 25% + Back angle 20% + Knee travel 15% + Bar path 5% |
| **Squat** (bodyweight) | Depth 40% + Knee alignment 30% + Back angle 20% + Knee travel 10% |
| **Deadlift** | Spinal neutrality 35% + Bar positioning 20% + Hip/knee sequencing 20% + Lockout 15% + Bar path 10% |
| **Bench Press** | Elbow tuck 30% + Bar contact point 20% + Shoulder retraction 20% + Leg drive 15% + Bar path 15% |
| **Push-up** (bodyweight) | Depth 40% + Body alignment 30% + Elbow angle 20% + Tempo 10% |
| **Pull-Up** | (Valid reps × 10) + (form-quality avg); form-quality = Shoulder retraction 35% + Swing penalty 25% + Elbow flex 25% + Lockout 15% |
| **Overhead Press** | Lumbar extension 30% + Bar path 20% + Elbow position 20% + Lockout 15% + Head clearance 15% |

### Critical red-flag summary (auto-RESTRICTED + clinical-referral surface)

| Exercise | Red-flag condition |
|---|---|
| Squat | Knee valgus deviation > 3 cm in frontal plane |
| Deadlift | Lumbar flexion > 15° at any concentric frame |
| Bench Press | Elbow flare > 85° **AND** bar contact > 5 cm off sternum (combo flag) |
| Overhead Press | Lumbar extension > 15° at any concentric frame |
| Pull-Up | None — but kipping > 10 cm hip swing invalidates rep count |

---

## Validity caveats (be upfront with users)

- **Computer vision is not a coach.** A flag is a signal to review, not a verdict.
- **Bench press has the highest error rate** of all 5 lifts due to self-occlusion — recommend the optional foot-end camera if available.
- **EMG is the only true muscle-activation measure.** The "inferred muscle bias" output is a kinematic proxy based on published EMG-to-kinematic correlations, not direct measurement.
- **1RM estimation degrades above 10 reps.** Recommend 3RM or 5RM for the most accurate strength estimate.
- **Pain ≠ score.** If the user reports pain (text input on upload screen), display the red-flag clinical-referral notice regardless of form score, same as your mobility spec.

---
