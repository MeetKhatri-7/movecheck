# Biomechanical Assessment System — Standing Barbell Military Press (OHP) & Seated Dumbbell Shoulder Press

> **Document 5 of 5** in a parallel series with the squat, deadlift, flat/incline bench, and pull-up references. Same structure, same depth, same MediaPipe-implementation rigor — adapted for vertical pressing.

---

## Table of Contents
1. Required Camera Angles
2. Military Press vs Seated DB Shoulder Press — Key Differences
3. Sagittal (Side) View Metrics
4. Frontal (Anterior) View Metrics
5. Posterior (Rear) View Metrics
6. Tempo & Control Metrics
7. Composite Scoring System
8. Grade & Label Mapping
9. Alternative Naming Schemes
10. Worked Example
11. Practical Notes & Caveats
12. MediaPipe Pose Implementation Guide
13. Appendix — Metric Summary Table

> **Scope.** This document covers two lifts:
> - **Standing Barbell Military Press (strict OHP)** — bar racked on clavicle/anterior delts, pressed strictly overhead with no leg drive. Includes both "true military" (heels touching, standing-at-attention origin) and the more common shoulder-width "strict press" stance.
> - **Seated Dumbbell Shoulder Press** — lifter seated on a bench with backrest typically 75–90°, DBs at shoulder/ear, pressed overhead.
>
> **Push press is OUT OF SCOPE as a primary lift but IN SCOPE as a hard-fail classifier.** If the system detects knee/hip drive prior to bar rise, the rep is reclassified as `push_press` and scored under a separate rubric — *not* graded against the strict-press standard.

---

## 1. Required Camera Angles

Overhead pressing is uniquely demanding for video assessment because (a) the implement starts low and finishes high above the head, so framing must accommodate ~1.5 m of vertical travel plus head clearance; (b) plates can occlude the face at lockout in the sagittal view; (c) for dumbbells, two independent paths must be tracked.

### 1.1 Priority of Views

| View | Military Press | Seated DB | Why |
|---|---|---|---|
| **Sagittal (side, 90°)** | **PRIMARY** | **PRIMARY** | Bar/DB path, torso lean, lumbar arch, head-under-bar, lockout |
| **Frontal (anterior, 0°)** | Secondary | **Co-primary** | Bar tilt, DB symmetry L/R, elbow flare, head centering |
| **Posterior (rear, 180°)** | Secondary | Optional | Scapular control, lateral lean, foot symmetry |
| **45° oblique** | Tertiary | Tertiary | Disambiguates bar-vs-head position when plates occlude head |

For the **strict military press**, sagittal is the single most informative view — every classifier-grade fault (lumbar arch, push-press cheat, bar drift, head movement) is most cleanly visible there. For the **seated DB**, frontal climbs to co-primary because L/R asymmetry is the dominant failure mode and only frontal resolves it cleanly.

### 1.2 Camera Setup Recommendations

| Parameter | Recommended | Minimum Acceptable |
|---|---|---|
| Frame rate | 60 fps | 30 fps |
| Resolution | 1080p | 720p |
| Lens height (sagittal) | Lifter's sternum height (≈1.3–1.5 m) | ±20 cm of sternum |
| Lens height (frontal) | Lifter's chest height | ±30 cm |
| Distance (sagittal, standing) | 3.0–4.0 m | 2.0 m |
| Distance (frontal, seated) | 2.5–3.0 m | 1.5 m |
| Tilt | 0° (lens optical axis horizontal) | <5° tilt |
| Shutter | 1/250 s or faster | 1/120 s |
| Lighting | Diffuse, front + side fill; ≥300 lux at lifter | Avoid backlight & single overhead spot |

### 1.3 Framing — Critical for Overhead Lifts

- **Vertical framing must include**: feet/seat at bottom of frame AND ≥15 cm clearance above the locked-out implement at top. A bar that exits the frame at lockout invalidates lockout metrics.
- For **standing military**, the full body must be in frame — the entire kinetic chain matters; lower-body cheats (knee bend, hip thrust) are scored against the strict-press standard.
- For **seated DB**, torso + arms + head must be in frame; legs below mid-thigh are optional.
- **Plate-occlusion warning**: in sagittal view, plates routinely occlude the head/face at the moment of lockout. Mitigations: (a) use 45° oblique as secondary camera, (b) interpolate head landmarks across the occlusion window using temporal smoothing, (c) prefer change-plate (smaller-diameter) loading during assessment when possible.

---

## 2. Military Press vs Seated DB Shoulder Press — Key Differences

| Dimension | Standing Barbell Military Press | Seated Dumbbell Shoulder Press |
|---|---|---|
| Implement | Single barbell; constrained 1-DOF path | Two independent DBs; 3-DOF each |
| Stance | Standing — feet together ("true military") or shoulder-width ("strict press") | Seated on bench, backrest 75–90° |
| Stability demand | Whole-body bracing; ankle, hip, lumbar all load-bearing stabilizers | Upper body only; bench removes lumbar/lower-limb stabilization |
| Bar path | Single vertical path forced; requires head movement back-and-through | Each DB free; bar-tilt impossible but L/R height divergence common |
| ROM (start) | Bar at clavicle/anterior delt — limited by bar contacting torso | DB at ear/shoulder — can descend lower for greater stretch |
| ROM (top) | Lockout overhead, arms by ears | Same; DBs may or may not "clang" together |
| Grip | Pronated only | Pronated standard; neutral / semi-supinated (Arnold-style) common |
| Primary movers | Anterior + medial delt, triceps, upper trap | Anterior + medial delt, triceps, upper trap |
| Stabilizer load | High: erector spinae, glutes, obliques, deep core | Low: glutes/quads passive, lumbar supported |
| 1-RM (Saeterbakken & Fimland 2013) | Standing barbell = reference | Standing DB ≈ 93% of standing BB; seated DB ≈ 103% of standing BB |
| EMG (anterior delt) | Higher | ≈11% higher than seated BB (p = 0.038); ≈8% lower than standing DB *(non-significant trend, p = 0.070)* |
| EMG (posterior delt) | Reference | ≈25% lower (seated vs standing BB, p < 0.001) |
| Common cheats | Push press (knee bend); hip thrust; lumbar hyperextension ("standing incline bench") | Excessive back arch off pad; uneven L/R press; bouncing DBs off shoulders; partial ROM |
| Rubric weight on lower-body metrics | High | None (skipped) |
| Rubric weight on L/R symmetry | Low (barbell-constrained) | High |

**Empirical anchors** (Saeterbakken & Fimland, *J Strength Cond Res* 27(7):1824–1831, 2013): anterior deltoid ≈11% lower for seated barbell vs dumbbell (p = 0.038), ≈15% lower in standing barbell vs dumbbell (p < 0.001); posterior deltoid ≈25% lower for seated vs standing barbell (p < 0.001); medial deltoid 15% lower for seated vs standing dumbbell (p = 0.008). 1-RM: "1-RM strength for standing dumbbells was ~7% lower than standing barbell (p = 0.002) and ~10% lower than seated dumbbells (p < 0.001)." Bench backrest was 75°.

**Push-press classification (HARD GATE).** If `Δknee_flexion > 8°` OR `Δhip_X > 4 cm` is detected **before** the bar/DB has risen 5 cm from start, the rep is flagged `push_press` and routed to a separate rubric. This is not a coaching nuance — it is the historical reason the strict press was removed from Olympic weightlifting after the 1972 Munich Games (IWF: "the proposal [to eliminate the press] was finally adopted (33 delegates in favour, 13 against)"). Per Wikipedia summarizing the IWF rationale: "Some athletes were able to initiate the press with a hip thrust so rapid that judges found it difficult to determine whether or not they had utilized any knee bend to generate additional force, something strictly prohibited in the rules." A CV system must address this explicitly.

