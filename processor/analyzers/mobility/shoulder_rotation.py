"""Exercise 5 — 90/90 Shoulder Rotation Test (Shoulder IR/ER).

Camera: Axial view — at foot of plinth looking down humeral long axis
Landmarks: SHOULDER(11/12), ELBOW(13/14), WRIST(15/16), HIP(23/24)

Inputs: 2 videos (left shoulder, right shoulder), 3 reps each.

Rep protocol per video (user-specified):
  IR → neutral → ER → neutral → IR → neutral → ER → neutral → IR → neutral → ER
  = 6 rotations total: 3 IR and 3 ER, alternating, IR first.
  We use temporal order to assign IR/ER without relying on sign convention.
"""
import math
import numpy as np
from utils.landmarks import (
    extract_all_landmarks, get_landmark_px, midpoint_px, LM, confidence_score
)
from utils.angles import angle_3pt, estimate_px_per_cm
from utils.rep_detection import detect_reps
from utils.scoring import (
    classify, classify_range, build_metric, build_bilateral, build_result,
    compute_overall_score, overall_status, generate_coaching_notes
)
from analyzers.frame_helpers import annotate_peak_frame, build_frame_entry, UPPER_BODY


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _forearm_angle(elbow_px, wrist_px):
    """Angle of the elbow→wrist vector from the upward vertical.

    Returns 0° when wrist is directly above elbow (neutral 90/90 setup).
    Positive = wrist to the right; negative = wrist to the left.
    Range: −180° to +180°.
    """
    if elbow_px is None or wrist_px is None:
        return None
    dx = wrist_px[0] - elbow_px[0]
    dy = -(wrist_px[1] - elbow_px[1])  # flip Y: positive = upward in physical space
    return math.degrees(math.atan2(dx, dy))


def _count_valid_frames(frames, elbow_i, wrist_i, w, h):
    """Count frames where both elbow and wrist are detected above threshold."""
    count = 0
    for f in frames:
        lm = f['landmarks']
        if lm and get_landmark_px(lm, elbow_i, w, h) and get_landmark_px(lm, wrist_i, w, h):
            count += 1
    return count


def _select_arm_landmarks(frames, side_label, w, h):
    """Choose elbow/wrist/shoulder indices with best landmark visibility.

    In axial view, MediaPipe sometimes labels the tested arm's landmarks
    under the opposite side (model isn't calibrated for end-on views).
    Try both sides and use whichever has more valid frames.
    """
    preferred = (
        (LM['LEFT_ELBOW'],  LM['LEFT_WRIST'],  LM['LEFT_SHOULDER'])
        if side_label == 'left'
        else (LM['RIGHT_ELBOW'], LM['RIGHT_WRIST'], LM['RIGHT_SHOULDER'])
    )
    opposite = (
        (LM['RIGHT_ELBOW'], LM['RIGHT_WRIST'], LM['RIGHT_SHOULDER'])
        if side_label == 'left'
        else (LM['LEFT_ELBOW'],  LM['LEFT_WRIST'],  LM['LEFT_SHOULDER'])
    )

    preferred_count = _count_valid_frames(frames, preferred[0], preferred[1], w, h)
    opposite_count  = _count_valid_frames(frames, opposite[0],  opposite[1],  w, h)

    # Use opposite side if it has substantially more valid frames (>20% more)
    if opposite_count > preferred_count * 1.2:
        return opposite
    return preferred


def _fill_gaps(values, fallback=0.0):
    """Forward-fill None values with the last valid value."""
    result = list(values)
    last = fallback
    for i, v in enumerate(result):
        if v is not None:
            last = v
        else:
            result[i] = last
    return result


def _scan_segment_for_peak(deviation, seg_start, seg_end):
    """Return (max_abs_deviation, frame_of_max) within a rep segment."""
    best_abs = 0.0
    best_frame = seg_start
    for fi in range(seg_start, min(seg_end, len(deviation))):
        a = abs(deviation[fi])
        if a > best_abs:
            best_abs = a
            best_frame = fi
    return best_abs, best_frame


# ─────────────────────────────────────────────────────────────
# Per-side analysis
# ─────────────────────────────────────────────────────────────

