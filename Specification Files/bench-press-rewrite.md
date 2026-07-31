# Biomechanical Assessment System — Flat & Incline Barbell Bench Press

> A working reference for camera-based, MediaPipe-driven technique assessment of the flat barbell bench press (BP-F) and incline barbell bench press (BP-I). Third document in a parallel series after Barbell Squat and Barbell Deadlift assessment systems. Structure, scoring methodology, and MediaPipe implementation depth mirror those documents.

---

## Table of Contents

1. Required Camera Angles
2. Flat vs Incline Bench Press: Key Differences
3. Sagittal (Side) View Metrics
4. Frontal / Overhead View Metrics
5. Posterior / Head-End View Metrics
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

The bench press is a supine, horizontally oriented lift where the bar moves primarily vertically with a small but technically critical horizontal component (the "J-curve"). Unlike the squat/deadlift, the lifter's longitudinal axis is parallel to the floor (flat) or angled 30–45° (incline), so camera placement has to be re-thought rather than copy-pasted from standing-lift protocols.

### 1.1 Views Needed

| View | Camera Position | Captures | Priority |
|---|---|---|---|
| **Sagittal (side, perpendicular to bench)** | 2.5–3.5 m off the side of the bench, lens at bench-surface height (flat) or perpendicular to bench plane (incline) | Bar path (J-curve), touch point, forearm angle, elbow flexion, ROM, arch height, head position, glute contact, heel position, pause quality | **PRIMARY** |
| **Frontal / overhead** | Directly above bench, lens parallel to floor, pointed straight down (or mounted to ceiling/tripod boom) | Bar tilt L/R, bar path symmetry, grip width, elbow flare in frontal plane, wrist alignment | **SECONDARY** |
| **Posterior / head-end** | Behind the head of the bench, 1.5–2 m back, lens at or slightly above bar-rack height | Elbow flare (cleanest angle), scapular position (proxy), bar tilt cross-check, bar centering on torso midline | **SECONDARY** |
| **45° oblique** | High-quarter angles (front-lateral, rear-lateral) | Backup view; covers occlusions; useful when only one camera is available | Tertiary |

### 1.2 Camera Setup Recommendations

| Parameter | Recommendation | Rationale |
|---|---|---|
| Frame rate | **≥ 60 fps** (120 fps for max-effort singles or sticking-point analysis) | Mean concentric velocity at 1RM ≈ 0.16 m/s (González-Badillo & Sánchez-Medina 2010), but eccentric velocities can spike to 0.6–1.0 m/s; bouncing produces sub-100 ms events |
| Resolution | ≥ 1080p (4K preferred for overhead) | Subtle bar tilt of 2–3° is ~2 cm differential at the ends of a 220 cm bar — needs pixel resolution |
| Lens height (sagittal) | Equal to bench surface (≈45 cm for flat); for incline, perpendicular to the bench's long axis | Avoids parallax-driven distortion of bar-path J-curve |
| Lens distance (sagittal) | 2.5–3.5 m, lens orthogonal to bench long axis | Far enough to minimise perspective compression of arch height and bar travel |
| Lighting | Diffuse, ≥ 500 lux at the bench; avoid back-lighting from windows | Pose-estimation models degrade severely with silhouette or contre-jour lighting |
| Background | Plain wall, contrasting with skin/clothing | Improves landmark visibility scores |
| Bar markers (optional) | Coloured tape on collars and bar centre | Improves bar-tracking when wrist landmarks slip |

### 1.3 Special Bench-Press Camera Challenges

- **The lifter is supine.** MediaPipe BlazePose was trained primarily on upright bodies; supine detection is measurably less reliable (see §12.7). Sagittal angle is critical because it maximises body silhouette area presented to the lens.
- **The bar occludes the chest/face.** Especially from overhead and head-end views — the bar and plates eclipse a strip across the torso, shoulders, and sometimes the face during pause and lockout.
- **The horizontal component is small.** Elite J-curve is on the order of 5–15 cm against ~35–50 cm of vertical travel — the camera must resolve cm-scale horizontal displacement.
- **For incline:** the body axis tilts, so a sagittal camera that "looks horizontal" no longer aligns with the bench. Either tilt the camera to be perpendicular to the bench, or compute a body-relative coordinate system in software (see §12.3).

### 1.4 Which Angle Captures Which Metrics

| Metric | Sagittal | Frontal/Overhead | Posterior/Head-end |
|---|---|---|---|
| Bar path J-curve | ★★★ | – | – |
| Touch point on chest | ★★★ | ★ | ★ |
| Forearm vertical (sagittal) | ★★★ | – | – |
| Elbow flexion angle | ★★★ | ★ | ★★ |
| Elbow flare (frontal plane) | – | ★★ | ★★★ |
| Bar tilt L/R | – | ★★★ | ★★ |
| Bar path symmetry L/R | – | ★★★ | ★★ |
| Grip width | ★ | ★★★ | ★★ |
| Arch height | ★★★ | – | – |
| Head position | ★★★ | – | ★★ |
| Glute contact | ★★★ | – | – |
| Heel contact / drive | ★★★ | ★ | – |
| Bar speed | ★★★ | ★★ | – |
| Pause duration | ★★★ | – | – |

---

## 2. Flat vs Incline Bench Press: Key Differences

| Dimension | Flat Bench (BP-F) | Incline Bench (BP-I) |
|---|---|---|
| **Bench angle** | 0° (horizontal) | 30–45° typical; per Rodríguez-Ridao et al. 2020 (5-angle study at 60% 1RM), maximal upper-pec (clavicular) EMG occurs at **30°**, while anterior deltoid peaks at **60°**; mid/lower pec peak at 0° |
| **Bar path geometry** | Pronounced J-curve: descends roughly vertical to lower chest/sternum, ascends back-and-up toward shoulder line | Shallower J: bar starts over upper chest/shoulders, descends to clavicular pec, ascends with smaller horizontal component (because the torso is already inclined) |
| **Touch point** | Lower sternum / xiphoid line in powerlifting; nipple line in bodybuilding | Upper sternum / clavicular pec line (≈2–5 cm below clavicle) |
| **Elbow position / flare** | Tucked 45–75° from torso for powerlifting; up to 75–80° for hypertrophy; ≥ 90° is injury territory | Naturally more tucked (35–60°) because the gravity vector is no longer perpendicular to the humerus |
| **Shoulder abduction at touch** | 45–75° (safe); 75–90° (high stress) | 30–60° typical |
| **Range of motion** | Larger if no arch; reduced 20–40% by competition arch | Larger relative humeral excursion because bench tilt forces longer travel to reach chest |
| **Arch geometry** | Lumbar + thoracic extension allowed; powerlifters can shorten ROM by 20–30% via arch | Arching is constrained by the bench back-pad; effectively flat-back |
| **Primary muscle emphasis** | Sternocostal (middle/lower) pec major, triceps, anterior delt | Clavicular (upper) pec major + anterior deltoid; per Saeterbakken et al. (2017, *J Hum Kinet* 57:91–98) at +25° vs flat (n = 12 national/international bench press athletes, 6RM, wide grip): **"58.5–62.6% lower triceps brachii activation"** and **"48.3–68.7% greater biceps brachii activation"**; pec major (both heads), anterior and posterior deltoid, and latissimus showed no significant differences |
| **Powerlifting vs bodybuilding style** | PL: wide grip (165–200% biacromial), tucked elbows, low touch, paused; BB: moderate grip, more flare, higher touch, touch-and-go | Incline is rarely competed; almost always bodybuilding-style (moderate grip, controlled tempo, full ROM) |
| **Grip width** | IPF max **81 cm** between forefingers; performance optimum 165–200% biacromial width (Wagner et al. 1992 reported peak 1RM at moderate-to-wide grips, ~7% greater than narrow) | Typically narrower than flat (1.0–1.5× biacromial); excessive width unnecessary because pec mechanics already favoured |
| **Typical same-lifter 1RM** | 100% baseline | ~80% of flat (Saeterbakken 2017 reported 6RM loads **"18.5–21.5% lower in the inclined bench position compared with flat and declined"**) |
| **Sticking-point depth** | ~3–11 cm above chest (van den Tillaar 2012: sticking begins 2–6 cm above sternum, ends ~11 cm; duration ~0.9 s per van den Tillaar & Ettema 2010) | Slightly higher in the concentric, because the mechanical disadvantage zone is shifted by the torso angle |