**On modern federation status**: strict press is NOT currently contested by the IPF (squat / bench / deadlift only). The closest competitive strict-press judging criteria come from strongman bodies (Official Strongman / USS), e.g.: "Push jerks, split jerks, and double-dipping (re-bending the knees after the initial leg drive) are NOT allowed. Each repetition must be pressed to full lockout (elbows fully extended, head through)." Return-to-rack: "Each rep must return to the shoulders before initiating the next press." These criteria inform our hard-fail overrides.

---

## 3. Sagittal (Side) View Metrics

**Scoring schema** (used throughout §§3–6): Very Good = 90–100, Good = 75–89, Yellow Flag = 60–74, Bad = 40–59, Very Bad = 0–39. Numerical thresholds are anchors; intra-bin scores are linearly interpolated (see §7).

### 3.1 Setup & Starting Position

**S1. Bar/DB starting height vs clavicle**
| Tier | Military (bar offset from clavicle) | Seated DB (DB centre vs acromion) |
|---|---|---|
| Very Good | bar resting on/touching anterior delts | DB at ear-height, just outside shoulder line |
| Good | ≤2 cm gap | ≤3 cm above/outside |
| Yellow | 2–5 cm (floating) | 3–6 cm |
| Bad | 5–10 cm | 6–10 cm |
| Very Bad | >10 cm (no rack contact) | DBs above ear (partial ROM) |

**S2. Forearm vertical at start** (radius angle from vertical, sagittal)
| Tier | Both lifts |
|---|---|
| Very Good | 0–5° |
| Good | 5–10° |
| Yellow | 10–20° |
| Bad | 20–35° |
| Very Bad | >35° (elbows far behind bar) |

**S3. Elbow angle at start (shoulder–elbow–wrist)**
| Tier | Military | Seated DB |
|---|---|---|
| Very Good | 85–105° | 80–100° |
| Good | 75–115° | 70–110° |
| Yellow | 65–125° | 60–120° |
| Bad | 55–135° | 50–130° |
| Very Bad | <55° or >135° | <50° or >130° |

**S4. Torso lean at start** (hip→shoulder vector angle from vertical; posterior = positive)
| Tier | Military | Seated DB |
|---|---|---|
| Very Good | ≤5° | ≤3° (back flush to pad) |
| Good | 5–10° | 3–7° |
| Yellow | 10–15° | 7–12° |
| Bad | 15–25° | 12–18° |
| Very Bad | >25° (standing incline-bench) | >18° (back peeled from pad) |

### 3.2 Concentric Phase

**S5. Bar/DB horizontal displacement** (max |Δx| of wrist centre, sagittal, vs setup)
| Tier | Both lifts |
|---|---|
| Very Good | ≤3 cm |
| Good | 3–6 cm |
| Yellow | 6–10 cm |
| Bad | 10–15 cm |
| Very Bad | >15 cm |

*Caveat: these thresholds are practitioner heuristics. No peer-reviewed kinematic study reports normative cm values for standing OHP horizontal sway; the Gundersen et al. (2025) shoulder-press kinematics paper studied seated press and grip width, not horizontal drift in the standing variation.*

**S6. Head movement back-and-through** (nose-X delta at sticking-point frame vs setup; toward bar column = positive)
| Tier | Description | Threshold |
|---|---|---|
| Very Good | Clear back-then-forward, nose ≥3 cm forward at lockout | Δx_forward ≥ +3 cm |
| Good | Nose forward by 1–3 cm at lockout | +1 to +3 cm |
| Yellow | Head static | −1 to +1 cm |
| Bad | Head still behind setup line at lockout | −3 to −1 cm |
| Very Bad | Head pulled further back at lockout | < −3 cm |

**S7. Torso lean at lockout** (max posterior lean during top half of press)
| Tier | Military | Seated DB |
|---|---|---|
| Very Good | ≤8° | ≤5° |
| Good | 8–13° | 5–9° |
| Yellow | 13–20° | 9–14° |
| Bad | 20–30° | 14–20° |
| Very Bad | >30° (lying-bench equivalent) | >20° |

**S8. Lumbar hyperextension / arch delta** (shoulder–hip–knee angle change vs setup; more negative = more extension)
| Tier | Both lifts | Δ angle |
|---|---|---|
| Very Good | Neutral spine maintained | ≤3° |
| Good | Minor extension | 3–7° |
| Yellow | Noticeable arch | 7–12° |
| Bad | Significant arch | 12–20° |
| Very Bad | Bow-like hyperextension | >20° — **safety override candidate** |

**S9. Knee flexion during press** (max Δ in hip–knee–ankle angle vs setup; standing only)
| Tier | Threshold |
|---|---|
| Very Good | ≤2° |
| Good | 2–5° |
| Yellow | 5–8° |
| Bad | 8–15° — borderline push press |
| Very Bad | >15° — **push press, hard reclassify** |

**S10. Hip-X thrust** (max forward hip-X displacement during concentric; standing only)
| Tier | Threshold |
|---|---|
| Very Good | ≤2 cm |
| Good | 2–4 cm |
| Yellow | 4–7 cm |
| Bad | 7–12 cm |
| Very Bad | >12 cm — **kipping equivalent, hard fail** |

### 3.3 Lockout

**S11. Elbow extension at lockout**
| Tier | Both lifts |
|---|---|
| Very Good | 175–180° |
| Good | 168–175° |
| Yellow | 160–168° |
| Bad | 150–160° |
| Very Bad | <150° (no lockout) |

**S12. Shoulder flexion at lockout** (humerus angle from vertical, sagittal)
| Tier | Both lifts |
|---|---|
| Very Good | 0–5° (arms by ears) |
| Good | 5–10° |
| Yellow | 10–18° |
| Bad | 18–28° |
| Very Bad | >28° (bar/DB in front of head) |

**S13. Bar-over-mid-foot at lockout** (standing; horizontal distance wrist-centre to ankle midpoint)
| Tier | Threshold |
|---|---|
| Very Good | ≤3 cm |
| Good | 3–6 cm |
| Yellow | 6–10 cm |
| Bad | 10–15 cm |
| Very Bad | >15 cm |

**S14. Wrist angle throughout** (max wrist extension, sagittal)
| Tier | Threshold |
|---|---|
| Very Good | ≤10° |
| Good | 10–20° |
| Yellow | 20–35° |
| Bad | 35–50° |
| Very Bad | >50° — wrist hyperextension under load |

**S15. Lockout pause / hold duration**
| Tier | Frames at lockout (60 fps) | Duration |
|---|---|---|
| Very Good | ≥30 frames | ≥0.5 s sustained |
| Good | 18–30 | 0.3–0.5 s |
| Yellow | 9–18 | 0.15–0.3 s |
| Bad | 3–9 | 0.05–0.15 s |
| Very Bad | <3 (immediate descent) | bouncing/no hold |

### 3.4 Eccentric & ROM Completion

**S16. ROM completion at bottom** (lowest wrist position vs setup)
| Tier | Threshold |
|---|---|
| Very Good | ≤2 cm short; touches clavicle/shoulder |
| Good | 2–5 cm short |
| Yellow | 5–10 cm |
| Bad | 10–15 cm |
| Very Bad | >15 cm — partial-rep |

