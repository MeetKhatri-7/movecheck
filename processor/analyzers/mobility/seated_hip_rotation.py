"""Exercise 2 — Seated Hip Rotation Test (Hip IR / ER).

Camera: Front view, eye-level with knees.
Inputs: 2 videos (left hip, right hip), 3 reps each direction.

────────────────────────────────────────────────────────────────────────
IR / ER convention (corrected — was inverted in the original docs):

  Seated on a high bench, hip flexed at 90°, lower leg hanging.
  The thigh's rotation is what we're measuring; the lower leg (knee→ankle)
  is the visible lever arm.

      Foot swings OUTWARD (away from body midline)
        → thigh rotates internally
        → INTERNAL ROTATION (IR)

      Foot swings INWARD (toward the other leg / body midline)
        → thigh rotates externally
        → EXTERNAL ROTATION (ER)

  We label direction from the SIGN of the foot's deviation, not from
  rep ordering — so the AI is correct regardless of whether the user
  starts with IR or ER and regardless of which side is being filmed.
────────────────────────────────────────────────────────────────────────
"""
from utils.landmarks import (
    extract_all_landmarks, get_landmark_px, midpoint_px, LM, confidence_score
)
from utils.angles import angle_to_vertical, signed_angle_from_vertical
from utils.rep_detection import detect_reps
from utils.scoring import (
    classify, build_metric, build_bilateral, build_result,
    compute_overall_score, overall_status, generate_coaching_notes
)
from utils.frame_annotator import generate_annotated_frame

HIP_CONNECTIONS = [
    (23, 25), (25, 27), (24, 26), (26, 28),
    (23, 24), (11, 23), (12, 24), (11, 12),
]


def _classify_direction(side_label, deviation_sign):
    """Map (side, sign of lower-leg deviation) → 'IR' / 'ER'.

    Image coords: x increases to the right.
    `deviation_sign` is the sign of (signed_angle_from_vertical at peak):
        positive → ankle ended up to the RIGHT of the knee
        negative → ankle ended up to the LEFT of the knee.

    For the LEFT hip (filmed from the front), the body midline is to the
    RIGHT of the foot:
        ankle to the right of knee  = foot moved TOWARD midline  = ER
        ankle to the left  of knee  = foot moved AWAY from midline = IR
    Right hip is mirrored.
    """
    if side_label == 'left':
        return 'ER' if deviation_sign > 0 else 'IR'
    return 'IR' if deviation_sign > 0 else 'ER'


