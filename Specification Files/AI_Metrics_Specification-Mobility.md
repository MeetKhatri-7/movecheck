# Athlete Mobility Assessment — AI Technical Specification

Complete measurement protocol for computer vision-based mobility scoring. Use MediaPipe Pose or equivalent 33-landmark skeletal tracking. All angles in degrees unless specified.



### Rules for the user (This info is to be displayed to user on the first page) : 
- Film in a well-lit space with a plain background if possible
- Use a phone propped up or held still — NOT hand-held shaky footage
- Wear fitted clothing so joints are clearly visible (avoid baggy shorts/tops)
- Film the EXACT camera angle listed for each exercise — this is critical for accurate analysis
- Do 3 slow, controlled reps (or the specified reps) per exercise
- Send all videos to your coach via the agreed method (WhatsApp / Google Drive / email)



---

## EXERCISE 1 — Knee-to-Wall Test (Ankle Dorsiflexion)

**Camera:** Side view, 90° to athlete, hip height, 1.5–2 m distance
**Landmarks tracked:** ANKLE (27/28), KNEE (25/26), HIP (23/24), foot index (31/32), heel (29/30)

### Mediapipe Instructions Metrics:

**Primary metric — Knee forward travel:**
- Measure horizontal distance from knee landmark to foot toe landmark at peak lunge position
- Unit: cm (calibrated against known reference in frame)

**Secondary metric — Heel lift detection:**
- Monitor vertical Y-coordinate of heel landmark (29/30) throughout movement
- Heel lift = Y-displacement > 1.5 cm from baseline floor contact

**Tertiary metric — Knee tracking (valgus):**
- Calculate vector from HIP → KNEE and HIP → ANKLE
- Flag if knee deviates medially from foot axis by > 10°

**Scoring thresholds:**
- GOOD: Knee clears toes by ≥ 10 cm (4+ finger-widths), heel stays flat (< 1.5 cm lift), knee tracks straight over 2nd toe
- NEEDS IMPROVEMENT: Knee clears 5–9 cm, heel may lift slightly at end range (1.5–3 cm)
- RESTRICTED: Knee clears < 5 cm OR heel lifts > 3 cm OR knee caves inward > 10°

**Bilateral symmetry:** Flag if left/right difference > 2 cm in knee travel

**More Details:** You have to make the different sections for right and left Video, so that the user can upload both right and left side videos differnetly, and have to analyse both videos differently, the score should be for right and left side separately. 

**Reps Details:** 3 reps each side, left and right side will be different video, so user will upload two videos for this exercise, one for left side and one for right side, and we have to analyse both videos differently, and the score should be for right and left side separately.


**Important:** I want to analyse all the three reps of the user, and should give a combined score for all the three reps, also i want to give a separate score for each rep, so that the user can see the performance in each rep. And the most important, I want the anlge of the user's knee when it is touching the wall or the when the user's knee is fully extended. So the process will, the mediapipe will the take the angles of the user's knee at all the frames, and the highest angles from the three reps will be the final angle of the user's knee. Also analyse the user's knee lift for all the three reps, and the highest knee lift from the three reps will be the final knee lift of the user.



---

## EXERCISE 2 — Seated Hip Rotation Test (Hip IR/ER)

**Camera:** Front view, eye-level with knees
**Landmarks tracked:** HIP (23/24), KNEE (25/26), ANKLE (27/28), SHOULDER (11/12) for trunk monitoring

**Rep Details:** 3 reps each side, left and right side will be different video, so user will upload two videos for this exercise, one for left side and one for right side, and we have to analyse both videos differently, and the score should be for right and left side separately.

### Mediapipe Instructions Metrics:

**Primary metric — Hip rotation angle:**
- Calculate angle of KNEE → ANKLE vector relative to vertical (gravity)
- ER (external rotation) = foot swings laterally (outward from centerline)
- IR (internal rotation) = foot swings medially (inward past centerline)
- Measure peak angle reached in both directions per leg

**Compensation metric — Trunk lean:**
- Monitor angle between SHOULDER midpoint → HIP midpoint vector and vertical
- Flag if trunk deviates > 5° from upright during test