---

## 3. Sagittal (Side) View Metrics

Each metric uses a 5-tier scoring rubric: **Very Good / Good / Yellow Flag / Bad / Very Bad**. Where flat and incline thresholds diverge, separate columns are given.

Scoring tier → sub-score (0–100):
- Very Good = 90–100
- Good = 75–89
- Yellow Flag = 60–74
- Bad = 40–59
- Very Bad = 0–39

---

### 3.1 Bar Path J-Curve Total Horizontal Displacement

**Definition:** Maximum horizontal (head-ward) displacement of the wrist-centre proxy from the touch point to lockout, measured in the sagittal plane.

| Tier | Flat BP | Incline BP |
|---|---|---|
| Very Good | 5–12 cm (back-and-up, smooth) | 3–8 cm |
| Good | 12–18 cm or 3–5 cm | 8–12 cm or 1–3 cm |
| Yellow Flag | 18–25 cm or 1–3 cm (near-vertical) | 12–18 cm or 0–1 cm |
| Bad | 25–35 cm OR > 0 cm forward (toward feet) | > 18 cm OR forward drift |
| Very Bad | > 35 cm OR clearly forward-drifting (away from face) | > 25 cm OR forward drift |

**Interpretation:** In McLaughlin's seminal *Bench Press More Now* (1984, Auburn University biomechanics lab) analysis comparing a 245 lb novice, Mike Bridges (world champion, 463 lb), and Bill Kazmaier (605 lb world record), Kazmaier's path showed the most pronounced horizontal back-and-up J, keeping the bar closest to the shoulder axis through the sticking point. Novices typically press more vertically off the chest then back, producing a forward-then-back zigzag rather than a clean J.

---

### 3.2 Bar Touch Point on Chest

**Definition:** Vertical position on the torso where the bar contacts at the bottom of the descent, expressed as % of torso length measured from the suprasternal notch (0%) to the xiphoid process (100%).

| Tier | Flat (powerlifting) | Flat (bodybuilding) | Incline |
|---|---|---|---|
| Very Good | 70–95% (lower sternum) | 45–70% (mid/lower sternum) | 5–25% (upper sternum / 2–5 cm below clavicle) |
| Good | 60–70% or 95–105% | 35–45% or 70–80% | 0–5% or 25–35% |
| Yellow Flag | 50–60% or 105–115% | 25–35% or 80–95% | -5–0% (on clavicle) or 35–45% |
| Bad | 30–50% or > 115% (belly) | < 25% or > 95% | Touching clavicle (-15 to -5%) or > 45% |
| Very Bad | Bar touches throat/neck or above abdomen | Bar touches throat or below xiphoid | Bar touches throat |

**Critical safety note:** Touch point migrating toward the throat (negative % on flat, very negative on incline) is the **single highest-risk error** in the bench press — it implies loss of control and the bar tracking back into the C-spine.

---

### 3.3 Forearm Vertical at Touch (Sagittal Projection)

**Definition:** Angle between the forearm (elbow → wrist vector) and gravity vector at the touch frame, in the sagittal plane. 0° = perfectly vertical.

| Tier | Both BP-F and BP-I |
|---|---|
| Very Good | 0–5° |
| Good | 5–10° |
| Yellow Flag | 10–15° |
| Bad | 15–25° |
| Very Bad | > 25° |

A non-vertical forearm at touch indicates either mismatched grip width vs touch point, or a moment arm being applied to the elbow that triceps must overcome unnecessarily.

---

### 3.4 Elbow Angle at Bottom (Touch)

**Definition:** Shoulder–elbow–wrist three-point angle at the touch frame.

| Tier | Flat BP | Incline BP |
|---|---|---|
| Very Good | 55–75° | 60–80° |
| Good | 50–55° or 75–85° | 55–60° or 80–90° |
| Yellow Flag | 45–50° or 85–95° | 50–55° or 90–100° |
| Bad | 40–45° or 95–105° | 45–50° or 100–110° |
| Very Bad | < 40° (crushed) or > 105° (insufficient ROM) | < 45° or > 110° |

---

### 3.5 Elbow Angle at Lockout

**Definition:** Shoulder–elbow–wrist angle at the wrist-Y maximum frame. Full extension is 180°.

| Tier | All bench variants |
|---|---|
| Very Good | 175–180° |
| Good | 170–175° |
| Yellow Flag | 165–170° |
| Bad | 155–165° |
| Very Bad | < 155° (short lockout) |

---

### 3.6 Shoulder Flexion Angle at Bottom

**Definition:** Angle between torso vector (hip→shoulder) and humerus vector (shoulder→elbow) in the sagittal plane at touch. Bench-relative, not gravity-relative.

| Tier | Flat | Incline |
|---|---|---|
| Very Good | 60–85° | 65–90° |
| Good | 55–60° or 85–95° | 60–65° or 90–100° |
| Yellow Flag | 50–55° or 95–105° | 55–60° or 100–110° |
| Bad | 45–50° or 105–115° | 50–55° or 110–120° |
| Very Bad | < 45° or > 115° | < 50° or > 120° |

---

### 3.7 Shoulder Abduction (Frontal-Plane Humeral Angle from Torso)

**Definition:** Angle between the torso long-axis and the humerus, measured in the frontal/transverse plane (best read from the posterior/head-end camera, but estimable from sagittal+overhead fusion). This is the "elbow flare" angle.

| Tier | Flat (powerlifting) | Flat (bodybuilding/general) | Incline |
|---|---|---|---|
| Very Good | 35–55° | 45–65° | 30–50° |
| Good | 30–35° or 55–65° | 35–45° or 65–75° | 25–30° or 50–60° |
| Yellow Flag | 25–30° or 65–75° | 25–35° or 75–85° | 20–25° or 60–70° |
| Bad | 15–25° or 75–85° | 15–25° or 85–90° | 70–80° |
| Very Bad | < 15° or > 85° | > 90° | > 80° |

Per Noteboom et al. (2024, *Frontiers in Physiology* 15:1393235, DOI 10.3389/fphys.2024.1393235), in which ten experienced lifters performed 21 bench-press variations at abduction angles of 45°, 70°, and 90° tracked with OpenSim musculoskeletal modelling, grip widths < 1.5 BAW significantly decreased acromioclavicular compression (p < 0.05). Green & Comfort (2007, *Strength Cond J* 29(5):10–14) state: **"Reducing grip width to ≤1.5 biacromial width appears to reduce this risk and does not affect muscle recruitment patterns, only resulting in a ±5% difference in one repetition maximum."**

---

### 3.8 Wrist Position

**Definition:** Wrist flexion/extension angle (forearm–hand vector deviation from straight) at touch. "Neutral" defined as ≤ 10° extension.

| Tier | All bench variants |
|---|---|
| Very Good | 0–10° extension (neutral or slightly bent back, bar stacked over forearm) |
| Good | 10–20° |
| Yellow Flag | 20–30° |
| Bad | 30–45° |
| Very Bad | > 45° hyperextended OR any flexion (wrist breaking forward) |

---

### 3.9 Bar Pause Quality (Paused Bench)

**Definition:** Duration and stillness of bar at touch point. Stillness = wrist-Y velocity magnitude ≤ 0.05 m/s.

| Tier | Duration & quality |
|---|---|
| Very Good | 0.8–1.5 s, velocity < 0.05 m/s throughout, no sink |
| Good | 0.5–0.8 s, brief micro-bounce |
| Yellow Flag | 0.3–0.5 s OR > 1.5 s (too long, wasting tension) |
| Bad | 0.1–0.3 s (touch-and-go disguised as pause) |
| Very Bad | No detectable static frame OR > 3 s (loss of position) |