def _analyse_side(video_path, side_label):
    """Analyse one hip video for IR/ER angles."""
    data = extract_all_landmarks(video_path)
    frames = data['frames']
    fps = data['fps']
    w, h = data['width'], data['height']
    conf = confidence_score(frames)

    knee_idx  = LM['LEFT_KNEE']  if side_label == 'left' else LM['RIGHT_KNEE']
    ankle_idx = LM['LEFT_ANKLE'] if side_label == 'left' else LM['RIGHT_ANKLE']

    # ── Lower-leg deviation series (signed angle of knee→ankle from vertical) ──
    angle_series = []
    for f in frames:
        lm = f['landmarks']
        if lm is None:
            angle_series.append(0)
            continue
        knee  = get_landmark_px(lm, knee_idx,  w, h)
        ankle = get_landmark_px(lm, ankle_idx, w, h)
        ang = signed_angle_from_vertical(knee, ankle)
        angle_series.append(ang if ang is not None else 0)

    valid_angles = [a for a in angle_series if a != 0]
    rest_angle = sorted(valid_angles)[len(valid_angles) // 2] if valid_angles else 0
    deviation = [a - rest_angle for a in angle_series]
    abs_deviation = [abs(d) for d in deviation]

    # ── Detect rep peaks ──
    reps = detect_reps(abs_deviation, expected_reps=6, fps=fps, min_hold_sec=0.5)
    if len(reps) > 6:
        reps.sort(key=lambda x: x['peak_value'], reverse=True)
        reps = reps[:6]
        reps.sort(key=lambda x: x['peak_frame'])

    ir_angles, er_angles, rep_details = [], [], []

    for rep in reps:
        # True extreme = frame with max |deviation| inside the rep window;
        # the smoothed peak frame systematically understates the real angle.
        seg_start = rep['start_frame']
        seg_end   = min(rep['end_frame'] + 1, len(deviation))
        peak_idx  = max(range(seg_start, seg_end), key=lambda i: abs_deviation[i])
        d = deviation[peak_idx]
        peak_angle = abs(d)
        if peak_angle < 10:
            continue

        # Direction from the SIGN of the foot's deviation (not rep ordering)
        direction = _classify_direction(side_label, d)

        rep_details.append({
            'peak_frame': peak_idx,
            'direction':  direction,
            'angle':      round(peak_angle, 1),
        })

        if direction == 'IR':
            ir_angles.append(peak_angle)
        else:
            er_angles.append(peak_angle)

    peak_ir = max(ir_angles) if ir_angles else 0.0
    peak_er = max(er_angles) if er_angles else 0.0

    # ── Trunk lean (sagittal — shoulders should stay over hips) ──
    trunk_lean_values = []
    for f in frames:
        lm = f['landmarks']
        if lm is None: continue
        smid = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
        hmid = midpoint_px(lm, LM['LEFT_HIP'],      LM['RIGHT_HIP'],      w, h)
        if smid and hmid:
            tl = angle_to_vertical(smid, hmid)
            if tl is not None: trunk_lean_values.append(abs(tl))
    max_trunk_lean = max(trunk_lean_values) if trunk_lean_values else 0

    # ── Annotated frames ──
    annotated = []
    for i, rd in enumerate(rep_details):
        lm = frames[rd['peak_frame']]['landmarks'] if rd['peak_frame'] < len(frames) else None
        if lm is None: continue
        angle_val = rd['angle']
        direction = rd['direction']

        metrics_overlay = [
            {'label': f'{direction} Angle', 'value': f"{angle_val}°",
             'status': 'good' if angle_val >= 40 else 'bad'},
            {'label': 'Trunk Lean', 'value': f"{round(max_trunk_lean,1)}°",
             'status': 'good' if max_trunk_lean < 5 else 'bad'},
        ]

        hip_landmark = LM['LEFT_HIP'] if side_label == 'left' else LM['RIGHT_HIP']
        angles_draw = [{
            'vertex_idx': knee_idx, 'p1_idx': ankle_idx, 'p2_idx': hip_landmark,
            'value': angle_val, 'label': f"{direction}: {angle_val}°",
            'color': (0, 229, 176) if direction == 'ER' else (255, 165, 0),
        }]

        img = generate_annotated_frame(
            video_path, rd['peak_frame'], lm, w, h,
            angles=angles_draw, metrics=metrics_overlay,
            rep_num=i + 1, total_reps=len(rep_details), side=side_label,
            exercise_connections=HIP_CONNECTIONS,
        )
        if img:
            annotated.append({
                'label': f"{side_label.title()} — Rep {i+1} ({direction})",
                'image_base64': img,
                'rep_num': i + 1, 'side': side_label,
                'is_best': (direction == 'IR' and angle_val == peak_ir) or
                           (direction == 'ER' and angle_val == peak_er),
                'metrics_shown': [f"{direction}: {angle_val}°"],
            })

    return {
        'side': side_label,
        'peak_ir': round(peak_ir, 1),
        'peak_er': round(peak_er, 1),
        'max_trunk_lean': round(max_trunk_lean, 1),
        'valid_reps': len(rep_details),
        'total_reps': 6,
        'confidence': conf,
        'per_rep': rep_details,
        'annotated_frames': annotated,
    }


def analyse(files):
    """Main entry point for Seated Hip Rotation analysis."""
    left  = _analyse_side(files.get('left', ''),  'left')
    right = _analyse_side(files.get('right', ''), 'right')

    total_valid = left['valid_reps'] + right['valid_reps']
    avg_conf = (left['confidence'] + right['confidence']) // 2

    metrics = []
    metrics.append(build_metric('Left Int. Rotation',  f"{left['peak_ir']}°",  left['peak_ir'],  '≥40°', 60,
                                classify(left['peak_ir'],  40, 30, higher_is_better=True)))
    metrics.append(build_metric('Right Int. Rotation', f"{right['peak_ir']}°", right['peak_ir'], '≥40°', 60,
                                classify(right['peak_ir'], 40, 30, higher_is_better=True)))
    metrics.append(build_metric('Left Ext. Rotation',  f"{left['peak_er']}°",  left['peak_er'],  '≥40°', 70,
                                classify(left['peak_er'],  40, 30, higher_is_better=True)))
    metrics.append(build_metric('Right Ext. Rotation', f"{right['peak_er']}°", right['peak_er'], '≥40°', 70,
                                classify(right['peak_er'], 40, 30, higher_is_better=True)))
    metrics.append(build_metric('Left Trunk Lean',  f"{left['max_trunk_lean']}°",  left['max_trunk_lean'],  '<5°', 20,
                                classify(left['max_trunk_lean'],  5, 10, higher_is_better=False)))
    metrics.append(build_metric('Right Trunk Lean', f"{right['max_trunk_lean']}°", right['max_trunk_lean'], '<5°', 20,
                                classify(right['max_trunk_lean'], 5, 10, higher_is_better=False)))

    bilateral = [
        build_bilateral('Internal Rotation', left['peak_ir'], right['peak_ir'], '°', 60),
        build_bilateral('External Rotation', left['peak_er'], right['peak_er'], '°', 70),
    ]

    score    = compute_overall_score(metrics)
    status   = overall_status(score)
    coaching = generate_coaching_notes(metrics, bilateral, 'Seated Hip Rotation Test')

    ir_diff = abs(left['peak_ir'] - right['peak_ir'])
    er_diff = abs(left['peak_er'] - right['peak_er'])
    if ir_diff > 10: coaching.insert(0, f"Internal rotation asymmetry of {round(ir_diff,1)}°.")
    if er_diff > 10: coaching.insert(0, f"External rotation asymmetry of {round(er_diff,1)}°.")

    summary = (f"Analysed {total_valid}/{left['total_reps'] + right['total_reps']} valid reps "
               f"across both hips.")

    stats = {
        'validReps':  f'{total_valid}/{left["total_reps"] + right["total_reps"]}',
        'confidence': f'{avg_conf}%',
        'sides':      'left, right',
        'cameraView': 'OK',
    }

    result = build_result(status, score, summary, stats, metrics, bilateral, coaching)
    result['annotated_frames'] = left.get('annotated_frames', []) + right.get('annotated_frames', [])
    result['per_rep'] = [
        {'rep': i + 1, 'side': r.get('side', 'left'), 'metrics': r}
        for i, r in enumerate(left['per_rep'] + right['per_rep'])
    ]
    return result
