# Biomechanical Assessment System for the Pull-Up
## Pronated, Supinated (Chin-Up), Neutral & Wide-Grip Variations — A MediaPipe-Ready Technical Reference

---

## Table of Contents
1. Required Camera Angles
2. Pull-Up Variation Comparison
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

---

## 1. Required Camera Angles

The pull-up is a vertical, closed-chain, body-mass exercise. Unlike the squat or deadlift — where an external load moves to or past the body — the **bar is fixed and the body moves to the bar**. This inverts the usual reference frame: the wrist landmarks (gripping the bar) become the *fixed* point, and almost every other landmark is measured relative to them.

### 1.1 Camera Setup Recommendations

| Parameter | Recommended | Notes |
|---|---|---|
| Frame rate | **60 fps minimum, 120 fps preferred, 240 fps for kipping** | ≥60 fps is the floor for biomechanics; 120–240 fps is recommended when AI skeleton tracking is used. |
| Resolution | 1080p minimum; 4K downsampled best for pose detection | |
| Codec | Constant frame rate (CFR), H.264/H.265 | Variable frame rate (common on phones) causes sync drift |
| Lens height | **Mid-bar height** (between dead-hang chin position and chin-over-bar position) | Critical: must capture both bottom and top frame without tilting |
| Distance | 3.0–4.5 m from athlete | Athlete + ~0.5 m head clearance + ~1 m foot clearance must all fit |
| Lens | 35–50 mm equivalent; avoid wide-angle (≤24 mm) | Wide lenses introduce vertical distortion that corrupts body-line angles |
| Background | Plain, high-contrast vs. skin/clothing | BlazePose degrades on cluttered backgrounds |
| Lighting | Even, frontal, no backlight from windows | Pull-ups are often done in garages/gyms with a single overhead light — this *backlights* the athlete and ruins landmark visibility |
| Tripod | Mandatory; handheld unusable for tempo metrics | |

### 1.2 The Four Views

| View | Camera Position | Primary Metrics Captured |
|---|---|---|
| **Sagittal (side)** — *most important* | 90° to the bar, athlete's side profile, lens at mid-bar height | Body line / hollow body, hip flexion, kipping/swing, ROM (chin over bar), elbow extension at bottom, bar-path-vs-body, head/neck position, tempo |
| **Frontal (anterior)** | Directly in front of athlete (perpendicular to bar) | Grip width, shoulder symmetry, elbow flare angle, lateral body sway, asymmetric pull, palm orientation (chin-up vs pull-up identification) |
| **Posterior (rear)** | Directly behind athlete | Scapular retraction/depression (inferred), lat flare, spinal alignment, symmetric ascent |
| **45° oblique** | Half-way between sagittal and frontal | Useful fallback when only one camera is available; captures ~80% of both views' metrics with reduced precision |

### 1.3 Pull-Up-Specific Framing Challenges

- **The athlete is fully airborne.** There is no ground contact reference; the wrist–bar interface is the only fixed point. Vertical calibration must use the wrist line, not the floor.
- **Lens height must capture both dead-hang and lockout positions.** Dead-hang puts the chin ~0.55–0.75 m below the bar (depending on stature); lockout puts the chin at bar height. The camera must frame this ~1 m vertical span without panning.
- **Bar occludes the head at lockout.** When the chin clears the bar, the bar passes in front of the face (sagittal view) or directly above the nose (frontal view) — both cases hide mouth/nose landmarks. Mitigation: use **shoulder-Y crossing wrist-Y minus a calibrated offset** as a chin-over-bar proxy when face landmarks vanish.
- **Body fully visible in dead-hang.** The athlete's feet often hang within 0.3 m of the floor. The camera must be backed off enough to include the feet without losing head-room above the bar.
- **General accuracy caveat.** Dill et al. (2023, "Accuracy Evaluation of 3D Pose Estimation with MediaPipe Pose for Physical Exercises") showed MediaPipe landmark accuracy degrades with partial occlusion and non-standard vertical orientations; their work evaluated squats rather than pull-ups, so the magnitude of degradation for overhead-arm postures is *not* benchmarked in published literature. Treat pose-only pull-up assessment as form-grading, not clinical-grade biomechanics.

---

## 2. Pull-Up Variation Comparison

| Dimension | **Pronated Pull-Up** (overhand, palms away — *the standard*) | **Supinated Chin-Up** (palms toward face) | **Neutral-Grip Pull-Up** (palms facing each other) | **Wide-Grip Pull-Up** (≥1.5× biacromial, pronated) |
|---|---|---|---|---|
| Grip orientation | Pronated | Supinated | Neutral | Pronated |
| Grip width | ~1.0–1.3× biacromial | ~1.0× biacromial (narrow/shoulder) | ~1.0–1.2× biacromial (parallel bars) | ≥1.5× biacromial |
| Shoulder mechanic | Shoulder extension + adduction | Shoulder extension dominant | Shoulder extension, mid-range | Shoulder adduction dominant; less extension |
| Elbow path | Slightly out and back | Down and slightly forward (near body) | Down, close to body | Out to sides, in scapular plane |
| Elbow ROM (Youdas 2010) | **93.4 ± 14.6°** | **100.6 ± 14.5°** | ~95° (interpolated, not separately reported) | <90° (reduced ROM, restricted by adduction angle) |
| Elbow angle at top | ~60–70° flexion | ~45–55° flexion | ~50–60° flexion | ~80–90° flexion |
| Primary muscles emphasized (Youdas 2010, %MVIC) | Lats 117–130%, lower trapezius 45–56% (significantly higher than chin-up) | Pec major and biceps brachii significantly higher than pull-up (biceps 78–96%, pec major 44–57%) | Brachioradialis emphasized; trap activation lower than pronated (Dickie 2017: pronated peak middle-trap EMG **60.1 ± 22.5 %MVIC vs neutral 37.1 ± 13.1 %MVIC, p = 0.004**) | Lats relatively highest in wide pull-ups (Prinold & Bull 2016); reduced biceps leverage |
| Difficulty (relative) | **Hard (baseline)** | Easiest (best biceps leverage) | Middle | Hardest (worst biceps leverage + impingement-prone scapular path) |
| ROM standard | Full extension → chin over bar | Full extension → chin over bar | Full extension → chin over bar | Full extension → chin or neck over bar (sternum-to-bar often impractical at wide grip) |
| Sub-acromial impingement risk | Moderate | Lowest of the four | Low | **Highest** — Prinold & Bull (2016, *J Sci Med Sport* 19(8), DOI 10.1016/j.jsams.2015.08.002, PMID 26383875): "Wide and reverse pull-ups demonstrate kinematics patterns linked with increased impingement risk." |
| Common cheats | Kipping, partial ROM (no dead-hang), chin-poke | Body sway, elbow flare, swinging | Forward-leaning torso, sticking-point cheat with hip flick | Truncated ROM, head-poke to "make" the rep |

### 2.1 Strict vs. Kipping vs. Butterfly

| Style | Definition | Scoring Bucket |
|---|---|---|
| **Strict dead-hang pull-up** (the gold standard) | Full elbow extension at bottom, controlled chin-over-bar at top, minimal swing, no momentum | **Primary rubric** (Sections 3–6 thresholds apply) |
| **Kipping pull-up** (CrossFit) | Uses sinusoidal hip flexion/extension to generate upward momentum | **Separate, lower-rigor rubric.** Score on coordination, hollow/arch transitions, and chin-over-bar; do NOT score against "no swing" criteria |
| **Butterfly pull-up** (CrossFit) | Continuous circular kip; chin clears bar, athlete drops in front of bar | Scored as kipping with additional cycle-continuity metric |
| **Chest-to-bar pull-up** (CrossFit) | Same as strict/kipping, but contact at clavicle or below required | Apply pull-up rubric + replace "chin over bar" with "sternum/clavicle touches bar" |
| **StrongFirst Tactical pull-up** | Thumbless overhand grip (men); pause motionless in dead hang with elbows locked before each rep; "neck (clearing the jawline, not the underside of the chin) must clear the bar, or the upper chest must touch the bar"; no kipping or swinging; near-vertical body | Apply strict rubric with the dead-hang and chin/chest thresholds tightened |
| **Sternum chin-up** (Gironda) | Pronounced layback, sternum to bar, head near horizontal | Apply pull-up rubric + layback angle metric (inverted body-inclination thresholds) |