**Scoring thresholds (per side):**
- GOOD: IR ≥ 40° AND ER ≥ 40°, trunk stays within 5° of vertical, L/R difference < 10°
- NEEDS IMPROVEMENT: IR or ER in range 30–39°, L/R difference 10–15°, minor trunk lean (5–10°)
- RESTRICTED: IR or ER < 30° OR L/R difference > 15° OR trunk lean > 10°

**Bilateral symmetry threshold:** Flag asymmetry if |Left IR − Right IR| > 10° OR |Left ER − Right ER| > 10°



**Important:** make different sections for left and right hips differently and analyse both differntly and then show the score of left and right hip rotation. 

**Mediapipe Instructions:** Analyse all the three reps, for each side for example right side, analyse each rep like first take the angle at which the leg is at rest, and then find the angle at which the leg is the farthest, take angle from rest at each fram, and the final result should contain the highest angle from all the fames for one rep, then after getting the angles of all the three reps, take the highest angle among the three reps, and show the result according to those.

---

## EXERCISE 3 — Thoracic Foam Roller Extension (T-Spine Extension)

**Camera:** Side view, 90° to athlete, torso height
**Landmarks tracked:** SHOULDER (11/12), HIP (23/24), EAR (7/8), KNEE (25/26)

**Rep Details:** Hold 30 sec, 1 sets, User will upload the videos of both the sets differenly.

**Hold duration:** Measure time in valid position — target 30 seconds


### Mediapipe Instructions Metrics:

**Primary metric — Thoracic curve depth:**
- Measure vertical depth of curve at mid-back over roller apex
- Calculate shoulder-to-hip line angle relative to horizontal
- GOOD shows negative angle (shoulders drop below hip line) of −15° to −25°

**Secondary metric — Head drop:**
- Measure EAR landmark Y-coordinate relative to SHOULDER Y-coordinate at end position
- Head drops back = EAR Y position at or below SHOULDER Y position

**Compensation metric — Lumbar hyperextension:**
- Monitor HIP vertical displacement during exercise
- Flag if hips rise significantly indicating lumbar arch compensation

**Scoring thresholds:**
- GOOD: Visible thoracic curve (shoulders −15° or more below hip line), ear drops to or below shoulder level, hips stay stable
- NEEDS IMPROVEMENT: Partial curve (−5° to −15°), head drops partway, minor hip lift
- RESTRICTED: Flat spine (0° to −5°) OR head cannot drop below shoulder level OR obvious lumbar hyperextension compensation



**Important:** Analyse the 1 sets fully.

---

## EXERCISE 4 — Quadruped Rotation / Thread the Needle (T-Spine Rotation)

**Camera:** Side view, 90° to athlete, hip height
**Landmarks tracked:** SHOULDER (11/12), HIP (23/24), ELBOW (13/14), WRIST (15/16)

**Rep Details:** 3 reps each side, user will upload the video of both the sides differently, and analyse them differently, and show the score of both the sets separately. Show the final score from both sets as which is the best score from both the sets.

### Mediapipe Instructions Metrics:

**Primary metric — Elbow rotation angle:**
- Establish spine baseline: line from HIP midpoint to SHOULDER midpoint
- Measure elbow tip (of rotating arm) position relative to this baseline
- Calculate angle from shoulder joint of rotating side to elbow, measured against spine baseline vertical plane

**Secondary metric — Hip lock detection:**
- Monitor bilateral HIP Y-coordinates and rotation
- Flag if hip vertical position changes > 2 cm OR hip rotation relative to baseline > 5°

**Scoring thresholds:**
- GOOD: Elbow rotates clearly above spine baseline (≥ 45° from starting horizontal), hips stay locked (< 2 cm displacement, < 5° rotation), L/R symmetry within 10°
- NEEDS IMPROVEMENT: Elbow reaches spine level but not clearly above (30–44°), minor hip shift (2–4 cm)
- RESTRICTED: Elbow cannot reach spine level (< 30°) OR hips rock/rotate significantly (> 4 cm or > 10°) OR L/R difference > 15°