**S17. Seated DB — back contact with pad** (hip-Y stability frame-to-frame)
| Tier | Max hip-Y deviation across rep |
|---|---|
| Very Good | ≤1 cm |
| Good | 1–2 cm |
| Yellow | 2–4 cm |
| Bad | 4–7 cm |
| Very Bad | >7 cm (driving off pad) |

**S18. Seated DB — feet contact** (ankle-Y stability)
| Tier | Max ankle-Y deviation |
|---|---|
| Very Good | ≤1 cm |
| Good | 1–2 cm |
| Yellow | 2–4 cm |
| Bad | 4–6 cm |
| Very Bad | >6 cm |

---

## 4. Frontal (Anterior) View Metrics

**F1. Grip width — biacromial ratio (military)**
| Tier | Ratio |
|---|---|
| Very Good | 1.3–1.5× biacromial |
| Good | 1.15–1.3× or 1.5–1.65× |
| Yellow | 1.0–1.15× or 1.65–1.8× |
| Bad | <1.0× or 1.8–2.0× |
| Very Bad | >2.0× (shoulder abduction >75°, impingement risk) |

*Reference grip widths in shoulder-press kinematics (Gundersen, Krosshaug, Mausehund, van den Tillaar & Larsen, "The impact of grip width on kinetics and kinematics in the shoulder press among resistance-trained men," Sports Biomechanics, published online 03 Dec 2025; n = 11 men, age 25.9 ± 3.1 yr): narrow 1.0×, medium 1.4×, wide 1.7× biacromial distance.*

**F2. Bar tilt (military)** (angle of wrist-L to wrist-R line from horizontal)
| Tier | Threshold |
|---|---|
| Very Good | ≤2° |
| Good | 2–4° |
| Yellow | 4–7° |
| Bad | 7–12° |
| Very Bad | >12° |

**F3. DB symmetry — peak height delta (seated DB)** (max |wristL_Y − wristR_Y|, normalized to torso height)
| Tier | Δ (cm) | Δ (% torso) |
|---|---|---|
| Very Good | ≤2 cm | ≤3% |
| Good | 2–4 cm | 3–6% |
| Yellow | 4–7 cm | 6–10% |
| Bad | 7–12 cm | 10–17% |
| Very Bad | >12 cm | >17% — **asymmetry override candidate** |

**F4. Elbow flare angle at start** (humerus-to-trunk angle, frontal)
| Tier | True Military (elbows forward) | Strict Press | Seated DB |
|---|---|---|---|
| Very Good | 25–40° | 35–55° | 35–55° |
| Good | 15–25° or 40–55° | 25–35° or 55–70° | 25–35° or 55–70° |
| Yellow | 55–70° | 70–80° | 70–85° |
| Bad | 70–85° | 80–90° | 85–95° |
| Very Bad | ≥85° | ≥90° | ≥95° |

**F5. Wrist alignment, frontal (lateral break)**
| Tier | Lateral deviation |
|---|---|
| Very Good | ≤5° |
| Good | 5–10° |
| Yellow | 10–18° |
| Bad | 18–28° |
| Very Bad | >28° |

**F6. Head lateral tilt** (nose-X offset from shoulder midpoint, % biacromial)
| Tier | Threshold |
|---|---|
| Very Good | ≤3% |
| Good | 3–6% |
| Yellow | 6–10% |
| Bad | 10–15% |
| Very Bad | >15% |

**F7. DB path parallelism (seated DB)** (angular divergence between DB-L and DB-R trajectories)
| Tier | Threshold |
|---|---|
| Very Good | ≤3° |
| Good | 3–7° |
| Yellow | 7–12° |
| Bad | 12–20° |
| Very Bad | >20° |

**F8. DB-clang at top** — categorical, advisory only (energy-loss flag, not graded).

---

## 5. Posterior (Rear) View Metrics

**P1. Scapular upward rotation symmetry**: *observation-grade only* — MediaPipe cannot directly track scapulae; shoulder-acromion-Y symmetry across lockout is the closest proxy.

**P2. Shoulder height symmetry**
| Tier | |shoulderL_Y − shoulderR_Y| (% biacromial) |
|---|---|
| Very Good | ≤3% |
| Good | 3–6% |
| Yellow | 6–10% |
| Bad | 10–15% |
| Very Bad | >15% |

**P3. Spinal lateral lean** (midhip → midshoulder angle from vertical, frontal)
| Tier | Threshold |
|---|---|
| Very Good | ≤3° |
| Good | 3–6° |
| Yellow | 6–10° |
| Bad | 10–16° |
| Very Bad | >16° |

**P4. Hip alignment** (|hipL_Y − hipR_Y|, standing only)
| Tier | Threshold |
|---|---|
| Very Good | ≤2% biacromial |
| Good | 2–4% |
| Yellow | 4–7% |
| Bad | 7–11% |
| Very Bad | >11% |

**P5. Foot stance** — categorical classifier input (standing only):
| Variant | Inter-ankle distance vs biacromial |
|---|---|
| True military | ≤0.7× |
| Strict press | 0.8–1.2× |
| Wide (push-press tendency) | >1.3× |

---

## 6. Tempo & Control Metrics

**T1. Pre-rep setup time**
| Tier | Duration |
|---|---|
| Very Good | 1.0–3.0 s |
| Good | 0.5–1.0 s or 3.0–5.0 s |
| Yellow | <0.5 s or 5–8 s |
| Bad | 8–15 s |
| Very Bad | <0.2 s (no brace) or >15 s |

**T2. Concentric duration**
| Tier | Standing (heavy strict) | Seated DB (hypertrophy) |
|---|---|---|
| Very Good | 1.2–3.0 s | 1.0–2.0 s |
| Good | 0.8–1.2 s or 3.0–4.0 s | 0.7–1.0 s or 2.0–3.0 s |
| Yellow | <0.8 s or 4–6 s | <0.7 s or 3–4 s |
| Bad | 6–10 s | 4–6 s |
| Very Bad | <0.5 s (suspect push press) or >10 s (grinding death) | <0.4 s or >6 s |

**T3. Eccentric duration**
| Tier | Both |
|---|---|
| Very Good | 1.5–3.0 s |
| Good | 1.0–1.5 s or 3.0–4.0 s |
| Yellow | 0.6–1.0 s or 4–6 s |
| Bad | 0.3–0.6 s |
| Very Bad | <0.3 s (drop) |

**T4. Eccentric : concentric ratio**
| Tier | Ratio |
|---|---|
| Very Good | 1.0–2.0 |
| Good | 0.8–1.0 or 2.0–2.5 |
| Yellow | 0.5–0.8 |
| Bad | 0.3–0.5 |
| Very Bad | <0.3 |

**T5. Sticking-point detection.** The OHP sticking point is characterized as the moment-arm peak at approximately forehead/eye-level height — i.e., the middle portion of bar travel. Per Outlift's coaching-side characterization: "The overhead press's main problem is its iffy strength curve… it has an extreme sticking point when the barbell is around forehead height." Operationally: locate the velocity minimum in the concentric phase and bin by its relative location.
| Tier | Location of v_min (% bar travel) | Interpretation |
|---|---|---|
| Very Good | 25–45% (textbook sticking region) | Lift well-grooved |
| Good | 45–55% | Slightly high |
| Yellow | 55–70% or 15–25% | Atypical — mobility/triceps gap |
| Bad | 70–85% | Failing at lockout — triceps weakness |
| Very Bad | >85% or no recovery from v_min | Failed/grinding rep |