### 2.2 Difficulty Hierarchy (Easiest → Hardest, Strict)

`Chin-up (supinated) < Neutral grip < Pronated shoulder-width < Pronated wide-grip < Sternum chin-up`

This ordering is supported by mechanical leverage at the elbow (biceps better positioned in supination) and by relative %MVIC in the prime mover (biceps brachii peaks at 96% MVIC in chin-up vs. 78% in pull-up; Youdas et al. 2010, *J Strength Cond Res* 24(12):3404–3414).

---

## 3. Sagittal (Side) View Metrics

**Scoring convention.** Every metric is mapped to a 5-tier band (Very Good / Good / Yellow Flag / Bad / Very Bad). The intra-band 0–100 sub-score is then computed by linear interpolation (Section 7, Step 1).

---

### 3.1 Dead-Hang Quality at Bottom (Elbow Extension)

**Definition.** Angle at the elbow formed by shoulder–elbow–wrist at the lowest body position of the rep. 180° = fully straight.

| Tier | Threshold | Sub-score band |
|---|---|---|
| Very Good | 175°–180° (fully extended) | 90–100 |
| Good | 170°–174° | 75–89 |
| Yellow Flag | 160°–169° | 60–74 |
| Bad | 145°–159° | 40–59 |
| Very Bad | <145° (clear partial-rep cheat) | 0–39 |

*Rationale: StrongFirst Tactical Pull-up standard explicitly requires "the elbows must be straight before each repetition with the bicep in line with the ear." Failure to reach ≥170° is the single most common partial-rep cheat.*

---

### 3.2 Body Inclination Angle at Bottom

**Definition.** Angle of body vector (ankle-centre → shoulder-centre) from true vertical, at the dead-hang frame.

| Tier | Threshold | Sub-score |
|---|---|---|
| Very Good | 0°–5° from vertical | 90–100 |
| Good | 5°–10° | 75–89 |
| Yellow Flag | 10°–15° | 60–74 |
| Bad | 15°–25° | 40–59 |
| Very Bad | >25° (massive forward swing) | 0–39 |

---

### 3.3 Body Inclination Angle at Top

**Definition.** Same vector, measured at the chin-over-bar frame. Some posterior lean is normal (especially with narrower grips and chest-to-bar work).

| Tier | Threshold (deviation from vertical, posterior = +) | Sub-score |
|---|---|---|
| Very Good | 0°–10° posterior lean | 90–100 |
| Good | 10°–20° | 75–89 |
| Yellow Flag | 20°–30° (substantial layback or anterior fold) | 60–74 |
| Bad | 30°–45° (heavy kip/sternum-chin position outside intended style) | 40–59 |
| Very Bad | >45° (uncontrolled) | 0–39 |

*Note: Sternum chin-ups intentionally exceed 45° posterior lean — for that style only, the threshold flips and 45°–70° is "Very Good."*

---

### 3.4 Shoulder Elevation at Bottom (Passive vs. Active Hang)

**Definition.** Wrist-Y minus shoulder-Y, normalized by torso length. In a passive dead-hang the shoulders rise toward the ears (high elevation); in an active hang they pull down (depression).

For a strict pull-up, a brief passive hang is acceptable at the bottom, but the *initiation* of the pull must depress the scapulae before the elbow flexes. We score the transition.

| Tier | Behaviour | Sub-score |
|---|---|---|
| Very Good | Clear active scapular depression initiates the pull (shoulder-Y drops 5–10% torso length before elbow angle changes) | 90–100 |
| Good | Depression occurs simultaneously with elbow flexion | 75–89 |
| Yellow Flag | Shoulders remain shrugged throughout; no depression visible | 60–74 |
| Bad | Shoulders shrug *upward* during the pull (jerking, "swinging from the trapezius") | 40–59 |
| Very Bad | Shoulders never leave passive hang; arm-only pull throughout | 0–39 |

---

### 3.5 Elbow Angle at Top (ROM Completion)

**Definition.** Elbow joint angle at the highest body position.

| Tier | Threshold (chin-up / pronated / wide) | Sub-score |
|---|---|---|
| Very Good | ≤50° / ≤60° / ≤80° (chin clearly over bar, often sternum near bar) | 90–100 |
| Good | 51–65° / 61–75° / 81–95° | 75–89 |
| Yellow Flag | 66–80° / 76–90° / 96–105° | 60–74 |
| Bad | 81–100° / 91–105° / >105° (chin at bar height, not clearly over) | 40–59 |
| Very Bad | >100° / >105° / >120° (no chin-over-bar) | 0–39 |

---

### 3.6 Chin-Over-Bar Detection

**Definition.** Is the mouth-centre Y-coordinate (or nose Y as fallback) above the wrist-line Y-coordinate at the top of the rep?

| Tier | Position | Sub-score |
|---|---|---|
| Very Good | Mouth ≥ 3 cm clearly above bar; sustained ≥0.2 s | 90–100 |
| Good | Mouth 0–3 cm above bar | 75–89 |
| Yellow Flag | Mouth at bar (within ±1 cm) | 60–74 |
| Bad | Chin below bar; eyes/nose only above | 40–59 |
| Very Bad | Top of head only, or no clearance | 0–39 |

*Per CrossFit Open 22.3 standard (CrossFit, LLC): "The athlete must start each rep with arms fully extended and feet off the ground… The rep is credited when the athlete's chin breaks the horizontal plane of the bar."*

---

### 3.7 Sternum-to-Bar (Chest-to-Bar variants only)

| Tier | Contact Point | Sub-score |
|---|---|---|
| Very Good | Sternum below clavicle touches bar | 90–100 |
| Good | Upper sternum / clavicle contact | 75–89 |
| Yellow Flag | Neck contact, not chest | 60–74 |
| Bad | Chin clearance only, no chest contact (fails C2B standard) | 40–59 |
| Very Bad | No clearance | 0–39 |

---

### 3.8 Body Line / Hollow-Body Maintenance

**Definition.** Standard deviation, across the rep, of the angle between (hip-centre → shoulder-centre) and (hip-centre → knee-centre). A rigid hollow body holds this near-constant.

| Tier | Std-Dev of body-line angle across rep | Sub-score |
|---|---|---|
| Very Good | <3° (rigid hollow body) | 90–100 |
| Good | 3°–6° | 75–89 |
| Yellow Flag | 6°–10° | 60–74 |
| Bad | 10°–20° | 40–59 |
| Very Bad | >20° (visible piking/arching) | 0–39 |

---

### 3.9 Hip Flexion Angle

**Definition.** Shoulder-hip-knee three-point angle. 180° = fully extended body (legs straight, hips not flexed); ~140° = legs bent at hip; ~90° = "L-sit pull-up" (intentional variant, do not penalize the absolute value, only inconsistency).

| Tier | Behaviour | Sub-score |
|---|---|---|
| Very Good | Consistent within ±5° across rep, athlete's chosen position (legs straight or knees bent fixed) | 90–100 |
| Good | Consistent within ±10° | 75–89 |
| Yellow Flag | ±10°–20° variation | 60–74 |
| Bad | ±20°–35° (clear hip kick) | 40–59 |
| Very Bad | >±35° (full kip generation) — auto-classify as kipping style | 0–39 |

---

### 3.10 Knee Position & Scissor Detection

**Definition.** Horizontal distance between left and right knee landmarks, normalized to hip width.

| Tier | Knee separation / behaviour | Sub-score |
|---|---|---|
| Very Good | Knees together throughout (separation <1.2× hip width) | 90–100 |
| Good | <1.5× | 75–89 |
| Yellow Flag | 1.5×–2.0× | 60–74 |
| Bad | One knee in front of the other (scissor motion to generate momentum) | 40–59 |
| Very Bad | Sustained scissor kicking, alternating | 0–39 |

---

### 3.11 Kipping Detection (Strict Style Scoring Only)

**Definition.** Peak-to-peak amplitude of hip-X (horizontal position of hip-centre) across the rep, normalized by femur length.

| Tier | Hip-X swing amplitude | Sub-score (strict) |
|---|---|---|
| Very Good | <0.10 femur-length (essentially static torso) | 90–100 |
| Good | 0.10–0.20 | 75–89 |
| Yellow Flag | 0.20–0.40 (visible body sway) | 60–74 |
| Bad | 0.40–0.80 (clear kip-assist) | 40–59 |
| Very Bad | >0.80 (full CrossFit kip cycle) | 0–39 |

