import type { Exercise } from '@/data/types';

/**
 * STRENGTH ASSESSMENT — 5 compound lifts.
 *
 * Spec: AI_Metrics_Specification-Strength.md
 *
 * Shape mirrors the mobility exercises so all generic pages (ExerciseGuide,
 * InstructionPage, ProcessingPage, ResultPage, Dashboard) reuse without
 * changes.  The `result` field on each exercise is a sample fallback used
 * only before the user has actually run an analysis.
 */

const sampleStats = (n: number) => ({
  validReps:  `${n}/${n}`,
  confidence: '88%',
  sides:      'side',
  cameraView: 'OK',
});

export const EXERCISES: Exercise[] = [
  /* ────────────────────────────────────────────────────────────────── */
  {
    id: 1, slug: 'back-squat', name: 'Back Squat', subtitle: 'Compound Knee + Hip Extension',
    category: 'Lower Body', duration: '~5 min', difficulty: 'Intermediate', color: '#00e5b0',
    description: 'Bilateral squat. Both side and front camera angles are REQUIRED. ' +
                 'Sagittal metrics (depth, knee/hip flexion, trunk lean, TTA, heel lift, ' +
                 'butt wink, bar path, tempo, MCV) come from the side; valgus and bilateral ' +
                 'knee tracking come from the front. Best score per metric is taken across both cams.',
    cameraSetup: 'Side: hip-height, 90°, 2.5–3 m · Front: knee-height, head-on (valgus)',
    checklist: [
      'Side cam: hip-height tripod, 90° to athlete, 2.5–3 m, plates fully visible',
      'Front cam: knee-height tripod, head-on, both knees visible',
      'Whole body + barbell in frame on BOTH cameras',
      'Variant: High bar squat or Low bar squat',
      'Enter reps in EACH video separately (side and front)',
      'Plain background helps plate detection',
    ],
    refs: [
      { type: 'VIDEO',  title: 'How To Perform',  sub: 'Back Squat', tag: 'Watch first', guide: null },
      { type: 'CAMERA', title: 'Camera Setup',    sub: 'Side + Front · Two cams required', tag: 'Position guide', guide: null },
      { type: 'GUIDE',  title: 'Technique Guide', sub: 'Step-by-step',
        tag: 'Read before recording',
        guide: '1. Side cam: 90° to athlete, hip-height tripod, 2.5–3 m. Plate faces fully visible.\n' +
               '2. Front cam: head-on, knee-height tripod. Both knees clearly framed.\n' +
               '3. Frame must include above-head to below-feet on both cams.\n' +
               '4. Film from the left side by default for the side cam.\n' +
               '5. Pick variant: High bar squat or Low bar squat.\n' +
               '6. Reps can differ per cam — enter each count separately when prompted.' },
      { type: 'IMAGE',  title: 'Exercise Image',  sub: 'Back Squat', tag: 'Body position', guide: null },
    ],
    uploads: [
      { id: 'side',  label: 'Side View',  angle: 'Side · 90° · Hip height · 2.5–3 m', reps: 'Enter side rep count' },
      { id: 'front', label: 'Front View', angle: 'Front · Head-on · Knee height',     reps: 'Enter front rep count' },
    ],
    result: {
      status: 'NEEDS IMPROVEMENT', score: 72,
      summary: 'Sample result — run the analysis for your actual numbers.',
      stats: sampleStats(3),
      metrics: [
        { name: 'Squat Depth (hip vs knee)', value: '+1.2 cm', raw: 1.2, target: '≥0 (parallel)', max: 10, status: 'good' },
        { name: 'Knee Flexion at Bottom',     value: '108°',   raw: 108, target: '≥100°',        max: 130, status: 'good' },
        { name: 'Trunk Lean',                  value: '32°',    raw: 32,  target: '~30°',          max: 80,  status: 'good' },
        { name: 'TTA (hip vs knee bias)',     value: '+4° · balanced', raw: 4, target: '±10°', max: 30, status: 'good' },
        { name: 'Heel Lift',                   value: '0.8 cm', raw: 0.8, target: '<1.5 cm',       max: 5,   status: 'good' },
        { name: 'Butt Wink',                   value: '6°',     raw: 6,   target: '<10°',          max: 30,  status: 'good' },
        { name: 'Bar Path Drift (RMS)',        value: '3.5 cm', raw: 3.5, target: '<5 cm',         max: 15,  status: 'good' },
      ],
      bilateral: [],
      coaching: ['Strong technique — increase load progressively while maintaining depth.'],
      annotated_frames: [],
      muscle_activation: {
        exercise: 'Back Squat',
        dominance: 'Balanced (Neutral)',
        muscles: [
          { slug: 'quadriceps', name: 'Quadriceps', percentage: 70, side: 'both', isPrimary: true },
          { slug: 'glutes', name: 'Gluteus Maximus', percentage: 65, side: 'both', isPrimary: true },
          { slug: 'hamstrings', name: 'Hamstrings', percentage: 50, side: 'both', isPrimary: true },
          { slug: 'adductors', name: 'Adductors', percentage: 40, side: 'both', isPrimary: false },
          { slug: 'erector_spinae', name: 'Erector Spinae', percentage: 35, side: 'both', isPrimary: false },
          { slug: 'core', name: 'Core / Abdominals', percentage: 45, side: 'both', isPrimary: false },
          { slug: 'calves', name: 'Calves', percentage: 30, side: 'both', isPrimary: false },
          { slug: 'hip_flexors', name: 'Hip Flexors', percentage: 25, side: 'both', isPrimary: false },
        ],
      },
    },
  },

  /* ────────────────────────────────────────────────────────────────── */
  {
    id: 2, slug: 'deadlift', name: 'Deadlift', subtitle: 'Hip-Dominant Pull Pattern',
    category: 'Lower Body', duration: '~5 min', difficulty: 'Intermediate', color: '#4488ff',
    description: 'Conventional / Romanian. Four-camera capture (sagittal, frontal, posterior, oblique) ' +
                 'drives a Safety 50% / Technique 35% / Performance 15% composite per the biomechanical ' +
                 'spec. Hard-fail safety overrides cap the composite on visible lumbar rounding, ' +
                 'stripper-deadlift hip-shoulder timing, gross bar drift, hyperextension, and knee valgus.',
    cameraSetup: '4 cameras · Sagittal + Frontal + Posterior + Oblique · 60 fps min · 1080p · Even lighting',
    checklist: [
      'Four cameras: sagittal (side, strong-side), frontal (head-on), posterior (rear), oblique (45°)',
      '60 fps minimum (120 fps for advanced velocity); 1080p+',
      'Sagittal at hip height, 3–4 m. Frontal/posterior at 2.5–3 m. Oblique 3 m at 45°',
      'Whole body + barbell in every frame, from above-head to floor',
      'Plates fully visible from the sagittal view; plain, contrasting background',
      'A known-length reference (45 cm Olympic plate edge-on) in calibration frame',
      'Pick variant: conventional or Romanian (RDL)',
      '3 / 5 / 10 reps at the chosen RM',
    ],
    refs: [
      { type: 'VIDEO',  title: 'How To Perform',  sub: 'Deadlift',  tag: 'Watch first', guide: null },
      { type: 'CAMERA', title: 'Camera Setup',    sub: '4 angles · Sagittal + Frontal + Posterior + Oblique', tag: 'Position guide', guide: null },
      { type: 'GUIDE',  title: 'Technique Guide', sub: 'Variants and cues',
        tag: 'Read before recording',
        guide: '1. Place all four cameras on tripods. Sagittal hip-height 3–4 m from the strong side. ' +
               'Frontal head-on at 2.5–3 m. Posterior directly behind at 3 m. Oblique at 45° between sagittal and frontal.\n' +
               '2. Even, diffuse lighting ≥500 lux. No backlight. Plain background.\n' +
               '3. Place an Olympic plate edge-on in the calibration frame so the analyzer can ' +
               'convert pixel distances to centimetres.\n' +
               '4. Conventional: bar over mid-foot, ~1 inch from vertical shin. Lats engaged. ' +
               'Romanian: stand tall, bar at hip/thigh, knees held at ~15° bend, hinge back.\n' +
               '5. Film one working set at 60 fps minimum. 120 fps for bar-velocity profiling.\n' +
               '6. CRITICAL: neutral spine throughout. Visible lumbar rounding caps the composite at 40.' },
      { type: 'IMAGE',  title: 'Exercise Image',  sub: 'Deadlift', tag: 'Body position', guide: null },
    ],
    uploads: [
      { id: 'sagittal',  label: 'Sagittal (Side)',     angle: 'Side · Strong-side · Hip height · 3–4 m', reps: 'Same set · the scored clip' },
      { id: 'frontal',   label: 'Frontal (Front)',     angle: 'Head-on · 2.5–3 m · Knee height',         reps: 'Same set, head-on' },
      { id: 'posterior', label: 'Posterior (Rear)',    angle: 'Directly behind · 3 m · Hip height',      reps: 'Same set, from behind' },
      { id: 'oblique',   label: 'Oblique (45°)',       angle: '45° between sagittal and frontal · 3 m',  reps: 'Same set, 45° view' },
    ],
    result: {
      status: 'GOOD', score: 84,
      summary: 'Sample result — run the analysis for your actual numbers.',
      stats: sampleStats(3),
      metrics: [
        { name: 'Min Spine Angle (concentric)', value: '171°',   raw: 171, target: '≥165°',  max: 180, status: 'good' },
        { name: 'Lumbar Flexion (worst)',        value: '9°',     raw: 9,   target: '<10°',   max: 30,  status: 'good' },
        { name: 'Bar Path Drift (RMS)',          value: '2.8 cm', raw: 2.8, target: '<5 cm',  max: 20,  status: 'good' },
        { name: 'Hip:Knee Extension Ratio',      value: '1.05',   raw: 1.05,target: '0.8–1.3',max: 3,   status: 'good' },
      ],
      bilateral: [],
      coaching: ['Solid neutral-spine pull — keep the bar tight to your legs.'],
      annotated_frames: [],
      muscle_activation: {
        exercise: 'Deadlift',
        dominance: 'Hip-Dominant (Conventional)',
        muscles: [
          { slug: 'glutes', name: 'Gluteus Maximus', percentage: 85, side: 'both', isPrimary: true },
          { slug: 'hamstrings', name: 'Hamstrings', percentage: 80, side: 'both', isPrimary: true },
          { slug: 'erector_spinae', name: 'Erector Spinae', percentage: 75, side: 'both', isPrimary: true },
          { slug: 'quadriceps', name: 'Quadriceps', percentage: 35, side: 'both', isPrimary: false },
          { slug: 'lats', name: 'Latissimus Dorsi', percentage: 40, side: 'both', isPrimary: false },
          { slug: 'traps', name: 'Trapezius', percentage: 35, side: 'both', isPrimary: false },
          { slug: 'core', name: 'Core / Abdominals', percentage: 45, side: 'both', isPrimary: false },
          { slug: 'forearms', name: 'Forearms', percentage: 40, side: 'both', isPrimary: false },
        ],
      },
    },
  },

  /* ────────────────────────────────────────────────────────────────── */
  {
    id: 3, slug: 'bench-press', name: 'Bench Press', subtitle: 'Horizontal Push',
    category: 'Upper Body', duration: '~5 min', difficulty: 'Intermediate', color: '#a855f7',
    description: 'Flat / Incline. Four-camera capture (sagittal, overhead, head-end, oblique) drives a ' +
                 'Safety 40% / Technique 35% / Performance 25% composite per the biomechanical spec. ' +
                 'Touch-frame anchored: every metric and every diagram is computed at the bar’s ' +
                 'lowest point (extreme position) in bench-relative coordinates. PL and BB styles use ' +
                 'different thresholds for grip width, arch, and elbow flare.',
    cameraSetup: '4 cameras · Sagittal + Overhead + Head-end + Oblique · 60 fps min · 1080p · Even lighting',
    checklist: [
      'Four cameras: sagittal (perpendicular to bench), overhead (lens parallel to floor, pointed down), ' +
      'head-end (behind the head, lens at bar-rack height), oblique (front-lateral 45°)',
      '60 fps minimum (120 fps for max-effort singles / bounce detection); 1080p+',
      'Sagittal lens height = bench surface for flat, perpendicular to bench plane for incline',
      'Both plate faces visible from the sagittal view; plain, contrasting background',
      'Diffuse lighting ≥500 lux; no backlight — supine pose detection suffers in silhouette',
      'Place a known-length reference (men’s bar = 220 cm sleeve-to-sleeve, or 45 cm Olympic plate edge-on) in frame',
      'Pick variant: Flat or Incline (enter incline angle); pick style: PL or BB',
      'Scapular retraction locked in BEFORE un-racking — this is the foundation',
      '3 / 5 / 10 reps at the chosen RM; enter the rep count for EACH camera',
    ],
    refs: [
      { type: 'VIDEO',  title: 'How To Perform',  sub: 'Bench Press', tag: 'Watch first', guide: null },
      { type: 'CAMERA', title: 'Camera Setup',    sub: '4 angles · Sagittal + Overhead + Head-end + Oblique',
        tag: 'Position guide', guide: null },
      { type: 'GUIDE',  title: 'Technique Guide', sub: 'Setup, tuck, J-curve',
        tag: 'Read before recording',
        guide: '1. Sagittal: perpendicular to bench, 2.5–3.5 m, lens at bench-surface height (flat) or ' +
               'perpendicular to bench plane (incline).\n' +
               '2. Overhead: directly above the bench, lens parallel to floor, pointed straight down.\n' +
               '3. Head-end: behind the head of the bench, 1.5–2 m back, lens at bar-rack height.\n' +
               '4. Oblique: front-lateral 45°, 2.5 m — covers occlusions; backup view for the analyzer.\n' +
               '5. PL: low touch (lower sternum), tucked elbows ~45°, max-allowed arch, wide grip ≤81 cm. ' +
               'BB: mid-chest touch, ~60–75° elbow, minimal arch, moderate grip.\n' +
               '6. CRITICAL: scapulae retracted + depressed BEFORE un-racking. Bar to chest (not throat). ' +
               'Pause for paused-bench protocol.\n' +
               '7. Film one working set at 60 fps minimum. 120 fps for max-effort singles.' },
      { type: 'IMAGE',  title: 'Exercise Image',  sub: 'Bench Press', tag: 'Body position', guide: null },
    ],
    uploads: [
      { id: 'sagittal', label: 'Sagittal (Side)',  angle: 'Perpendicular to bench · 2.5–3.5 m · Bench-surface lens height', reps: 'Enter sagittal rep count' },
      { id: 'overhead', label: 'Overhead',         angle: 'Directly above · Lens parallel to floor, pointed down',         reps: 'Enter overhead rep count' },
      { id: 'headEnd',  label: 'Head-end (Rear)',  angle: 'Behind the head · 1.5–2 m · Bar-rack height',                    reps: 'Enter head-end rep count' },
      { id: 'oblique',  label: 'Oblique (45°)',    angle: 'Front-lateral 45° · 2.5 m',                                      reps: 'Enter oblique rep count' },
    ],
    result: {
      status: 'NEEDS IMPROVEMENT', score: 75,
      summary: 'Sample result — run the analysis for your actual numbers.',
      stats: sampleStats(3),
      metrics: [
        { name: 'Elbow Flare',          value: '48°',    raw: 48,  target: '30–60°',  max: 90,  status: 'good' },
        { name: 'Elbow Angle at Chest', value: '82°',    raw: 82,  target: '70–90°',  max: 120, status: 'good' },
        { name: 'Bar Path J-curve',     value: '11.5 cm',raw: 11.5,target: '8–18 cm', max: 30,  status: 'good' },
        { name: 'Hip Lift',              value: '0.4 cm', raw: 0.4, target: '<1 cm',   max: 5,   status: 'good' },
      ],
      bilateral: [],
      coaching: ['Solid tuck and path — keep the pause at the chest for a clean strict rep.'],
      annotated_frames: [],
      muscle_activation: {
        exercise: 'Bench Press',
        dominance: 'Balanced (Pec + Tricep)',
        muscles: [
          { slug: 'pectorals', name: 'Pectoralis Major', percentage: 75, side: 'both', isPrimary: true },
          { slug: 'triceps', name: 'Triceps Brachii', percentage: 60, side: 'both', isPrimary: true },
          { slug: 'anterior_deltoid', name: 'Anterior Deltoid', percentage: 35, side: 'both', isPrimary: false },
          { slug: 'core', name: 'Core / Abdominals', percentage: 25, side: 'both', isPrimary: false },
          { slug: 'biceps', name: 'Biceps Brachii', percentage: 15, side: 'both', isPrimary: false },
          { slug: 'lats', name: 'Latissimus Dorsi', percentage: 20, side: 'both', isPrimary: false },
        ],
      },
    },
  },

  /* ────────────────────────────────────────────────────────────────── */
  {
    id: 4, slug: 'pull-up', name: 'Pull-Up', subtitle: 'Vertical Pull Pattern',
    category: 'Upper Body', duration: '~3 min', difficulty: 'Intermediate', color: '#f59e0b',
    description: 'Pronated / Supinated (chin-up) / Neutral / Wide. Four-camera capture drives a Safety 20% / ' +
                 'Technique 45% / Performance 35% composite per the biomechanical spec. Each rep is anchored ' +
                 'on TWO extreme positions: dead-hang (bottom) for elbow extension + body line, and ' +
                 'chin-over-bar (top) for ROM + layback + shoulder symmetry. Style toggle ' +
                 '(strict / kipping / butterfly / sternum / C2B / tactical) switches the rubric.',
    cameraSetup: '4 cameras · Sagittal + Frontal + Posterior + Oblique · 60 fps min · 1080p · Mid-bar lens height',
    checklist: [
      'Four cameras: sagittal (90° to bar, side profile), frontal (perpendicular to bar, in front of athlete), ' +
      'posterior (directly behind), oblique (45° between sagittal and frontal)',
      '60 fps minimum (120 fps for kipping / butterfly; 240 fps for fast eccentrics)',
      'Lens at MID-BAR height — must capture both dead-hang chin AND chin-over-bar lockout without panning',
      'Frame 3–4.5 m back: athlete + ~0.5 m head clearance above + ~1 m foot clearance below',
      '35–50 mm lens equivalent (avoid wide-angle <24 mm — vertical distortion corrupts body-line angles)',
      'Even, frontal lighting — no backlight from windows or overhead lights',
      'Tripod mandatory; handheld unusable for tempo and kip detection',
      'Pick grip (pronated / supinated / neutral / wide) and style (strict / kipping / etc)',
      'Strict: motionless dead-hang ≥1 s before first rep; no kipping, no swinging',
      'Enter rep count for EACH camera',
    ],
    refs: [
      { type: 'VIDEO',  title: 'How To Perform',  sub: 'Pull-Up', tag: 'Watch first', guide: null },
      { type: 'CAMERA', title: 'Camera Setup',    sub: '4 angles · Sagittal + Frontal + Posterior + Oblique',
        tag: 'Position guide', guide: null },
      { type: 'GUIDE',  title: 'Technique Guide', sub: 'Strict, kipping, butterfly',
        tag: 'Read before recording',
        guide: '1. Sagittal: 90° to the bar, side profile, lens at mid-bar height, 3–4.5 m back. THIS is the load-bearing view.\n' +
               '2. Frontal: directly in front, perpendicular to bar, lens at mid-bar height.\n' +
               '3. Posterior: directly behind, lens at mid-bar height — for inferred scapular kinematics.\n' +
               '4. Oblique: 45° between sagittal and frontal — fallback when sagittal/frontal occlude.\n' +
               '5. STRICT: come to motionless dead-hang ≥1 s before first rep. Elbows fully extended (≥170°) ' +
               'between every rep. Initiate the pull with scapular depression BEFORE the elbow flexes. ' +
               'Chin (NOT eyes / nose) clears the bar. Eccentric controlled, 2–4 s.\n' +
               '6. KIPPING: continuous hollow-arch transitions; chin clears bar. CrossFit style.\n' +
               '7. BUTTERFLY: continuous circular kip, no pause at top, athlete drops in front of bar.\n' +
               '8. STERNUM CHIN-UP (Gironda): pronounced layback (45–70° posterior), sternum to bar.\n' +
               '9. C2B (chest-to-bar): chin over bar + sternum/clavicle contact required.\n' +
               '10. TACTICAL (StrongFirst): thumbless overhand, motionless dead hang each rep, ' +
               'jawline (not chin) clears the bar OR upper chest touches.' },
      { type: 'IMAGE',  title: 'Exercise Image',  sub: 'Pull-Up', tag: 'Body position', guide: null },
    ],
    uploads: [
      { id: 'sagittal',  label: 'Sagittal (Side)',     angle: '90° to bar · Side profile · Mid-bar lens height · 3–4.5 m', reps: 'Enter sagittal rep count' },
      { id: 'frontal',   label: 'Frontal (Front)',     angle: 'Perpendicular to bar · In front · Mid-bar lens height',     reps: 'Enter frontal rep count' },
      { id: 'posterior', label: 'Posterior (Rear)',    angle: 'Directly behind · Mid-bar lens height · 3 m',                reps: 'Enter posterior rep count' },
      { id: 'oblique',   label: 'Oblique (45°)',       angle: '45° between sagittal and frontal · 3 m',                     reps: 'Enter oblique rep count' },
    ],
    result: {
      status: 'NEEDS IMPROVEMENT', score: 70,
      summary: 'Sample result — run the analysis for your actual numbers.',
      stats: sampleStats(6),
      metrics: [
        { name: 'Valid Reps (chin-over-bar)', value: '5/6',  raw: 5,   target: '≥5',   max: 10,  status: 'good' },
        { name: 'Chin Clearance Rate',         value: '83%',  raw: 83,  target: '100%', max: 100, status: 'bad' },
        { name: 'Elbow ROM',                    value: '92°',  raw: 92,  target: '≥85°', max: 130, status: 'good' },
        { name: 'Hip Swing (kipping)',          value: '4 cm', raw: 4,   target: '<5 cm',max: 25,  status: 'good' },
      ],
      bilateral: [],
      coaching: ['Add scapular initiation drills (scap pull-ups) before counting another set.'],
      annotated_frames: [],
      muscle_activation: {
        exercise: 'Pull-Up',
        dominance: 'Lat-Dominant (Pronated)',
        muscles: [
          { slug: 'lats', name: 'Latissimus Dorsi', percentage: 90, side: 'both', isPrimary: true },
          { slug: 'biceps', name: 'Biceps Brachii', percentage: 45, side: 'both', isPrimary: true },
          { slug: 'rhomboids', name: 'Rhomboids', percentage: 25, side: 'both', isPrimary: false },
          { slug: 'traps', name: 'Trapezius', percentage: 30, side: 'both', isPrimary: false },
          { slug: 'posterior_deltoid', name: 'Posterior Deltoid', percentage: 40, side: 'both', isPrimary: false },
          { slug: 'core', name: 'Core / Abdominals', percentage: 50, side: 'both', isPrimary: false },
          { slug: 'forearms', name: 'Forearms', percentage: 45, side: 'both', isPrimary: false },
        ],
      },
    },
  },

  /* ────────────────────────────────────────────────────────────────── */
  {
    id: 5, slug: 'overhead-press', name: 'Overhead Press', subtitle: 'Vertical Push',
    category: 'Upper Body', duration: '~3 min', difficulty: 'Advanced', color: '#ff4466',
    description: 'Military Press / Seated Dumbbell Shoulder Press. Four-camera capture drives a Safety 45% / ' +
                 'Technique 35% / Performance 20% composite per the biomechanical spec. Each rep is anchored ' +
                 'on THREE extreme positions: SETUP (bar at clavicle / DB at ear), STICKING POINT (velocity ' +
                 'minimum at ~25–45% bar travel), and LOCKOUT (top). Push-press detection is a HARD ' +
                 'CLASSIFIER: any knee bend > 8° or hip thrust > 4 cm before bar rises 5 cm reclassifies the ' +
                 'rep as push-press and excludes it from the strict-press set average.',
    cameraSetup: '4 cameras · Sagittal + Frontal + Posterior + Oblique · 60 fps min · 1080p · Mid-sternum lens height',
    checklist: [
      'Four cameras: sagittal (90° to lifter, sternum-height lens), frontal (head-on, chest-height lens), ' +
      'posterior (directly behind), oblique (45° — sagittal fallback when plates occlude head)',
      '60 fps minimum; 1080p+; shutter ≥1/250 s',
      'Vertical framing MUST include feet/seat at bottom AND ≥15 cm clearance above the locked-out bar/DB',
      'Sagittal: 3–4 m from standing lifter; 2.5–3 m for seated DB',
      'Pick variant: Military Press (standing barbell, strict) or Seated Dumbbell Shoulder Press',
      'For Seated DB: select backrest angle (90° / 85° / 75°); <70° is incline bench, not OHP',
      'Include a known-length calibration object (220 cm bar OR known-length tape) in first 3 s',
      'Standing: feet flat, knees LOCKED throughout — any knee bend reclassifies as push-press',
      'Brace ribs DOWN — no lumbar layback to "press" the bar',
      'Enter rep count for EACH camera',
    ],
    refs: [
      { type: 'VIDEO',  title: 'How To Perform',  sub: 'Overhead Press', tag: 'Watch first', guide: null },
      { type: 'CAMERA', title: 'Camera Setup',    sub: '4 angles · Sagittal + Frontal + Posterior + Oblique',
        tag: 'Position guide', guide: null },
      { type: 'GUIDE',  title: 'Technique Guide', sub: 'Strict press, military vs seated DB',
        tag: 'Read before recording',
        guide: '1. Sagittal: 90° to the lifter, lens at sternum height (~1.3–1.5 m), 3–4 m for standing or 2.5–3 m for seated.\n' +
               '2. Frontal: directly in front, lens at chest height, 2.5–3 m back.\n' +
               '3. Posterior: directly behind, lens at chest height — for inferred scapular kinematics.\n' +
               '4. Oblique: 45° between sagittal and frontal — backup when plates occlude head at lockout.\n' +
               '5. MILITARY: rack the bar on the anterior delts / clavicle; elbows just in front of wrists. ' +
               'Lean the head BACK to let the bar go up; head moves THROUGH the window at lockout. ' +
               'Lockout = bar over mid-foot, ribs down, glutes squeezed, knees LOCKED.\n' +
               '6. SEATED DB: bench at 75–90° backrest. DBs start at ear/shoulder height. Drive straight up; ' +
               'DBs lock out overhead, arms by ears, back flush to pad. NO arching off the pad.\n' +
               '7. CRITICAL: knee bend, hip thrust, or lumbar layback >15° will reclassify or cap the rep. ' +
               'Verified strict-press form earns the best composite.' },
      { type: 'IMAGE',  title: 'Exercise Image',  sub: 'Overhead Press', tag: 'Body position', guide: null },
    ],
    uploads: [
      { id: 'sagittal',  label: 'Sagittal (Side)',     angle: '90° to lifter · Sternum-height lens · 3–4 m', reps: 'Enter sagittal rep count' },
      { id: 'frontal',   label: 'Frontal (Front)',     angle: 'Head-on · Chest-height lens · 2.5–3 m',       reps: 'Enter frontal rep count' },
      { id: 'posterior', label: 'Posterior (Rear)',    angle: 'Directly behind · Chest-height lens · 3 m',   reps: 'Enter posterior rep count' },
      { id: 'oblique',   label: 'Oblique (45°)',       angle: '45° between sagittal and frontal · 3 m',      reps: 'Enter oblique rep count' },
    ],
    result: {
      status: 'GOOD', score: 86,
      summary: 'Sample result — run the analysis for your actual numbers.',
      stats: sampleStats(3),
      metrics: [
        { name: 'Lumbar Extension (worst)', value: '4°',     raw: 4,   target: '<5°',   max: 30,  status: 'good' },
        { name: 'Lockout Stack',             value: '+1.2 cm',raw: 1.2, target: '±3 cm', max: 15,  status: 'good' },
        { name: 'Bar Path RMS',              value: '3.4 cm', raw: 3.4, target: '<5 cm', max: 20,  status: 'good' },
        { name: 'Face Clearance',            value: '6.1 cm', raw: 6.1, target: '≥5 cm', max: 15,  status: 'good' },
      ],
      bilateral: [],
      coaching: ['Strong strict press pattern — maintain ribs-down brace as load increases.'],
      annotated_frames: [],
      muscle_activation: {
        exercise: 'Overhead Press',
        dominance: 'Lateral Delt + Tricep (Balanced)',
        muscles: [
          { slug: 'lateral_deltoid', name: 'Lateral Deltoid', percentage: 70, side: 'both', isPrimary: true },
          { slug: 'anterior_deltoid', name: 'Anterior Deltoid', percentage: 50, side: 'both', isPrimary: true },
          { slug: 'triceps', name: 'Triceps Brachii', percentage: 60, side: 'both', isPrimary: true },
          { slug: 'traps', name: 'Trapezius', percentage: 55, side: 'both', isPrimary: false },
          { slug: 'core', name: 'Core / Abdominals', percentage: 40, side: 'both', isPrimary: false },
          { slug: 'erector_spinae', name: 'Erector Spinae', percentage: 30, side: 'both', isPrimary: false },
        ],
      },
    },
  },
];