def _analyse_side(video_path, side_label):
    """Analyse one shoulder video (left or right) for IR/ER.

    Rep protocol: IR → neutral → ER → neutral × 3  (6 movements).
    Temporal assignment: peaks 1,3,5 = IR;  peaks 2,4,6 = ER.
    This avoids unreliable sign-based direction detection in axial view.
    """
    if not video_path:
        return _empty_side(side_label)

    data = extract_all_landmarks(video_path)
    frames = data['frames']
    fps   = data['fps']
    w, h  = data['width'], data['height']
    conf  = confidence_score(frames)
    px_per_cm = estimate_px_per_cm(h)

    # ── Landmark selection ──────────────────────────────────
    elbow_idx, wrist_idx, shoulder_idx = _select_arm_landmarks(frames, side_label, w, h)

    # ── Build forearm angle series ───────────────────────────
    raw_angles = []
    compensation_frames = 0

    for f in frames:
        lm = f['landmarks']
        if lm is None:
            raw_angles.append(None)
            continue

        elbow   = get_landmark_px(lm, elbow_idx,   w, h)
        wrist   = get_landmark_px(lm, wrist_idx,   w, h)

        if elbow and wrist:
            raw_angles.append(_forearm_angle(elbow, wrist))
        else:
            raw_angles.append(None)

        # Compensation: trunk roll (bilateral shoulder tilt > 5°)
        sl = get_landmark_px(lm, LM['LEFT_SHOULDER'],  w, h)
        sr = get_landmark_px(lm, LM['RIGHT_SHOULDER'], w, h)
        if sl and sr:
            tilt_deg = abs(math.degrees(math.atan2(sr[1] - sl[1], sr[0] - sl[0])))
            if tilt_deg > 5:
                compensation_frames += 1

    angle_series = _fill_gaps(raw_angles)

    # ── Deviation from neutral ───────────────────────────────
    # The forearm-from-vertical angle is SELF-REFERENCING: 0° IS the true
    # 90/90 neutral (wrist directly above elbow) by definition. Measuring a
    # "rest" window instead broke both sample videos — one starts mid-
    # movement (rest read 23°), the other holds a non-neutral setup (−48°),
    # which inflated a 75° rotation into a reported 122°.
    deviation = list(angle_series)

    # ── Detect all 6 rotation peaks ─────────────────────────
    # Each IR and ER movement produces one peak in |deviation|.
    abs_dev = [abs(d) for d in deviation]
    reps_raw = detect_reps(abs_dev, expected_reps=6, fps=fps, min_hold_sec=0.3)

    # Keep at most 6, sorted by time
    reps_sorted = sorted(reps_raw, key=lambda r: r['peak_frame'])
    if len(reps_sorted) > 6:
        # Keep the 6 largest peaks
        reps_sorted = sorted(reps_sorted, key=lambda r: r['peak_value'], reverse=True)[:6]
        reps_sorted = sorted(reps_sorted, key=lambda r: r['peak_frame'])

    # ── Assign IR/ER anatomically per peak ───────────────────
    # At the ER extreme the forearm lies back toward the HEAD (overhead);
    # at the IR extreme it rotates down toward the HIP. Comparing the
    # wrist's distance to head vs hip at the true extreme classifies each
    # peak regardless of camera orientation or which direction came first
    # (the old fixed IR-first alternation mislabeled videos that started
    # with ER or repeated a direction).
    ir_peaks = []   # list of (angle, frame_idx)
    er_peaks = []

    def _peak_direction(frame_idx):
        lm = frames[frame_idx]['landmarks'] if frame_idx < len(frames) else None
        if lm is None:
            return None
        wrist = get_landmark_px(lm, wrist_idx, w, h)
        head  = get_landmark_px(lm, LM['NOSE'], w, h) or \
                get_landmark_px(lm, LM['LEFT_EAR'], w, h) or \
                get_landmark_px(lm, LM['RIGHT_EAR'], w, h)
        hip   = midpoint_px(lm, LM['LEFT_HIP'], LM['RIGHT_HIP'], w, h)
        if not (wrist and head and hip):
            return None
        d_head = math.hypot(wrist[0]-head[0], wrist[1]-head[1])
        d_hip  = math.hypot(wrist[0]-hip[0],  wrist[1]-hip[1])
        return 'ER' if d_head < d_hip else 'IR'

    rep_details = []
    sign_dirs = {}   # sign → direction votes, fallback for ambiguous peaks
    for i, rep in enumerate(reps_sorted):
        seg_start = rep['start_frame']
        seg_end   = rep['end_frame'] + 1
        # Scan the full segment for the true maximum deviation
        peak_angle, peak_frame = _scan_segment_for_peak(deviation, seg_start, seg_end)

        if peak_angle < 15:         # ignore noise / setup wobble
            continue

        direction = _peak_direction(peak_frame)
        sign = 1 if deviation[peak_frame] >= 0 else -1
        if direction is None:
            # Fall back to the direction other peaks of this sign resolved to
            votes = sign_dirs.get(sign, {})
            direction = max(votes, key=votes.get) if votes else ('IR' if i % 2 == 0 else 'ER')
        else:
            sign_dirs.setdefault(sign, {}).setdefault(direction, 0)
            sign_dirs[sign][direction] += 1

        if direction == 'IR':
            ir_peaks.append((peak_angle, peak_frame))
            rep_num = len(ir_peaks)
        else:
            er_peaks.append((peak_angle, peak_frame))
            rep_num = len(er_peaks)

        rep_details.append({
            'rep_num': rep_num,
            'direction': direction,
            'peak_frame': peak_frame,
            'angle': round(peak_angle, 1),
        })

    # ── Aggregate ────────────────────────────────────────────
    peak_ir = max((a for a, _ in ir_peaks), default=0.0)
    peak_er = max((a for a, _ in er_peaks), default=0.0)
    trm     = peak_ir + peak_er

    # Frame indices for the best IR and best ER (for annotation)
    best_ir_frame = max(ir_peaks, key=lambda x: x[0])[1] if ir_peaks else None
    best_er_frame = max(er_peaks, key=lambda x: x[0])[1] if er_peaks else None

    valid_ir = len(ir_peaks)
    valid_er = len(er_peaks)
    comp_pct = round(compensation_frames / max(len(frames), 1) * 100)

    return {
        'side': side_label,
        'peak_er':  round(peak_er,  1),
        'peak_ir':  round(peak_ir,  1),
        'trm':      round(trm,       1),
        'valid_ir': valid_ir,
        'valid_er': valid_er,
        'valid_reps': valid_ir + valid_er,
        'total_reps': 6,
        'compensation_pct': comp_pct,
        'confidence': conf,
        'per_rep':   rep_details,
        'ir_per_rep': [round(a, 1) for a, _ in ir_peaks],
        'er_per_rep': [round(a, 1) for a, _ in er_peaks],
        # Carry forward for annotation
        'video_path':    video_path,
        'frames':        frames,
        'w': w, 'h': h,
        'elbow_idx':     elbow_idx,
        'wrist_idx':     wrist_idx,
        'shoulder_idx':  shoulder_idx,
        'best_ir_frame': best_ir_frame,
        'best_er_frame': best_er_frame,
    }