---

### 3.12 Leg Swing / Pendulum

**Definition.** Peak-to-peak ankle-X amplitude across the rep, normalized by leg length. Slightly more permissive than hip-X because feet pendulate more naturally.

| Tier | Ankle-X swing amplitude | Sub-score |
|---|---|---|
| Very Good | <0.15 leg-length | 90–100 |
| Good | 0.15–0.30 | 75–89 |
| Yellow Flag | 0.30–0.50 | 60–74 |
| Bad | 0.50–0.80 | 40–59 |
| Very Bad | >0.80 | 0–39 |

---

### 3.13 Bar-Path-vs-Body

**Definition.** Wrist-X displacement across the rep (in image coordinates). For a perfect strict pull-up, the wrist is fixed; only the body moves.

| Tier | Wrist-X drift amplitude | Sub-score |
|---|---|---|
| Very Good | <2% of image width (camera-stable, athlete-stable) | 90–100 |
| Good | 2–5% | 75–89 |
| Yellow Flag | 5–10% (visible bar bend or athlete hand-creep) | 60–74 |
| Bad | 10–20% | 40–59 |
| Very Bad | >20% (athlete is gripping unstable surface or camera moved) | 0–39 |

---

### 3.14 Head/Neck Position (Chin-Poke Detection)

**Definition.** Angle of the neck vector (shoulder-centre → nose) relative to the torso vector (hip-centre → shoulder-centre). Chin-poking = athlete extends neck forward to "make" the rep without raising the body enough.

| Tier | Neck deviation from torso line | Sub-score |
|---|---|---|
| Very Good | <10° (neutral) | 90–100 |
| Good | 10°–20° | 75–89 |
| Yellow Flag | 20°–30° (mild chin-poke) | 60–74 |
| Bad | 30°–45° (clear chin-poke compensation) | 40–59 |
| Very Bad | >45° (head whip) | 0–39 |

---

## 4. Frontal (Anterior) View Metrics

### 4.1 Grip Width (relative to biacromial)

**Definition.** Distance between left and right wrist landmarks ÷ distance between left and right shoulder (acromial) landmarks.

| Tier | Width ratio | Sub-score (strict pronated pull-up) |
|---|---|---|
| Very Good | 1.10–1.35 (just outside shoulder) | 90–100 |
| Good | 1.00–1.10 or 1.35–1.50 | 75–89 |
| Yellow Flag | 0.85–1.00 (narrow) or 1.50–1.75 (moderately wide) | 60–74 |
| Bad | 0.70–0.85 (very narrow) or 1.75–2.00 (wide) | 40–59 |
| Very Bad | <0.70 or >2.00 (extreme wide → impingement risk) | 0–39 |

*For chin-ups, optimal narrows to 0.95–1.15×; for neutral grip, fixed by handle spacing. Andersen et al. (2014) found similar lat EMG across narrow / medium / wide pronated grips (1×, 1.5×, 2× biacromial) for the lat pulldown, but lifters achieved higher 6RM loads with narrow and medium widths than wide.*

---

### 4.2 Hand-Width Symmetry (Hand Placement Symmetry)

**Definition.** Distance from each wrist to the midline of the body should be equal.

| Tier | |L_wrist – midline| − |R_wrist – midline| | Sub-score |
|---|---|---|
| Very Good | <2% of biacromial | 90–100 |
| Good | 2–5% | 75–89 |
| Yellow Flag | 5–10% (one hand wider than the other) | 60–74 |
| Bad | 10–20% | 40–59 |
| Very Bad | >20% | 0–39 |

---

### 4.3 Shoulder Symmetry (Asymmetric Pull)

**Definition.** Absolute difference between left-shoulder-Y and right-shoulder-Y at the top of the rep.

| Tier | Y-difference / torso length | Sub-score |
|---|---|---|
| Very Good | <2% (essentially level) | 90–100 |
| Good | 2–5% | 75–89 |
| Yellow Flag | 5–8% (~5°–10° tilt) | 60–74 |
| Bad | 8–12% (~10°–15° tilt) | 40–59 |
| Very Bad | >12% (>15° tilt — one side dominant) | 0–39 |

*A >15° shoulder asymmetry at lockout is one of the safety/quality overrides in Section 7.4.*

---

### 4.4 Elbow Flare Angle

**Definition.** Angle in the frontal plane between (shoulder → elbow) vector and the vertical, at the moment of peak elbow flexion. Measured per side.

| Tier | Pronated pull-up flare | Chin-up flare | Sub-score |
|---|---|---|---|
| Very Good | 15°–35° | 0°–15° | 90–100 |
| Good | 35°–50° | 15°–25° | 75–89 |
| Yellow Flag | 50°–65° | 25°–40° | 60–74 |
| Bad | 65°–80° | 40°–55° | 40–59 |
| Very Bad | >80° (elbows out to sides, lat disengaged) | >55° | 0–39 |

---

### 4.5 Lateral Body Sway

**Definition.** Peak-to-peak hip-X amplitude *in the frontal plane*, normalized to femur length.

| Tier | Amplitude | Sub-score |
|---|---|---|
| Very Good | <0.05 | 90–100 |
| Good | 0.05–0.10 | 75–89 |
| Yellow Flag | 0.10–0.20 | 60–74 |
| Bad | 0.20–0.35 | 40–59 |
| Very Bad | >0.35 | 0–39 |

---

### 4.6 Vertical Alignment (Head over Centre Between Hands)

**Definition.** Horizontal offset of nose-X from the midpoint between the two wrists, at the top of the rep.

| Tier | Offset / wrist separation | Sub-score |
|---|---|---|
| Very Good | <5% | 90–100 |
| Good | 5–10% | 75–89 |
| Yellow Flag | 10–15% | 60–74 |
| Bad | 15–25% | 40–59 |
| Very Bad | >25% (athlete pulling toward one side) | 0–39 |

---

## 5. Posterior (Rear) View Metrics

*Note: All five rear-view metrics suffer the fundamental limitation that **MediaPipe Pose has no scapular landmarks**. They are inferred from acromial (shoulder) landmark behaviour and back contour. Where scapular kinematic data is required for clinical applications, marker-based motion capture (as in Prinold & Bull 2016, who used a skin-fixed scapula tracking technique with retro-reflective markers and achieved CMC values of 0.77–0.90 for scapulothoracic rotations) or a depth camera is required.*

### 5.1 Scapular Retraction at Top (Inferred)

**Definition.** Apparent inter-shoulder distance at the top of the rep vs. at the dead-hang. Retraction shortens the visible distance between the two shoulder landmarks projected on the rear view.

| Tier | (Top distance − Bottom distance) / Bottom distance | Sub-score |
|---|---|---|
| Very Good | −10% to −15% (clear retraction) | 90–100 |
| Good | −5% to −10% | 75–89 |
| Yellow Flag | −5% to +5% (no change) | 60–74 |
| Bad | +5% to +15% (shoulders rolling forward) | 40–59 |
| Very Bad | >+15% (protraction — opposite of intended) | 0–39 |

---

### 5.2 Scapular Depression at Top (Shoulders Not Shrugged)

**Definition.** Shoulder-Y to ear-Y vertical distance at top of rep, normalized to neck length.

| Tier | Behaviour | Sub-score |
|---|---|---|
| Very Good | Shoulders clearly below ears; depression maintained | 90–100 |
| Good | Slight elevation at peak effort | 75–89 |
| Yellow Flag | Mild shrug visible | 60–74 |
| Bad | Pronounced shrug; shoulders within 3 cm of earlobes | 40–59 |
| Very Bad | Shoulders touch ears (extreme shrug, lat disengaged) | 0–39 |

---

### 5.3 Lat Engagement Visualization (Lat Flare)

**Definition.** Apparent torso-width at mid-back at top of rep, normalized to torso-width at start. (Visual proxy only — no direct EMG correlate from pose.)

| Tier | Width increase | Sub-score |
|---|---|---|
| Very Good | ≥15% | 90–100 |
| Good | 10–15% | 75–89 |
| Yellow Flag | 5–10% | 60–74 |
| Bad | 0–5% | 40–59 |
| Very Bad | Decrease in width (no flare) | 0–39 |

---

### 5.4 Spinal Alignment (No Lateral Deviation)

**Definition.** Angle of (hip-centre → shoulder-centre) vector from the vertical in the frontal/rear projection.