**Important:** Find all the metrics for all the 3 reps.

**Mediapipe Instructions:** The baseline should be calculated from the mid point of the shoulder to the mid point of the hip, that should be throughout the rep for each side. For example right you are analysing the video of right side - so the video will contain 3 reps, firstly for each side - find the baseline as shown above, for each rep : 
 - for each fram - find the distance between the elbow tip and baseline, and the maximum distance should be considered as the angle of the rep, take the maximum distance from all the frames for one rep. Do this for all the 3 reps. So you will get three maximum distances from each fram
 - from the  

---

## EXERCISE 5 — 90/90 Shoulder Rotation Test (Shoulder IR/ER) 

**Camera:** Axial view — positioned at foot of plinth looking down humeral long axis
**Landmarks tracked:** SHOULDER (11/12), ELBOW (13/14), WRIST (15/16), HIP (23/24) for trunk monitoring

**Rep Details:** 3 reps each side, user will upload the video of both the sides differently, and analyse them differently, and show the score of both the sets separately. Show the final score from both sets as which is the best score from both the sets.

### Mediapipe Instructions Metrics:

**Setup validation (AI must verify before scoring):**
- Humerus abducted to 90° ± 5° (SHOULDER to ELBOW vector horizontal)
- Elbow flexed to 90° ± 5° (angle at ELBOW between humerus and forearm)
- If setup outside tolerance, prompt athlete to adjust — do not score

**Primary metric — ER and IR angles:**
- Measure signed angle between ELBOW → WRIST vector and gravity vertical
- External Rotation (ER): forearm rotates upward/backward, wrist moves toward head — positive angle above horizontal
- Internal Rotation (IR): forearm rotates downward/forward, wrist moves toward feet — negative angle below horizontal
- Record peak angle in each direction

**Derived metrics:**
- Total Rotational Motion (TRM) = ER + IR (same arm)
- GIRD (Glenohumeral Internal Rotation Deficit) = Non-dominant IR − Dominant IR
- TRM Deficit = Non-dominant TRM − Dominant TRM
- ER Gain = Dominant ER − Non-dominant ER

**Compensation metrics:**
- Scapular anterior tilt: SHOULDER landmark vertical displacement > 2 cm during IR = invalid end-range
- Humeral drift: SHOULDER-ELBOW angle deviation from 90° abduction > 5° = invalid frame
- Elbow angle drift: ELBOW angle deviation from 90° > 5° = invalid frame
- Trunk roll: bilateral SHOULDER-to-HIP line tilt > 5° = compensation detected
- Lumbar hyperextension during ER (for athletes testing standing alternatives)

**Scoring thresholds — General adult population (AAOS / Norkin & White clinical standards):**
- GOOD: ER 80–95°, IR 60–75°, TRM 150–175°, L/R difference < 5°
- NEEDS IMPROVEMENT: ER 65–79° OR IR 45–59° OR L/R difference 5–10°
- RESTRICTED: ER < 65° OR IR < 45° OR L/R difference > 10°

**Scoring thresholds — Overhead athletes (throwing/swimming/tennis):**
- GOOD (NORMAL ADAPTATION): Dominant ER 110–140°, dominant IR 45–65°, dominant TRM within 5° of non-dominant TRM
- NEEDS IMPROVEMENT (MONITOR): GIRD 15–20° AND TRM deficit ≤ 5° (likely anatomic adaptation)
- RESTRICTED (PATHOLOGIC GIRD): GIRD > 18–20° WITH TRM deficit > 5° — elevated injury risk
- RESTRICTED (ER INSUFFICIENCY): ER gain < 5° on dominant side — strongest injury predictor (Wilk 2015: 2.2× injury risk, 4.0× surgery risk)

**Bilateral comparison (critical for this test):**
- Always compute and report: Dominant vs Non-dominant ER, IR, TRM
- GIRD threshold: > 18° indicates posterior capsule tightness
- TRM deficit threshold: > 5° indicates pathologic (not adaptive) restriction
- ER gain < 5° indicates ER insufficiency

