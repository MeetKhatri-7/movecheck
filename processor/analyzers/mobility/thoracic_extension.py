"""Exercise 3 — Thoracic Foam Roller Extension (T-Spine Extension).

Camera: Side view, 90° to athlete, torso height
Landmarks: SHOULDER(11/12), HIP(23/24), EAR(7/8), KNEE(25/26)

Inputs: 1 video, 1 hold of 30 sec.
"""
from utils.landmarks import (
    extract_all_landmarks, get_landmark_px, LM, confidence_score
)
from utils.angles import angle_to_horizontal, vertical_distance_px
from utils.rep_detection import detect_holds, moving_average
from utils.scoring import (
    classify, build_metric, build_result,
    compute_overall_score, overall_status, generate_coaching_notes
)
from analyzers.frame_helpers import annotate_peak_frame, build_frame_entry, UPPER_BODY


def analyse(files):
    """Main entry point for Thoracic Extension analysis."""
    video_path = files.get('all', '') or list(files.values())[0]
    data = extract_all_landmarks(video_path)
    frames = data['frames']
    fps = data['fps']
    w, h = data['width'], data['height']
    conf = confidence_score(frames)

    # Use visible side's landmarks (both are tracked, use midpoint or best)
    shoulder_l, shoulder_r = LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER']
    hip_l, hip_r = LM['LEFT_HIP'], LM['RIGHT_HIP']
    ear_l, ear_r = LM['LEFT_EAR'], LM['RIGHT_EAR']

    # Compute shoulder-to-hip angle relative to horizontal at each frame.
    # Clinical convention: negative angle = shoulders physically below hip line = good extension.
    # In image coords (Y increases downward):
    #   shoulder physically below hip → shoulder.y > hip.y
    #   angle_to_horizontal(shoulder, hip) = atan2(hip.y - shoulder.y, hip.x - shoulder.x)
    angle_values = []     # actual degrees, positive = shoulder above hip, negative = shoulder below hip
    arch_values = []      # signed shoulder→ear angle off the torso axis (head release)
    ear_below_shoulder = []

    for i, f in enumerate(frames):
        lm = f['landmarks']
        if lm is None:
            angle_values.append(None)
            ear_below_shoulder.append(False)
            continue

        s_l = get_landmark_px(lm, shoulder_l, w, h)
        s_r = get_landmark_px(lm, shoulder_r, w, h)
        shoulder = s_l or s_r
        if s_l and s_r:
            shoulder = ((s_l[0]+s_r[0])/2, (s_l[1]+s_r[1])/2)

        h_l = get_landmark_px(lm, hip_l, w, h)
        h_r = get_landmark_px(lm, hip_r, w, h)
        hip = h_l or h_r
        if h_l and h_r:
            hip = ((h_l[0]+h_r[0])/2, (h_l[1]+h_r[1])/2)

        e_l = get_landmark_px(lm, ear_l, w, h)
        e_r = get_landmark_px(lm, ear_r, w, h)
        ear = e_l or e_r
        if e_l and e_r:
            ear = ((e_l[0]+e_r[0])/2, (e_l[1]+e_r[1])/2)

        if shoulder and hip:
            import math
            # Direction-independent angle relative to horizontal
            # Positive angle = shoulder above hip
            # Negative angle = shoulder below hip (good extension)
            dx = abs(shoulder[0] - hip[0])
            dy = hip[1] - shoulder[1]
            ang = math.degrees(math.atan2(dy, dx))
            angle_values.append(ang)
        else:
            angle_values.append(None)

        # Head-arch angle: signed angle of the shoulder→ear vector off the
        # shoulder→hip torso axis. This is where most of the visible motion
        # of a roller extension lives — the head releasing back — while the
        # shoulder-hip line itself only tilts a few degrees.
        if ear and shoulder and hip:
            import math
            ax, ay = hip[0] - shoulder[0], hip[1] - shoulder[1]
            ex, ey = ear[0] - shoulder[0], ear[1] - shoulder[1]
            dot   = ax * ex + ay * ey
            cross = ax * ey - ay * ex
            # Unsigned angle (0..180): the signed version wraps at ±180
            # right where the ear sits (opposite the hip), which made the
            # p90−p10 excursion read ~346°.
            arch_values.append(abs(math.degrees(math.atan2(cross, dot))))
        else:
            arch_values.append(None)

        if ear and shoulder:
            ear_below_shoulder.append(ear[1] >= shoulder[1])
        else:
            ear_below_shoulder.append(False)

    valid_angles = [a for a in angle_values if a is not None]
    if not valid_angles:
        return _empty_result(conf)

    # Peak extension = minimum of the SMOOTHED angle series. A raw global
    # minimum is set by a single jitter frame, which then poisons both the
    # reported angle and the hold-segment threshold anchored to it.
    smoothed_angles = moving_average(angle_values, max(int(fps * 0.3), 3))
    smoothed_valid = [(i, a) for i, a in enumerate(smoothed_angles) if a is not None]
    max_extension_idx, best_angle = min(smoothed_valid, key=lambda t: t[1])

    # The extension METRIC is the observed ROM: the excursion between the
    # resting arch (upper envelope of the smoothed series — 90th percentile,
    # robust to a brief sit-up at the ends) and the deepest extension. An
    # absolute "shoulders below hips" angle depends entirely on roller
    # height and camera line — it graded honest extensions as RESTRICTED —
    # and a first-seconds baseline fails when the athlete starts the clip
    # already moving.
    sorted_smoothed = sorted(a for a in smoothed_angles if a is not None)
    baseline_angle = sorted_smoothed[int(len(sorted_smoothed) * 0.90)] \
        if sorted_smoothed else best_angle
    torso_rom = max(0.0, baseline_angle - best_angle)

    # Head-arch ROM — excursion of the shoulder→ear angle off the torso
    # axis (robust p90 − p10 of the smoothed series). The total extension
    # ROM combines the small torso-line tilt with the much larger head
    # release that the roller extension actually produces.
    arch_rom = 0.0
    smoothed_arch = moving_average(arch_values, max(int(fps * 0.3), 3))
    arch_sorted = sorted(a for a in smoothed_arch if a is not None)
    if len(arch_sorted) >= 10:
        arch_rom = max(0.0, arch_sorted[int(len(arch_sorted) * 0.90)] -
                            arch_sorted[int(len(arch_sorted) * 0.10)])
    extension_rom = torso_rom + arch_rom

    # Detect the longest contiguous segment where angle is within 10 degrees of best_angle
    threshold_angle = best_angle + 10.0
    longest_hold_start = 0
    longest_hold_end = 0
    current_start = -1

    for i, ang in enumerate(smoothed_angles):
        if ang is not None and ang <= threshold_angle:
            if current_start == -1:
                current_start = i
        else:
            if current_start != -1:
                if (i - current_start) > (longest_hold_end - longest_hold_start):
                    longest_hold_start = current_start
                    longest_hold_end = i
                current_start = -1
                
    if current_start != -1 and (len(angle_values) - current_start) > (longest_hold_end - longest_hold_start):
        longest_hold_start = current_start
        longest_hold_end = len(angle_values)

    hold_duration_sec = (longest_hold_end - longest_hold_start) / fps

    # Secondary metrics — measured only over DEEP-extension frames (within
    # 5° of peak): head relaxation and hip stillness matter at end range,
    # not during the rests between excursions.
    deep_idx = [i for i, a in enumerate(smoothed_angles)
                if a is not None and a <= best_angle + 5.0]
    if deep_idx:
        head_drop_frames = sum(1 for i in deep_idx if ear_below_shoulder[i])
        head_drop_pct = head_drop_frames / len(deep_idx) * 100

        hip_y_values = []
        for i in deep_idx:
            lm = frames[i]['landmarks']
            if not lm: continue
            h_l = get_landmark_px(lm, hip_l, w, h)
            h_r = get_landmark_px(lm, hip_r, w, h)
            if h_l and h_r:
                hip_y_values.append((h_l[1]+h_r[1])/2)

        if len(hip_y_values) > 2:
            import numpy as np
            # Detrend so slow, legitimate repositioning between excursions
            # doesn't read as instability — only residual jitter counts.
            trend = moving_average(hip_y_values, max(int(fps * 1.0), 3))
            resid = [y - t for y, t in zip(hip_y_values, trend) if t is not None]
            hip_stability = float(np.std(resid)) if len(resid) > 2 else 0
        else:
            hip_stability = 0
    else:
        head_drop_pct = 0
        hip_stability = 0

    # Scoring — extension ROM from the athlete's own baseline
    if extension_rom >= 15:
        ext_class = 'GOOD'
    elif extension_rom >= 8:
        ext_class = 'NEEDS IMPROVEMENT'
    else:
        ext_class = 'RESTRICTED'

    head_class = classify(head_drop_pct, 70, 30, higher_is_better=True)
    hold_class = classify(hold_duration_sec, 30, 20, higher_is_better=True)
    hip_class = classify(hip_stability, 5, 15, higher_is_better=False)

    metrics = [
        build_metric('Extension ROM', f"{round(extension_rom, 1)}°",
                     extension_rom, '≥15°', 45, ext_class),
        build_metric('Head Drop', f"{round(head_drop_pct, 0)}%",
                     head_drop_pct, '≥70%', 100, head_class),
        build_metric('Hold Duration', f"{round(hold_duration_sec, 1)} s",
                     hold_duration_sec, '≥30s', 35, hold_class),
        build_metric('Hip Stability', f"{round(hip_stability, 1)} px",
                     hip_stability, '<5 px SD', 30, hip_class),
    ]

    score = compute_overall_score(metrics)
    status = overall_status(score)
    coaching = generate_coaching_notes(metrics, [], 'Thoracic Foam Roller Extension')

    summary = f"Thoracic extension analysis complete."
    if status == 'RESTRICTED':
        summary += " Significant restriction — mid-back stiffness likely limiting overhead mechanics."
    elif status == 'NEEDS IMPROVEMENT':
        summary += " Partial extension achieved — focus on progressive foam roller drills."
    else:
        summary += " Good thoracic extension mobility."

    stats = {
        'validReps': '1/1',
        'confidence': f'{conf}%',
        'sides': 'n/a',
        'cameraView': 'OK',
    }

    # Annotated frame at peak extension
    annotated_frames = []
    peak_lm = frames[max_extension_idx]['landmarks'] if max_extension_idx < len(frames) else None
    if peak_lm:
        img = annotate_peak_frame(
            video_path, max_extension_idx, peak_lm, w, h,
            metric_list=[
                ('Extension ROM', f"{round(extension_rom,1)}°", ext_class == 'GOOD'),
                ('Head Drop', f"{round(head_drop_pct,0)}%", head_class == 'GOOD'),
                ('Hold', f"{round(hold_duration_sec,1)}s", hold_class == 'GOOD'),
                ('Hip Stable', f"{round(hip_stability,1)}px SD", hip_class == 'GOOD'),
            ],
            angle_list=[(LM['LEFT_SHOULDER'], LM['LEFT_HIP'], LM['LEFT_EAR'], round(extension_rom, 1), f"ROM: {round(extension_rom,1)}°")],
            status=status, score=score,
            rep_num=1, total_reps=1, connections=UPPER_BODY,
        )
        entry = build_frame_entry('Peak Extension', img, 1, 'center', True, [f"ROM: {round(extension_rom,1)}°"])
        if entry: annotated_frames.append(entry)

    result = build_result(status, score, summary, stats, metrics, [], coaching)
    result['annotated_frames'] = annotated_frames
    return result


def _empty_result(conf):
    """Return an empty result if no landmarks detected."""
    return build_result('RESTRICTED', 0, 'Could not detect pose landmarks in the video.',
                        {'validReps': '0/1', 'confidence': f'{conf}%', 'sides': 'n/a', 'cameraView': 'POOR'},
                        [], [], ['Ensure the camera captures your full torso from the side.'])