For IPF competition, only a "motionless on the chest" judge call is required — typically ≥ 0.5–1.0 s in practice.

---

### 3.10 Touch-and-Go Quality (Non-Paused)

**Definition:** Reversal smoothness for touch-and-go reps. Measured as peak deceleration at touch.

| Tier | Reversal |
|---|---|
| Very Good | Smooth, peak |deceleration| < 12 m/s² |
| Good | 12–18 m/s² |
| Yellow Flag | 18–25 m/s² |
| Bad | 25–35 m/s² (visible bar bounce) |
| Very Bad | > 35 m/s² (sternum bounce, rib slap) |

---

### 3.11 Bar Wobble / Control

**Definition:** Root-mean-square of bar lateral and longitudinal jitter (after low-pass filtering at 6 Hz) over the descent and ascent.

| Tier | RMS wobble |
|---|---|
| Very Good | < 1 cm |
| Good | 1–2 cm |
| Yellow Flag | 2–4 cm |
| Bad | 4–7 cm |
| Very Bad | > 7 cm |

---

### 3.12 Arch Height

**Definition:** Vertical distance from the bench surface to the highest point of the lumbar/thoracic spine (proxy: shoulder-Y minus hip-Y minus expected resting offset, normalised by torso length). Expressed as % torso length.

| Tier | Powerlifting style | Bodybuilding / general | Incline (bench-pad constrains arch) |
|---|---|---|---|
| Very Good | 8–20% torso length | 2–6% | 0–3% |
| Good | 6–8% or 20–25% | 0–2% or 6–10% | 3–5% |
| Yellow Flag | 4–6% or 25–30% | -1–0% or 10–13% | 5–7% |
| Bad | < 4% or 30–35% | < -1% (rounded) or 13–18% | > 7% |
| Very Bad | > 35% (extreme cramp risk) | > 18% | > 10% |

---

### 3.13 Scapular Retraction Maintenance

**Definition:** Proxy measured as the distance between MediaPipe shoulder landmarks (11,12) and the bench plane, plus shoulder-Y stability across reps. Pinched-back, depressed scapulae sit closer to bench and remain near-static; loss of retraction shows as shoulder landmarks rising or migrating forward (anteriorly).

| Tier | Behaviour |
|---|---|
| Very Good | Shoulder-Y stable within ±1 cm during entire rep; no anterior shrug |
| Good | ±1–2 cm drift, recovers between reps |
| Yellow Flag | 2–4 cm drift, mild shrug on press |
| Bad | 4–7 cm drift, visible shoulder roll-forward |
| Very Bad | > 7 cm; scapular protraction at touch (high pec-tear and impingement risk) |

---

### 3.14 Head Position on Bench

**Definition:** Nose-Y position relative to shoulder-Y line, sampled across the rep. Head must stay in contact with bench (IPF rule).

| Tier | Behaviour |
|---|---|
| Very Good | Nose-Y stable, head fully on bench throughout |
| Good | Slight lift (< 2 cm) during pause or sticking point |
| Yellow Flag | 2–4 cm head lift |
| Bad | 4–7 cm or sustained neck flexion |
| Very Bad | Head fully off bench (red-light in competition; cervical strain risk) |

---

### 3.15 Glute Contact with Bench (IPF Rule)

**Definition:** Hip-Y stability through the rep. Glutes must remain in contact (IPF Technical Rules, Causes for Disqualification of a Bench Press).

| Tier | Behaviour |
|---|---|
| Very Good | Hip-Y stable within ±1 cm |
| Good | 1–2 cm transient lift |
| Yellow Flag | 2–4 cm lift (gym-legal, not competition-legal) |
| Bad | 4–7 cm — clear glute rise |
| Very Bad | Full bridge / hips off bench |

---

### 3.16 Heel Contact / Foot Drive

**Definition:** Ankle-Y stability; for IPF rules feet must remain flat on the platform.

| Tier | Behaviour |
|---|---|
| Very Good | Feet flat, no slide, no lift |
| Good | Minor foot adjustment between reps only |
| Yellow Flag | Mid-rep foot creep < 3 cm horizontal |
| Bad | Heel lifts during press |
| Very Bad | Foot slides off platform OR full heel-up (legal in some federations, illegal in IPF) |

---

### 3.17 Lockout Completion

**Definition:** Elbow extension at the top of the rep + bar height stability.

| Tier | Behaviour |
|---|---|
| Very Good | Elbow 178–180°, bar still ≥ 0.5 s |
| Good | 173–178° |
| Yellow Flag | 168–173° (soft lockout) |
| Bad | 160–168° |
| Very Bad | < 160° or no detectable end of concentric |

---

## 4. Frontal / Overhead View Metrics

### 4.1 Grip Width

**Definition:** Distance between wrist landmarks, normalised by biacromial width (shoulder–shoulder distance from landmarks 11–12).

| Tier | Powerlifting (competition) | General / bodybuilding | Incline |
|---|---|---|---|
| Very Good | 165–200% biacromial AND ≤ 81 cm | 130–170% biacromial | 110–150% biacromial |
| Good | 150–165% or 81 cm cap touched | 115–130% or 170–185% | 100–110% or 150–170% |
| Yellow Flag | 130–150% or > 81 cm by ≤ 2 cm | 100–115% or 185–200% | 90–100% or 170–185% |
| Bad | < 130% or > 81 cm by 2–5 cm | < 100% or 200–220% | < 90% or > 185% |
| Very Bad | > 81 cm by > 5 cm (illegal) | > 220% (extreme injury risk) | > 200% |

Per IPF Technical Rules 2023: **"The spacing of the hands shall not exceed 81 cm measured between the forefingers (both forefingers must be within the 81 cm marks, and the whole of the forefingers must be in contact with the 81 cm marks if maximum grip is used). The use of the reverse grip is forbidden."**

### 4.2 Bar Tilt (One Side Higher)

**Definition:** Angle of the line between left and right wrists relative to horizontal, in the frontal plane.

| Tier | Tilt |
|---|---|
| Very Good | < 2° |
| Good | 2–4° |
| Yellow Flag | 4–7° |
| Bad | 7–12° |
| Very Bad | > 12° (potential red-light; strength asymmetry) |

### 4.3 Bar Path Symmetry L/R

**Definition:** Difference between left-wrist and right-wrist horizontal travel paths across the concentric phase. Computed as L2 distance between the left and right trajectories after spatial normalisation.

| Tier | Normalised path divergence |
|---|---|
| Very Good | < 2% bar-length |
| Good | 2–4% |
| Yellow Flag | 4–7% |
| Bad | 7–12% |
| Very Bad | > 12% — one arm dominating |

### 4.4 Elbow Flare Angle (Frontal Plane)

**Definition:** Angle between torso midline and humerus in the frontal plane at touch.

Use the **same thresholds as §3.7 Shoulder Abduction** — the head-end / overhead view provides the cleanest measurement of this metric (sagittal is approximate).

### 4.5 Wrist Alignment (No Lateral Break)

**Definition:** Lateral (ulnar/radial) deviation angle of the wrist relative to the forearm, frontal plane.

| Tier | Deviation |
|---|---|
| Very Good | < 5° |
| Good | 5–10° |
| Yellow Flag | 10–15° |
| Bad | 15–25° |
| Very Bad | > 25° (high wrist sprain risk) |

### 4.6 Hand Spacing Symmetry

**Definition:** Difference between left-hand and right-hand distance from bar centre.

| Tier | Asymmetry |
|---|---|
| Very Good | < 1 cm |
| Good | 1–2 cm |
| Yellow Flag | 2–4 cm |
| Bad | 4–7 cm |
| Very Bad | > 7 cm (red-flag for grip imbalance / dominant side) |

### 4.7 Bar Drift in Frontal Plane

**Definition:** Maximum lateral excursion of bar centre (wrist-midpoint) from a vertical line through the torso midline.

| Tier | Drift |
|---|---|
| Very Good | < 2 cm |
| Good | 2–4 cm |
| Yellow Flag | 4–7 cm |
| Bad | 7–12 cm |
| Very Bad | > 12 cm |

