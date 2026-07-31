"""Exercise 4 — Quadruped Rotation / Thread the Needle (T-Spine Rotation).

Camera: Side view, 90° to athlete, hip height
Landmarks: SHOULDER(11/12), HIP(23/24), ELBOW(13/14), WRIST(15/16)

Inputs: 2 videos (left side, right side), 3 reps each.
"""
from utils.landmarks import (
    extract_all_landmarks, get_landmark_px, midpoint_px, LM, confidence_score
)
from utils.angles import (
    angle_3pt, point_to_line_distance, vertical_distance_px, estimate_px_per_cm
)
from utils.rep_detection import detect_reps
from utils.scoring import (
    classify, build_metric, build_bilateral, build_result,
    compute_overall_score, overall_status, generate_coaching_notes
)
from analyzers.frame_helpers import annotate_peak_frame, build_frame_entry, FULL_BODY


def _analyse_side(video_path, side_label):
    """Analyse one side video for quadruped rotation."""
    data = extract_all_landmarks(video_path)
    frames = data['frames']
    fps = data['fps']
    w, h = data['width'], data['height']
    conf = confidence_score(frames)
    px_per_cm = estimate_px_per_cm(h)

    # The rotating arm's elbow: if analysing right side rotation, right elbow moves
    elbow_idx = LM['LEFT_ELBOW'] if side_label == 'left' else LM['RIGHT_ELBOW']
    shoulder_idx = LM['LEFT_SHOULDER'] if side_label == 'left' else LM['RIGHT_SHOULDER']

    # Spine baseline: HIP midpoint → SHOULDER midpoint
    # Compute elbow distance from spine baseline at each frame
    elbow_distances = []
    hip_y_values = []

    for f in frames:
        lm = f['landmarks']
        if lm is None:
            elbow_distances.append(0)
            hip_y_values.append(None)
            continue

        hip_mid = midpoint_px(lm, LM['LEFT_HIP'], LM['RIGHT_HIP'], w, h)
        shoulder_mid = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
        elbow = get_landmark_px(lm, elbow_idx, w, h)

        if hip_mid and shoulder_mid and elbow:
            dist = point_to_line_distance(elbow, hip_mid, shoulder_mid)
            elbow_distances.append(dist if dist is not None else 0)
        else:
            elbow_distances.append(0)

        # Track hip stability
        if hip_mid:
            hip_y_values.append(hip_mid[1])
        else:
            hip_y_values.append(None)

    # Detect 3 reps via peak elbow distance from baseline
    reps = detect_reps(elbow_distances, expected_reps=3, fps=fps, min_hold_sec=0.5)

    # Analyse each rep — scan ALL frames for frame with max elbow-to-baseline distance (spec)
    rep_results = []
    for rep in reps:
        seg_start = rep['start_frame']
        seg_end = min(rep['end_frame'] + 1, len(frames))

        # Find the frame with maximum elbow distance from spine baseline
        max_elbow_dist = 0.0
        best_frame = rep['peak_frame']
        for fi in range(seg_start, seg_end):
            lm = frames[fi]['landmarks']
            if lm is None:
                continue
            hm = midpoint_px(lm, LM['LEFT_HIP'], LM['RIGHT_HIP'], w, h)
            sm = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
            el = get_landmark_px(lm, elbow_idx, w, h)
            if hm and sm and el:
                d = point_to_line_distance(el, hm, sm)
                if d is not None and d > max_elbow_dist:
                    max_elbow_dist = d
                    best_frame = fi

        lm = frames[best_frame]['landmarks'] if best_frame < len(frames) else None
        if lm is None:
            continue

        # Compute rotation angle at the frame of max elbow excursion
        shoulder = get_landmark_px(lm, shoulder_idx, w, h)
        elbow = get_landmark_px(lm, elbow_idx, w, h)
        hip_mid = midpoint_px(lm, LM['LEFT_HIP'], LM['RIGHT_HIP'], w, h)

        rotation_angle = 0.0
        if shoulder and elbow and hip_mid:
            rotation_angle = angle_3pt(hip_mid, shoulder, elbow) or 0.0

        # Hip displacement — measured ONLY across the contiguous loaded
        # region around this rep's true extreme (signal ≥ 50% of peak,
        # unbroken through the peak frame), against the quiet-phase baseline
        # immediately around it. Rep windows can also contain setup motion
        # and other high-signal excursions (reaching into position), which
        # produced 12–19 cm phantom shifts on stable hips.
        seg_sig  = elbow_distances[seg_start:seg_end]
        sig_lo, sig_hi = min(seg_sig), max(seg_sig)
        sig_span = max(sig_hi - sig_lo, 1e-6)

        def _level(fi):
            return (elbow_distances[fi] - sig_lo) / sig_span

        lo_i = best_frame
        while lo_i - 1 >= seg_start and _level(lo_i - 1) >= 0.5:
            lo_i -= 1
        hi_i = best_frame
        while hi_i + 1 < seg_end and _level(hi_i + 1) >= 0.5:
            hi_i += 1

        base_ys = sorted(
            hip_y_values[fi]
            for fi in list(range(seg_start, lo_i)) + list(range(hi_i + 1, seg_end))
            if hip_y_values[fi] is not None and _level(fi) <= 0.4
        )
        base_y = base_ys[len(base_ys) // 2] if base_ys else None

        hip_disp = 0.0
        if base_y is not None:
            for fi in range(lo_i, hi_i + 1):
                if hip_y_values[fi] is None:
                    continue
                d_cm = abs(hip_y_values[fi] - base_y) / px_per_cm if px_per_cm > 0 else abs(hip_y_values[fi] - base_y)
                hip_disp = max(hip_disp, d_cm)

        rep_results.append({
            'rotation_angle': round(rotation_angle, 1),
            'hip_displacement_cm': round(hip_disp, 1),
        })

    valid = [r for r in rep_results if r is not None]
    best_rotation = max((r['rotation_angle'] for r in valid), default=0)
    max_hip_disp = max((r['hip_displacement_cm'] for r in valid), default=0)

    return {
        'side': side_label,
        'best_rotation': round(best_rotation, 1),
        'max_hip_displacement': round(max_hip_disp, 1),
        'valid_reps': len(valid),
        'total_reps': 3,
        'confidence': conf,
        'per_rep': valid,
        'video_path': video_path,
        'frames': frames, 'w': w, 'h': h,
        'reps': reps, 'elbow_idx': elbow_idx, 'shoulder_idx': shoulder_idx,
    }


def analyse(files):
    """Main entry point for Quadruped Rotation analysis."""
    left = _analyse_side(files.get('left', ''), 'left')
    right = _analyse_side(files.get('right', ''), 'right')

    total_valid = left['valid_reps'] + right['valid_reps']
    total_reps = left['total_reps'] + right['total_reps']
    avg_conf = (left['confidence'] + right['confidence']) // 2

    metrics = []

    # Rotation angles
    l_rot_class = classify(left['best_rotation'], 45, 30, higher_is_better=True)
    r_rot_class = classify(right['best_rotation'], 45, 30, higher_is_better=True)
    metrics.append(build_metric('Left Rotation', f"{left['best_rotation']}°",
                                left['best_rotation'], '≥45°', 70, l_rot_class))
    metrics.append(build_metric('Right Rotation', f"{right['best_rotation']}°",
                                right['best_rotation'], '≥45°', 70, r_rot_class))

    # Hip displacement
    l_hip_class = classify(left['max_hip_displacement'], 2, 4, higher_is_better=False)
    r_hip_class = classify(right['max_hip_displacement'], 2, 4, higher_is_better=False)
    metrics.append(build_metric('Left Hip Shift', f"{left['max_hip_displacement']} cm",
                                left['max_hip_displacement'], '<2 cm', 8, l_hip_class))
    metrics.append(build_metric('Right Hip Shift', f"{right['max_hip_displacement']} cm",
                                right['max_hip_displacement'], '<2 cm', 8, r_hip_class))

    bilateral = [
        build_bilateral('Rotation Range', left['best_rotation'], right['best_rotation'], '°', 70),
    ]

    score = compute_overall_score(metrics)
    status = overall_status(score)
    coaching = generate_coaching_notes(metrics, bilateral, 'Quadruped Rotation')

    rot_diff = abs(left['best_rotation'] - right['best_rotation'])
    if rot_diff > 15:
        coaching.insert(0, f"Significant L/R rotation asymmetry of {round(rot_diff, 1)}° — indicates unilateral thoracic restriction.")
    elif rot_diff > 10:
        coaching.insert(0, f"Rotation asymmetry of {round(rot_diff, 1)}° — monitor and address with targeted drills.")

    summary = f"Analysed {total_valid}/{total_reps} reps across both sides."
    if status == 'RESTRICTED':
        summary += " Thoracic rotation significantly limited."
    elif status == 'NEEDS IMPROVEMENT':
        summary += " Partial rotation — focus on thread-the-needle progressions."
    else:
        summary += " Good thoracic rotation range."

    stats = {
        'validReps': f'{total_valid}/{total_reps}',
        'confidence': f'{avg_conf}%',
        'sides': 'left, right',
        'cameraView': 'OK',
    }

    # Generate annotated frames for best rep on each side
    annotated_frames = []
    for side_data in [left, right]:
        side = side_data['side']
        vp = side_data.get('video_path', '')
        frs = side_data.get('frames', [])
        reps_data = side_data.get('reps', [])
        sw, sh = side_data.get('w', 0), side_data.get('h', 0)
        if reps_data and frs:
            best_idx = max(range(len(reps_data)), key=lambda i: side_data['per_rep'][i]['rotation_angle'] if i < len(side_data['per_rep']) else 0) if side_data['per_rep'] else 0
            if best_idx < len(reps_data):
                peak = reps_data[best_idx]['peak_frame']
                lm = frs[peak]['landmarks'] if peak < len(frs) else None
                rd = side_data['per_rep'][best_idx] if best_idx < len(side_data['per_rep']) else {}
                if lm:
                    img = annotate_peak_frame(vp, peak, lm, sw, sh,
                        metric_list=[
                            ('Rotation', f"{rd.get('rotation_angle',0)}°", rd.get('rotation_angle',0) >= 45),
                            ('Hip Shift', f"{rd.get('hip_displacement_cm',0)}cm", rd.get('hip_displacement_cm',0) < 2),
                        ],
                        angle_list=[(side_data['shoulder_idx'],
                                     LM['LEFT_HIP'] if side == 'left' else LM['RIGHT_HIP'],
                                     side_data['elbow_idx'], rd.get('rotation_angle',0), f"Rot: {rd.get('rotation_angle',0)}°")],
                        status=status, score=score, rep_num=best_idx+1, total_reps=len(reps_data), side=side,
                    )
                    entry = build_frame_entry(f"{side.title()} Best Rep", img, best_idx+1, side, True, [f"Rot: {rd.get('rotation_angle',0)}°"])
                    if entry: annotated_frames.append(entry)

    result = build_result(status, score, summary, stats, metrics, bilateral, coaching)
    result['annotated_frames'] = annotated_frames
    # Label each rep with the side it actually came from — the per-rep dicts
    # don't carry a 'side' key, so deriving it from the source list is the
    # only correct option (previously every right-side rep was labelled left).
    per_rep = []
    for i, r in enumerate(left['per_rep']):
        per_rep.append({'rep': i + 1, 'side': 'left', 'metrics': r})
    for i, r in enumerate(right['per_rep']):
        per_rep.append({'rep': len(left['per_rep']) + i + 1, 'side': 'right', 'metrics': r})
    result['per_rep'] = per_rep
    return result
