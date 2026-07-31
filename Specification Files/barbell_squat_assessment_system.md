# Barbell Squat Assessment System

A complete framework for rating barbell squats (normal/parallel and deep/ATG variants) using camera-based biomechanical metrics, scoring thresholds, weighted aggregation, and grading.

---

## Table of Contents

1. [Required Camera Angles](#1-required-camera-angles)
2. [Normal vs Deep Squat: Key Differences](#2-normal-vs-deep-squat-key-differences)
3. [Sagittal (Side) View Metrics](#3-sagittal-side-view-metrics)
4. [Frontal (Front) View Metrics](#4-frontal-front-view-metrics)
5. [Posterior (Rear) View Metrics](#5-posterior-rear-view-metrics)
6. [Tempo & Control Metrics](#6-tempo--control-metrics)
7. [Composite Scoring System](#7-composite-scoring-system)
8. [Grade & Label Mapping](#8-grade--label-mapping)
9. [Alternative Naming Schemes](#9-alternative-naming-schemes)
10. [Worked Example](#10-worked-example)
11. [Practical Notes & Caveats](#11-practical-notes--caveats)

---

## 1. Required Camera Angles

You need a minimum of **two views**, ideally **three**, to capture all the metrics:

1. **Sagittal (side) view** — perpendicular to the lifter, lens at hip height. Captures depth, torso lean, bar path, knee/hip/ankle angles. This is the single most informative angle.
2. **Frontal (anterior) view** — directly in front, lens at hip height. Captures knee valgus, foot position, lateral shifts, bar tilt.
3. **Posterior (rear) view** — directly behind. Captures hip shift, spinal alignment, bar tilt (cross-check with front view).

For research-grade analysis, add a **45° oblique** view to resolve out-of-plane motion. For most coaching use, side + front is sufficient.

### Camera Setup Recommendations

| Parameter | Recommendation |
|---|---|
| Frame rate | ≥60 fps (120 fps preferred for bar speed/tempo) |
| Resolution | 1080p minimum |
| Lens height | At hip crease of lifter |
| Distance | 2–3 m from lifter, full body in frame |
| Lighting | Even, no backlighting silhouettes |
| Markers (optional) | Reflective dots on hip, knee, ankle, shoulder, bar end |

---

## 2. Normal vs Deep Squat: Key Differences

Many thresholds below split by squat style because what's "good" form differs.

| Aspect | Normal Squat (parallel/low-bar) | Deep Squat (ATG/high-bar) |
|---|---|---|
| Target depth | Hip crease at or just below knee | Hamstring contact with calf |
| Torso lean | More forward (hip-dominant) | More upright (knee-dominant) |
| Bar position | Low-bar (rear delts) | High-bar (traps) |
| Ankle ROM demand | Moderate | High |
| Stance | Wider, more toe-out | Closer to shoulder-width |
| Primary movers | Posterior chain (glutes, hamstrings) | Quads, glutes |
| Typical use | Powerlifting | Olympic lifting, bodybuilding |

---

## 3. Sagittal (Side) View Metrics

### 3.1 Squat Depth
**Definition:** Hip crease position relative to top of knee at lowest point (negative = below knee).

| Score | Normal Squat | Deep Squat |
|---|---|---|
| Very Good | −2 to −5 cm (clearly below) | Hamstring-on-calf contact |
| Good | 0 to −2 cm (parallel) | −10 to −15 cm |
| Yellow Flag | +2 to +5 cm above parallel | −5 to −10 cm |
| Bad | +5 to +10 cm | 0 to −5 cm |
| Very Bad | >+10 cm (quarter squat) | Above parallel |

### 3.2 Torso Angle
**Definition:** Degrees of forward lean from vertical at bottom position, measured along the line from hip to shoulder.

| Score | Normal (Low-Bar) | Deep (High-Bar) |
|---|---|---|
| Very Good | 30°–45° | 0°–20° |
| Good | 25°–50° | 20°–30° |
| Yellow Flag | 15°–25° or 50°–60° | 30°–40° |
| Bad | <15° or 60°–70° | 40°–50° |
| Very Bad | >70° (good-morning collapse) | >50° |

### 3.3 Bar Path Deviation
**Definition:** Horizontal drift of bar from start position to bottom position (cm). Bar should travel vertically over midfoot.

| Score | Threshold |
|---|---|
| Very Good | <2 cm (essentially vertical over midfoot) |
| Good | 2–4 cm |
| Yellow Flag | 4–7 cm |
| Bad | 7–10 cm |
| Very Bad | >10 cm (bar travels forward of toes) |

### 3.4 Hip–Bar Vertical Alignment
**Definition:** Horizontal distance between bar and hip at bottom position (cm). Hips drifting back relative to bar indicates good-morning compensation.

| Score | Threshold |
|---|---|
| Very Good | <5 cm |
| Good | 5–10 cm |
| Yellow Flag | 10–15 cm |
| Bad | 15–20 cm |
| Very Bad | >20 cm (hips far behind bar = good morning) |

### 3.5 Butt Wink / Posterior Pelvic Tilt
**Definition:** Degrees of lumbar flexion / posterior pelvic tilt at bottom of squat. Indicates loss of neutral spine under load.

| Score | Threshold |
|---|---|
| Very Good | 0° (neutral lumbar throughout) |
| Good | <5° (small, late in descent) |
| Yellow Flag | 5°–10° |
| Bad | 10°–20° |
| Very Bad | >20° (visible lumbar rounding under load) |

### 3.6 Heel Contact
**Definition:** Maintenance of heel-to-floor contact through the full range of motion.

| Score | Description |
|---|---|
| Very Good | Full heel contact, midfoot pressure throughout |
| Good | Full heel contact, slight forward weight shift |
| Yellow Flag | Brief heel lift at bottom (<0.5 s) |
| Bad | Sustained heel rise or visible plate slipping |
| Very Bad | Lifter on toes throughout movement |

### 3.7 Shin / Ankle Dorsiflexion Angle
**Definition:** Degrees from vertical at bottom position. Reflects ankle mobility and squat style demands.

| Score | Normal Squat | Deep Squat |
|---|---|---|
| Very Good | 15°–25° | 30°–40° |
| Good | 10°–30° | 25°–45° |
| Yellow Flag | <10° or >35° | <25° or >50° |
| Bad | Knees barely break vertical | <20° (insufficient ROM) |
| Very Bad | Knees behind toes throughout | <15° |

### 3.8 Knee Flexion Angle
**Definition:** Internal angle between thigh and shin at bottom position.

| Score | Normal Squat | Deep Squat |
|---|---|---|
| Very Good | 85°–95° | 30°–45° (deep flexion) |
| Good | 80°–100° | 45°–60° |
| Yellow Flag | 100°–115° | 60°–75° |
| Bad | 115°–135° | 75°–90° |
| Very Bad | >135° (quarter squat) | >90° |

---

## 4. Frontal (Front) View Metrics

### 4.1 Knee Valgus
**Definition:** Inward deviation of knee from the line of the toes (degrees). "Knees caving in."

| Score | Threshold |
|---|---|
| Very Good | 0° (knees track directly over toes) |
| Good | <5°, transient, only at bottom |
| Yellow Flag | 5°–10°, transient |
| Bad | 10°–20° or sustained through movement |
| Very Bad | >20° or asymmetric (one knee collapsing) |

### 4.2 Stance Width
**Definition:** Distance between feet relative to shoulder/biacromial width.

| Score | Normal | Deep |
|---|---|---|
| Very Good | 1.2–1.5× shoulder width | 1.0–1.2× |
| Good | 1.0–1.6× | 0.9–1.3× |
| Yellow Flag | <1.0× or >1.6× | <0.9× or >1.3× |
| Bad | Extremely narrow or sumo-wide | Extreme either direction |
| Very Bad | Inconsistent rep-to-rep | Inconsistent rep-to-rep |

### 4.3 Foot/Toe-Out Angle
**Definition:** Degrees of external rotation of each foot relative to forward direction.

| Score | Threshold |
|---|---|
| Very Good | 15°–30° (symmetric, matches stance) |
| Good | 10°–35° |
| Yellow Flag | <10° or >35° |
| Bad | Asymmetric (>5° difference between feet) |
| Very Bad | Asymmetric >10° or feet rotating during rep |

### 4.4 Lateral Hip Shift
**Definition:** Horizontal offset of hip midpoint from body centerline at bottom (cm). Indicates side-to-side imbalance.

| Score | Threshold |
|---|---|
| Very Good | <1 cm |
| Good | 1–2 cm |
| Yellow Flag | 2–4 cm |
| Bad | 4–7 cm |
| Very Bad | >7 cm (significant load asymmetry) |

### 4.5 Bar Tilt
**Definition:** Angle of barbell relative to horizontal (degrees). One side lower than the other.

| Score | Threshold |
|---|---|
| Very Good | <1° |
| Good | 1°–3° |
| Yellow Flag | 3°–5° |
| Bad | 5°–10° |
| Very Bad | >10° (plates clearly uneven) |

---

## 5. Posterior (Rear) View Metrics

### 5.1 Spinal Alignment
**Definition:** Lateral deviation of spine from vertical (degrees). Detects scoliotic compensation under load.

| Score | Threshold |
|---|---|
| Very Good | <2° |
| Good | 2°–4° |
| Yellow Flag | 4°–7° |
| Bad | 7°–12° |
| Very Bad | >12° |

### 5.2 Shoulder Symmetry
**Definition:** Vertical height difference between left and right shoulders during the lift (cm).

| Score | Threshold |
|---|---|
| Very Good | <1 cm |
| Good | 1–2 cm |
| Yellow Flag | 2–4 cm |
| Bad | 4–6 cm |
| Very Bad | >6 cm |

---

## 6. Tempo & Control Metrics

These can be measured from any view but are easiest to extract from the side view.

### 6.1 Eccentric (Descent) Time

| Score | Threshold |
|---|---|
| Very Good | 2–3 s, smooth |
| Good | 1.5–4 s |
| Yellow Flag | <1.5 s or 4–5 s |
| Bad | <1 s (uncontrolled drop) or >5 s |
| Very Bad | Bouncing at bottom |

### 6.2 Concentric (Ascent) Time

| Score | Threshold |
|---|---|
| Very Good | 1–2 s, continuous |
| Good | <3 s, no stalling |
| Yellow Flag | Brief sticking point (<1 s pause) |
| Bad | Visible grind (>1 s) or speed loss >50% |
| Very Bad | Failed lockout or multiple stalls |

### 6.3 Rep-to-Rep Consistency
**Definition:** Variance across the set in any of the metrics above.

| Score | Threshold |
|---|---|
| Very Good | <5% variance in depth, bar path, tempo |
| Good | 5%–10% |
| Yellow Flag | 10%–15% |
| Bad | 15%–25% (form degrading) |
| Very Bad | >25% (clear breakdown) |

---

## 7. Composite Scoring System

### 7.1 Step 1 — Convert Each Metric to a 0–100 Sub-Score

Map the five tiers to score bands, then **linearly interpolate** within each band based on the raw value:

| Tier | Score Band |
|---|---|
| Very Good | 90–100 |
| Good | 75–89 |
| Yellow Flag | 60–74 |
| Bad | 40–59 |
| Very Bad | 0–39 |

**Formula (one-sided metrics, e.g. knee valgus where 0 is ideal):**

```
score = 100 − (raw_value − ideal) / (worst − ideal) × 100
```

clamped to [0, 100]. Anchor the band boundaries to the thresholds defined above.

**Example for knee valgus:**

| Raw valgus | Sub-score |
|---|---|
| 0° | 100 |
| 5° (Good/Yellow boundary) | 75 |
| 10° (Yellow/Bad boundary) | 60 |
| 20° (Bad/V.Bad boundary) | 40 |
| ≥30° | 0 |

**For two-sided metrics** (torso angle, foot angle — where both too-little and too-much are bad), use a **tent function**: score peaks at the ideal value and falls off in both directions toward the threshold boundaries.

### 7.2 Step 2 — Apply Category Weights

Group metrics so safety dominates technique, and technique dominates aesthetics:

| Category | Weight | Metrics (individual weight in parentheses) |
|---|---|---|
| **Safety** | 40% | Knee valgus (15), Butt wink (15), Heel contact (5), Spinal alignment (5) |
| **Technique** | 40% | Depth (15), Torso angle (10), Bar path (10), Hip shift (5) |
| **Performance** | 20% | Bar tilt (3), Tempo eccentric (4), Tempo concentric (4), Consistency (9) |

Individual weights sum to 100. Adjust to your context:
- **Coaching beginners** → weight safety to 50%
- **Competition prep** → weight performance higher
- **Rehab** → safety to 60%, omit performance entirely

### 7.3 Step 3 — Compute Composite Score

**Weighted arithmetic mean** (simple, most explainable):

```
Composite = Σ (weight_i × sub_score_i)
```

**Weighted geometric mean** (penalizes single low scores harder):

```
Composite = Π (sub_score_i ^ weight_i)
```

Use geometric mean when "one bad component ruins the rep" matches your philosophy.

### 7.4 Step 4 — Hard-Fail Safety Overrides

Apply these *after* the weighted mean. They prevent a lifter from "averaging out" a dangerous flaw:

| Condition | Override |
|---|---|
| Any Safety metric scores <40 | Cap composite at 55 (max D) |
| Two or more Safety metrics <40 | Cap at 40 (max E) |
| Spinal flexion / butt wink >20° under load | Cap at 50 |
| Sustained knee valgus >20° | Cap at 50 |
| Bar dropped / lifter falls | Score = 0 |

### 7.5 Step 5 — Per-Set Aggregation

Each **rep** gets a composite score. The **set** score is computed by one of:

- **Mean of reps** — rewards consistency
- **Worst rep** — safety-conservative (recommended for novices)
- **Last 3 reps mean** — captures form breakdown under fatigue

---

## 8. Grade & Label Mapping

| Score | Grade | Default Label |
|---|---|---|
| 90–100 | A | Very Good |
| 75–89 | B | Good |
| 60–74 | C | Yellow Flag |
| 40–59 | D | Bad |
| 0–39 | E | Very Bad |

For finer resolution, split into **A+/A/A−** using ±3 points around boundaries (e.g., A+ = 97–100, A = 93–96, A− = 90–92).

---

## 9. Alternative Naming Schemes

Pick the one that fits your audience — gym-goers respond differently to "Elite" vs "Pathological."

### Scheme Set 1

| Grade | Traffic Light | Sports Tier | Coaching | Medical/PT | Risk | Tier List | Belt System |
|---|---|---|---|---|---|---|---|
| A | Green | Elite | Master | Optimal | Safe | S | Black |
| B | Light Green | Advanced | Skilled | Functional | Cleared | A | Brown |
| C | Yellow | Intermediate | Developing | Compensated | Caution | B | Blue |
| D | Orange | Novice | Needs Work | Dysfunctional | Warning | C | Green |
| E | Red | Beginner | Critical | Pathological | Stop | D | White |

### Scheme Set 2

| Grade | Stars | Olympic | Descriptive | Percentile | Status |
|---|---|---|---|---|---|
| A | ★★★★★ | Gold | Pristine | 90th+ | Pass |
| B | ★★★★ | Silver | Polished | 75th–90th | Pass |
| C | ★★★ | Bronze | Passable | 50th–75th | Review |
| D | ★★ | — | Problematic | 25th–50th | Coach |
| E | ★ | — | Perilous | <25th | Fail |

### Scheme Set 3 (additional options)

| Grade | Academic | Quality | Threat Level | Diving | Climbing |
|---|---|---|---|---|---|
| A | Distinction | Excellent | Clear | 10/10 | Onsight |
| B | Merit | Proficient | Low | 8/10 | Flash |
| C | Pass | Acceptable | Moderate | 6/10 | Redpoint |
| D | Borderline | Deficient | High | 4/10 | Project |
| E | Fail | Poor | Critical | 2/10 | Crux |

---

## 10. Worked Example

A lifter's rep yields these sub-scores:

| Metric | Sub-score | Weight |
|---|---|---|
| Depth | 92 | 0.15 |
| Torso angle | 85 | 0.10 |
| Knee valgus | 65 | 0.15 |
| Bar path | 80 | 0.10 |
| Butt wink | 70 | 0.15 |
| Heel contact | 95 | 0.05 |
| Spinal alignment | 90 | 0.05 |
| Hip shift | 88 | 0.05 |
| Bar tilt | 80 | 0.03 |
| Eccentric tempo | 75 | 0.04 |
| Concentric tempo | 85 | 0.04 |
| Consistency | 78 | 0.09 |

**Weighted sum:**

```
(0.15×92) + (0.15×65) + (0.05×95) + (0.05×90)  ← Safety = 22.05
+ (0.15×92) + (0.10×85) + (0.10×80) + (0.05×88)  ← Technique = 34.70
+ (0.03×80) + (0.04×75) + (0.04×85) + (0.09×78)  ← Performance = 15.82

Total ≈ 72.57
```

No safety override triggered (all Safety metrics ≥40).

**Final: 73 → Grade C → "Yellow Flag" / "Intermediate" / "Compensated" / "Bronze"**

Top weaknesses to surface to the lifter: **knee valgus (65)** and **butt wink (70)**.

---

## 11. Practical Notes & Caveats

### 11.1 Anthropometry Matters
Thresholds are population averages. Femur-to-torso ratio and ankle mobility shift what counts as "good" torso lean and shin angle for individuals. **Low-bar lifters with long femurs should lean more**; flagging them as Bad for a 50° torso would be wrong. If building automated scoring, adjust torso-angle thresholds by the lifter's femur-to-tibia ratio.

### 11.2 Track Continuously, Not Just at the Bottom
Most metrics above describe the bottom position, but many (knee valgus, heel contact, bar path) should be tracked **continuously** through the rep, with the **worst frame** determining the score for that metric.

### 11.3 Calibration > Formula
The math is easy; the thresholds are the hard part. Collect baseline data from 20–30 lifters of known skill levels, plot composite scores against expert ratings, and shift the band boundaries (75/60/40 cutoffs) until grades match coach intuition.

### 11.4 Always Surface the Reason
Don't show users only the final grade — surface the **two lowest-scoring metrics** alongside it:

> "B, 82 — work on knee valgus and tempo."

A grade without a reason is useless for improvement.

### 11.5 Style-Specific Scoring
Always know which squat style is being graded **before** scoring. Applying low-bar torso thresholds to a high-bar squat (or vice versa) will produce false flags for nearly every lifter.

### 11.6 Suggested Metric Priorities

If you must trim metrics for a minimum-viable assessment, this is the priority order:

1. Squat depth (definitional — without it, it's not a squat)
2. Knee valgus (highest injury risk)
3. Butt wink / spinal flexion (highest injury risk under load)
4. Torso angle (style-defining, indicates compensation)
5. Bar path (indicates balance and efficiency)
6. Heel contact (foundational stability)
7. Lateral hip shift (indicates asymmetric weakness)
8. Tempo (control marker)
9. Consistency (fatigue marker)
10. Everything else

### 11.7 Frame-Rate Trade-offs
At 30 fps, you cannot reliably catch a 0.3-second heel lift or a brief knee valgus dip. **60 fps is the minimum** for meaningful biomechanical scoring; 120 fps is preferable if measuring bar speed or sticking points.

---

## Appendix: Metric Summary Table

| # | Metric | View | Type | Default Weight |
|---|---|---|---|---|
| 1 | Squat Depth | Sagittal | One-sided | 15 |
| 2 | Torso Angle | Sagittal | Two-sided | 10 |
| 3 | Bar Path Deviation | Sagittal | One-sided | 10 |
| 4 | Hip–Bar Alignment | Sagittal | One-sided | (incl. in bar path) |
| 5 | Butt Wink | Sagittal | One-sided | 15 |
| 6 | Heel Contact | Sagittal | Categorical | 5 |
| 7 | Shin/Ankle Angle | Sagittal | Two-sided | (incl. in depth/style) |
| 8 | Knee Flexion Angle | Sagittal | One-sided | (incl. in depth) |
| 9 | Knee Valgus | Frontal | One-sided | 15 |
| 10 | Stance Width | Frontal | Two-sided | (style check) |
| 11 | Foot/Toe-Out Angle | Frontal | Two-sided | (style check) |
| 12 | Lateral Hip Shift | Frontal | One-sided | 5 |
| 13 | Bar Tilt | Frontal | One-sided | 3 |
| 14 | Spinal Alignment | Posterior | One-sided | 5 |
| 15 | Shoulder Symmetry | Posterior | One-sided | (incl. in bar tilt) |
| 16 | Eccentric Tempo | Any | Two-sided | 4 |
| 17 | Concentric Tempo | Any | Two-sided | 4 |
| 18 | Consistency | Any | One-sided | 9 |

**Total weights: 100**

---

*End of Document*