---

## 5. Posterior / Head-End View Metrics

(Camera at head end of bench, looking down body toward the feet.)

### 5.1 Bar Tilt Cross-Check
Same thresholds as §4.2; this view often gives cleaner detection because the bar is closer to the lens at lockout.

### 5.2 Shoulder Symmetry (Scapular Position Proxy)
Difference in Y-coordinate between left and right shoulder landmarks at touch.

| Tier | Vertical Y difference (normalised to biacromial width) |
|---|---|
| Very Good | < 3% |
| Good | 3–6% |
| Yellow Flag | 6–10% |
| Bad | 10–15% |
| Very Bad | > 15% |

### 5.3 Elbow Flare (Cleanest Angle)
Same thresholds as §3.7; head-end view is the primary measurement view.

### 5.4 Bar Path Centering Relative to Torso Midline

**Definition:** Lateral displacement of bar midpoint from the line connecting the head/nose to the hip-midpoint, in the head-end view.

| Tier | Offset |
|---|---|
| Very Good | < 1 cm |
| Good | 1–3 cm |
| Yellow Flag | 3–6 cm |
| Bad | 6–10 cm |
| Very Bad | > 10 cm |

---

## 6. Tempo & Control Metrics

### 6.1 Setup Time / Pre-Rep Tension

**Definition:** Time from un-rack (or grip on bar) to first descent. Should be deliberate; rushed setup correlates with loss of scapular retraction.

| Tier | Time |
|---|---|
| Very Good | 2–5 s, with visible breath + foot set |
| Good | 1–2 s or 5–8 s |
| Yellow Flag | < 1 s or 8–15 s |
| Bad | 15–25 s |
| Very Bad | > 25 s (loses oxygen/tightness) or zero (rush) |

### 6.2 Eccentric Tempo (Descent)

**Definition:** Time from start of descent (wrist-Y velocity goes negative) to touch.

| Tier | Time (working sets, RPE 6–10) |
|---|---|
| Very Good | 1.5–3.0 s (controlled) |
| Good | 1.0–1.5 s or 3.0–4.0 s |
| Yellow Flag | 0.7–1.0 s or 4.0–6.0 s |
| Bad | 0.4–0.7 s or > 6.0 s |
| Very Bad | < 0.4 s (free-fall / drop) |

McLaughlin & Madsen (1984, *NSCA Journal* 6(4):44, "Bench press techniques of elite heavyweight powerlifters") found that **"the world class powerlifters moved the bar more slowly throughout the exercise and kept the bar more directly over the shoulder during the lift phase"** — slower descent reduces the force needed to arrest the bar.

### 6.3 Pause at Chest (Duration & Stillness)
See §3.9.

### 6.4 Concentric Tempo (Press to Lockout)

**Definition:** Time from end-of-pause (or touch, for touch-and-go) to lockout. Use velocity-based thresholds rather than wall-clock for max-effort sets.

| Tier | 1RM / heavy | Hypertrophy (RPE 7–9) |
|---|---|---|
| Very Good | Smooth, no stalls; MCV ≥ 0.15 m/s at 1RM | 1.0–2.0 s |
| Good | MCV 0.12–0.15 m/s | 0.7–1.0 s or 2.0–3.0 s |
| Yellow Flag | MCV 0.08–0.12 m/s (grinder) | < 0.7 s or 3.0–5.0 s |
| Bad | MCV < 0.08 m/s | > 5.0 s |
| Very Bad | Stall > 2 s at any point | Stalls / fails |

González-Badillo & Sánchez-Medina (2010, *Int J Sports Med* 31:347–352, n = 120 strength-trained men): **"A very close relationship between mean propulsive velocity and load (%1RM) was observed (R² = 0.98). Mean velocity attained with 1RM was 0.16 ± 0.04 m·s⁻¹."** Approximate load-velocity points: 90% 1RM ≈ 0.31 m/s; 80% ≈ 0.47 m/s; 70% ≈ 0.62 m/s; 60% ≈ 0.79 m/s; 50% ≈ 0.92 m/s.

### 6.5 Lockout Hold Quality

| Tier | Hold |
|---|---|
| Very Good | Bar still ≥ 0.5 s with elbows locked, in line with shoulders |
| Good | 0.3–0.5 s |
| Yellow Flag | 0.1–0.3 s (rushed re-rack) |
| Bad | No detectable hold |
| Very Bad | Bar still moving when re-racked |

### 6.6 Sticking Point Analysis

**Definition:** Position of minimum concentric velocity (vmin) as % of total concentric ROM, and the depth/duration of the sticking region (vmax1 → vmin).

Per van den Tillaar & Ettema (2010, *J Sports Sci* 28(5):529–535): **"All participants showed a sticking period during the upward movement that started about 0.2 s after the initial upward movement, and lasted about 0.9 s."** Per van den Tillaar et al. (2012): sticking begins ~2–6 cm above the chest and ends ~11 cm above the chest. Per Martínez-Cava et al. (2019): at 1RM, the sticking region spans approximately 12.7% → 42% of ROM.

| Tier | Sticking duration at 1RM |
|---|---|
| Very Good | < 0.6 s |
| Good | 0.6–0.9 s |
| Yellow Flag | 0.9–1.3 s |
| Bad | 1.3–2.0 s |
| Very Bad | > 2.0 s (failed rep imminent) |

### 6.7 Bouncing Detection (Bar-Off-Chest)

**Definition:** Acceleration spike at touch frame. Tag as bounce if |a| > 25 m/s² and the bar reverses within 100 ms with no detectable pause.

| Tier | Bounce |
|---|---|
| Very Good | No bounce; smooth reversal |
| Good | Imperceptible (< 100 ms reversal, low amplitude) |
| Yellow Flag | Mild bounce (touch-and-go ambiguous) |
| Bad | Clear bounce, audible chest contact |
| Very Bad | Sternum-bounce drives bar upward — sternum/rib injury risk |

### 6.8 Rep-to-Rep Consistency

**Definition:** Coefficient of variation (CV) of touch-point, bar path, and concentric time across the set.

| Tier | CV (touch-point Y) |
|---|---|
| Very Good | < 3% |
| Good | 3–6% |
| Yellow Flag | 6–10% |
| Bad | 10–15% |
| Very Bad | > 15% |

---

## 7. Composite Scoring System

### Step 1 — Convert Each Raw Metric to a 0–100 Sub-Score

For metric *m*, find the tier the value falls in, then linearly interpolate inside that tier's score band:

```
sub_score = lower_band + (upper_band - lower_band) × (1 - |value - tier_center| / tier_half_width)
```

Score bands per tier: Very Good 90–100 / Good 75–89 / Yellow 60–74 / Bad 40–59 / Very Bad 0–39.

For two-sided metrics with an optimal midpoint (e.g. shoulder abduction 50°), interpolate from the centre of the Very-Good range outward.

### Step 2 — Apply Category Weights

| Category | Weight | Rationale |
|---|---|---|
| **Safety** | **40%** | Bengtsson, Berglund & Aasa (2018, *BMJ Open Sport Exerc Med* 4:e000382, narrative review of 39 studies) reported that **"subelite to elite lifters report that 22%–32% of their injuries are related to the squat, 18%–46% to the bench press and 12%–31% to the deadlift"** — bench has the highest injury attribution among the three powerlifts. Strömbäck et al. (2018, Swedish subelite powerlifters, n = 104) found **70% currently injured** and **56.3% of current shoulder injuries started during bench-press training** (OR 4.84; 95% CI 1.42–16.51). Bak, Cameron & Henderson (2000) meta-analysis: bench press is the most common activity causing pectoralis major rupture (> 50% of athletic cases). |
| **Technique** | 35% | Determines force transfer and long-term progression |
| **Performance** | 25% | Bar speed, ROM completion, sticking-point management |

**Within-category metric weights** (sum to 100 per category):

