"""Exercise 6 — Single-Leg Glute Bridge (Glute Activation).

Camera: Side view, 90° to athlete, waist-to-knee frame
Landmarks: SHOULDER(11/12), HIP(23/24), KNEE(25/26), ANKLE(27/28)

Inputs: 2 videos (left leg, right leg), 3 reps + 3s hold each.

Protocol per video (repeated 3×):
  raise hips → hold ~3 s → lower to rest
"""
import math
import numpy as np
from utils.landmarks import (
    extract_all_landmarks, get_landmark_px, LM, confidence_score
)
from utils.angles import angle_3pt, estimate_px_per_cm
from utils.rep_detection import detect_reps
from utils.scoring import (
    classify, build_metric, build_bilateral, build_result,
    compute_overall_score, overall_status, generate_coaching_notes
)
from analyzers.frame_helpers import annotate_peak_frame, build_frame_entry, LOWER_BODY


# ─────────────────────────────────────────────────────────────
# Per-side analysis
# ─────────────────────────────────────────────────────────────

def _analyse_side(video_path, side_label):
    """Analyse one side video.

    For each of the 3 reps:
      1. Find the frame with the maximum hip extension angle (true peak).
      2. Define a hold window from the peak frame for up to 3 seconds
         (clamped to the rep segment so it doesn't bleed into the rest).
      3. Compute hold stability as SD of all hip-extension angles in that window.
      4. Compute pelvic drop and rotation as the maximum bilateral hip
         Y-difference / tilt over that same hold window.
    """
    data = extract_all_landmarks(video_path)
    frames = data['frames']
    fps    = data['fps']
    w, h   = data['width'], data['height']
    conf   = confidence_score(frames)
    px_per_cm = estimate_px_per_cm(h)

    # Side-view: pick the near-side landmarks
    shoulder_idx = LM['LEFT_SHOULDER'] if side_label == 'left' else LM['RIGHT_SHOULDER']
    hip_idx      = LM['LEFT_HIP']      if side_label == 'left' else LM['RIGHT_HIP']
    knee_idx     = LM['LEFT_KNEE']     if side_label == 'left' else LM['RIGHT_KNEE']

    # ── Build angle series ──────────────────────────────────
    hip_angles = []
    for f in frames:
        lm = f['landmarks']
        if lm is None:
            hip_angles.append(0.0)
            continue
        shoulder = get_landmark_px(lm, shoulder_idx, w, h)
        hip      = get_landmark_px(lm, hip_idx,      w, h)
        knee     = get_landmark_px(lm, knee_idx,     w, h)
        ang = angle_3pt(shoulder, hip, knee)
        hip_angles.append(ang if ang is not None else 0.0)

    # ── Detect 3 rep peaks ──────────────────────────────────
    # min_hold_sec=1.0 ensures peaks are at least 2 s apart.
    reps = detect_reps(hip_angles, expected_reps=3, fps=fps, min_hold_sec=1.0)

    rep_results  = []  # final per-rep data
    frames_to_annotate = []  # (rep_num, peak_frame, metrics_dict)

    for rep_i, rep in enumerate(reps):
        seg_start = rep['start_frame']
        seg_end   = min(rep['end_frame'] + 1, len(frames))

        # ── True peak frame within segment ──────────────────
        best_angle = 0.0
        best_frame = rep['peak_frame']
        for fi in range(seg_start, seg_end):
            if hip_angles[fi] > best_angle:
                best_angle = hip_angles[fi]
                best_frame = fi

        peak       = best_frame
        peak_angle = best_angle

        # ── Hold window: the actual held plateau — frames in this rep where
        # the hip angle stays within 5° of the rep's peak. A fixed
        # peak→+3 s window bled into the lowering phase and inflated the
        # stability SD several-fold on clean holds.
        hold_frames_idx = [fi for fi in range(seg_start, seg_end)
                           if hip_angles[fi] >= peak_angle - 5.0]
        if not hold_frames_idx:
            hold_frames_idx = [peak]
        hold_start = hold_frames_idx[0]
        hold_end   = hold_frames_idx[-1] + 1

        # ── Hold stability: SD of angles across the plateau ──
        hold_angles = [hip_angles[fi] for fi in hold_frames_idx if hip_angles[fi] > 0]
        hold_sd = float(np.std(hold_angles)) if len(hold_angles) > 1 else 0.0

        # ── Pelvic drop & rotation over the hold window ─────
        # Both need a REAL bilateral hip line. This is a side-view exercise:
        # when the two hip landmarks nearly coincide (separation below 15%
        # of torso length), the line's angle/gap is pure noise (it read
        # 87–90° "rotation" on stable pelvises) — mark unmeasurable instead.
        pelvic_drops     = []
        pelvic_rotations = []
        for fi in hold_frames_idx:
            lm = frames[fi]['landmarks']
            if lm is None:
                continue
            hip_l = get_landmark_px(lm, LM['LEFT_HIP'],  w, h)
            hip_r = get_landmark_px(lm, LM['RIGHT_HIP'], w, h)
            sh    = get_landmark_px(lm, shoulder_idx, w, h)
            hp    = get_landmark_px(lm, hip_idx, w, h)
            if not (hip_l and hip_r):
                continue
            hip_sep = math.hypot(hip_r[0] - hip_l[0], hip_r[1] - hip_l[1])
            torso   = math.hypot(sh[0] - hp[0], sh[1] - hp[1]) if (sh and hp) else 0.0
            if hip_sep < max(0.15 * torso, 12.0):
                continue                      # side-on: line is degenerate
            # Pelvic drop: vertical pixel gap → cm
            drop_px = abs(hip_l[1] - hip_r[1])
            drop_cm = drop_px / px_per_cm if px_per_cm > 0 else 0.0
            pelvic_drops.append(drop_cm)

            # Pelvic rotation: tilt of hip line from horizontal
            dx = hip_r[0] - hip_l[0]
            dy = hip_r[1] - hip_l[1]
            angle_h = math.degrees(math.atan2(dy, dx)) if (dx != 0 or dy != 0) else 0.0
            tilt = abs(angle_h)
            if tilt > 90:
                tilt = 180 - tilt
            pelvic_rotations.append(tilt)

        max_drop     = max(pelvic_drops)     if pelvic_drops     else None
        max_rotation = max(pelvic_rotations) if pelvic_rotations else None

        result = {
            'rep_num':        rep_i + 1,
            'peak_angle':     round(peak_angle, 1),
            'hold_sd':        round(hold_sd,    1),
            'pelvic_drop_cm': round(max_drop,   1) if max_drop     is not None else None,
            'pelvic_rotation':round(max_rotation, 1) if max_rotation is not None else None,
            'hold_sec':       round(len(hold_frames_idx) / fps, 1) if fps > 0 else 0.0,
            'peak_frame':     peak,
        }
        rep_results.append(result)
        frames_to_annotate.append(result)

    # ── Aggregate ────────────────────────────────────────────
    best_angle   = max((r['peak_angle']     for r in rep_results), default=0.0)
    avg_hold_sd  = (sum(r['hold_sd']        for r in rep_results) / len(rep_results)
                    if rep_results else 0.0)
    drops = [r['pelvic_drop_cm']  for r in rep_results if r['pelvic_drop_cm']  is not None]
    rots  = [r['pelvic_rotation'] for r in rep_results if r['pelvic_rotation'] is not None]
    max_drop     = max(drops) if drops else None
    max_rotation = max(rots)  if rots  else None

    return {
        'side':              side_label,
        'best_angle':        round(best_angle,   1),
        'avg_hold_sd':       round(avg_hold_sd,  1),
        'max_pelvic_drop':   round(max_drop,     1) if max_drop     is not None else None,
        'max_pelvic_rotation': round(max_rotation, 1) if max_rotation is not None else None,
        'valid_reps':        len(rep_results),
        'total_reps':        3,
        'confidence':        conf,
        'per_rep':           rep_results,
        'frames_to_annotate': frames_to_annotate,
        # Raw data for annotation
        'video_path':    video_path,
        'frames_data':   frames,
        'w': w, 'h': h, 'fps': fps,
        'shoulder_idx':  shoulder_idx,
        'hip_idx':       hip_idx,
        'knee_idx':      knee_idx,
    }


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def analyse(files):
    """Main entry point for Single-Leg Glute Bridge analysis."""
    left  = _analyse_side(files.get('left',  ''), 'left')
    right = _analyse_side(files.get('right', ''), 'right')

    total_valid = left['valid_reps'] + right['valid_reps']
    total_reps  = left['total_reps'] + right['total_reps']
    avg_conf    = (left['confidence'] + right['confidence']) // 2

    # ── Metrics ──────────────────────────────────────────────
    metrics = []

    # Hip extension (GOOD ≥ 170°, NEEDS 160–170°, RESTRICTED < 160°)
    l_ext_class = classify(left['best_angle'],  170, 160, higher_is_better=True)
    r_ext_class = classify(right['best_angle'], 170, 160, higher_is_better=True)
    metrics.append(build_metric('Left Hip Extension',  f"{left['best_angle']}°",
                                left['best_angle'],  '≥170°', 185, l_ext_class))
    metrics.append(build_metric('Right Hip Extension', f"{right['best_angle']}°",
                                right['best_angle'], '≥170°', 185, r_ext_class))

    # Hold stability — SD (GOOD < 2°, NEEDS 2–5°, RESTRICTED > 5°)
    l_hold_class = classify(left['avg_hold_sd'],  2, 5, higher_is_better=False)
    r_hold_class = classify(right['avg_hold_sd'], 2, 5, higher_is_better=False)
    metrics.append(build_metric('Left Hold Stability',  f"{left['avg_hold_sd']}° SD",
                                left['avg_hold_sd'],  '<2° SD', 10, l_hold_class))
    metrics.append(build_metric('Right Hold Stability', f"{right['avg_hold_sd']}° SD",
                                right['avg_hold_sd'], '<2° SD', 10, r_hold_class))

    # Pelvic drop / rotation — only when the camera could actually see a
    # bilateral hip line (mostly-frontal framing). From a pure side view
    # these are unmeasurable; omitting beats reporting noise.
    pelvis_measurable = (left['max_pelvic_drop'] is not None or
                         right['max_pelvic_drop'] is not None)
    if pelvis_measurable:
        l_drop = left['max_pelvic_drop']  if left['max_pelvic_drop']  is not None else 0.0
        r_drop = right['max_pelvic_drop'] if right['max_pelvic_drop'] is not None else 0.0
        metrics.append(build_metric('Left Pelvic Drop',  f"{l_drop} cm",
                                    l_drop,  '<1 cm', 5, classify(l_drop, 1, 2, higher_is_better=False)))
        metrics.append(build_metric('Right Pelvic Drop', f"{r_drop} cm",
                                    r_drop, '<1 cm', 5, classify(r_drop, 1, 2, higher_is_better=False)))
        l_rot = left['max_pelvic_rotation']  if left['max_pelvic_rotation']  is not None else 0.0
        r_rot = right['max_pelvic_rotation'] if right['max_pelvic_rotation'] is not None else 0.0
        metrics.append(build_metric('Left Pelvic Rotation',  f"{l_rot}°",
                                    l_rot,  '<3°', 15, classify(l_rot, 3, 5, higher_is_better=False)))
        metrics.append(build_metric('Right Pelvic Rotation', f"{r_rot}°",
                                    r_rot, '<3°', 15, classify(r_rot, 3, 5, higher_is_better=False)))

    # ── Bilateral ─────────────────────────────────────────────
    bilateral = [
        build_bilateral('Hip Extension',    left['best_angle'],        right['best_angle'],        '°',  185),
        build_bilateral('Hold Stability',   left['avg_hold_sd'],       right['avg_hold_sd'],       '° SD', 10),
    ]
    if pelvis_measurable:
        bilateral.append(build_bilateral(
            'Pelvic Drop',
            left['max_pelvic_drop']  if left['max_pelvic_drop']  is not None else 0.0,
            right['max_pelvic_drop'] if right['max_pelvic_drop'] is not None else 0.0,
            ' cm', 5))

    score  = compute_overall_score(metrics)
    status = overall_status(score)
    coaching = generate_coaching_notes(metrics, bilateral, 'Single-Leg Glute Bridge')

    # Bilateral symmetry flag
    ext_diff = abs(left['best_angle'] - right['best_angle'])
    if ext_diff > 10:
        worse = 'left' if left['best_angle'] < right['best_angle'] else 'right'
        coaching.insert(0,
            f"Hip extension asymmetry of {round(ext_diff, 1)}° detected — "
            f"prioritise {worse} side glute activation.")

    summary = f"Analysed {total_valid}/{total_reps} reps across both sides."
    if status == 'GOOD':
        summary += " Strong glute bridge performance with stable holds."
    elif status == 'NEEDS IMPROVEMENT':
        summary += " Moderate glute strength — focus on hold stability and pelvic control."
    else:
        summary += " Glute activation deficit detected."

    stats = {
        'validReps':  f'{total_valid}/{total_reps}',
        'confidence': f'{avg_conf}%',
        'sides':      'left, right',
        'cameraView': 'OK',
        'passRate':   f'{sum(1 for m in metrics if m["status"] == "good")}/{len(metrics)}',
    }

    # ── Annotated frames — ALL reps for both sides ────────────
    annotated_frames = []
    for sd in [left, right]:
        side        = sd['side']
        vp          = sd['video_path']
        frs         = sd['frames_data']
        sw, sh      = sd['w'], sd['h']
        best_a      = sd['best_angle']

        for rd in sd['frames_to_annotate']:
            pk = rd['peak_frame']
            if pk >= len(frs):
                continue
            lm = frs[pk]['landmarks']
            if lm is None:
                continue

            rep_num = rd['rep_num']
            ang     = rd['peak_angle']
            sd_val  = rd['hold_sd']
            drop    = rd['pelvic_drop_cm']
            rot     = rd['pelvic_rotation']
            hold_s  = rd.get('hold_sec', 0.0)
            is_best = (ang == best_a)

            overlay = [
                ('Hip Extension', f"{ang}°",    ang  >= 170),
                ('Hold',          f"{hold_s}s", hold_s >= 2),
                ('Hold SD',       f"{sd_val}°", sd_val < 2),
            ]
            shown = [f"Ext: {ang}°", f"SD: {sd_val}°", f"Hold: {hold_s}s"]
            if drop is not None:
                overlay.append(('Pelvic Drop', f"{drop} cm", drop < 1))
                shown.append(f"Drop: {drop}cm")
            if rot is not None:
                overlay.append(('Pelv. Rot.', f"{rot}°", rot < 3))
                shown.append(f"Rot: {rot}°")

            img = annotate_peak_frame(
                vp, pk, lm, sw, sh,
                metric_list=overlay,
                angle_list=[
                    (sd['hip_idx'], sd['shoulder_idx'], sd['knee_idx'],
                     ang, f"Ext: {ang}°"),
                ],
                status=status, score=score,
                rep_num=rep_num, total_reps=len(sd['frames_to_annotate']),
                side=side,
                connections=LOWER_BODY,
            )
            entry = build_frame_entry(
                f"{side.title()} — Rep {rep_num}" + (" (Best)" if is_best else ""),
                img, rep_num, side, is_best,
                shown,
            )
            if entry:
                annotated_frames.append(entry)

    result = build_result(status, score, summary, stats, metrics, bilateral, coaching)
    result['annotated_frames'] = annotated_frames
    result['per_rep'] = (
        [{'rep': r['rep_num'], 'side': 'left',  'metrics': r} for r in left['per_rep']] +
        [{'rep': r['rep_num'], 'side': 'right', 'metrics': r} for r in right['per_rep']]
    )
    return result