| Tier | Deviation | Sub-score |
|---|---|---|
| Very Good | <3° | 90–100 |
| Good | 3°–6° | 75–89 |
| Yellow Flag | 6°–10° | 60–74 |
| Bad | 10°–15° | 40–59 |
| Very Bad | >15° (clear lateral spinal lean) | 0–39 |

---

### 5.5 Symmetric Ascent

**Definition.** Phase-lag (in frames) between left-shoulder-Y trajectory and right-shoulder-Y trajectory, computed by cross-correlation over the concentric phase.

| Tier | Phase lag | Sub-score |
|---|---|---|
| Very Good | 0–2 frames @ 60 fps (<33 ms) | 90–100 |
| Good | 2–4 frames | 75–89 |
| Yellow Flag | 4–8 frames | 60–74 |
| Bad | 8–15 frames | 40–59 |
| Very Bad | >15 frames (one side leads dramatically) | 0–39 |

---

## 6. Tempo & Control Metrics

### 6.1 Setup Quality

| Tier | Behaviour | Sub-score |
|---|---|---|
| Very Good | Stepped/jumped quietly to bar, came to motionless dead hang for ≥1 s before pulling | 90–100 |
| Good | Brief settle (<1 s) before pull | 75–89 |
| Yellow Flag | Pull starts with residual swing from grip approach | 60–74 |
| Bad | Jumping start used to clear first rep | 40–59 |
| Very Bad | Aggressive jump that completes ½ the rep | 0–39 |

---

### 6.2 Concentric Tempo (Bottom → Top)

| Tier | Time (strict pull-up) | Sub-score |
|---|---|---|
| Very Good | 1.0–2.0 s (controlled, no jerk) | 90–100 |
| Good | 0.7–1.0 s or 2.0–2.5 s | 75–89 |
| Yellow Flag | <0.7 s (explosive/kip-like) or 2.5–4.0 s (grinding) | 60–74 |
| Bad | 4.0–6.0 s | 40–59 |
| Very Bad | >6.0 s (failure/sticking-point grinder) | 0–39 |

---

### 6.3 Pause at Top (Chin-Over-Bar Hold)

| Tier | Hold duration | Sub-score |
|---|---|---|
| Very Good | ≥0.5 s clear hold | 90–100 |
| Good | 0.3–0.5 s | 75–89 |
| Yellow Flag | 0.1–0.3 s (brief touch) | 60–74 |
| Bad | <0.1 s (bounce off lockout) | 40–59 |
| Very Bad | No discernible top position | 0–39 |

---

### 6.4 Eccentric Tempo (Top → Bottom)

| Tier | Time | Sub-score |
|---|---|---|
| Very Good | 2.0–4.0 s controlled | 90–100 |
| Good | 1.5–2.0 s or 4.0–5.0 s | 75–89 |
| Yellow Flag | 1.0–1.5 s | 60–74 |
| Bad | 0.5–1.0 s (drop) | 40–59 |
| Very Bad | <0.5 s (free fall to dead hang — shoulder-injury risk) | 0–39 |

---

### 6.5 Dead-Hang Reset Between Reps

| Tier | Behaviour | Sub-score |
|---|---|---|
| Very Good | Full extension ≥170° elbow + brief motionless pause every rep | 90–100 |
| Good | Full extension, no pause | 75–89 |
| Yellow Flag | 160°–170° (slight residual bend) | 60–74 |
| Bad | 145°–160° between reps | 40–59 |
| Very Bad | <145° (continuous "half-rep" cycle) | 0–39 |

---

### 6.6 Sticking-Point Detection

**Definition.** Identify the frame where concentric vertical velocity drops to <30% of its peak. In strict pull-ups this typically falls in the chin-to-bar transition, when the elbow approaches ~90° flexion.

Track:
- Time spent in sticking region (>30% of concentric duration → flag)
- Body-position deterioration during stick (chin-poke, elbow flare, shoulder shrug)

---

### 6.7 Rep-to-Rep Consistency

**Definition.** Standard deviation, across all reps in a set, of: concentric time, peak chin-Y, body-line angle SD per rep.

| Tier | Consistency (SD of concentric time across reps) | Sub-score |
|---|---|---|
| Very Good | <0.15 s | 90–100 |
| Good | 0.15–0.30 s | 75–89 |
| Yellow Flag | 0.30–0.60 s | 60–74 |
| Bad | 0.60–1.20 s (clear fatigue creep) | 40–59 |
| Very Bad | >1.20 s (set has fallen apart) | 0–39 |

---

### 6.8 ROM Completion Rate

**Definition.** Fraction of reps in the set that satisfy BOTH dead-hang at bottom (≥170° elbow) AND chin clearly over bar at top.

| Tier | Valid-rep fraction | Sub-score |
|---|---|---|
| Very Good | 100% | 90–100 |
| Good | 85–99% | 75–89 |
| Yellow Flag | 65–85% | 60–74 |
| Bad | 40–65% | 40–59 |
| Very Bad | <40% | 0–39 |

---

## 7. Composite Scoring System

### 7.1 Step 1 — Sub-Score Mapping

Each raw metric maps to a 0–100 sub-score via **linear interpolation between threshold boundaries**:

| Tier | Sub-score range |
|---|---|
| Very Good | 90–100 |
| Good | 75–89 |
| Yellow Flag | 60–74 |
| Bad | 40–59 |
| Very Bad | 0–39 |

For example, if "Body Inclination at Top" is 22° (which is inside the Yellow Flag 20°–30° band), the sub-score is:
`60 + (74 − 60) × (30 − 22) / (30 − 20) = 60 + 14 × 0.8 = 71.2`

### 7.2 Step 2 — Category Weights

Pull-up safety risk is lower than barbell lifts (no falling weight on athlete) but non-trivial (shoulder labrum/rotator-cuff). Per Summitt RJ, Cotton RA, Kays AC & Slaven EJ ("Shoulder Injuries in Individuals Who Participate in CrossFit Training," *Sports Health* 2016;8(6):541–546, PMID 27578854): of 187 surveyed CrossFit athletes, 44 (**23.5%**) reported a shoulder injury in the prior 6 months; kipping pull-ups were specifically attributed to 5 of 51 (~10%) of reported shoulder injuries, behind overhead presses (25%) and snatches (20%). Performance and Technique therefore weigh heaviest in the composite, but Safety is non-negligible.

| Category | Weight |
|---|---|
| Safety | 20% |
| Technique | 45% |
| Performance | 35% |

Within each category, individual-metric weights sum to 100. Suggested defaults:

**SAFETY (20% of composite)**
| Metric | Within-cat. weight |
|---|---|
| Dead-hang Quality (elbow ≥170°) | 25 |
| Eccentric Tempo (no drop) | 20 |
| Shoulder Symmetry (frontal) | 15 |
| Scapular Depression at top | 15 |
| Spinal Alignment (rear) | 10 |
| Setup Quality | 10 |
| Lateral Body Sway | 5 |

**TECHNIQUE (45% of composite)**
| Metric | Within-cat. weight |
|---|---|
| Chin-Over-Bar Detection | 18 |
| Elbow Angle at Top | 12 |
| Body Line / Hollow Body | 12 |
| Active Scapular Initiation | 10 |
| Kipping Detection (strict only) | 10 |
| Body Inclination at Top | 8 |
| Grip Width | 7 |
| Elbow Flare | 6 |
| Head/Neck Position | 6 |
| Hip Flexion Consistency | 6 |
| Knee Position | 5 |

**PERFORMANCE (35% of composite)**
| Metric | Within-cat. weight |
|---|---|
| Concentric Tempo | 20 |
| Pause at Top | 10 |
| Rep-to-Rep Consistency | 20 |
| ROM Completion Rate | 25 |
| Symmetric Ascent | 10 |
| Sticking-Point Severity | 10 |
| Bar-Path Stability | 5 |

### 7.3 Step 3 — Composite Computation

**Default (weighted arithmetic mean):**
`Composite = 0.20·S_safety + 0.45·S_technique + 0.35·S_performance`

where each `S_x = Σ w_i · sub_score_i` (within-category weights, normalized to 1).

**Alternative (geometric mean — punishes single-metric failures harder):**
`Composite_geom = (S_safety^0.20 · S_technique^0.45 · S_performance^0.35)`

