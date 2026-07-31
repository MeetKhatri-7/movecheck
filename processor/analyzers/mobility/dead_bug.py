"""Exercise 7 — Dead Bug (Core Activation).

Camera: Side view, 90° to athlete, head-to-knee frame

Input: 1 video — all 8 movements in one clip.

Protocol (4 rounds, alternating):
  REST → Left arm + Right leg extend (slow, ~4 s) → REST
       → Right arm + Left leg extend  (slow, ~4 s) → REST   ... × 4

Rep assignment by temporal order:
  Movement 0,2,4,6 = Left arm  + Right leg
  Movement 1,3,5,7 = Right arm + Left leg

Key measurement insight:
  At TRUE EXTREME the arm is nearly horizontal overhead (10° from floor),
  and the leg is nearly horizontal (10° from floor).
  Both endpoints (wrist and ankle) are therefore at MAXIMUM Y in image coords
  (closest to the floor, which is at the bottom of the frame).
  → Extension signal = sum of wrist+ankle Y positions; peaks at true extreme.

Angle convention used here (matching spec reference image):
  ARM/LEG ANGLE = deviation from horizontal in degrees.
  0° = arm/leg perfectly horizontal = maximum extension (BEST).
  Computed as  abs(angle_to_vertical(A, B) − 90°).
"""
import math
import numpy as np
from utils.landmarks import (
    extract_all_landmarks, get_landmark_px, midpoint_px, LM, confidence_score
)
from utils.angles import angle_to_vertical, angle_to_horizontal, estimate_px_per_cm
from utils.rep_detection import detect_reps
from utils.scoring import (
    classify, build_metric, build_bilateral, build_result,
    compute_overall_score, overall_status, generate_coaching_notes
)
from analyzers.frame_helpers import annotate_peak_frame, build_frame_entry, CORE_BODY


# Which landmarks correspond to each side's extending arm and leg
_SIDE_LM = {
    'left': {                           # left arm + right leg
        'arm_shoulder': LM['LEFT_SHOULDER'],
        'arm_elbow':    LM['LEFT_ELBOW'],
        'arm_wrist':    LM['LEFT_WRIST'],
        'leg_hip':      LM['RIGHT_HIP'],
        'leg_knee':     LM['RIGHT_KNEE'],
        'leg_ankle':    LM['RIGHT_ANKLE'],
    },
    'right': {                          # right arm + left leg
        'arm_shoulder': LM['RIGHT_SHOULDER'],
        'arm_elbow':    LM['RIGHT_ELBOW'],
        'arm_wrist':    LM['RIGHT_WRIST'],
        'leg_hip':      LM['LEFT_HIP'],
        'leg_knee':     LM['LEFT_KNEE'],
        'leg_ankle':    LM['LEFT_ANKLE'],
    },
}


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _angle_from_horizontal(pt_a, pt_b):
    """Deviation of vector A→B from horizontal, in degrees [0, 90].

    0° = perfectly horizontal (arm/leg at floor level = max extension).
    90° = perfectly vertical.
    Uses angle_to_vertical then shifts by 90° so 90°=horizontal becomes 0°.
    """
    if pt_a is None or pt_b is None:
        return None
    v = angle_to_vertical(pt_a, pt_b)   # 0° = down, 90° = horizontal, 180° = up
    if v is None:
        return None
    return abs(v - 90.0)


def _angle_diff(a, b):
    """Smallest absolute angular difference between two angles (degrees), in [0, 180]."""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def _calibrate_px_per_cm(baseline_frames, w, h):
    """Compute px/cm from the HORIZONTAL shoulder-to-hip distance.

    In side-view the body lies along the X axis, so shoulder-X to hip-X = torso
    length ≈ 50 cm.  This is far more accurate than using frame height (which
    assumes the person is standing upright).
    """
    lengths = []
    for f in baseline_frames:
        lm = f['landmarks']
        if lm is None:
            continue
        mid_sh  = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
        mid_hip = midpoint_px(lm, LM['LEFT_HIP'],      LM['RIGHT_HIP'],      w, h)
        if mid_sh and mid_hip:
            px = abs(mid_sh[0] - mid_hip[0])
            if px > 20:
                lengths.append(px)
    if not lengths:
        return estimate_px_per_cm(h)     # fallback (less accurate)
    return (sum(lengths) / len(lengths)) / 50.0   # torso ≈ 50 cm