**T6. DB tempo symmetry (seated DB)** (|t_concentric_L − t_concentric_R|)
| Tier | Threshold |
|---|---|
| Very Good | ≤50 ms |
| Good | 50–100 ms |
| Yellow | 100–200 ms |
| Bad | 200–400 ms |
| Very Bad | >400 ms |

**T7. Rep-to-rep consistency** (CV of T2 across the set)
| Tier | CV |
|---|---|
| Very Good | ≤10% |
| Good | 10–15% |
| Yellow | 15–25% |
| Bad | 25–40% |
| Very Bad | >40% |

---

## 7. Composite Scoring System

### Step 1 — Raw → 0–100 Sub-score

Each metric returns a measured value; this is mapped to 0–100 via piecewise-linear interpolation between tier midpoints (VG = 95, G = 82, Y = 67, B = 50, VB = 20; boundaries at 90 / 75 / 60 / 40).

```
if x ≤ VG_threshold:   score = 95 + (VG_threshold − x)/VG_threshold * 5   (capped 100)
elif x ≤ G_threshold:  score = lerp(90, 75, fraction between VG and G)
… etc.
```

### Step 2 — Category Weights

For OHP — where the dominant injury mechanism is lumbar hyperextension under axial load and the dominant performance failure is bar drift — **Safety is weighted highest**.

| Category | Weight | Rationale |
|---|---|---|
| **Safety** | 45% | Lumbar/disc/facet risk; shoulder impingement; wrist hyperextension; lockout failure |
| **Technique** | 35% | Bar path, head-under-bar, lockout quality, ROM |
| **Performance** | 20% | Tempo, sticking-point profile, consistency |

### Step 3 — Per-metric weights within categories (sum to 100)

**Safety (45%) — Standing Military Press**
| Metric | Weight |
|---|---|
| S8 Lumbar hyperextension | 35 |
| S10 Hip thrust | 15 |
| S9 Knee flexion (push-press detector) | 15 |
| S14 Wrist angle | 10 |
| S13 Bar over mid-foot | 10 |
| F1 Grip width (impingement risk) | 8 |
| F4 Elbow flare | 7 |

**Safety (45%) — Seated DB**
| Metric | Weight |
|---|---|
| S8 Lumbar hyperextension (off-pad arch) | 30 |
| S17 Back contact | 20 |
| F3 DB symmetry | 15 |
| S14 Wrist angle | 10 |
| F4 Elbow flare | 10 |
| F5 Wrist lateral break | 8 |
| F7 DB path parallelism | 7 |

**Technique (35%)**
| Metric | Military | Seated DB |
|---|---|---|
| S5 Bar/DB horizontal displacement | 20 | 15 |
| S6 Head under bar | 15 | 5 |
| S11 Elbow lockout | 15 | 18 |
| S12 Shoulder flexion at lockout | 12 | 14 |
| S16 ROM completion bottom | 12 | 14 |
| S1/S2/S3 Setup (combined) | 10 | 14 |
| S15 Lockout hold | 8 | 10 |
| S7 Torso lean at lockout | 8 | 10 |

**Performance (20%)**
| Metric | Military | Seated DB |
|---|---|---|
| T2 Concentric duration | 35 (T6 weight redistributed) | 20 |
| T3 Eccentric duration | 15 | 15 |
| T4 E:C ratio | 10 | 10 |
| T5 Sticking-point location | 15 | 15 |
| T6 DB tempo symmetry | — | 15 |
| T7 Rep-to-rep CV | 15 | 15 |
| T1 Setup time | 10 | 10 |

### Step 4 — Composite

```
Composite = 0.45 × Safety + 0.35 × Technique + 0.20 × Performance
```
Default = weighted **arithmetic mean**. **Geometric-mean alternative** penalizes any single very-low sub-score more aggressively — recommended for screening contexts (rehab, novice):

```
Composite_geom = Safety^0.45 × Technique^0.35 × Performance^0.20
```

### Step 5 — Hard-Fail Safety Overrides

| Override | Trigger | Effect |
|---|---|---|
| Lumbar bow | S8 arch delta > 20° | Cap at **D** (≤55) |
| Knee bend during strict press | S9 > 15° | Reclassify as `push_press` |
| Hip thrust | S10 > 12 cm | Cap at **D**; flag `kipping_equivalent` |
| Asymmetric DB press | F3 > 12 cm | Cap at **D**; flag `unsafe_asymmetry` |
| Bar-forward-of-head at lockout | S12 > 28° | Cap at **D** |
| Wrist hyperextension | S14 > 50° | Cap at **C** (≤70) |
| Failed lockout | S11 < 150° at peak | Cap at **D**; flag `no_lockout` |
| Frame exit at lockout | bar/DB or head leaves frame | Mark metric `NaN`; flag for re-shoot |

### Step 6 — Per-Set Aggregation

- **Default**: mean of all rep composites.
- **Conservative (screening)**: worst rep.
- **Coaching mode**: mean of last three reps (captures fatigue).
- **Hybrid**: 0.5 × mean + 0.5 × worst.

---

## 8. Grade & Label Mapping

| Composite | Grade | Label |
|---|---|---|
| 90–100 | **A** | Very Good |
| 75–89 | **B** | Good |
| 60–74 | **C** | Yellow Flag |
| 40–59 | **D** | Bad |
| 0–39 | **E** | Very Bad |

---

## 9. Alternative Naming Schemes

| Scheme | A (90–100) | B (75–89) | C (60–74) | D (40–59) | E (0–39) |
|---|---|---|---|---|---|
| Traffic light | Green | Light Green | Yellow | Orange | Red |
| Sports tier | Elite | Competitive | Developmental | Novice | Untrained |
| Coaching | Picture-perfect | Solid | Needs work | Form breakdown | Stop the set |
| Medical / PT | No flags | Minor flags | Watch | Refer | Stop & assess |
| Risk | Negligible | Low | Moderate | High | Severe |
| Tier list | S | A | B | C | D/F |
| Belt system | Black | Brown | Purple | Blue | White |
| Stars | ★★★★★ | ★★★★ | ★★★ | ★★ | ★ |
| Olympic | Gold | Silver | Bronze | Finalist | DNF |
| Descriptive | Textbook | Clean | Acceptable | Problematic | Dangerous |
| Percentile | ≥90th | 75–89th | 50–74th | 25–49th | <25th |
| Academic | A | B | C | D | F |
| Quality | Excellent | Good | Fair | Poor | Failing |
| Weather | Clear | Partly sunny | Overcast | Stormy | Severe weather |
| Animals | Eagle | Hawk | Sparrow | Pigeon | Dodo |
| Heat | Cold | Cool | Warm | Hot | Burning |
| **Military fitness** | **Squared away** | **Standard** | **Needs PT** | **Remedial** | **Medical hold** |
| **Military rank** | Officer | NCO | Junior NCO | Recruit | Failed selection |
| CrossFit-style | RX+ | RX | Scaled | Foundations | Rest |

---

## 10. Worked Example