Use the geometric mean when even one of the three categories matters absolutely (e.g., a video grader that should never approve a rep with poor safety even if technique and performance are excellent).

### 7.4 Step 4 — Hard-Fail / Safety-Quality Overrides

If any of the following are detected, apply the override regardless of sub-scores:

| Override Trigger | Action |
|---|---|
| Dead-hang failure (elbow <145° at bottom of any rep) | Cap composite at 50; flag "Partial ROM" |
| No chin over bar (mouth ≤ wrist-Y at peak of any rep) | Cap composite at 50; flag "Incomplete ROM" |
| Kipping detected (strict mode): hip-X swing > 0.40 femur-length | Cap composite at 60; flag "Kipping in strict scoring" |
| Excessive shoulder shrug at top (shoulder within 3 cm of earlobe) | −10 composite penalty per occurrence |
| Eccentric tempo <0.5 s (free-fall drop) | Cap composite at 55; flag "Uncontrolled descent — shoulder risk" |
| Asymmetric pull (>15° shoulder tilt at top) | Cap composite at 60; flag "Asymmetric ascent" |
| Excessive body swing (hip-X > 0.80 femur-length, non-kipping style) | Cap composite at 55 |
| Loss of grip / fall from bar | Set composite to 0 for that rep; exclude from set aggregate |
| Hand release from bar during rep | Rep invalid; mark "DNC" (did not complete) |

### 7.5 Step 5 — Per-Set Aggregation

Pull-up form degrades dramatically across a set as fatigue accumulates. Three aggregation modes:

| Mode | Formula | Use Case |
|---|---|---|
| **Mean** | Mean of all valid reps' composites | General training feedback |
| **Worst** | Min composite of any rep in set | Strict assessment / certification |
| **Last-3** | Mean of last 3 reps | Endurance + form-under-fatigue grading |
| **Best-3** | Mean of best 3 reps | Talent ID / max-effort grading |
| **Weighted** | Linear-decay weights (later reps weigh more) | Endurance pull-up tests (USMC PFT context) |

**Recommended default:** report **Mean** as headline + **Worst** and **Last-3** as flags.

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

| Tier | Traffic Light | Sports Tier | Coaching | Medical/PT | Risk | Tier List | Belt | Stars | Olympic | Descriptive | Percentile | Academic | Quality | Weather | Animals | Heat | USMC PFT (2026) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Very Good | 🟢 Green | S | Mastery | Optimal | Negligible | S-Tier | Black | ★★★★★ | Gold | Polished | 90th+ | A+ | Excellent | Sunny | Eagle | Cool | 1st Class (285+/300) |
| Good | 🟢 Green-Yellow | A | Proficient | Functional | Low | A-Tier | Brown | ★★★★ | Silver | Solid | 75–89th | B | Good | Partly Sunny | Falcon | Warm | 1st Class (235–284) |
| Yellow Flag | 🟡 Yellow | B | Developing | Suboptimal | Moderate | B-Tier | Purple | ★★★ | Bronze | Inconsistent | 50–74th | C | Acceptable | Cloudy | Hawk | Hot | 2nd Class (200–234) |
| Bad | 🟠 Orange | C | Faulty | At-Risk | High | C-Tier | Blue | ★★ | Honorable Mention | Compromised | 25–49th | D | Marginal | Stormy | Mockingbird | Scorching | 3rd Class (150–199) |
| Very Bad | 🔴 Red | D/F | Broken | Pathological | Critical | D-Tier | White | ★ | Did Not Place | Failing | <25th | F | Unsafe | Hurricane | Newborn Chick | Inferno | Failure (<150) |

USMC PFT minimum-passing reference (per Task & Purpose reporting on 2026 MARADMIN, citing fitness.marines.mil): male age 17–25 scores 100 points for **23 strict dead-hang pull-ups** and the 40-point minimum at **4 reps**; female maxes at **12 reps**. Combat-arms Marines must reach ≥210/300 total. The PFT explicitly disallows kipping: "Marines may not bring their knees up horizontal to their waist, a technique known as kipping."

---

## 10. Worked Example

**Subject:** Male, 32 yr, 82 kg, intermediate trainee. Strict pronated pull-ups at moderate fatigue (set of 8, this analysis covers rep 6).

### 10.1 Raw Measurements (Rep 6 of 8)

| Metric | Raw Value | Tier | Sub-score |
|---|---|---|---|
| Dead-hang elbow angle | 171° | Good | 78 |
| Body inclination at bottom | 7° | Good | 82 |
| Body inclination at top | 18° | Good | 78 |
| Active scapular initiation | Simultaneous with elbow flexion | Good | 80 |
| Elbow angle at top | 68° (pronated) | Good | 80 |
| Chin-over-bar | Mouth 1.5 cm above bar | Good | 80 |
| Body line SD | 7° | Yellow Flag | 68 |
| Hip flexion consistency | ±13° variation | Yellow Flag | 70 |
| Knee separation | 1.4× hip width | Good | 80 |
| Hip-X kip swing | 0.22 femur-length | Yellow Flag | 70 |
| Ankle-X swing | 0.28 leg-length | Good | 78 |
| Bar-path-vs-body | 3% image width | Good | 80 |
| Head/neck position | 24° forward | Yellow Flag | 66 |
| Grip width | 1.25× biacromial | Very Good | 92 |
| Hand symmetry | 3% | Good | 80 |
| Shoulder symmetry at top | 4% (~5° tilt) | Good | 80 |
| Elbow flare | 42° each side | Good | 78 |
| Lateral body sway | 0.08 femur-length | Good | 80 |
| Head over wrist-midline | 7% | Good | 80 |
| Scapular retraction (rear) | −7% inter-shoulder | Good | 80 |
| Scapular depression at top | Slight elevation | Good | 78 |
| Lat flare | 11% increase | Good | 80 |
| Spinal alignment | 4° | Good | 80 |
| Symmetric ascent | 3 frames @ 60 fps | Good | 80 |
| Setup quality | Settled <1 s | Good | 80 |
| Concentric tempo | 1.6 s | Very Good | 92 |
| Pause at top | 0.2 s | Yellow Flag | 68 |
| Eccentric tempo | 2.1 s | Very Good | 92 |
| Dead-hang reset | 171° | Good | 78 |
| Rep-to-rep consistency (set-level SD) | 0.35 s | Yellow Flag | 70 |
| ROM completion rate (set) | 8/8 = 100% | Very Good | 100 |
| Sticking-point severity | 22% of concentric in stick | Good | 80 |

### 10.2 Category Sub-Scores

**Safety** (weights normalized to 1.0):
0.25·78 + 0.20·92 + 0.15·80 + 0.15·78 + 0.10·80 + 0.10·80 + 0.05·80 = **81.7**

**Technique:**
0.18·80 + 0.12·80 + 0.12·68 + 0.10·80 + 0.10·70 + 0.08·78 + 0.07·92 + 0.06·78 + 0.06·66 + 0.06·70 + 0.05·80 = **76.8**

**Performance:**
0.20·92 + 0.10·68 + 0.20·70 + 0.25·100 + 0.10·80 + 0.10·80 + 0.05·80 = **82.7**

### 10.3 Composite

`Composite = 0.20 · 81.7 + 0.45 · 76.8 + 0.35 · 82.7 = 16.34 + 34.56 + 28.95 = `**79.85**

### 10.4 Override Check

- Dead-hang: 171° ≥ 145° → no override
- Chin-over-bar: ✓
- Kipping: 0.22 < 0.40 → no override
- Shrug: not within 3 cm of ear → no override
- Eccentric tempo: 2.1 s > 0.5 s → no override
- Asymmetry: 5° < 15° → no override
- Grip released: no
- **No overrides triggered.**

### 10.5 Final Grade & Feedback

**Composite = 79.85 → B (Good)**

**Two lowest sub-scores (to surface as feedback):**
1. **Head/neck position (66, Yellow Flag)** — "Chin-poking detected at top of rep. Cue: keep gaze forward, hold an imaginary orange between chin and chest. Aim to pull the chest up, not the chin over."
2. **Body line / hollow body (68, Yellow Flag)** — "Mild loss of hollow body position mid-rep. Cue: brace abs as if for a dead bug; 'wrinkle the front of your shirt' (Callaway's cue)."

---

## 11. Practical Notes & Caveats

### 11.1 Anthropometry Effects