**Hold requirement:** Athlete must maintain end-range position for ≥ 1 second to register a valid measurement (prevents momentum artifacts)

**Mediapipe and Important Instructions:**

**Important:** Find all the metrics for all the 3 reps.


---

## EXERCISE 6 — Single-Leg Glute Bridge (Glute Activation)

**Camera:** Side view, 90° to athlete, waist-to-knee frame of the performing side
**Landmarks tracked:** SHOULDER (11/12), HIP (23/24), KNEE (25/26), ANKLE (27/28)

**Rep details:** 3 reps + 3 sec hold, each side. The user will upload the video of both the sides differently, and analyse them differently, and show the score of both the sets separately. Show the final score from both sets as which is the best score from both the sets.

### Mediapipe Instructions Metrics:

**Primary metric — Hip extension angle:**
- Calculate angle at HIP between SHOULDER-HIP vector and HIP-KNEE vector at peak
- GOOD: hip extension angle ≥ 170° (near-straight line shoulder-hip-knee)

**Secondary metric — Pelvic levelness:**
- Monitor bilateral HIP Y-coordinates throughout 3-second hold
- Pelvic drop = vertical difference between left and right HIP landmarks
- Pelvic rotation = transverse tilt of bilateral HIP line from horizontal

**Hold stability metric:**
- Measure standard deviation of hip extension angle during 3-second hold
- GOOD: SD < 2° (stable hold)

**Scoring thresholds (per side):**
- GOOD: Hip extension ≥ 170°, pelvic drop < 1 cm, pelvic rotation < 3°, stable 3-second hold
- NEEDS IMPROVEMENT: Hip extension 160–170°, pelvic drop 1–2 cm, minor wobble during hold
- RESTRICTED: Hip extension < 160° OR pelvic drop > 2 cm OR visible pelvic rotation > 5°

**Bilateral symmetry:** Flag if |Left hip extension − Right hip extension| > 10° OR one side shows significant drop while other is stable

**Rep Details:** 3 reps each side, user will upload the video of both the sides differently, and analyse them differently, and show the score of both the sets separately. Show the final score from both sets as which is the best score from both the sets.

**Important:** Find all the metrics for all the 3 reps.

**Mediapipe and Important Instructions:** 
- **Hip Extension Anlge:** First the baseline is the ground. Measure the distance between the ground and the hip for each for each side. The user will perform 3 reps for each side so you will get 3 maximum hip (Remember - take the values when the user first touches the highest point, because the user is going to hold the position ofr 3 secs, so take the point value like wehn the user the touches the highest point ( the frame) ) to baseline height values. Where you find the 3 baseline values, for the 1st go to the time stamp the user will be at the highest point  in the rep, the user will hold the pose for 3 sec, From there , for each second ( for three secs ) calculate the angle between two axis - SHOULDER-HIP vector and HIP-KNEE vector. Do the Standard deviation all the 3 angles values and there you get the hip extension angle for one rep.
- **Pelvic drop:**
- **Pelvic Rotation:**


---

## EXERCISE 7 — Dead Bug (Core Activation)

**Camera:** Side view, 90° to athlete, head-to-knee frame
**Landmarks tracked:** SHOULDER (11/12), HIP (23/24), KNEE (25/26), ELBOW (13/14), WRIST (15/16), ANKLE (27/28)

**Rep details:** 4 reps each side, slow, the user will upload for each side separately.

### Mediapipe Instructions Metrics:

**Primary metric — Lumbar-to-floor gap:**
- Detect lower back contact with floor via torso line angle
- Measure any lumbar arch as deviation from straight SHOULDER-HIP line
- Critical measurement: maintain gap < 1 cm throughout movement

**Secondary metric — Limb lowering angle:**
- Lowered arm: measure angle from vertical at end-range
- Lowered leg: measure knee-to-floor angle at end-range (target: lower leg parallel to floor)

**Tempo metric:**
- Measure time from start to full extension
- Target: 4 seconds per rep
- Flag rushed movement (< 2.5 seconds) = momentum compensation