**Subject**: Male intermediate lifter, age 32, BW 82 kg, height 178 cm (5'10"), training age 2 yr. **Lift**: standing barbell strict press, 60 kg × 5, set 1 of 3. **Cameras**: sagittal (right side) at 1.4 m height, 3 m distance, 60 fps; frontal at 2.8 m. Stance: shoulder-width "strict press" style.

### 10.1 Raw measurements (rep 3 — representative)

| Metric | Raw | Tier | Sub-score |
|---|---|---|---|
| S1 Bar offset from clavicle | 1.2 cm | Good | 86 |
| S2 Forearm vertical | 8° | Good | 80 |
| S3 Elbow angle start | 92° | VG | 96 |
| S4 Torso lean start | 4° | VG | 95 |
| S5 Bar horizontal max | 4.8 cm | Good | 79 |
| S6 Head under bar | +1.7 cm | Good | 81 |
| S7 Torso lean at lockout | 11° | Good | 78 |
| S8 Lumbar arch delta | 9° | Yellow | 67 |
| S9 Knee flexion delta | 3° | Good | 85 |
| S10 Hip-X thrust | 2.8 cm | Good | 84 |
| S11 Elbow extension lockout | 174° | Good | 88 |
| S12 Shoulder flexion lockout | 7° | Good | 83 |
| S13 Bar over mid-foot | 5.1 cm | Good | 78 |
| S14 Wrist angle (max ext) | 22° | Yellow | 65 |
| S15 Lockout hold | 0.35 s | Good | 84 |
| S16 ROM bottom | 1.5 cm short | VG | 92 |
| F1 Grip ratio | 1.42× | VG | 95 |
| F2 Bar tilt max | 2.1° | Good | 88 |
| F4 Elbow flare start | 31° | VG (strict) | 94 |
| F5 Wrist lateral break | 4° | VG | 95 |
| F6 Head lateral tilt | 2% | VG | 96 |
| T1 Setup time | 2.4 s | VG | 95 |
| T2 Concentric | 1.8 s | VG | 93 |
| T3 Eccentric | 1.6 s | VG | 93 |
| T4 E:C ratio | 0.89 | Good | 84 |
| T5 Sticking-point | 42% travel | VG | 93 |
| T7 Rep CV | 12% | Good | 82 |

### 10.2 Category aggregation (military weights)

**Safety**
```
0.35(67) + 0.15(84) + 0.15(85) + 0.10(65) + 0.10(78) + 0.08(95) + 0.07(94)
= 23.45 + 12.60 + 12.75 + 6.50 + 7.80 + 7.60 + 6.58
= 77.3
```

**Technique** (setup combined = avg(86, 80, 96) = 87.3)
```
0.20(79) + 0.15(81) + 0.15(88) + 0.12(83) + 0.12(92) + 0.10(87.3) + 0.08(84) + 0.08(78)
= 15.80 + 12.15 + 13.20 + 9.96 + 11.04 + 8.73 + 6.72 + 6.24
= 83.8
```

**Performance** (BB — T6 weight folded into T2 → 35)
```
0.35(93) + 0.15(93) + 0.10(84) + 0.15(93) + 0.15(82) + 0.10(95)
= 32.55 + 13.95 + 8.40 + 13.95 + 12.30 + 9.50
= 90.7
```

### 10.3 Composite
```
Composite = 0.45(77.3) + 0.35(83.8) + 0.20(90.7)
          = 34.79 + 29.33 + 18.14
          = 82.3 → Grade B, "Good"
```

### 10.4 Override checks
- Lumbar 9° (<20°) → OK
- Knee 3° (<15°) → not push press
- Hip 2.8 cm (<12) → OK
- Wrist 22° (<50°) → OK
- Lockout 174° (>150°) → OK

**Final: B / Good (82.3/100).**

### 10.5 Two lowest sub-scores → feedback surface

1. **S14 wrist angle 22° (Yellow, 65)** — "Your wrists are bending back under the load. Cue: 'punch the ceiling with the heel of your palm.' Consider wrist wraps for working sets above ~75% 1RM."
2. **S8 lumbar arch delta 9° (Yellow, 67)** — "Slight arch through the sticking point. Cue: 'ribs down, glutes squeezed.' If this worsens on rep 5, the load is too heavy for strict-form practice today."

---

## 11. Practical Notes & Caveats

### 11.1 Anthropometry

- **Long-armed lifters** (long radius/humerus) inherently have more horizontal bar travel during the press. Relax `S5` thresholds by ≈20% for lifters whose forearm length (wrist→elbow) exceeds 0.16 × standing height.
- **Bar resting position** depends on forearm length: lifters with very long forearms cannot rest the bar on anterior delts and will hold it floating just below the chin. Do not score `S1` as a fault if `S3` elbow angle is in spec.
- **Wide-chested lifters** may exceed 1.3× biacromial grip in absolute cm — score by ratio, not absolute width.

### 11.2 Mobility Prerequisites

- **Shoulder flexion** ≥165° passive ROM. Lifters below this *will* compensate via lumbar hyperextension — the press is an inappropriate exercise selection until mobility is addressed (consensus across Bret Contreras, Active PT and physiotherapy literature).
- **T-spine extension** sufficient to extend through ≥T6 with arms overhead.
- **Wrist extension** ≥70°.
- **System should flag** suspected mobility deficits when S8 and S12 are both Yellow-or-worse — that pattern is diagnostic of shoulder/T-spine restriction rather than weakness.

### 11.3 Variant Classification

The classifier resolves each video to one of: `military_true` (heels together), `military_strict_shoulder_width`, `push_press` (knee bend pre-bar-rise), `seated_db_90`, `seated_db_incline_75-85`, or `unclear`. Different rubric weights apply per branch.

### 11.4 Continuous Tracking vs Single-Frame

Use **continuous (frame-by-frame)** tracking for: bar path, lumbar arch evolution, head trajectory, tempo, velocity profile. Use **key-frame extraction** for: setup, sticking-point, lockout, deepest-eccentric. Both are required; either alone is insufficient.

### 11.5 Calibration

Always include a calibration object of known length (e.g., bar = 220 cm for a standard 20 kg Olympic bar; or a known-length tape) in the first 3 s of the clip. Sub-scores expressed in cm (S5, S13, S17, F3) are otherwise meaningless.

### 11.6 Always Surface the Reason

The system MUST output the **driver metric** behind any sub-A grade — not just the composite. Users develop trust in feedback they can map to a coachable cue.

### 11.7 Bench-back-angle for Seated DB

| Backrest | Effect |
|---|---|
| 90° (vertical) | Maximizes anterior-delt isolation; most spinal support; least forgiving of shoulder mobility deficit |
| 80–85° | "Sweet spot" for most lifters — default in most overhead-press tutorials |
| 75° (Saeterbakken & Fimland 2013 setup) | Common research/coaching anchor; recruits more upper pec; reduces external-rotation demand |
| <70° | Becomes an incline bench press, not a shoulder press — reclassify |

Detect backrest angle from the hip→shoulder vector relative to vertical at setup, and apply the appropriate rubric variant. *Note: no peer-reviewed study has directly compared 90° vs 75° backrest on shoulder-press EMG or 1-RM as the primary variable — this is a documented gap in the literature.*

### 11.8 Camera Occlusion Challenges

Three failure modes dominate:

1. **Bar/DB exits frame at lockout** — set tall framing, OR refuse to score lockout metrics.
2. **Plates occlude head/face from sagittal at lockout** — interpolate nose/ear landmarks across the occlusion window, OR use oblique camera as backup. S6 (head-under-bar) is the most error-prone metric in this rubric.
3. **Bench occludes back for seated DB** — back contact (S17) cannot be measured directly; use hip-Y stability as proxy.

### 11.9 Frame-Rate Tradeoffs

- 30 fps: minimum acceptable; sticking-point detection has ±33 ms uncertainty.
- 60 fps: recommended; resolves DB tempo asymmetry to ≤17 ms.
- 120 fps: ideal for velocity profiling, rarely available in gym settings.

### 11.10 Minimum-Viable Metric Priority

If only 5 metrics can be computed reliably, choose:

1. **S8** lumbar arch — primary safety
2. **S5** bar path horizontal — primary technique
3. **S11** elbow lockout — primary ROM
4. **S9** knee flexion — push-press detector
5. **F3** DB symmetry (DB) or **S6** head-under-bar (BB) — primary lift-specific

### 11.11 Common Mobility Deficits to Flag

| Pattern | Diagnostic combo | Recommended flag |
|---|---|---|
| Shoulder-flexion limit | S8 Yellow + S12 Yellow + S6 Yellow | "Test passive shoulder flexion; <165° suggests lat / pec-minor restriction" |
| T-spine restriction | S4 Yellow at setup + S12 Yellow at lockout | "T-spine extension drills (foam roller, quadruped rotation)" |
| Wrist restriction | S14 Bad + F5 Yellow | "Wrist mobility work; wrist wraps for heavy sets" |
| Triceps weakness | T5 v_min >70% travel + S11 Yellow | "Add close-grip bench, pin press" |

---

## 12. MediaPipe Pose Implementation Guide

### 12.1 MediaPipe Pose Landmark Reference

MediaPipe Pose / BlazePose returns 33 3D landmarks per frame with `(x, y, z, visibility)`. `x, y` are normalized [0, 1] image coordinates; `z` is relative depth; `visibility` ∈ [0, 1].

| Idx | Landmark | OHP relevance |
|---|---|---|
| 0 | Nose | **Critical** — head-under-bar tracking |
| 1–6 | Eyes (inner/outer/center L/R) | Head orientation, secondary |
| 7 | Left ear | **Critical** — backup when nose occluded |
| 8 | Right ear | **Critical** |
| 9 | Mouth left | Chin position |
| 10 | Mouth right | Chin position |
| 11 | **Left shoulder** | **Critical** |
| 12 | **Right shoulder** | **Critical** |
| 13 | **Left elbow** | **Critical** |
| 14 | **Right elbow** | **Critical** |
| 15 | **Left wrist** | **Critical — bar/DB proxy** |
| 16 | **Right wrist** | **Critical** |
| 17, 19, 21 | Left pinky, index, thumb | Grip orientation (DB) |
| 18, 20, 22 | Right pinky, index, thumb | Grip orientation (DB) |
| 23 | **Left hip** | **Critical — lumbar arch, hip thrust** |
| 24 | **Right hip** | **Critical** |
| 25 | **Left knee** | **Critical — push-press detection** |
| 26 | **Right knee** | **Critical** |
| 27 | **Left ankle** | **Critical — mid-foot reference (standing)** |
| 28 | **Right ankle** | **Critical** |
| 29, 31 | Left heel, foot-index | Foot symmetry |
| 30, 32 | Right heel, foot-index | Foot symmetry |

### 12.2 Derived Reference Points

```
shoulder_centre = midpoint(11, 12)
hip_centre      = midpoint(23, 24)
ankle_midpoint  = midpoint(27, 28)        # standing only
ear_midpoint    = midpoint(7, 8)
wrist_centre    = midpoint(15, 16)        # barbell proxy
DB_L_proxy      = landmark 15             # left DB independent
DB_R_proxy      = landmark 16             # right DB independent
body_line       = vector(ankle_midpoint → shoulder_centre)
torso_line      = vector(hip_centre → shoulder_centre)
humerus_L       = vector(11 → 13);  humerus_R = vector(12 → 14)
forearm_L       = vector(13 → 15);  forearm_R = vector(14 → 16)
backrest_proxy  = vector(hip_centre → shoulder_centre)   # seated
vertical_ref    = (0, -1)                 # image-up; gravity-down assumed
```

For **standing**: `mid_foot_X = ankle_midpoint.x` defines the vertical reference column. Bar-over-mid-foot = `|wrist_centre.x − mid_foot_X|`.
For **seated DB**: use `hip_centre.x` as base-of-support proxy, or `(hip_centre.x + ankle_midpoint.x)/2` if feet are visible.

### 12.3 General Computational Principles

- **Visibility filtering**: discard any landmark with `visibility < 0.5`. If a critical landmark (shoulders, elbows, wrists) fails for >3 consecutive frames, mark that metric `NaN`.
- **Side selection** (sagittal): prefer side with higher mean visibility across 11–28, or user-specified camera-facing side.
- **Smoothing**: 1-€ filter or Savitzky-Golay (window 5–7 frames @ 60 fps) per landmark series before metric extraction.
- **Coordinate system**: gravity-relative vertical inferred from `ankle_midpoint → shoulder_centre` at setup frame. All angle metrics use this vertical (not raw image y-axis) to tolerate slight camera tilt.

#### Phase Detection State Machine

```
states: REST → SETUP → CONCENTRIC → STICKING → LOCKOUT → ECCENTRIC → REST

SETUP entry:     wrist_centre.y stable AND elbow_angle ∈ [70°, 110°]
                 AND wrist near shoulder
CONCENTRIC entry: dwrist_y/dt < threshold (upward in image, image y inverts)
                 for ≥3 frames
STICKING:         local minimum of |dwrist_y/dt| within CONCENTRIC,
                  between 25–55% bar travel
LOCKOUT entry:    elbow_angle > 170° AND dwrist_y/dt ≈ 0
LOCKOUT hold:     count frames in lockout state
ECCENTRIC entry:  dwrist_y/dt > threshold (downward) AND elbow_angle decreasing
REST entry:       wrist at setup level AND elbow_angle back to setup range
PUSH-PRESS GATE:  if min(knee_angle) − knee_angle_SETUP < −8°
                  BEFORE wrist_centre rises 5 cm → flag, reclassify
```

A **rep** is a complete REST → … → REST cycle. Reject "ghost reps" where peak elbow angle < 150°.

#### 2D vs 3D

The base MediaPipe Pose `landmarks` (image space) are the workhorse. The `world_landmarks` (3D metric) are useful for cross-camera reasoning but noisier on z. Google's BlazePose GHUM 3D model card explicitly lists "applications requiring metric accurate depth" as out-of-scope. **Do not** rely on z for bar drift; use orthogonal 2D views (sagittal + frontal) instead.

### 12.4 Foundational Math Operations

```python
def angle_from_vertical(v):              # image y points down
    return atan2(v.x, -v.y) * 180/pi      # 0° = straight up

def three_point_angle(a, b, c):           # angle at vertex b
    ba = (a.x-b.x, a.y-b.y)
    bc = (c.x-b.x, c.y-b.y)
    cos_t = dot(ba, bc) / (norm(ba) * norm(bc))
    return acos(clip(cos_t, -1, 1)) * 180/pi

def bar_over_midfoot(wrist_centre, ankle_midpoint, px_to_cm):
    return abs(wrist_centre.x - ankle_midpoint.x) * px_to_cm
```

Special derivations:

- **Head-under-bar (S6)**: `Δ = nose.x_LOCKOUT − nose.x_SETUP`, signed toward the bar's vertical column.
- **Torso vertical (S4, S7)**: `angle_from_vertical(torso_line)`. For seated DB, this approximates the backrest angle when the lifter is in contact with the pad.
- **Lumbar arch (S8)**: `three_point_angle(shoulder_centre, hip_centre, knee_midpoint)` — track Δ from the SETUP baseline. *More negative Δ (angle opening past 180°) = more extension*. For seated DB, substitute knee_midpoint with hip + a downward unit vector to get a vertical reference.

### 12.5 Per-Metric Computation Guide

| # | Metric | Landmarks | Compute | Track | Caveats |
|---|---|---|---|---|---|
| S1 | Bar start vs clavicle | 15,16,11,12 | `wrist_centre.y − shoulder_centre.y` at SETUP, scaled to cm | single frame | Bar is below clavicle if wrist_y > shoulder_y (image-down) |
| S2 | Forearm vertical | 13,15 / 14,16 | `angle_from_vertical(forearm)` at SETUP | single frame | Sagittal only |
| S3 | Elbow angle start | 11,13,15 / 12,14,16 | three-point angle at SETUP | single frame | Report L and R for DB |
| S4 | Torso lean start | 23,11 / 24,12 | `angle_from_vertical(torso_line)` at SETUP | single frame | Subtract bench angle for seated |
| S5 | Bar horizontal max | 15,16 | `max\|wrist_centre.x − wrist_centre.x_SETUP\|` over concentric+lockout | continuous | Convert px → cm via calibration |
| S6 | Head under bar | 0, 15, 16 | `nose.x_LOCKOUT − nose.x_SETUP`, signed toward wrist column | two frames | Use ear midpoint if nose visibility <0.5 |
| S7 | Torso lean lockout | 23,11 / 24,12 | max `angle_from_vertical(torso_line)` over upper-half of press | continuous | |
| S8 | Lumbar arch delta | 11,12,23,24,25,26 | three-point angle (SC, HC, KM); Δ vs SETUP | continuous | Seated DB: substitute KM with vertical reference |
| S9 | Knee flexion | 23,25,27 / 24,26,28 | three-point angle; track minimum over concentric | continuous | Push-press detector: must fall before bar rises 5 cm |
| S10 | Hip-X thrust | 23, 24 | `max(hip_centre.x_t) − hip_centre.x_SETUP` during concentric | continuous | Standing only |
| S11 | Elbow lockout | 11,13,15 / 12,14,16 | max three-point angle over rep | continuous | For DB use min(L, R) |
| S12 | Shoulder flex lockout | 11,13 / 12,14 | `angle_from_vertical(humerus)` at LOCKOUT | single frame | Sagittal critical |
| S13 | Bar over mid-foot | 15,16,27,28 | `\|wrist_centre.x − ankle_midpoint.x\|` × scale at LOCKOUT | single frame | Standing only |
| S14 | Wrist angle | 13,15,19 / 14,16,20 | three-point angle deviation from 180° | continuous (max) | Hand landmarks may be low-visibility under bar |
| S15 | Lockout hold | 15,16 + elbow | count frames where elbow>170° AND \|dwrist_y/dt\| < ε | continuous | |
| S16 | ROM bottom | 15,16,11,12 | `min(wrist_centre.y)` during eccentric vs SETUP wrist_y | continuous | Image y inverts |
| S17 | Back contact (seated) | 23,24 | `max(hip_centre.y_t) − min(hip_centre.y_t)` | continuous | Bench assumed fixed |
| S18 | Feet contact (seated) | 27,28 | `max(ankle.y_t) − min(ankle.y_t)` per side | continuous | Heel-up indicates loss of base |
| F1 | Grip width | 15,16,11,12 | `\|wrist_L.x − wrist_R.x\| / \|shoulder_L.x − shoulder_R.x\|` at SETUP | single frame | Frontal view only |
| F2 | Bar tilt | 15,16 | `atan2(wrist_R.y − wrist_L.y, wrist_R.x − wrist_L.x)` | continuous (max abs) | Frontal only |
| F3 | DB symmetry | 15,16 | `max\|wrist_L.y − wrist_R.y\|` during concentric | continuous | DB only |
| F4 | Elbow flare | 11,13 / 12,14; trunk | angle between humerus and trunk in frontal | SETUP + concentric mid | |
| F5 | Wrist lateral break | 13,15,21 / 14,16,22 | three-point angle in frontal | continuous (max) | |
| F6 | Head lateral tilt | 0,11,12 | `(nose.x − shoulder_centre.x) / biacromial_px` | continuous | |
| F7 | DB path parallelism | 15,16 over t | angular divergence of linear-regression trajectories | whole rep | DB only |
| P2 | Shoulder symmetry | 11,12 | `\|y_L − y_R\| / biacromial` | continuous | |
| P3 | Lateral lean | 23,24,11,12 | `angle_from_vertical(midhip → midshoulder)` in frontal | continuous | |
| P4 | Hip alignment | 23,24 | `\|y_L − y_R\| / biacromial` | continuous | |
| T1 | Setup time | wrist_centre.y | duration in SETUP state | phase machine | |
| T2 | Concentric duration | wrist_centre.y | duration SETUP → LOCKOUT | phase machine | |
| T3 | Eccentric duration | wrist_centre.y | duration LOCKOUT → REST | phase machine | |
| T4 | E:C ratio | derived | T3 / T2 | per rep | |
| T5 | Sticking-point | velocity profile | `argmin(\|dwrist_y/dt\|)` in concentric, as % of `(LOCKOUT_y − SETUP_y)` | continuous | |
| T6 | DB tempo symmetry | 15,16 timestamps | `\|t_L_lockout − t_R_lockout\|` | per rep | DB only |
| T7 | Rep-to-rep CV | T2 across reps | `std(T2)/mean(T2)` | across set | |

#### Detection of key frames

```
SETUP frame:    first frame with elbow_angle ∈ [80°, 110°]
                AND wrist_centre.y > shoulder_centre.y - 5 cm
                AND |dwrist_y/dt| < ε for ≥10 frames
LOCKOUT frame:  elbow_angle > 170° AND wrist_centre.y local-min in image y
                AND shoulder_flexion < 15° from vertical, sustained ≥3 frames
```

### 12.6 Sample Pipeline (Conceptual Flow)

1. **Ingest** — load video; extract fps, resolution; detect calibration object → `pixel_to_cm`. User selects lift_type [military / seated_db / auto] and view [sagittal / frontal / oblique].
2. **Pose extraction** — run MediaPipe Pose (model_complexity = 2); store 33 landmarks + visibility per frame; smooth with 1-€ or SG filter.
3. **Classification** — examine ankle distance / hip-shoulder vector / bench presence → `{military_true, military_strict, seated_db_90, seated_db_75, push_press, unclear}`.
4. **Phase segmentation** — run state machine on `wrist_centre.y` and `elbow_angle`; emit per-rep boundaries.
5. **Push-press gate** — check `knee_angle` and `hip_X` around CONCENTRIC_start; if triggered, route to push-press rubric and return.
6. **Metric extraction** — for each metric in §12.5, compute raw value + confidence (from visibility). Mark `NaN` below confidence threshold.
7. **Scoring** — raw → sub-score (§7.1) → category subtotals (§7.2–7.3) → composite (§7.4) → safety overrides (§7.5) → grade (§8).
8. **Set aggregation** — mean / worst / last-3; cross-session deltas.
9. **Feedback surface** — surface the 2 lowest sub-scores with coachable cues; flag any override triggers; optional timestamped overlay video.

### 12.7 Known Limitations of MediaPipe for OHP Assessment

1. **Bar/DB is not detected.** MediaPipe Pose returns body landmarks only; the implement is implicit via wrist proxy. Consequence: bar tilt (F2) and DB independence (F3, T6) rely entirely on each wrist landmark being accurate; plates extending laterally are completely invisible; DB centre-of-mass may differ from the wrist in neutral grip.

2. **Overhead arm positions are under-represented in training data.** The BlazePose paper (Bazarevsky et al., *BlazePose: On-device Real-time Body Pose Tracking*, CVPR Workshop CV4ARVR 2020, arXiv:2006.10204) describes: "Our training dataset consists of 60K images with a single or few people in the scene in common poses and 25K images with a single person in the scene performing fitness exercises." There is no documented overhead-vertical subset. Expect higher landmark error at full lockout.

3. **Head-must-be-visible constraint.** Per the same paper: "we make the strong, yet for AR applications valid, assumption that the head of the person should always be visible." The official BlazePose GHUM 3D model card lists "Head is not visible" as an out-of-scope condition. When plates eclipse the head from sagittal at lockout, *all* head-position metrics degrade — including the critical S6. Mitigation: prefer **ear** landmarks (7, 8) over the nose (more likely to remain visible past the plate edge) and use a 45° oblique backup.

4. **No scapular tracking.** Landmarks 11, 12 approximate the acromion but the scapula itself — and crucially its upward rotation and posterior tilt during overhead motion — is invisible. P1 is therefore inferential only.

5. **Lumbar spine is not directly tracked.** The lumbar arch in S8 is estimated via the angle between (hip-shoulder) and (hip-knee) vectors, which conflates true lumbar extension with thoracic extension and pelvic anterior tilt. It is a usable safety proxy, not a clinical measurement.

6. **DBs move independently.** The averaged `wrist_centre` is misleading for DB work; always track 15 and 16 separately and surface F3/T6 explicitly.

7. **Z-axis unreliable.** Per the BlazePose GHUM model card, depth is not metric-accurate. Bar-drift detection requires the sagittal view, not z-displacement.

8. **Bench occludes the back for seated DB.** S17 back-contact is a hip-y stability proxy, not a true measurement. A rigid bench is assumed.

9. **Camera framing must include lockout.** Many gym cameras crop the top of the press; the system must detect this (wrist exits frame) and refuse to score lockout-dependent metrics rather than fabricate values.

10. **Lockout pause requires temporal analysis.** A genuine pause is ≥0.3 s with bar/DB stable; a "touch-and-go" bounces immediately. S15 is intrinsically temporal — single-frame analysis cannot detect it.

11. **Single-person model.** If a spotter is in frame, MediaPipe may track the wrong subject. Use ROI propagation (`static_image_mode=False`) and reject reps with landmark jumps >30% of frame between consecutive frames.

12. **PCK@0.2 evaluation tolerance.** BlazePose is benchmarked using "Percent of Correct Points with 20% tolerance (PCK@0.2)" — i.e., a keypoint is "correct" if within 20% of torso size, giving ~6 cm of landmark uncertainty for a typical adult. Sub-3-cm thresholds (S5 Very-Good, S13 Very-Good) operate at the *edge* of model reliability. Use rolling averages over 3–5 frames and reject single-frame outliers.

---

## 13. Appendix — Metric Summary Table

Legend: **View** S=Sagittal, F=Frontal, R=Rear, T=Tempo (cross-view). **Type** 1=one-sided, 2=two-sided, C=categorical. **Weight** within category.

| # | Metric | View | Type | Cat | Weight (Mil) | Weight (DB) | Mil | DB |
|---|---|---|---|---|---|---|---|---|
| S1 | Bar start vs clavicle | S | 1 | Tech | (part of setup 10) | (part of setup 14) | ✓ | ✓ |
| S2 | Forearm vertical start | S | 1 | Tech | (setup) | (setup) | ✓ | ✓ |
| S3 | Elbow angle start | S | 2 | Tech | (setup) | (setup) | ✓ | ✓ |
| S4 | Torso lean start | S | 1 | Tech | (setup) | (setup) | ✓ | ✓ |
| S5 | Bar/DB horizontal max | S | 1 | Tech | 20 | 15 | ✓ | ✓ |
| S6 | Head under bar | S | 1 | Tech | 15 | 5 | ✓ | ✓ |
| S7 | Torso lean lockout | S | 1 | Tech | 8 | 10 | ✓ | ✓ |
| S8 | Lumbar arch delta | S | 1 | **Safety** | 35 | 30 | ✓ | ✓ |
| S9 | Knee flexion | S | 1 | **Safety** | 15 | — | ✓ | — |
| S10 | Hip-X thrust | S | 1 | **Safety** | 15 | — | ✓ | — |
| S11 | Elbow lockout | S | 2 | Tech | 15 | 18 | ✓ | ✓ |
| S12 | Shoulder flexion lockout | S | 1 | Tech | 12 | 14 | ✓ | ✓ |
| S13 | Bar over mid-foot | S | 1 | **Safety** | 10 | — | ✓ | — |
| S14 | Wrist angle | S | 2 | **Safety** | 10 | 10 | ✓ | ✓ |
| S15 | Lockout hold | T | 1 | Tech | 8 | 10 | ✓ | ✓ |
| S16 | ROM bottom | S | 1 | Tech | 12 | 14 | ✓ | ✓ |
| S17 | Back contact (seated) | S | 1 | **Safety** | — | 20 | — | ✓ |
| S18 | Feet contact (seated) | S | 2 | Tech | — | (setup) | — | ✓ |
| F1 | Grip width | F | 1 | **Safety** | 8 | — | ✓ | — |
| F2 | Bar tilt | F | 1 | Tech | (replaces F3 for BB) | — | ✓ | — |
| F3 | DB symmetry | F | 2 | **Safety** | — | 15 | — | ✓ |
| F4 | Elbow flare | F | 2 | **Safety** | 7 | 10 | ✓ | ✓ |
| F5 | Wrist lateral break | F | 2 | **Safety** | (low) | 8 | ✓ | ✓ |
| F6 | Head lateral tilt | F | 1 | Tech | (small) | (small) | ✓ | ✓ |
| F7 | DB path parallelism | F | 2 | **Safety** | — | 7 | — | ✓ |
| F8 | DB-clang at top | F | C | Advisory | — | flag | — | ✓ |
| P2 | Shoulder symmetry | R/F | 2 | Tech | (small) | (small) | ✓ | ✓ |
| P3 | Lateral lean | R/F | 1 | **Safety** | (small) | (small) | ✓ | ✓ |
| P4 | Hip alignment | R | 2 | Tech | (small) | — | ✓ | — |
| P5 | Foot stance | R | C | Class | classifier input | — | ✓ | — |
| T1 | Setup time | T | 1 | Perf | 10 | 10 | ✓ | ✓ |
| T2 | Concentric duration | T | 1 | Perf | 35 (T6 folded in) | 20 | ✓ | ✓ |
| T3 | Eccentric duration | T | 1 | Perf | 15 | 15 | ✓ | ✓ |
| T4 | E:C ratio | T | 1 | Perf | 10 | 10 | ✓ | ✓ |
| T5 | Sticking-point location | T | 1 | Perf | 15 | 15 | ✓ | ✓ |
| T6 | DB tempo symmetry | T | 2 | Perf | — | 15 | — | ✓ |
| T7 | Rep-to-rep CV | T | 1 | Perf | 15 | 15 | ✓ | ✓ |

**Category totals (sum-to-100 check, Military)**: Safety 35+15+15+10+10+8+7 = 100 ✓ | Technique 20+15+15+12+12+10+8+8 = 100 ✓ | Performance 10+35+15+10+15+15 = 100 ✓.

**Category totals (sum-to-100 check, Seated DB)**: Safety 30+20+15+10+10+8+7 = 100 ✓ | Technique 15+5+18+14+14+14+10+10 = 100 ✓ | Performance 10+20+15+10+15+15+15 = 100 ✓.

---

*End of document.*