- **Longer arms = longer ROM.** A 195-cm athlete with +5 ape-index travels ~70 cm body-vertically per rep; a 165-cm athlete with average ape-index travels ~50 cm. Reps should not be directly compared without normalizing by ROM-distance.
- **Shorter arms = mechanical advantage at the shoulder.** The lat moment arm and the load distance both shorten, but the shorter load distance dominates → shorter-armed athletes typically rep higher numbers.
- **Heavier athlete = harder mechanical load.** A 100-kg athlete moves 100 kg per rep; a 65-kg athlete moves 65 kg.

### 11.2 Bodyweight & Difficulty Calibration

Per Strength Level (4,814,965 logged lifts as of May 2026), the pull-up rep table for an 80 kg male reads: **Beginner <1, Novice 5–6, Intermediate 13–14, Advanced 22–23, Elite 33–34.** The site's "entire community" overall averages are Novice 5, Intermediate 14, Advanced 25, Elite 37. USMC PFT (2026): male age 17–25 needs 23 reps for 100 points (max), 4 reps for 40 points (min); female maxes at 12 reps. These rep benchmarks are useful prior context for the *Performance* category but do **not** replace form scoring.

Note that ExRx.net is widely cited as the source of rep-tier tables, but ExRx itself does not publish a specific reps-by-bodyweight pull-up table — the rep-tier framework typically attributed to "ExRx" is in fact the Strength Level table above. Cite accordingly.

### 11.3 Strict vs. Kipping Classification

Apply the classification BEFORE scoring. Use hip-X amplitude:
- **<0.20 femur-length** → strict
- **0.20–0.40** → "loose strict" (apply strict rubric with hip swing penalty)
- **>0.40** → kipping (switch to kipping rubric — do not penalize swing; instead score kip coordination, hollow-arch transitions, chin-over-bar)
- **Butterfly** is distinguished by continuous-cycle motion (no pause at top, athlete drops in front of bar) — detect via no-reverse in hip-X velocity at the top of the rep.

### 11.4 Grip Variation Handling

Each grip changes optimal elbow-angle-at-top and elbow-ROM thresholds. The Sagittal Section 3.5 table provides per-grip ranges. Detect grip from frontal view: pronated = thumbs face each other; supinated = thumbs face outward; neutral = visible parallel handles.

### 11.5 Continuous Tracking vs. Single Frame

All Section 3–6 metrics that name "at top" or "at bottom" require event detection (rep-phase segmentation; see 12.3). Single-frame analysis is unreliable for pull-ups because dead-hang and lockout are brief frames within a continuous trajectory.

### 11.6 Calibration

Calibrate vertical pixels-per-cm using the bar (if known length) or the athlete's wrist-to-wrist distance at dead-hang (if their hand-width is known). This is critical for normalizing chin-over-bar offset distance and any centimetre-based threshold.

### 11.7 Always Surface the Reason

The system must surface the two lowest sub-scores as plain-language feedback (see Worked Example 10.5). Never report a grade without the *why*.

### 11.8 Style-Specific Scoring

- **Strict / Tactical** — apply Sections 3–6 thresholds directly with the strict-mode kipping penalty.
- **CrossFit kipping** — disable kipping detection penalty (Section 3.11), disable knee scissor penalty (3.10), disable hip flexion consistency (3.9), and add a new metric: hollow-arch transition cleanliness.
- **Butterfly** — disable pause-at-top (no pause expected), add cycle continuity (front-of-bar drop trajectory).
- **Sternum chin-up** — invert Section 3.3 (45°–70° posterior lean is "Very Good") and require sternum-to-bar contact via Section 3.7.

### 11.9 Minimum-Viable Metric Priority List

For a stripped-down implementation (e.g., mobile, single-camera, 60 fps), use only the top 8 metrics:

1. Elbow angle at bottom (dead-hang)
2. Chin-over-bar detection
3. Elbow angle at top
4. Kipping detection (hip-X amplitude)
5. Eccentric tempo
6. Body line / hollow body
7. Shoulder symmetry (frontal)
8. Concentric tempo

These eight cover all five hard-fail overrides.

### 11.10 Frame-Rate Tradeoffs

- 30 fps: ROM detection OK; tempo metrics ±33 ms; eccentric drop detection unreliable
- 60 fps: All metrics in this document work
- 120 fps: Sticking-point precision, kipping-cycle analysis precise
- 240 fps: Required for full force-velocity profiling (research only)

### 11.11 Camera Occlusion at Lockout

When the head goes behind the bar at the top, MediaPipe face landmarks (0, 9, 10) lose visibility. Fallback chain:
1. Use mouth-centre (avg of landmarks 9 & 10) if `visibility > 0.5`
2. Else nose (landmark 0)
3. Else, use shoulder-Y + a calibrated `chin_to_shoulder` offset measured at the dead-hang frame (where the chin is fully visible)

### 11.12 Counting Reps Automatically

A rep is counted when mouth-Y (or proxy) crosses **above** the wrist-Y line, then crosses **back below**, AND the elbow angle reaches ≥170° at the bottom of the cycle. Half-reps (top reached but no dead-hang) are tracked separately as "partial reps."

### 11.13 Validation Note

A practical limitation worth surfacing: implementations published to date (e.g., Mishra et al. 2024 IJRASET "AI Human Fitness Tracker using Computer Vision with MediaPipe") report pull-up tracking accuracy as lower than walking and squats — the authors note "Pull-ups had lower accuracy due to vertical pose challenges." Treat any single-camera pose-only pull-up grader as a coaching aid, not an objective measurement system, until paired with controlled validation.

---

## 12. MediaPipe Pose Implementation Guide

### 12.1 MediaPipe Pose Landmark Reference

| Index | Landmark | Pull-Up Relevance |
|---|---|---|
| 0 | Nose | **Chin-over-bar proxy** (head position) |
| 1 | Left eye (inner) | — |
| 2 | Left eye | — |
| 3 | Left eye (outer) | — |
| 4 | Right eye (inner) | — |
| 5 | Right eye | — |
| 6 | Right eye (outer) | — |
| 7 | Left ear | Shrug detection (distance to shoulder) |
| 8 | Right ear | Shrug detection |
| 9 | Mouth (left) | **Chin-over-bar** (avg with 10) |
| 10 | Mouth (right) | **Chin-over-bar** (avg with 9) |
| 11 | Left shoulder | **Critical — shoulder elevation/depression, symmetry** |
| 12 | Right shoulder | **Critical** |
| 13 | Left elbow | **Critical — elbow angle** |
| 14 | Right elbow | **Critical** |
| 15 | Left wrist | **Critical — bar position proxy** |
| 16 | Right wrist | **Critical** |
| 17 | Left pinky | Hand orientation (chin-up vs pull-up) |
| 18 | Right pinky | |
| 19 | Left index | Hand orientation |
| 20 | Right index | |
| 21 | Left thumb | **Grip orientation detection** (pronated/supinated) |
| 22 | Right thumb | **Grip orientation detection** |
| 23 | Left hip | **Critical — body line, kip detection** |
| 24 | Right hip | **Critical** |
| 25 | Left knee | Knee position, scissor detection |
| 26 | Right knee | |
| 27 | Left ankle | **Critical — leg swing, body verticality** |
| 28 | Right ankle | **Critical** |
| 29 | Left heel | — |
| 30 | Right heel | — |
| 31 | Left foot index | — |
| 32 | Right foot index | — |

### 12.2 Derived Reference Points

```
shoulder_centre = ((L11 + L12) / 2)
hip_centre      = ((L23 + L24) / 2)
knee_centre     = ((L25 + L26) / 2)
ankle_centre    = ((L27 + L28) / 2)
wrist_centre    = ((L15 + L16) / 2)          # bar position proxy
mouth_centre    = ((L9  + L10) / 2)          # chin-over-bar reference
chin_proxy      = mouth_centre if visible else nose (L0)

# Body line vector (should be near-vertical)
body_vector     = shoulder_centre − ankle_centre

# Torso vector (subset)
torso_vector    = shoulder_centre − hip_centre

# Bar reference (assumed horizontal between wrists)
bar_y           = wrist_centre.y
bar_line        = horizontal line through (L15.x, bar_y) and (L16.x, bar_y)
```

### 12.3 General Computational Principles

**Visibility filtering.** Reject any landmark with `visibility < 0.5`. For mouth_centre, require both 9 AND 10 above threshold; fall back to nose if either fails; fall back to shoulder-Y + offset if all face landmarks fail.