**Safety (40% global)**
| Metric | Weight |
|---|---|
| Shoulder abduction / elbow flare | 20 |
| Bar drift toward neck (touch-point safety) | 15 |
| Loss of scapular retraction | 13 |
| Bouncing detection | 12 |
| Wrist hyperextension | 10 |
| Press symmetry L/R | 10 |
| Bar tilt | 8 |
| Head position | 6 |
| Glute contact | 6 |
| **Total** | **100** |

**Technique (35% global)**
| Metric | Weight |
|---|---|
| Bar path J-curve | 15 |
| Touch point on chest | 12 |
| Forearm vertical at touch | 12 |
| Elbow angle at bottom | 8 |
| Grip width | 8 |
| Arch height (style-appropriate) | 8 |
| Bar path symmetry L/R | 8 |
| Rep-to-rep consistency | 8 |
| Bar wobble / control | 6 |
| Wrist alignment (frontal) | 6 |
| Hand spacing symmetry | 4 |
| Heel contact / drive | 5 |
| **Total** | **100** |

**Performance (25% global)**
| Metric | Weight |
|---|---|
| Concentric mean velocity | 22 |
| Sticking-point duration | 16 |
| Lockout completion | 14 |
| Pause / touch-and-go quality | 14 |
| ROM completion | 12 |
| Eccentric tempo (controlled) | 10 |
| Setup time | 6 |
| Lockout hold | 6 |
| **Total** | **100** |

### Step 3 — Compute Composite Score

**Default (weighted arithmetic mean):**

```
Composite = 0.40 · S_safety + 0.35 · S_tech + 0.25 · S_perf
```
where each S_x is itself the weighted mean of its within-category sub-scores.

**Alternative (geometric mean):**
```
Composite_geo = S_safety^0.40 · S_tech^0.35 · S_perf^0.25
```
The geometric mean penalises any one weak category disproportionately — useful when "safety must never be compensated by performance."

### Step 4 — Hard-Fail Safety Overrides

Any of these conditions caps the composite at the indicated ceiling, regardless of the weighted mean:

| Trigger | Cap | Label override |
|---|---|---|
| Shoulder abduction > 90° (extreme flare) | ≤ 45 | "Bad" minimum |
| Bar drifts toward neck (touch-point above clavicle on flat, into throat on incline) | ≤ 35 | "Very Bad" |
| Sternum bounce (peak |a| > 35 m/s² at touch with no pause) | ≤ 45 | "Bad" |
| Loss of scapular retraction (shoulder Y drift > 7 cm) | ≤ 50 | "Bad" |
| Wrist hyperextension > 45° under load | ≤ 50 | "Bad" |
| Head lifts > 7 cm off bench | ≤ 55 | "Bad" |
| Glute lifts > 7 cm off bench | ≤ 55 | "Bad" |
| Press asymmetry > 20° (one side higher) | ≤ 40 | "Bad" |
| Bar tilt > 15° at any frame | ≤ 50 | "Bad" |
| Bar dropped uncontrolled (eccentric < 0.4 s, no deceleration) | ≤ 30 | "Very Bad" |

Multiple overrides → take the lowest cap.

### Step 5 — Per-Set Aggregation

| Aggregation | Use |
|---|---|
| **Mean of reps** | Default — describes general set quality |
| **Worst rep** | Safety-critical signal — surfaces breakdown |
| **Last 3 reps** | Fatigue-sensitive — captures form degradation on AMRAP / RPE 9–10 sets |
| **Median** | Robust to a single anomalous rep |

Recommended display: show mean + worst, and flag "fatigue drift" if last-3 mean is ≥ 10 points below first-3 mean.

---

## 8. Grade & Label Mapping

| Score Range | Grade | Label |
|---|---|---|
| 90–100 | **A** | Very Good |
| 75–89 | **B** | Good |
| 60–74 | **C** | Yellow Flag |
| 40–59 | **D** | Bad |
| 0–39 | **E** | Very Bad |

---

## 9. Alternative Naming Schemes

| Scheme | Very Good | Good | Yellow Flag | Bad | Very Bad |
|---|---|---|---|---|---|
| **Traffic light** | Green | Light green | Yellow | Orange | Red |
| **Sports tier** | Elite | Advanced | Intermediate | Novice | Untrained |
| **Coaching** | Competition-ready | Polished | Needs work | Major flaw | Stop and reset |
| **Medical / PT** | Asymptomatic | Low risk | Watch | Symptomatic | High injury risk |
| **Risk** | Negligible | Low | Moderate | High | Critical |
| **Tier list** | S | A | B | C | D |
| **Belt system** | Black | Brown | Blue | Yellow | White |
| **Stars** | ★★★★★ | ★★★★ | ★★★ | ★★ | ★ |
| **Olympic** | Gold | Silver | Bronze | Participant | DNF |
| **Descriptive** | Textbook | Solid | Acceptable | Poor | Dangerous |
| **Percentile** | 90–100th | 75–89th | 60–74th | 40–59th | 0–39th |
| **Academic** | A | B | C | D | F |
| **Quality** | Excellent | Good | Fair | Poor | Unacceptable |
| **Weather** | Sunny | Partly cloudy | Overcast | Storm | Severe |
| **Animals** | Lion | Wolf | Deer | Sheep | Newborn |
| **Heat** | Cool | Warm | Hot | Burning | Scorched |
| **Powerlifting cue** | "Three white lights" | "Mostly clean" | "Borderline call" | "Red light" | "DQ / dump" |

---

## 10. Worked Example

**Scenario:** Male intermediate lifter, paused flat bench, working set @ 85% 1RM, rep 3 of 5.

**Raw metrics → sub-scores:**

| Metric | Raw value | Tier | Sub-score |
|---|---|---|---|
| Bar path horizontal | 9 cm back-and-up | Very Good | 93 |
| Touch point | 78% torso (just below sternum) | Very Good | 91 |
| Forearm vertical at touch | 7° | Good | 82 |
| Elbow angle at bottom | 72° | Very Good | 95 |
| Elbow angle at lockout | 176° | Very Good | 92 |
| Shoulder flexion at bottom | 80° | Very Good | 94 |
| Shoulder abduction (flare) | 68° | Good | 81 |
| Wrist position | 18° extension | Good | 76 |
| Bar pause quality | 0.6 s, clean | Good | 84 |
| Bar wobble | 1.4 cm RMS | Good | 86 |
| Arch height | 14% torso (PL style) | Very Good | 92 |
| Scapular retraction | 1.5 cm shoulder Y drift | Good | 85 |
| Head position | < 2 cm lift | Good | 88 |
| Glute contact | Stable | Very Good | 96 |
| Heel contact | Stable | Very Good | 95 |
| Lockout completion | 176° + 0.6 s hold | Very Good | 91 |
| Grip width | 78 cm (under 81 cm cap) | Very Good | 93 |
| Bar tilt | 3° | Good | 83 |
| Bar path symmetry L/R | 3% divergence | Good | 81 |
| Hand spacing symmetry | 1.2 cm | Good | 82 |
| Bar drift frontal | 3 cm | Good | 80 |
| Setup time | 4 s | Very Good | 95 |
| Eccentric tempo | 2.3 s | Very Good | 93 |
| Concentric tempo (MCV) | 0.22 m/s @ 85% 1RM | Good | 84 |
| Sticking point duration | 0.7 s | Good | 87 |
| Bouncing detection | None | Very Good | 97 |
| Rep-to-rep consistency | 4% CV | Good | 85 |

**Category aggregates** (weighted means within category):
- Safety: ~ **87**
- Technique: ~ **86**
- Performance: ~ **88**

**Composite (arithmetic):**
`0.40 · 87 + 0.35 · 86 + 0.25 · 88 = 34.8 + 30.1 + 22.0 = 86.9 ≈ 87`

**Override checks:**
- All safety triggers clear → no cap applied.

**Final score: 87 → Grade B → "Good"**

**Two lowest sub-scores to surface as feedback:**
1. **Wrist position (76)** — wrist extension at touch is 18°; cue lifter to grip lower in the palm and squeeze the bar harder.
2. **Bar drift frontal (80)** — 3 cm lateral excursion; cue equal hand pressure and "bend the bar in half."

---

## 11. Practical Notes & Caveats