**Compensation metrics:**
- Ribcage flare: shoulder-to-rib angle change during arm extension
- Breath hold / bearing down: detect abdominal bracing pattern

**Scoring thresholds:**
- GOOD: Zero lumbar lift throughout all 4 reps, full limb extension achieved, 4-second tempo maintained, no rib flare
- NEEDS IMPROVEMENT: Minor lumbar lift (< 1 cm) only at end range, tempo 2.5–4 seconds, slight rib flare
- RESTRICTED: Lumbar lift > 1 cm before full extension OR rushed tempo (< 2.5 sec) OR obvious rib flare OR breath holding

**Bilateral asymmetry:** Flag if one side shows significantly more lumbar lift than the other

**Important:** Find all the metrics for all the 4 reps, each side.

**mediapipe and Important Instructions:** 


---

## EXERCISE 8 — Hollow Body Hold (Core Activation)

**Camera:** Side view, 90° to athlete, full body frame
**Landmarks tracked:** SHOULDER (11/12), HIP (23/24), KNEE (25/26), ANKLE (27/28), EAR (7/8) for head position

**Rep Details:** 3 x 10 sec hold

### Mediapipe Instructions Metrics:

**Primary metric — Leg-to-floor angle:**
- Calculate angle from HIP → ANKLE vector relative to horizontal floor line
- LOWER angle = STRONGER core (less than 30° ideal)

**Critical constraint — Lumbar contact:**
- Lower back must maintain floor contact throughout
- Measure any lift as vertical displacement of lumbar spine region
- If lumbar lifts, increase leg angle until contact restores — this becomes the score

**Hold duration metric:**
- Target: 10 seconds continuous hold
- Valid hold = no lumbar lift AND no position breakdown for full duration
- Record actual hold time achieved

**Stability metric:**
- Measure position tremor via landmark oscillation amplitude during hold
- GOOD: minimal oscillation (< 1 cm at ankle)

**Scoring thresholds:**
- GOOD: Legs at ≤ 30° above floor, lumbar fully flat, full 10-second hold, no tremor
- NEEDS IMPROVEMENT: Legs at 30–45°, lumbar mostly flat with minor lift, 6–10 second hold, slight tremor
- RESTRICTED: Legs must stay > 45° to keep lumbar flat, OR hold duration < 6 seconds, OR significant tremor/position breakdown

**Important:** Find all the metrics for all the 3 reps.

---

## EXERCISE 9 — Plank with Shoulder Tap (Core Activation)

**Camera:** Side view, 90° to athlete, full body frame
**Landmarks tracked:** SHOULDER (11/12), HIP (23/24), KNEE (25/26), ANKLE (27/28), WRIST (15/16)

**Rep Details:** 10 Taps, Each side

### Mediapipe Instructions Metrics:

**Primary metric — Hip drop (vertical):**
- Measure HIP Y-coordinate displacement from plank baseline during each tap
- Target: zero drop — hips stay level with plank line

**Primary metric — Hip rotation (transverse twist):**
- Measure rotation of bilateral HIP line relative to bilateral SHOULDER line during tap
- Target: zero rotation — hips and shoulders stay parallel

**Plank line integrity:**
- Measure body line sag/pike: angle at HIP between SHOULDER-HIP and HIP-KNEE vectors
- Target: ≥ 170° (straight line)

**Tempo metric:**
- Measure time per tap — target 2 seconds per tap
- Flag rushed pace (< 1 sec per tap) = compensation via momentum

**Bilateral comparison:**
- Compare left hand tap vs right hand tap for drop/rotation differences

**Scoring thresholds:**
- GOOD: Hip drop < 1 cm, hip rotation < 3°, plank line ≥ 170°, 2-second tempo, symmetric L/R
- NEEDS IMPROVEMENT: Hip drop 1–2 cm, rotation 3–8°, slight sag/pike, slightly rushed
- RESTRICTED: Hip drop > 2 cm OR rotation > 8° OR plank line < 160° OR rushed tempo OR significant L/R asymmetry

**Important:** Find all the metrics for all the 10 taps, each side.

---

## EXERCISE 10 — Prone Y-T-W Raise (Scapular Stability)