def _mid_hip_y_baseline(baseline_frames, w, h):
    vals = []
    for f in baseline_frames:
        lm = f['landmarks']
        if lm is None:
            continue
        mid = midpoint_px(lm, LM['LEFT_HIP'], LM['RIGHT_HIP'], w, h)
        if mid:
            vals.append(mid[1])
    return sum(vals) / len(vals) if vals else None


def _torso_angle_baseline(baseline_frames, w, h):
    vals = []
    for f in baseline_frames:
        lm = f['landmarks']
        if lm is None:
            continue
        mid_sh  = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
        mid_hip = midpoint_px(lm, LM['LEFT_HIP'],      LM['RIGHT_HIP'],      w, h)
        if mid_sh and mid_hip:
            vals.append(angle_to_horizontal(mid_sh, mid_hip))
    return sum(vals) / len(vals) if vals else None


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def analyse(files):
    """Analyse the single Dead Bug clip containing all 8 movements."""
    video_path = files.get('all', '')
    if not video_path:
        return _fallback('No video uploaded.')

    data   = extract_all_landmarks(video_path)
    frames = data['frames']
    fps    = data['fps']
    w, h   = data['width'], data['height']
    conf   = confidence_score(frames)

    if not frames:
        return _fallback('Could not read frames from video.')

    # ── Baseline — first 0.5 s lying flat ───────────────────
    n_base        = max(int(fps * 0.5), 5)
    base_frames   = frames[:n_base]
    hip_base_y    = _mid_hip_y_baseline(base_frames, w, h)
    torso_base_ang = _torso_angle_baseline(base_frames, w, h)
    px_per_cm     = _calibrate_px_per_cm(base_frames, w, h)

    # ── Per-frame signals ─────────────────────────────────────
    # Extension signal: sum of Y-positions of BOTH wrists + BOTH ankles.
    #
    # At rest:    all 4 endpoints are elevated (small Y) → signal moderate.
    # At extreme: the extending wrist moves overhead toward the floor (large Y),
    #             and the extending ankle lowers to near the floor (large Y)
    #             → signal peaks sharply at true end-range of each movement.
    #
    # This fires once per movement regardless of which side, giving 8 clean peaks.

    extension_signal  = []
    all_mid_hip_y     = []
    all_torso_angles  = []

    for f in frames:
        lm = f['landmarks']
        if lm is None:
            extension_signal.append(0.0)
            all_mid_hip_y.append(None)
            all_torso_angles.append(None)
            continue

        mid_sh  = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
        mid_hip = midpoint_px(lm, LM['LEFT_HIP'],      LM['RIGHT_HIP'],      w, h)

        # Sum of Y positions — larger = endpoints closer to floor = more extended
        sig = 0.0
        for idx in (LM['LEFT_WRIST'], LM['RIGHT_WRIST'],
                    LM['LEFT_ANKLE'], LM['RIGHT_ANKLE']):
            pt = get_landmark_px(lm, idx, w, h)
            if pt:
                sig += pt[1]
        extension_signal.append(sig)

        all_mid_hip_y.append(mid_hip[1] if mid_hip else None)

        if mid_sh and mid_hip:
            all_torso_angles.append(angle_to_horizontal(mid_sh, mid_hip))
        else:
            all_torso_angles.append(None)

    # ── Detect 8 movement peaks ──────────────────────────────
    reps_raw = detect_reps(extension_signal, expected_reps=8, fps=fps,
                           min_hold_sec=0.4)
    reps_sorted = sorted(reps_raw, key=lambda r: r['peak_frame'])
    if len(reps_sorted) > 8:
        reps_sorted = sorted(reps_sorted, key=lambda r: r['peak_value'], reverse=True)[:8]
        reps_sorted = sorted(reps_sorted, key=lambda r: r['peak_frame'])

    # ── Per-movement analysis ────────────────────────────────
    per_side            = {'left': [], 'right': []}
    frames_to_annotate  = []

    for i, rep in enumerate(reps_sorted):
        seg_start = rep['start_frame']
        seg_end   = min(rep['end_frame'] + 1, len(frames))

        # ── TRUE EXTREME: frame with max extension signal in the segment ──
        # This is the frame where arm is most overhead AND leg is most lowered —
        # exactly the position shown in the reference spec image.
        best_sig   = -1.0
        best_frame = rep['peak_frame']
        for fi in range(seg_start, seg_end):
            if extension_signal[fi] > best_sig:
                best_sig   = extension_signal[fi]
                best_frame = fi

        peak = best_frame
        lm   = frames[peak]['landmarks'] if peak < len(frames) else None
        if lm is None:
            continue

        # ── Which side actually extended? Detect it, don't assume ──
        # The extending arm reaches overhead toward the floor, so its wrist
        # sits LOWER in the image (larger Y) than the tabletop-side wrist.
        # A fixed left-first alternation mislabels every rep when the athlete
        # starts on the other side or repeats a side.
        l_wr = get_landmark_px(lm, LM['LEFT_WRIST'],  w, h)
        r_wr = get_landmark_px(lm, LM['RIGHT_WRIST'], w, h)
        if l_wr and r_wr:
            side = 'left' if l_wr[1] > r_wr[1] else 'right'
        else:
            side = 'left' if i % 2 == 0 else 'right'   # fallback: alternation
        lm_ids = _SIDE_LM[side]

        # ── Rep-local rest baseline and "loaded window" ─────────
        # Baseline from THIS rep's rest phase (lowest 40% of the extension
        # signal). The old global first-0.5 s baseline broke whenever the
        # athlete was still settling at video start — it reported 27 cm
        # phantom "lumbar lifts" on clean reps. Lift/flare are only measured
        # while the limbs are actually extended (top 30% of signal range).
        seg_sig  = [extension_signal[fi] for fi in range(seg_start, seg_end)]
        sig_lo   = min(seg_sig)
        sig_hi   = max(seg_sig)
        sig_span = max(sig_hi - sig_lo, 1e-6)

        rest_hips, rest_torso = [], []
        for fi in range(seg_start, seg_end):
            if (extension_signal[fi] - sig_lo) / sig_span > 0.4:
                continue
            if all_mid_hip_y[fi] is not None:
                rest_hips.append(all_mid_hip_y[fi])
            if all_torso_angles[fi] is not None:
                rest_torso.append(all_torso_angles[fi])
        rest_hips.sort()
        rep_hip_base = rest_hips[len(rest_hips) // 2] if rest_hips else hip_base_y
        rest_torso.sort()
        rep_torso_base = rest_torso[len(rest_torso) // 2] if rest_torso else torso_base_ang

        # ── Lumbar lift: max bilateral-hip Y-rise in the loaded window ──
        # Rise = hip moving UP = Y DECREASING in image coords.
        max_lumbar_cm = 0.0
        if rep_hip_base is not None:
            for fi in range(seg_start, seg_end):
                if (extension_signal[fi] - sig_lo) / sig_span < 0.7:
                    continue
                hy = all_mid_hip_y[fi]
                if hy is not None:
                    rise_px = rep_hip_base - hy      # positive = hip rose
                    if rise_px > 0:
                        rise_cm = rise_px / px_per_cm
                        max_lumbar_cm = max(max_lumbar_cm, rise_cm)

        # ── Rib flare (torso angle deviation proxy) ──────────
        # Max change from THIS rep's rest torso angle, loaded window only.
        # Use _angle_diff to avoid 360° wrap artefact (was giving 355°).
        max_rib_dev = 0.0
        if rep_torso_base is not None:
            for fi in range(seg_start, seg_end):
                if (extension_signal[fi] - sig_lo) / sig_span < 0.7:
                    continue
                ta = all_torso_angles[fi]
                if ta is not None:
                    max_rib_dev = max(max_rib_dev,
                                     _angle_diff(ta, rep_torso_base))

        # ── Limb angles at the TRUE EXTREME frame ────────────
        arm_sh  = get_landmark_px(lm, lm_ids['arm_shoulder'], w, h)
        arm_wr  = get_landmark_px(lm, lm_ids['arm_wrist'],    w, h)
        leg_hip = get_landmark_px(lm, lm_ids['leg_hip'],      w, h)
        leg_ank = get_landmark_px(lm, lm_ids['leg_ankle'],    w, h)

        # ARM ANGLE from horizontal — 0° = arm fully horizontal overhead (best)
        arm_angle = _angle_from_horizontal(arm_sh, arm_wr)
        arm_angle = round(arm_angle, 1) if arm_angle is not None else 90.0

        # LEG ANGLE from horizontal — 0° = leg fully horizontal (best, nearly on floor)
        # Using full-leg hip→ankle vector (matches spec reference image)
        leg_angle = _angle_from_horizontal(leg_hip, leg_ank)
        leg_angle = round(leg_angle, 1) if leg_angle is not None else 90.0

        # ── Tempo: segment start → peak frame ────────────────
        tempo_sec = round((peak - seg_start) / fps, 1) if fps > 0 else 0.0

        result = {
            'rep_num':             len(per_side[side]) + 1,
            'side':                side,
            'lumbar_lift_cm':      round(max_lumbar_cm, 1),
            'rib_flare_deg':       round(max_rib_dev,   1),
            'arm_angle':           arm_angle,
            'leg_angle':           leg_angle,
            'tempo_sec':           tempo_sec,
            'peak_frame':          peak,
        }
        per_side[side].append(result)
        frames_to_annotate.append({
            'result': result,
            'lm':     lm,
            'lm_ids': lm_ids,
        })

    left_reps  = per_side['left']
    right_reps = per_side['right']
    total_valid = len(left_reps) + len(right_reps)

    # ── Aggregate per side ───────────────────────────────────
    def _agg(reps):
        if not reps:
            return {'max_lumbar': 0.0, 'avg_tempo': 0.0,
                    'consistency': 100, 'max_rib': 0.0,
                    'best_arm': 90.0, 'best_leg': 90.0}
        lumbars = [r['lumbar_lift_cm'] for r in reps]
        tempos  = [r['tempo_sec']      for r in reps]
        ribs    = [r['rib_flare_deg']  for r in reps]
        arms    = [r['arm_angle']      for r in reps]
        legs    = [r['leg_angle']      for r in reps]
        sd      = float(np.std(lumbars)) if len(lumbars) > 1 else 0.0
        # sd is in cm with a landmark noise floor of ~0.5–1 cm; ×10 maps a
        # 1 cm spread to 90% instead of the old ×20 which zeroed clean sets.
        cons    = max(0, min(100, round(100 - sd * 10)))
        return {
            'max_lumbar':  max(lumbars),
            'avg_tempo':   round(sum(tempos) / len(tempos), 1),
            'consistency': cons,
            'max_rib':     max(ribs),
            'best_arm':    min(arms),    # lower = more extension = better
            'best_leg':    min(legs),
        }

    L = _agg(left_reps)
    R = _agg(right_reps)

    # ── Metrics ──────────────────────────────────────────────
    metrics = []

    # Lumbar lift — GOOD < 1.5 cm, NEEDS 1.5–3 cm, RESTRICTED > 3 cm.
    # The proxy is hip-landmark rise, whose jitter floor at typical framing
    # is ~1 cm — a 0.5 cm GOOD gate graded landmark noise, not the athlete.
    l_lum = classify(L['max_lumbar'], 1.5, 3.0, higher_is_better=False)
    r_lum = classify(R['max_lumbar'], 1.5, 3.0, higher_is_better=False)
    metrics.append(build_metric('Left Lumbar Lift',  f"{L['max_lumbar']} cm",
                                L['max_lumbar'], '<1.5 cm', 5, l_lum))
    metrics.append(build_metric('Right Lumbar Lift', f"{R['max_lumbar']} cm",
                                R['max_lumbar'], '<1.5 cm', 5, r_lum))

    # Arm extension angle from horizontal — GOOD < 20°, NEEDS 20–45°, RESTRICTED > 45°
    l_arm = classify(L['best_arm'], 20, 45, higher_is_better=False)
    r_arm = classify(R['best_arm'], 20, 45, higher_is_better=False)
    metrics.append(build_metric('Left Arm Extension',  f"{L['best_arm']}° from horiz.",
                                L['best_arm'], '<20°', 90, l_arm))
    metrics.append(build_metric('Right Arm Extension', f"{R['best_arm']}° from horiz.",
                                R['best_arm'], '<20°', 90, r_arm))

    # Leg extension angle from horizontal — GOOD < 20°, NEEDS 20–45°, RESTRICTED > 45°
    l_leg = classify(L['best_leg'], 20, 45, higher_is_better=False)
    r_leg = classify(R['best_leg'], 20, 45, higher_is_better=False)
    metrics.append(build_metric('Left Leg Extension',  f"{L['best_leg']}° from horiz.",
                                L['best_leg'], '<20°', 90, l_leg))
    metrics.append(build_metric('Right Leg Extension', f"{R['best_leg']}° from horiz.",
                                R['best_leg'], '<20°', 90, r_leg))

    # Tempo — GOOD ≥ 4 s, NEEDS 2.5–4 s, RESTRICTED < 2.5 s
    l_tempo = classify(L['avg_tempo'], 4.0, 2.5, higher_is_better=True)
    r_tempo = classify(R['avg_tempo'], 4.0, 2.5, higher_is_better=True)
    metrics.append(build_metric('Left Avg Tempo',  f"{L['avg_tempo']} s",
                                L['avg_tempo'], '≥4 s', 8, l_tempo))
    metrics.append(build_metric('Right Avg Tempo', f"{R['avg_tempo']} s",
                                R['avg_tempo'], '≥4 s', 8, r_tempo))

    # Rib flare — GOOD < 5°, NEEDS 5–10°, RESTRICTED > 10°
    l_rib = classify(L['max_rib'], 5.0, 10.0, higher_is_better=False)
    r_rib = classify(R['max_rib'], 5.0, 10.0, higher_is_better=False)
    metrics.append(build_metric('Left Rib Flare',  f"{round(L['max_rib'],1)}°",
                                L['max_rib'], '<5°', 20, l_rib))
    metrics.append(build_metric('Right Rib Flare', f"{round(R['max_rib'],1)}°",
                                R['max_rib'], '<5°', 20, r_rib))

    # Rep consistency
    l_cons = classify(L['consistency'], 80, 60, higher_is_better=True)
    r_cons = classify(R['consistency'], 80, 60, higher_is_better=True)
    metrics.append(build_metric('Left Consistency',  f"{L['consistency']}%",
                                L['consistency'], '≥80%', 100, l_cons))
    metrics.append(build_metric('Right Consistency', f"{R['consistency']}%",
                                R['consistency'], '≥80%', 100, r_cons))

    # ── Bilateral ─────────────────────────────────────────────
    bilateral = [
        build_bilateral('Lumbar Lift',    L['max_lumbar'], R['max_lumbar'], 'cm', 3),
        build_bilateral('Avg Tempo',      L['avg_tempo'],  R['avg_tempo'],  's',  8),
        build_bilateral('Best Arm Angle', L['best_arm'],   R['best_arm'],   '°',  90),
        build_bilateral('Best Leg Angle', L['best_leg'],   R['best_leg'],   '°',  90),
    ]

    score  = compute_overall_score(metrics)
    status = overall_status(score)
    coaching = generate_coaching_notes(metrics, bilateral, 'Dead Bug')

    # Bilateral lumbar asymmetry
    lumbar_diff = abs(L['max_lumbar'] - R['max_lumbar'])
    if lumbar_diff > 0.5:
        worse = 'left' if L['max_lumbar'] > R['max_lumbar'] else 'right'
        coaching.insert(0,
            f"Bilateral asymmetry: {worse} side shows {round(lumbar_diff, 1)} cm more "
            f"lumbar lift — opposite-limb control weaker on that side.")

    # Flag rushed reps
    for side_reps, label in [(left_reps, 'Left'), (right_reps, 'Right')]:
        rushed = [r for r in side_reps if r['tempo_sec'] < 2.5]
        if rushed:
            coaching.insert(0,
                f"{label} side: {len(rushed)} rep(s) under 2.5 s — "
                f"momentum compensation. Slow to a 4-second count.")

    summary = (f"Analysed {total_valid}/8 movements "
               f"({len(left_reps)} left, {len(right_reps)} right).")
    if status == 'GOOD':
        summary += " Excellent core stability — no lumbar compensation detected."
    elif status == 'NEEDS IMPROVEMENT':
        summary += " Minor lumbar compensation at end range — focus on maintaining back contact."
    else:
        summary += " Significant lumbar arch or rushed tempo detected — reduce range until control improves."

    stats = {
        'validReps':  f'{total_valid}/8',
        'confidence': f'{conf}%',
        'sides':      'left arm+right leg, right arm+left leg',
        'cameraView': 'OK',
        'passRate':   f'{sum(1 for m in metrics if m["status"] == "good")}/{len(metrics)}',
    }

    # ── Annotated frames — all 8 movements ───────────────────
    annotated_frames = []
    for entry in frames_to_annotate:
        rd     = entry['result']
        lm     = entry['lm']
        lm_ids = entry['lm_ids']
        side   = rd['side']
        pk     = rd['peak_frame']

        if pk >= len(frames):
            continue

        rep_num = rd['rep_num']
        lumbar  = rd['lumbar_lift_cm']
        tempo   = rd['tempo_sec']
        arm_ang = rd['arm_angle']
        leg_ang = rd['leg_angle']
        rib     = rd['rib_flare_deg']

        # Best rep = lowest arm+leg angle (most extension achieved)
        ext_score = arm_ang + leg_ang
        side_reps = per_side[side]
        best_ext  = min((r['arm_angle'] + r['leg_angle'] for r in side_reps),
                        default=180)
        is_best   = (ext_score == best_ext)

        img = annotate_peak_frame(
            video_path, pk, lm, w, h,
            metric_list=[
                ('Lumbar Lift', f"{lumbar} cm",  lumbar < 0.5),
                ('Arm Angle',   f"{arm_ang}°",   arm_ang <= 20),
                ('Leg Angle',   f"{leg_ang}°",   leg_ang <= 20),
                ('Tempo',       f"{tempo} s",    tempo  >= 4.0),
                ('Rib Flare',   f"{rib}°",       rib    <  5.0),
            ],
            angle_list=[
                (lm_ids['arm_shoulder'], lm_ids['arm_wrist'],
                 lm_ids['leg_hip'], arm_ang, f"Arm: {arm_ang}°"),
                (lm_ids['leg_hip'], lm_ids['leg_ankle'],
                 lm_ids['leg_knee'], leg_ang, f"Leg: {leg_ang}°"),
            ],
            status=status, score=score,
            rep_num=rep_num, total_reps=4,
            side=side,
            connections=CORE_BODY,
        )
        side_label  = 'L arm+R leg' if side == 'left' else 'R arm+L leg'
        frame_label = f"{side_label} — Rep {rep_num}" + (" (Best)" if is_best else "")
        frame_entry = build_frame_entry(
            frame_label, img, rep_num, side, is_best,
            [f"Lumbar: {lumbar}cm", f"Arm: {arm_ang}°",
             f"Leg: {leg_ang}°", f"Tempo: {tempo}s", f"Rib: {rib}°"],
        )
        if frame_entry:
            annotated_frames.append(frame_entry)

    result = build_result(status, score, summary, stats, metrics, bilateral, coaching)
    result['annotated_frames'] = annotated_frames
    result['per_rep'] = (
        [{'rep': r['rep_num'], 'side': 'left',  'metrics': r} for r in left_reps]  +
        [{'rep': r['rep_num'], 'side': 'right', 'metrics': r} for r in right_reps]
    )
    return result


def _fallback(msg):
    return build_result(
        'NEEDS IMPROVEMENT', 50,
        f'Analysis could not complete: {msg}',
        {'validReps': '0/8', 'confidence': '0%',
         'sides': 'n/a', 'cameraView': 'UNKNOWN'},
        [], [],
        [msg, 'Please ensure the video was uploaded and the camera angle is correct.'],
    )