### 11.1 Anthropometry Effects

| Trait | Effect |
|---|---|
| **Long arms relative to torso** | Longer bar path; deeper sticking region; benefits more from wider grip; will touch lower on chest at equal grip width |
| **Short arms** | Shorter ROM; easier mechanical leverage; can touch higher; close-grip favoured |
| **Deep chest (high ribcage)** | Reduces ROM by raising the touch point; often allows higher bench numbers |
| **Shallow chest** | Larger ROM; harder bottom position |
| **Limited shoulder external-rotation mobility** | Forces narrower grip and more tucked elbows; flaring is unsafe for these lifters |
| **Limited shoulder flexion mobility** | Impairs incline more than flat; may force shallower incline angles (20–30° rather than 45°) |

### 11.2 Powerlifting vs Bodybuilding Style

| Feature | Powerlifting | Bodybuilding |
|---|---|---|
| Touch point | Low sternum / xiphoid | Mid sternum / nipple line |
| Elbow flare | 30–50° (tucked) | 60–80° |
| Arch | Maximal allowed | Minimal |
| Grip | Wide (cap 81 cm IPF) | Moderate (≤ 1.5 biacromial) |
| Pause | Required | Optional |
| ROM | Minimised | Maximised |
| **Apply which thresholds?** | PL columns | BB columns |

**Critical:** Do not score a bodybuilder against PL thresholds (will under-score arch and grip width) or vice versa.

### 11.3 Continuous Tracking vs Single-Frame

Always compute metrics as time-series, then aggregate to per-rep values. Single-frame snapshots miss the most diagnostically rich data (bar path shape, sticking-point depth, deceleration spike).

### 11.4 Calibration Importance

For absolute measurements (cm of bar travel, °/m of arch), the camera must be calibrated:
- Use the **bar length** (men's bar = 220 cm sleeve-to-sleeve; women's bar = 201 cm) as a scale reference.
- Or use **plate diameter** (45 lb / 20 kg = 450 mm).
- Without calibration, only ratios and angles are reliable; absolute distances are not.

### 11.5 Always Surface the Reason

A composite score alone is unhelpful coaching feedback. Always display:
1. Score + grade + label
2. Top 2 lowest sub-scores
3. The actual numerical value of the worst metric (e.g., "shoulder abduction 88° — target ≤ 75°")
4. Whether a safety override was applied

### 11.6 Style-Specific Scoring

Tag the lifter or session with a style flag (PL / BB / Recovery / Incline) and apply the matching threshold columns. The incline column applies regardless of style.

### 11.7 Minimum-Viable Metric Priority

If you can only compute three metrics, choose:
1. **Touch-point on chest** (proxy for everything — grip, ROM, elbow, safety)
2. **Bar path J-curve horizontal displacement**
3. **Shoulder abduction / elbow flare angle**

If you can add three more:
4. Forearm vertical at touch
5. Lockout completion
6. Pause quality / sticking-point duration

### 11.8 Frame-Rate Tradeoffs

| FPS | Adequate for |
|---|---|
| 30 | Slow technique work, walk-through reps |
| 60 | Hypertrophy and most working sets |
| 120 | Max-effort singles, sticking-point analysis, bounce detection |
| 240+ | Research; sub-frame velocity reconstruction |

Most consumer phones do 60 fps at 1080p reliably and 120 fps in dedicated slow-mo mode.

### 11.9 Camera Occlusion Challenges

The bar **physically blocks the camera's view** of the face and chest from overhead and head-end angles during much of the lift. Mitigations:
- Always pair an overhead camera with a sagittal one.
- Use bar-tracking from coloured markers when wrist landmarks vanish under plates.
- Drop frames with combined wrist + shoulder visibility < 0.5 from the metric averages.

---

## 12. MediaPipe Pose Implementation Guide

### 12.1 MediaPipe Pose Landmark Reference

MediaPipe BlazePose outputs **33 landmarks** with (x, y, z, visibility, presence). Per the Google Research blog post on BlazePose (CV4ARVR @ CVPR 2020), the model also "predicts the midpoint of a person's hips, the radius of a circle circumscribing the whole person, and the incline angle of the line connecting the shoulder and hip midpoints" — convenient since the incline angle is exactly what we need for bench-angle calibration.

| # | Name | BP Relevance |
|---|---|---|
| 0 | Nose | **Head position** monitoring |
| 1 | Left eye (inner) | Face stability |
| 2 | Left eye | Face stability |
| 3 | Left eye (outer) | Face stability |
| 4 | Right eye (inner) | Face stability |
| 5 | Right eye | Face stability |
| 6 | Right eye (outer) | Face stability |
| 7 | Left ear | – |
| 8 | Right ear | – |
| 9 | Mouth (left) | – |
| 10 | Mouth (right) | – |
| **11** | **Left shoulder** | ★ Scapular position, shoulder angle, torso ref |
| **12** | **Right shoulder** | ★ Scapular position, shoulder angle, torso ref |
| **13** | **Left elbow** | ★ Elbow angle, flare |
| **14** | **Right elbow** | ★ Elbow angle, flare |
| **15** | **Left wrist** | ★ Bar proxy, bar path |
| **16** | **Right wrist** | ★ Bar proxy, bar path |
| 17 | Left pinky | Grip estimation |
| 18 | Right pinky | Grip estimation |
| 19 | Left index | Grip estimation |
| 20 | Right index | Grip estimation |
| 21 | Left thumb | Grip estimation |
| 22 | Right thumb | Grip estimation |
| **23** | **Left hip** | ★ Torso ref, arch, glute lift |
| **24** | **Right hip** | ★ Torso ref, arch, glute lift |
| **25** | **Left knee** | Leg drive |
| **26** | **Right knee** | Leg drive |
| **27** | **Left ankle** | ★ Heel contact, foot drive |
| **28** | **Right ankle** | ★ Heel contact, foot drive |
| 29 | Left heel | Heel contact (preferred over ankle) |
| 30 | Right heel | Heel contact (preferred over ankle) |
| 31 | Left foot index | Foot stability |
| 32 | Right foot index | Foot stability |

### 12.2 Derived Reference Points

| Point | Formula |
|---|---|
| **Wrist centre (bar proxy)** | `WC = (P15 + P16) / 2` |
| **Shoulder centre** | `SC = (P11 + P12) / 2` |
| **Hip centre** | `HC = (P23 + P24) / 2` |
| **Elbow midpoint** | `EM = (P13 + P14) / 2` |
| **Torso vector** | `T = SC - HC` |
| **Biacromial width** | `BAW = ‖P11 - P12‖` |
| **Bench plane reference (flat)** | Line through hip-centre and shoulder-centre at setup frame (proxy — actual bench is below the body) |
| **Bench-angle estimate (incline)** | `θ_bench = atan2(SC_y − HC_y, SC_x − HC_x)` after the lifter is settled; should be ≈ 30–45° for incline |
| **Bar tilt angle** | `atan2(P16_y − P15_y, P16_x − P15_x)` |
| **Body-relative vertical axis** | Unit vector perpendicular to bench plane (rotate gravity vector by −θ_bench) |

### 12.3 General Computational Principles

#### 12.3.1 Visibility Filtering
Use only landmarks with `visibility ≥ 0.5` and `presence ≥ 0.5`. For paired left/right landmarks, prefer the side closer to the camera (higher average visibility). For ambiguous frames, interpolate from neighbouring frames.

#### 12.3.2 Side Selection
For sagittal-view sessions, identify the "near" side at the first frame (higher shoulder visibility) and consistently use that side for shoulder, elbow, wrist throughout. For overhead, use both sides symmetrically.

#### 12.3.3 Phase Detection for Bench Press

Define wrist-centre Y as W_y(t). Note: in image coordinates, +Y typically points **downward**, so "high in the air" = low Y. Use the convention where bench-relative "up" is positive.