**Side selection.** In sagittal view, both sides are present but one occludes the other. Choose the side closer to the camera (higher visibility scores on the upper-body landmarks). Mirror left/right computations as needed.

**Coordinate system.** MediaPipe normalized image coords: `x ∈ [0,1]` left-to-right, `y ∈ [0,1]` top-to-bottom. **Smaller Y = higher in image.** This must be flipped for any "is X above Y" comparison; we want the body and chin to have *smaller* Y values when "up."

**Phase detection (rep-state machine):**

| Phase | Detection Rule |
|---|---|
| `DEAD_HANG` | elbow angles both ≥170°, vertical velocity ≈ 0, wrist-Y stable |
| `CONCENTRIC` | body vertical velocity < 0 (rising in image), elbow flexing |
| `TOP` | mouth_centre.y < wrist_centre.y, vertical velocity ≈ 0 |
| `ECCENTRIC` | body vertical velocity > 0, elbow extending |
| `RETURN` | back to DEAD_HANG criteria |

Use a Schmitt trigger (hysteresis) on the elbow-angle and chin-Y signals to avoid noise-induced phase flips.

**Rep boundary.** Detect a complete rep on the `TOP → ECCENTRIC → DEAD_HANG → CONCENTRIC` cycle. Hand-release events (sudden visibility drop in wrist landmarks) abort the rep.

**2D vs 3D.** Use 2D normalized coords for all sagittal/frontal metrics. MediaPipe's 3D `z` is referenced to mid-hip and is unreliable for airborne subjects, particularly for kip front/back swing. Avoid `z`.

### 12.4 Foundational Math Operations

**Three-point joint angle** (e.g., elbow at landmark 13 between 11 and 15):
```
v1 = L11 − L13       (shoulder − elbow)
v2 = L15 − L13       (wrist − elbow)
cos_theta = (v1 · v2) / (|v1| · |v2|)
angle = arccos(clip(cos_theta, −1, 1))   # in radians, convert to deg
```

**Angle of a vector from vertical** (for body inclination):
```
v = shoulder_centre − ankle_centre
angle_from_vertical = arctan2(v.x, −v.y)    # note flipped y
```

**Chin-over-bar:**
```
chin_y    = mouth_centre.y if mouth_visible else nose.y
bar_y     = wrist_centre.y
above_bar = chin_y < bar_y       # smaller y means higher in image
clearance = (bar_y − chin_y) / torso_length    # normalize
```

**Body verticality** (used for "should be vertical" checks):
```
deviation_deg = |angle_of(shoulder − hip, vertical)|
```

**Kip detection (frequency-domain):**
```
hip_x_signal = hip_centre.x over the last N frames
detrend, then compute amplitude of dominant frequency
if amplitude > 0.40 · femur_length AND frequency in 0.5–2.5 Hz:
    kip detected
```

**Grip orientation** (frontal view): compute the angle of (thumb − index) for each hand. If both thumbs point toward each other → pronated. If both point outward → supinated. If thumbs lie roughly in line with wrists pointing toward each other and palms face each other → neutral.

### 12.5 Per-Metric Computation Guide

| Metric | Landmarks | Vectors / Formula | Track Over Time | Caveats |
|---|---|---|---|---|
| Dead-hang elbow angle | 11/13/15, 12/14/16 | Three-point angle at elbow at `DEAD_HANG` frame | Per-rep min, per-rep mean | Sample at the local minimum of body vertical velocity (most-extended position) |
| Body inclination at bottom | 23/24, 27/28, 11/12 | angle_from_vertical(shoulder_centre − ankle_centre) | At dead-hang frame | If feet not visible, use knee_centre as fallback (less accurate) |
| Body inclination at top | same | same | At top frame | |
| Shoulder elevation at bottom | 11/12, 15/16, 7/8 | (wrist_centre.y − shoulder_centre.y) / torso_length; (ear_y − shoulder_y) | Across rep | Active vs passive hang ambiguous without ear visibility |
| Active scapular initiation | 11/12, 13/14 | Δ(shoulder_y) at first 100 ms of concentric vs Δ(elbow_angle) | At concentric start | Requires high frame rate (≥60 fps) |
| Elbow angle at top | 11/13/15, 12/14/16 | three-point | Per-rep min angle (peak flexion) | |
| Chin-over-bar | 0, 9, 10, 15, 16 | chin_y < wrist_centre.y | Across rep; record (bar_y − chin_y) max | Face landmarks may occlude — see 11.11 |
| Sternum-to-bar | 11/12, 15/16 | shoulder_centre.y at top vs wrist_centre.y, offset by sternum_distance | Per rep | Sternum position approximated as ~0.10·torso_length below shoulder_centre |
| Body line / hollow body | 11/12, 23/24, 25/26 | Angle between (shoulder_centre − hip_centre) and (hip_centre − knee_centre); SD across rep | Across rep | Knees-bent style holds a fixed non-180° angle — score consistency, not magnitude |
| Hip flexion | 11/12, 23/24, 25/26 | three-point angle at hip | Across rep | |
| Knee position | 25, 26 | |L25.x − L26.x| / hip_width; also (L25.y − L26.y) for scissor | Across rep | |
| Kipping detection | 23, 24 | Peak-to-peak amplitude of hip_centre.x / femur_length; FFT for frequency | Across rep | Use Butterworth low-pass at 5 Hz before FFT |
| Leg swing | 27, 28 | Peak-to-peak amplitude of ankle_centre.x / leg_length | Across rep | |
| Bar-path-vs-body | 15, 16 | Peak-to-peak wrist_centre.x | Across rep | Camera shake confound — subtract reference static frame |
| Head/neck position | 0, 11/12, 23/24 | Angle between (shoulder − nose) and (hip − shoulder) | At top frame | |
| Grip width | 15, 16, 11, 12 | |L15 − L16| / |L11 − L12| | At dead hang | Frontal view required |
| Hand symmetry | 15, 16, midline | |L15.x − mid_x| − |L16.x − mid_x| where mid_x = nose.x | At dead hang | |
| Shoulder symmetry | 11, 12 | (L11.y − L12.y) / torso_length | At top frame | |
| Elbow flare | 11/13, 12/14 | Angle of (shoulder − elbow) from vertical, in frontal plane | At top frame | Sagittal view gives a poor approximation |
| Lateral body sway | 23, 24 | Peak-to-peak hip_centre.x amplitude (frontal) | Across rep | |
| Vertical head alignment | 0, 15, 16 | (nose.x − wrist_centre.x) / |L15 − L16| | At top frame | |
| Scapular retraction (rear) | 11, 12 | (|L11 − L12|_top − |L11 − L12|_bottom) / |L11 − L12|_bottom | At top vs bottom | Posterior view required |
| Scapular depression (rear) | 11/12, 7/8 | (L7.y − L11.y) / neck_length; same for right | At top | |
| Lat flare | 11/12, 23/24, segmentation mask | torso_width at mid-back (estimated from pose contour) | At top vs bottom | Better with MediaPipe segmentation mask than pose-only |
| Spinal alignment | 11/12, 23/24 | angle of (shoulder_centre − hip_centre) from vertical | Across rep | Posterior view |
| Symmetric ascent | 11, 12 | Cross-correlation of L11.y(t) and L12.y(t) during concentric | Per rep | |
| Setup quality | all body landmarks | Variance of all landmark positions in first 1 s before pull | Pre-rep window | |
| Concentric tempo | all body | Time(TOP) − Time(CONCENTRIC_START) | Per rep | |
| Pause at top | mouth, wrist | Duration(chin_y < bar_y AND vertical_velocity ≈ 0) | Per rep | |
| Eccentric tempo | all body | Time(DEAD_HANG_END) − Time(TOP) | Per rep | |
| Dead-hang reset | elbow angles | min elbow angle in DEAD_HANG phase between reps | Per rep | |
| Rep consistency | all metrics | SD across reps within set | Per set | |
| ROM completion | elbow + chin | Fraction of reps satisfying both `dead_hang ≥170°` and `chin_over_bar` | Per set | |

### 12.6 Sample Pipeline (Conceptual Flow)