**Camera 1 (Primary):** Overhead view — phone mounted directly above athlete
**Camera 2 (Secondary):** Foot-side view at 45° elevation, pointing toward head
**Landmarks tracked:** SHOULDER (11/12), ELBOW (13/14), WRIST (15/16), HIP (23/24), spine midline

**Rep Details:** 3 reps each shape (Y, T, W). The user will upload separate videos for each shape from two angles, so the total videos you will get is 6. in it the user will do 3 reps, 3 reps per video of different shape, so make 6 sections specifying the user the angle from which they should record the video and the excercise name, for example - 

1. Prone Y (Overhead View)
2. Prone Y (Foot-Side View)
3. Prone T (Overhead View)
4. Prone T (Foot-Side View)
5. Prone W (Overhead View)
6. Prone W (Foot-Side View)

### Mediapipe Instructions Metrics:

**Y-SHAPE metrics:**
- Measure angle from SHOULDER → ELBOW vector relative to torso longitudinal axis
- TARGET: 30–45° above shoulder line (both arms)
- Measure arm elevation height off floor (from foot-side camera)
- Compare L vs R arm angles and elevation heights

**T-SHAPE metrics:**
- Measure angle from SHOULDER → ELBOW vector relative to torso longitudinal axis
- TARGET: 90° (arms straight out perpendicular to body)
- Measure arm elevation height off floor
- Compare L vs R

**W-SHAPE metrics:**
- Measure elbow flexion angle (should be ~90°)
- Measure shoulder blade retraction (scapular adduction)
- Monitor humeral position behind torso midline

**Compensation metrics (applicable to all shapes):**
- Shoulder shrug: distance from EAR to SHOULDER landmark — flag if decreases from baseline
- Neck tension: measure neck angle
- Lumbar arch: monitor HIP elevation — flag compensatory back arch
- Thumb position: thumbs should point up (measure if pose estimation supports)

**Scapular winging (from foot-side camera):**
- Detect medial border of scapula lifting off back
- Measured as bilateral shoulder blade prominence asymmetry

**Scoring thresholds:**
- GOOD: Y arms 30–45° symmetrical, T arms at 90° equal height, W elbows level with/above torso, no shrug or rib flare, no scapular winging
- NEEDS IMPROVEMENT: Arms reach position but L/R differs by 10–15°, slight shrug or neck tension
- RESTRICTED: Arms short of target angles, L/R difference > 15°, visible scapular winging, significant shrug compensation

**Hold duration:** 2 seconds at end-range for each shape, 3 reps per shape

---

## GENERAL AI IMPLEMENTATION NOTES

**Minimum frame rate:** 30 fps for accurate tempo detection

**Calibration requirements:**
- In-frame reference object of known size (e.g., tape measure, A4 paper, ruler) for pixel-to-cm conversion
- Plumb line or level indicator for gravity reference
- Athlete should wear fitted clothing for accurate landmark detection

**Measurement reliability:**
- Shoulder landmarks have highest error in 2D pose estimation (MAE ~6.5°)
- For 90/90 test specifically, consider ML refinement layer for clinical-grade accuracy
- Dual-camera setups recommended for exercises with scapular components (Y-T-W, 90/90)

**Bilateral comparison is critical:**
- Every metric should be computed for left and right sides where applicable
- Asymmetry flags should be reported independently of absolute value scoring

**Movement validation:**
- AI must detect and reject invalid reps (wrong tempo, obvious compensation, setup outside tolerance)
- Report number of valid reps out of total attempted

**Output format per exercise:**
- Classification: GOOD / NEEDS IMPROVEMENT / RESTRICTED
- Numerical metrics (all measurements in degrees, cm, or seconds)
- Bilateral comparison data
- Compensation flags detected
- Confidence score based on landmark visibility and movement quality

**Overall mobility profile:**
- Composite score across all 10 exercises (8 areas, Core has 3 sub-tests)
- Identified weakest areas (priority for corrective programming)
- Bilateral asymmetry summary
- Red flags requiring clinical referral (sharp pain, severe restriction, etc.)