| Phase | Definition |
|---|---|
| Setup | Velocity ≈ 0 at high W_y position, before any descent |
| Unrack | Brief horizontal-then-down transition (W_x changes faster than W_y) |
| Descent (eccentric) | dW_y/dt < 0 (bench-up convention); ends when velocity returns to 0 at minimum height |
| Touch | W_y reaches minimum AND visible chest proximity (W_y within ~5–10 cm of shoulder-Y in bench coordinates) |
| Pause | |dW_y/dt| < 0.05 m/s sustained at minimum W_y |
| Concentric (press) | dW_y/dt > 0 from touch to lockout |
| Lockout | W_y at maximum AND elbow angle > 170° |

For incline: **transform all coordinates into bench-relative frame first** by rotating by −θ_bench; then the same logic applies.

#### 12.3.4 2D vs 3D
BlazePose returns z-coordinates but they are **less reliable** than x and y, especially for supine subjects. Default to 2D analysis from the sagittal view. Use z only for sanity checks (sign of bar drift) and never for absolute distance.

#### 12.3.5 Bench-Angle Calibration
Two approaches:
1. **Static frame calibration:** before the lifter starts the rep, capture a frame and compute `θ_bench = atan2(SC_y − HC_y, SC_x − HC_x)`. Apply this rotation throughout the session.
2. **External calibration:** if the bench's seat-back is visible, fit a line to its edge using classical CV (Hough transform) once.

For flat bench, θ_bench ≈ 0; for incline, expect 25–50°.

### 12.4 Foundational Math Operations

```text
angle_between(u, v) = acos( clip( dot(u,v) / (|u| · |v|), -1, 1 ) ) · 180/π

three_point_angle(A, B, C) = angle_between(A − B, C − B)
    // returns the angle at vertex B

distance(A, B) = ‖A − B‖
```

**Bench-perpendicular projection (for J-curve):**
Given the bench-tilt angle θ:
```
R = [[cos θ, sin θ], [-sin θ, cos θ]]
W_bench = R · (W − HC)
// W_bench.y = perpendicular distance from bench surface
// W_bench.x = along-bench distance (horizontal in flat; sliding in incline)
```

**Forearm-vertical (gravity-relative):**
```
gravity = [0, 1]  // image-down
forearm = wrist − elbow
θ_FV = acos( dot(forearm, gravity) / ‖forearm‖ ) · 180/π
// θ_FV = 0 means forearm points straight down (vertical)
```

### 12.5 Per-Metric Computation Guide

#### 12.5.1 Bar Path J-Curve
- **Landmarks:** 15, 16 → WC
- **Vectors:** WC trajectory through time
- **Compute:** `horizontal_displacement = max(WC_x(t)) − min(WC_x(t))` during concentric, signed toward the head. Decompose: `path_horizontal = WC_x(t) − WC_x(touch)`; `path_vertical = WC_y(t) − WC_y(touch)`.
- **Track:** entire (x, y) trace; classify shape via curvature.
- **Caveats:** Wrist drifts on the bar; coloured bar markers improve accuracy.

#### 12.5.2 Touch Point on Chest
- **Landmarks:** 15/16 (wrist), 11/12 (shoulder), 23/24 (hip), nose
- **Compute:** At the touch frame, compute `(WC_y − SC_y) / (HC_y − SC_y)` in bench-relative coordinates. 0% = at shoulder line; 100% = at hip line. Suprasternal notch ≈ 5–10% above shoulder line; xiphoid ≈ 30–40% down.
- **Caveats:** Sternum landmarks not directly available; use proportional torso reference. Calibrate per-lifter if possible.

#### 12.5.3 Forearm Vertical at Touch
- **Landmarks:** 13/14 (elbow), 15/16 (wrist)
- **Compute:** `θ_FV = angle_between(wrist − elbow, gravity)` at the touch frame; for incline, **use bench-perpendicular axis** instead of gravity if you want bench-relative interpretation.
- **Track:** also compute across the entire concentric — should remain near vertical through the sticking region for efficient leverage.

#### 12.5.4 Elbow Angle
- **Landmarks:** 11/12, 13/14, 15/16
- **Compute:** `three_point_angle(shoulder, elbow, wrist)` at touch and at lockout.

#### 12.5.5 Shoulder Abduction / Elbow Flare
- **Landmarks:** 11/12, 13/14, 23/24
- **Compute:** Best from overhead or head-end. In frontal view: angle between torso-midline vector (HC → SC) and humerus vector (shoulder → elbow), in the frontal plane.
- **Caveats:** From sagittal view alone, this is approximate (depth ambiguity); pair with overhead.

#### 12.5.6 Wrist Position
- **Landmarks:** 13/14 (elbow), 15/16 (wrist), 19/20 (index) or 21/22 (thumb)
- **Compute:** `three_point_angle(elbow, wrist, index_finger)`. Subtract 180° to get signed extension/flexion.
- **Caveats:** Finger landmarks have lower presence; if both visibility < 0.5, mark metric as N/A.

#### 12.5.7 Bar Pause Quality
- **Landmarks:** 15/16 → WC
- **Compute:** detect contiguous frames near W_y minimum (within 1 cm) and |dW_y/dt| < 0.05 m/s. Duration = number of such frames / fps.

#### 12.5.8 Touch-and-Go Quality
- **Compute:** `a_max = max(|d²W_y/dt²|)` in the 100 ms window around touch (after low-pass at 6 Hz).

#### 12.5.9 Bar Wobble
- **Compute:** RMS lateral deviation of WC from a polynomial fit to the bar path during the concentric.

#### 12.5.10 Arch Height (Hard Problem)
- **Landmarks:** 11/12, 23/24 → SC, HC
- **Compute:** Without bench-surface detection, the bench plane is approximated as the line through SC and HC at the **setup** frame (before the lifter arches and props ribs). Compare to the position of the rib cage during the lift. Since BlazePose has no rib-cage landmark, use the perpendicular displacement of SC from the bench-line proxy. Alternative: place a fiducial marker on the bench surface.
- **Caveats:** Approximate at best — disclose this limitation in any output. The most diagnostic signal is *change* across reps, not absolute arch.

#### 12.5.11 Scapular Retraction
- **Landmarks:** 11/12
- **Compute:** stability of SC position across the rep. Track `SC_y(t)` standard deviation and the trend across reps. Loss of retraction shows as SC rising (shoulders shrugging) or SC moving anteriorly (in z, where reliable).
- **Caveats:** MediaPipe has **no scapular landmarks** — this is a proxy only.

#### 12.5.12 Head Position
- **Landmarks:** 0 (nose)
- **Compute:** track `Nose_y − SC_y` deviation from setup-frame baseline. Threshold lifts > 2 cm (Yellow), > 7 cm (Bad).

#### 12.5.13 Glute Contact
- **Landmarks:** 23/24 → HC
- **Compute:** `HC_y(t)` deviation from setup-frame baseline. In IPF, any unambiguous lift = no-lift.

#### 12.5.14 Heel Contact
- **Landmarks:** 29/30 (heel) or 27/28 (ankle)
- **Compute:** heel-Y stability throughout. Threshold: > 1 cm lift detection.

#### 12.5.15 Lockout Completion
- **Compute:** elbow angle at peak W_y; combine with hold-duration metric.

#### 12.5.16 Grip Width
- **Landmarks:** 15, 16, 11, 12
- **Compute:** `‖P15 − P16‖ / ‖P11 − P12‖` = grip-to-biacromial ratio. Convert to cm using bar-length calibration if absolute width is needed.

#### 12.5.17 Bar Tilt
- **Landmarks:** 15, 16
- **Compute:** `atan2(P16_y − P15_y, P16_x − P15_x)` in frontal plane.

#### 12.5.18 Bar Path Symmetry L/R
- **Landmarks:** 15, 16
- **Compute:** normalise each wrist trajectory by torso length; compute pointwise Euclidean distance across the rep; integrate / sum.

#### 12.5.19 Bar Centre Relative to Torso
- **Landmarks:** 15, 16, 0, 23, 24
- **Compute:** lateral distance from WC to the line (Nose → HC) in head-end view.

#### 12.5.20 Bar Speed / MCV
- **Landmarks:** 15/16 → WC
- **Compute:** `MCV = mean(dW_y/dt)` during concentric. Calibrate units via bar length.