```
1. Capture video at 60 fps minimum; verify CFR.
2. Pre-process:
   - Detect bar location (first-frame manual annotation OR assume = wrist_centre)
   - Calibrate torso_length from initial dead-hang frame
   - Calibrate femur_length and leg_length from initial frame
3. Run MediaPipe Pose Landmarker on each frame.
4. For each frame: filter low-visibility landmarks; derive centres and vectors.
5. State machine for phase detection:
       DEAD_HANG → CONCENTRIC → TOP → ECCENTRIC → DEAD_HANG (= 1 rep)
6. Per rep:
   a. Sample all "at bottom" metrics at the DEAD_HANG entry frame.
   b. Sample all "at top" metrics at the TOP frame.
   c. Compute all "across rep" metrics from the full trajectory.
7. Per rep: classify style (strict / loose-strict / kipping / butterfly).
8. Per rep: compute sub-scores using thresholds from Sections 3–6.
9. Per rep: compute category sub-scores and composite using weights in Section 7.2.
10. Per rep: evaluate hard-fail overrides (Section 7.4).
11. Per set: aggregate (mean, worst, last-3, ROM completion rate, consistency).
12. Output:
    - Composite + grade
    - Top 2 lowest-scoring metrics with plain-language feedback
    - Override flags
    - Per-rep timeline visualisation
```

### 12.7 Known Limitations of MediaPipe for Pull-Up Assessment

| Limitation | Mitigation |
|---|---|
| **Bar is not a landmark.** | Use wrist_centre as bar proxy. Assumes hands don't slide on the bar (usually true). |
| **No scapular landmarks.** Scapular retraction/depression/upward rotation cannot be measured directly. | Use shoulder (acromial) landmark movement as a proxy. Acknowledge this limits clinical-grade scapular assessment. For true scapular kinematics use Prinold & Bull (2016) marker-based mocap or depth cameras. |
| **Head occluded by bar at lockout.** | Fallback chain: mouth_centre → nose → (shoulder + calibrated chin-shoulder offset). |
| **Body airborne — no ground reference.** | Use wrist line (bar) as the vertical anchor, not the floor. Normalize displacements by torso_length and femur_length. |
| **3D `z` axis unreliable.** | Use only 2D coordinates. Use multiple cameras (sagittal + frontal) for full 3D recovery if needed. |
| **Lat activation invisible.** | Cannot be measured. Only kinematic proxies (lat flare width on rear view, body line maintenance) are available. State this in any clinical output. |
| **Fast eccentrics need higher fps.** | Require ≥120 fps for eccentrics under 1 s; otherwise drop detection is unreliable. |
| **Camera framing critical.** | A camera that crops the feet at dead-hang or the head at lockout corrupts body-line, kip, and chin-over-bar metrics. Provide a setup wizard with framing checks. |
| **Hand visibility on bar degrades.** | At wide grips and high-angle camera positions, the wrist landmark drifts. Manually annotate the bar line in pre-processing for high-stakes assessment. |
| **Overhead arm posture is under-represented in BlazePose training data.** | Compared to standing/seated postures. Expect elevated landmark jitter when arms are overhead — use temporal smoothing (Kalman / one-Euro filter) on shoulder and elbow landmarks. |
| **Pull-ups specifically suffer "vertical pose challenges."** | Mishra et al. (2024 IJRASET) explicitly note "Pull-ups had lower accuracy due to vertical pose challenges." Validate against ground truth before deploying. |

---

## 13. Appendix — Metric Summary Table

| # | Metric | Primary View | Type | Default Weight (% of composite) | Pronated | Chin-up | Neutral | Wide |
|---|---|---|---|---|---|---|---|---|
| 1 | Dead-hang elbow angle | Sagittal | Two-sided | 5.0 (Safety 0.25) | ✓ | ✓ | ✓ | ✓ |
| 2 | Body inclination at bottom | Sagittal | Categorical-ranged | 1.0 | ✓ | ✓ | ✓ | ✓ |
| 3 | Body inclination at top | Sagittal | Categorical-ranged | 3.6 (Tech 0.08) | ✓ | ✓ | ✓ | ✓ |
| 4 | Active scapular initiation | Sagittal | Two-sided | 4.5 (Tech 0.10) | ✓ | ✓ | ✓ | ✓ |
| 5 | Elbow angle at top | Sagittal | Two-sided | 5.4 (Tech 0.12) | ✓ | ✓ | ✓ | ✓ |
| 6 | Chin-over-bar | Sagittal | One-sided | 8.1 (Tech 0.18) | ✓ | ✓ | ✓ | ✓ |
| 7 | Sternum-to-bar (variant) | Sagittal | One-sided | optional | ◐ | ◐ | ◐ | ◐ |
| 8 | Body line / hollow body | Sagittal | One-sided | 5.4 (Tech 0.12) | ✓ | ✓ | ✓ | ✓ |
| 9 | Hip flexion | Sagittal | One-sided | 2.7 (Tech 0.06) | ✓ | ✓ | ✓ | ✓ |
| 10 | Knee position / scissor | Sagittal | Two-sided | 2.25 (Tech 0.05) | ✓ | ✓ | ✓ | ✓ |
| 11 | Kipping detection | Sagittal | One-sided | 4.5 (Tech 0.10) | ✓ | ✓ | ✓ | ✓ |
| 12 | Leg swing | Sagittal | One-sided | embedded in kipping | ✓ | ✓ | ✓ | ✓ |
| 13 | Bar-path-vs-body | Sagittal | One-sided | 1.75 (Perf 0.05) | ✓ | ✓ | ✓ | ✓ |
| 14 | Head/neck position | Sagittal | One-sided | 2.7 (Tech 0.06) | ✓ | ✓ | ✓ | ✓ |
| 15 | Grip width | Frontal | One-sided | 3.15 (Tech 0.07) | ✓ | ✓ | ✓ | ✓ |
| 16 | Hand symmetry | Frontal | One-sided | flagged at override | ✓ | ✓ | ✓ | ✓ |
| 17 | Shoulder symmetry at top | Frontal | One-sided | 3.0 (Safety 0.15) | ✓ | ✓ | ✓ | ✓ |
| 18 | Elbow flare | Frontal | Two-sided | 2.7 (Tech 0.06) | ✓ | ✓ | ✓ | ✓ |
| 19 | Lateral body sway | Frontal | One-sided | 1.0 (Safety 0.05) | ✓ | ✓ | ✓ | ✓ |
| 20 | Head-over-midline | Frontal | One-sided | embedded in symmetry | ✓ | ✓ | ✓ | ✓ |
| 21 | Scapular retraction (rear) | Posterior | One-sided | optional (sub of #4) | ✓ | ✓ | ✓ | ✓ |
| 22 | Scapular depression (rear) | Posterior | Two-sided | 3.0 (Safety 0.15) | ✓ | ✓ | ✓ | ✓ |
| 23 | Lat flare | Posterior | One-sided | optional | ✓ | ✓ | ✓ | ◐ |
| 24 | Spinal alignment | Posterior | One-sided | 2.0 (Safety 0.10) | ✓ | ✓ | ✓ | ✓ |
| 25 | Symmetric ascent | Sagittal/Frontal | Two-sided | 3.5 (Perf 0.10) | ✓ | ✓ | ✓ | ✓ |
| 26 | Setup quality | Sagittal | One-sided | 2.0 (Safety 0.10) | ✓ | ✓ | ✓ | ✓ |
| 27 | Concentric tempo | Sagittal | One-sided | 7.0 (Perf 0.20) | ✓ | ✓ | ✓ | ✓ |
| 28 | Pause at top | Sagittal | One-sided | 3.5 (Perf 0.10) | ✓ | ✓ | ✓ | ✓ |
| 29 | Eccentric tempo | Sagittal | One-sided | 4.0 (Safety 0.20) | ✓ | ✓ | ✓ | ✓ |
| 30 | Dead-hang reset | Sagittal | Two-sided | embedded in #1 | ✓ | ✓ | ✓ | ✓ |
| 31 | Rep-to-rep consistency | All views | Categorical | 7.0 (Perf 0.20) | ✓ | ✓ | ✓ | ✓ |
| 32 | ROM completion rate | Sagittal | Set-level | 8.75 (Perf 0.25) | ✓ | ✓ | ✓ | ✓ |
| 33 | Sticking-point severity | Sagittal | One-sided | 3.5 (Perf 0.10) | ✓ | ✓ | ✓ | ✓ |

Legend: ✓ = applies; ◐ = with caveats; "embedded" = not weighted separately but contributes to another metric.

---

*End of document.*