def _empty_side(side_label):
    return {
        'side': side_label,
        'peak_er': 0.0, 'peak_ir': 0.0, 'trm': 0.0,
        'valid_ir': 0, 'valid_er': 0, 'valid_reps': 0, 'total_reps': 6,
        'compensation_pct': 0, 'confidence': 0,
        'per_rep': [], 'ir_per_rep': [], 'er_per_rep': [],
        'video_path': '', 'frames': [], 'w': 0, 'h': 0,
        'elbow_idx': LM['LEFT_ELBOW'], 'wrist_idx': LM['LEFT_WRIST'],
        'shoulder_idx': LM['LEFT_SHOULDER'],
        'best_ir_frame': None, 'best_er_frame': None,
    }


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def analyse(files):
    """Main entry point for 90/90 Shoulder Rotation analysis."""
    left  = _analyse_side(files.get('left',  ''), 'left')
    right = _analyse_side(files.get('right', ''), 'right')

    total_valid = left['valid_reps'] + right['valid_reps']
    total_reps  = left['total_reps'] + right['total_reps']
    avg_conf    = (left['confidence'] + right['confidence']) // 2

    # Assume right-hand dominant
    dom     = right
    non_dom = left

    gird        = non_dom['peak_ir'] - dom['peak_ir']
    trm_deficit = non_dom['trm']     - dom['trm']
    er_gain     = dom['peak_er']     - non_dom['peak_er']

    # ── Metrics ─────────────────────────────────────────────
    metrics = []

    # External Rotation  (GOOD: 80–95°)
    l_er_class = classify_range(left['peak_er'],  80, 95, 65, 110)
    r_er_class = classify_range(right['peak_er'], 80, 95, 65, 110)
    metrics.append(build_metric('Left Ext. Rotation',  f"{left['peak_er']}°",
                                left['peak_er'],  '80–95°', 120, l_er_class))
    metrics.append(build_metric('Right Ext. Rotation', f"{right['peak_er']}°",
                                right['peak_er'], '80–95°', 120, r_er_class))

    # Internal Rotation  (GOOD: 60–75°)
    l_ir_class = classify_range(left['peak_ir'],  60, 75, 45, 80)
    r_ir_class = classify_range(right['peak_ir'], 60, 75, 45, 80)
    metrics.append(build_metric('Left Int. Rotation',  f"{left['peak_ir']}°",
                                left['peak_ir'],  '60–75°', 90, l_ir_class))
    metrics.append(build_metric('Right Int. Rotation', f"{right['peak_ir']}°",
                                right['peak_ir'], '60–75°', 90, r_ir_class))

    # Total Rotational Motion  (GOOD: 150–175°)
    l_trm_class = classify_range(left['trm'],  150, 175, 130, 200)
    r_trm_class = classify_range(right['trm'], 150, 175, 130, 200)
    metrics.append(build_metric('Left TRM',  f"{left['trm']}°",
                                left['trm'],  '150–175°', 200, l_trm_class))
    metrics.append(build_metric('Right TRM', f"{right['trm']}°",
                                right['trm'], '150–175°', 200, r_trm_class))

    # Derived — GIRD, TRM Deficit, ER Gain
    gird_class    = classify(abs(gird),        18, 20, higher_is_better=False)
    trm_def_class = classify(abs(trm_deficit),  5, 10, higher_is_better=False)
    er_gain_class = classify(er_gain,           5,  0, higher_is_better=True)

    metrics.append(build_metric('GIRD',
                                f"{round(gird, 1)}°",        abs(gird),        '<18°', 30, gird_class))
    metrics.append(build_metric('TRM Deficit',
                                f"{round(trm_deficit, 1)}°", abs(trm_deficit), '<5°',  20, trm_def_class))
    metrics.append(build_metric('ER Gain (Dominant)',
                                f"{round(er_gain, 1)}°",     er_gain,          '≥5°',  30, er_gain_class))

    # ── Bilateral ───────────────────────────────────────────
    bilateral = [
        build_bilateral('External Rotation', left['peak_er'], right['peak_er'], '°', 120),
        build_bilateral('Internal Rotation', left['peak_ir'], right['peak_ir'], '°',  90),
        build_bilateral('Total Rotation',    left['trm'],     right['trm'],     '°', 200),
    ]

    score  = compute_overall_score(metrics)
    status = overall_status(score)
    coaching = generate_coaching_notes(metrics, bilateral, '90/90 Shoulder Rotation')

    # Clinical flags
    if abs(gird) > 18 and abs(trm_deficit) > 5:
        coaching.insert(0, "⚠️ Pathologic GIRD detected — posterior capsule tightness likely. Consider clinical evaluation.")
    if er_gain < 5:
        coaching.insert(0, "⚠️ ER insufficiency on dominant side — strongest injury predictor (Wilk 2015). Prioritise ER strengthening.")

    summary = f"Analysed {total_valid}/{total_reps} reps across both shoulders."
    if any('⚠️' in c for c in coaching):
        summary += " Clinical flags detected — review coaching notes carefully."
    elif status == 'RESTRICTED':
        summary += " Significant shoulder rotation restriction."
    else:
        summary += " Shoulder rotation within acceptable range."

    stats = {
        'validReps':  f'{total_valid}/{total_reps}',
        'confidence': f'{avg_conf}%',
        'sides':      'left (non-dom), right (dom)',
        'cameraView': 'OK',
    }

    # ── Annotated frames — 4 images: Left IR, Left ER, Right IR, Right ER ──
    annotated_frames = []
    for sd in [left, right]:
        side = sd['side']
        vp   = sd.get('video_path', '')
        frs  = sd.get('frames', [])
        sw, sh = sd.get('w', 0), sd.get('h', 0)

        for direction, frame_key, peak_val, good_thresh in [
            ('IR', 'best_ir_frame', sd['peak_ir'], 60),
            ('ER', 'best_er_frame', sd['peak_er'], 80),
        ]:
            pk = sd.get(frame_key)
            if pk is None or pk >= len(frs):
                continue
            lm = frs[pk]['landmarks']
            if lm is None:
                continue

            img = annotate_peak_frame(
                vp, pk, lm, sw, sh,
                metric_list=[
                    (f'{direction}', f"{peak_val}°", peak_val >= good_thresh),
                    ('TRM', f"{sd['trm']}°",         sd['trm'] >= 150),
                    ('ER',  f"{sd['peak_er']}°",     sd['peak_er'] >= 80),
                    ('IR',  f"{sd['peak_ir']}°",     sd['peak_ir'] >= 60),
                ],
                angle_list=[(sd['elbow_idx'], sd['shoulder_idx'], sd['wrist_idx'],
                             peak_val, f"{direction}: {peak_val}°")],
                status=status, score=score,
                rep_num=1, total_reps=3, side=side,
                connections=UPPER_BODY,
            )
            entry = build_frame_entry(
                f"{side.title()} Shoulder — {direction}",
                img, 1, side, True,
                [f"{direction}: {peak_val}°", f"TRM: {sd['trm']}°"],
            )
            if entry:
                annotated_frames.append(entry)

    result = build_result(status, score, summary, stats, metrics, bilateral, coaching)
    result['annotated_frames'] = annotated_frames
    result['per_rep'] = (
        [{'rep': i + 1, 'side': 'left',  'metrics': r} for i, r in enumerate(left['per_rep'])]  +
        [{'rep': i + 1, 'side': 'right', 'metrics': r} for i, r in enumerate(right['per_rep'])]
    )
    return result