#### 12.5.21 Sticking-Point Detection
- **Compute:** find vmax1 (first local maximum of upward velocity after touch); find vmin (first local minimum after vmax1); sticking_duration = t(vmin) − t(vmax1); sticking_position = (W_y(vmin) − W_y(touch)) / (W_y(lockout) − W_y(touch)).

#### 12.5.22 Bouncing Detection
- **Compute:** look for acceleration spike at touch in the 50–150 ms window. If |a| > 25 m/s² AND no flat-velocity pause window detected → flag bounce.

### 12.6 Sample Pipeline (Conceptual Flow)

```
1. Capture video (≥ 60 fps, sagittal primary + overhead optional)
2. Run MediaPipe Pose Landmarker per frame → 33 landmarks × N frames
3. Filter visibility (drop or interpolate low-confidence landmarks)
4. Calibrate:
     - Detect bar length in pixels (manual or auto via plate detection) → pixels/cm
     - Detect bench angle θ_bench from setup frame
5. Build derived points: WC, SC, HC, EM
6. Transform to bench-relative coordinates (rotate by −θ_bench)
7. Detect phases (setup → unrack → eccentric → touch → pause → concentric → lockout)
8. Per phase / per rep, compute every metric in §12.5
9. Convert raw metric → tier → sub-score (linear interpolation)
10. Apply category weights → category scores
11. Apply hard-fail safety overrides
12. Aggregate per-set (mean / worst / last-3)
13. Render: composite score + grade + label + top-2 feedback metrics
```

### 12.7 Known Limitations of MediaPipe for Bench Press

| Limitation | Impact | Mitigation |
|---|---|---|
| **Supine pose detection less reliable** than upright (BlazePose training data is dominated by standing poses; Google Research notes the model handles "specific yoga asanas" but bench-press supine is a known weak spot) | Landmark jitter higher, especially around face/shoulders | Bench-relative coordinate frame; low-pass smoothing (Butterworth, 6 Hz) |
| **No bar detection** — wrist used as proxy | Hands can shift on bar, especially with thumbless grip; bar-tilt and bar-symmetry suffer | Add coloured bar markers + classical CV detector; or use both wrists' midpoint |
| **No scapular landmarks** | Scapular retraction (foundation of safe benching) is unmeasurable directly — Noteboom et al. (2024) note that "the traditional flat bench press may limit scapular movement and disrupt normal scapulohumeral rhythm, particularly by restricting scapular retraction" | Proxy via shoulder-Y stability and anterior drift; disclose limitation |
| **Bench plane not detected** | Arch-height and bench-angle metrics are approximate | Place fiducial markers on bench; or accept proportional rather than absolute values |
| **Bar / face occlusion** | Frequent visibility drops on head-end and overhead views | Multi-camera fusion; visibility-weighted interpolation |
| **Lumbar / thoracic spine not tracked** | Arch height is an inferred metric | Same — disclose |
| **Z-axis unreliable** | 3D shoulder-abduction estimates noisy | Use frontal + sagittal fusion instead of single-view 3D |
| **Frame-rate hunger** | 30 fps misses bounce events and sticking-point structure | Run at ≥ 60 fps; 120 fps for max effort |
| **Lateral camera critical** | Overhead/head-end has severe bar occlusion | Always have a sagittal camera as primary; treat others as supplementary |
| **Detection fails when face is obscured** by the bar at lockout | Frames may briefly lose all landmarks | Track across, interpolate, and re-acquire post-lockout |

---

## 13. Appendix — Metric Summary Table

| # | Metric | Primary View | Type | Default Weight (within category) | Category | Flat | Incline |
|---|---|---|---|---|---|---|---|
| 1 | Bar path J-curve | Sagittal | Continuous, 1-sided | 15 | Technique | ✓ | ✓ (smaller) |
| 2 | Touch point on chest | Sagittal | Continuous, 2-sided | 12 | Technique | ✓ | ✓ (different range) |
| 3 | Forearm vertical at touch | Sagittal | Continuous, 1-sided | 12 | Technique | ✓ | ✓ |
| 4 | Elbow angle at bottom | Sagittal | Continuous, 2-sided | 8 | Technique | ✓ | ✓ |
| 5 | Elbow angle at lockout | Sagittal | Continuous, 1-sided | 14 | Performance | ✓ | ✓ |
| 6 | Shoulder flexion at bottom | Sagittal | Continuous, 2-sided | 8 | Technique | ✓ | ✓ |
| 7 | Shoulder abduction / flare | Posterior + Sagittal | Continuous, 2-sided | 20 | Safety | ✓ | ✓ |
| 8 | Wrist flexion/extension | Sagittal | Continuous, 1-sided | 10 | Safety | ✓ | ✓ |
| 9 | Bar pause duration & stillness | Sagittal | Continuous, 1-sided | 14 (paused) | Performance | ✓ | optional |
| 10 | Touch-and-go quality | Sagittal | Continuous, 1-sided | 14 (TnG) | Performance | ✓ | ✓ |
| 11 | Bar wobble | Sagittal | Continuous, 1-sided | 6 | Technique | ✓ | ✓ |
| 12 | Arch height | Sagittal | Continuous, 2-sided (style) | 8 | Technique | ✓ | reduced |
| 13 | Scapular retraction maintenance | Sagittal + Posterior | Continuous, 1-sided | 13 | Safety | ✓ | ✓ |
| 14 | Head position | Sagittal | Continuous, 1-sided | 6 | Safety | ✓ | ✓ |
| 15 | Glute contact | Sagittal | Continuous, 1-sided | 6 | Safety | ✓ | n/a (seated incline) |
| 16 | Heel contact / drive | Sagittal | Continuous, 1-sided | 5 | Technique | ✓ | ✓ |
| 17 | Lockout completion | Sagittal | Continuous, 1-sided | 14 | Performance | ✓ | ✓ |
| 18 | Grip width | Overhead | Continuous, 2-sided | 8 | Technique | ✓ | ✓ |
| 19 | Bar tilt | Overhead + Posterior | Continuous, 1-sided | 8 | Safety | ✓ | ✓ |
| 20 | Bar path symmetry L/R | Overhead | Continuous, 1-sided | 8 (tech) + 10 (safety) | Technique + Safety | ✓ | ✓ |
| 21 | Wrist alignment (frontal) | Overhead | Continuous, 1-sided | 6 | Technique | ✓ | ✓ |
| 22 | Hand spacing symmetry | Overhead | Continuous, 1-sided | 4 | Technique | ✓ | ✓ |
| 23 | Bar drift frontal | Overhead | Continuous, 1-sided | 15 | Safety | ✓ | ✓ |
| 24 | Bar centre vs torso midline | Posterior | Continuous, 1-sided | folded into 23 | Safety | ✓ | ✓ |
| 25 | Setup time | Sagittal | Continuous, 2-sided | 6 | Performance | ✓ | ✓ |
| 26 | Eccentric tempo | Sagittal | Continuous, 2-sided | 10 | Performance | ✓ | ✓ |
| 27 | Concentric tempo / MCV | Sagittal | Continuous, 1-sided | 22 | Performance | ✓ | ✓ |
| 28 | Lockout hold | Sagittal | Continuous, 1-sided | 6 | Performance | ✓ | ✓ |
| 29 | Sticking-point duration | Sagittal | Continuous, 1-sided | 16 | Performance | ✓ | ✓ |
| 30 | Bouncing detection | Sagittal | Categorical | 12 | Safety | ✓ | ✓ |
| 31 | Rep-to-rep consistency | Sagittal | Continuous, 1-sided | 8 | Technique | ✓ | ✓ |
| 32 | ROM completion | Sagittal | Continuous, 1-sided | 12 | Performance | ✓ | ✓ |

> Where a metric appears in two categories (e.g. bar path symmetry contributes to both Technique and Safety), the within-category weights given above apply separately in each category — the metric contributes to both safety and technique sub-scores in the per-category weighted means.

---

*End of document. Save as `bench_press_assessment.md`.*