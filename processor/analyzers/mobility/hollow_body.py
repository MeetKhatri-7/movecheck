"""Exercise 8 — Hollow Body Hold (Core Activation).

Camera: Side view, 90° to athlete, full body frame
Landmarks: SHOULDER(11/12), HIP(23/24), KNEE(25/26), ANKLE(27/28)

Input: 1 video — 3 × ~10 s holds with rest between each.

Key detection fix:
  The previous signal used `90 - leg_angle` which PEAKS when the person is
  lying FLAT (rest, leg_angle ≈ 0° → signal ≈ 90) and is LOW during the active
  hollow body hold (legs elevated, leg_angle ≈ 60° → signal ≈ 30).
  This caused rest periods to be detected as "holds".

  Correct signal: ankle elevation above the floor = (h - ankle_y) / h.
    Rest (ankle at floor):    signal ≈ 0.05–0.10  (LOW)
    Active hollow body hold:  signal ≈ 0.30–0.70  (HIGH)
  detect_holds then correctly finds the 3 sustained active periods.

Metrics are measured at the best frame WITHIN each detected hold —
  the frame where the ankle is most elevated = the hardest/most active
  position = the "extreme" position the user wants assessed.
"""
import numpy as np
from utils.landmarks import (
    extract_all_landmarks, get_landmark_px, midpoint_px, LM, confidence_score
)
from utils.angles import angle_to_horizontal, estimate_px_per_cm
from utils.rep_detection import detect_holds, moving_average
from utils.scoring import (
    classify, build_metric, build_result,
    compute_overall_score, overall_status, generate_coaching_notes
)
from analyzers.frame_helpers import annotate_peak_frame, build_frame_entry, FULL_BODY


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _elevation_from_horizontal(ang_deg):
    """Angle of hip→ankle vector above (or below) horizontal, in [0, 90].

    Handles both feet-left and feet-right orientations:
      feet-right: atan2 ≈ −20°  → elevation = 20°
      feet-left:  atan2 ≈ −160° → naive abs = 160° (WRONG)
                                   min(160, 20)   = 20°  (CORRECT)
    """
    if ang_deg is None:
        return 90.0
    a = abs(ang_deg)
    return a if a <= 90 else 180.0 - a


def _calibrate_px_per_cm(frames, w, h):
    """px/cm from horizontal shoulder-to-hip distance (torso ≈ 50 cm).

    Far more accurate than frame-height estimate for a lying-down person.
    """
    lengths = []
    sample = frames[:max(len(frames) // 10, 15)]
    for f in sample:
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
        return estimate_px_per_cm(h)
    return (sum(lengths) / len(lengths)) / 50.0   # torso ≈ 50 cm


def _get_ankle(lm, w, h):
    al = get_landmark_px(lm, LM['LEFT_ANKLE'],  w, h)
    ar = get_landmark_px(lm, LM['RIGHT_ANKLE'], w, h)
    if al and ar:
        return ((al[0] + ar[0]) / 2, (al[1] + ar[1]) / 2)
    return al or ar


def _get_hip(lm, w, h):
    hl = get_landmark_px(lm, LM['LEFT_HIP'],  w, h)
    hr = get_landmark_px(lm, LM['RIGHT_HIP'], w, h)
    if hl and hr:
        return ((hl[0] + hr[0]) / 2, (hl[1] + hr[1]) / 2)
    return hl or hr


def _get_shoulder(lm, w, h):
    sl = get_landmark_px(lm, LM['LEFT_SHOULDER'],  w, h)
    sr = get_landmark_px(lm, LM['RIGHT_SHOULDER'], w, h)
    if sl and sr:
        return ((sl[0] + sr[0]) / 2, (sl[1] + sr[1]) / 2)
    return sl or sr


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def analyse(files):
    """Analyse the Hollow Body Hold video (3 × ~10 s holds)."""
    video_path = (files.get('hold') or files.get('all') or
                  (list(files.values())[0] if files else ''))
    if not video_path:
        return _fallback('No video uploaded.')

    data   = extract_all_landmarks(video_path)
    frames = data['frames']
    fps    = data['fps']
    w, h   = data['width'], data['height']
    conf   = confidence_score(frames)

    if not frames:
        return _fallback('Could not read frames from video.')

    px_per_cm = _calibrate_px_per_cm(frames, w, h)

    # ── Pass 1: collect raw per-frame values ─────────────────
    leg_angles  = []
    all_ankle_y = []
    all_hip_y   = []

    for f in frames:
        lm = f['landmarks']
        if lm is None:
            leg_angles.append(90.0)
            all_ankle_y.append(None)
            all_hip_y.append(None)
            continue

        hip   = _get_hip(lm, w, h)
        ankle = _get_ankle(lm, w, h)

        if hip and ankle:
            raw = angle_to_horizontal(hip, ankle)
            leg_angles.append(_elevation_from_horizontal(raw))
        else:
            leg_angles.append(90.0)

        all_hip_y.append(hip[1] if hip else None)
        all_ankle_y.append(ankle[1] if ankle else None)

    # ── Anchor: 85th-percentile ankle Y = person's natural floor position ──
    # Works regardless of where in the frame the person is positioned.
    # 85th pct because most of the video is spent at rest between holds.
    valid_ys = sorted([y for y in all_ankle_y if y is not None])
    if len(valid_ys) >= 5:
        floor_ankle_y = valid_ys[int(len(valid_ys) * 0.85)]
    else:
        floor_ankle_y = h * 0.85

    # ── Pass 2: active signal = how far ankle is ABOVE the floor position ──
    # REST (ankle at floor_ankle_y) → signal ≈ 0.0
    # ACTIVE hold (ankle elevated)  → signal > 0.0 (proportional to elevation)
    # This is camera-position-independent: we measure elevation relative to
    # the person's own resting ankle height, not relative to frame bottom.
    active_signal = []
    for ankle_y in all_ankle_y:
        if ankle_y is None:
            active_signal.append(0.0)
        else:
            elevation = max(0.0, (floor_ankle_y - ankle_y) / h)
            active_signal.append(elevation)

    # Smooth with 0.5 s window so single noisy frames don't break a hold
    smooth_window = max(int(fps * 0.5), 5)
    smoothed = moving_average(active_signal, smooth_window)

    # Threshold: ankle must be elevated by at least 8 % of frame height
    # (~10–15 cm for a typical camera distance) — easily met in a true hold.
    active_threshold = 0.08

    # ── Detect 3 holds ────────────────────────────────────────
    holds = detect_holds(smoothed, threshold=active_threshold,
                         fps=fps, min_hold_sec=3.0)
    if not holds:
        holds = detect_holds(smoothed, threshold=active_threshold * 0.65,
                             fps=fps, min_hold_sec=2.0)
    if not holds:
        holds = detect_holds(smoothed, threshold=active_threshold * 0.40,
                             fps=fps, min_hold_sec=1.5)

    # ── Per-hold metrics ──────────────────────────────────────
    hold_results = []
    for hold in holds[:3]:
        start = hold['start_frame']
        end   = hold['end_frame']

        # Trim 10% off each end of the hold — entry/exit transitions are not
        # part of the hold and inflate every stability statistic.
        span = end - start
        trim = max(int(span * 0.10), int(fps * 0.3))
        t_start = min(start + trim, end)
        t_end   = max(end - trim, t_start)

        seg_leg    = leg_angles[t_start:t_end + 1]
        seg_act    = active_signal[start:end + 1]   # unsmoothed for true peak
        seg_hip_y  = [y for y in all_hip_y[t_start:t_end + 1]   if y is not None]
        seg_ank_y  = [y for y in all_ankle_y[t_start:t_end + 1] if y is not None]

        # ── Best frame = ankle most elevated = deepest in hold ────────────
        if seg_act:
            best_local = int(np.argmax(seg_act))
        else:
            best_local = 0
        best_frame = start + best_local

        # Leg angle AT the best frame (the extreme position the user wants graded)
        peak_leg_angle = leg_angles[best_frame]

        # Average leg angle across the whole hold
        avg_angle = (sum(seg_leg) / len(seg_leg)) if seg_leg else 90.0

        # Lumbar contact: hip Y should stay stable (no arch = hip doesn't rise).
        lumbar_pct = 0.0
        if seg_hip_y:
            ref_y = float(np.median(seg_hip_y))
            tol   = h * 0.035          # 3.5% of frame height
            ok    = sum(1 for y in seg_hip_y if abs(y - ref_y) <= tol)
            lumbar_pct = ok / len(seg_hip_y) * 100.0

        # Ankle tremor: SD of the DETRENDED ankle Y during the hold → cm.
        # Raw SD conflates slow, legitimate leg repositioning with shake —
        # it read >10 cm on stable holds. Subtracting a 1 s moving average
        # leaves only the high-frequency tremor component.
        tremor_cm = 0.0
        if len(seg_ank_y) > int(fps):
            from utils.rep_detection import moving_average as _ma
            trend = _ma(seg_ank_y, max(int(fps * 1.0), 3))
            resid = [y - t for y, t in zip(seg_ank_y, trend) if t is not None]
            if len(resid) > 2:
                tremor_px = float(np.std(resid))
                tremor_cm = tremor_px / px_per_cm if px_per_cm > 0 else tremor_px

        hold_results.append({
            'hold_num':           len(hold_results) + 1,
            'duration_sec':       round(hold['duration_sec'], 1),
            'peak_leg_angle':     round(peak_leg_angle, 1),
            'avg_leg_angle':      round(avg_angle, 1),
            'lumbar_contact_pct': round(lumbar_pct, 1),
            'tremor_cm':          round(tremor_cm, 1),
            'best_frame':         best_frame,
            'start_frame':        start,
            'end_frame':          end,
        })

    # ── Aggregate across all holds ─────────────────────────────
    if hold_results:
        best_duration  = max(r['duration_sec']       for r in hold_results)
        avg_leg_angle  = sum(r['peak_leg_angle']     for r in hold_results) / len(hold_results)
        avg_lumbar     = sum(r['lumbar_contact_pct'] for r in hold_results) / len(hold_results)
        avg_tremor     = sum(r['tremor_cm']           for r in hold_results) / len(hold_results)
    else:
        best_duration = 0.0
        avg_leg_angle = 90.0
        avg_lumbar    = 0.0
        avg_tremor    = 5.0

    # ── Scoring ────────────────────────────────────────────────
    # Leg angle — GOOD ≤ 30°, NEEDS 30–45°, RESTRICTED > 45°
    angle_class  = classify(avg_leg_angle, 30, 45, higher_is_better=False)
    lumbar_class = classify(avg_lumbar,    90, 70, higher_is_better=True)
    hold_class   = classify(best_duration, 10,  6, higher_is_better=True)
    tremor_class = classify(avg_tremor,     1,  3, higher_is_better=False)

    metrics = [
        build_metric('Leg Angle (avg)',    f"{round(avg_leg_angle, 1)}°",
                     avg_leg_angle,  '≤30°',  90, angle_class),
        build_metric('Lumbar Contact',     f"{round(avg_lumbar, 1)}%",
                     avg_lumbar,     '≥90%', 100, lumbar_class),
        build_metric('Best Hold Duration', f"{round(best_duration, 1)} s",
                     best_duration,  '≥10s',  15, hold_class),
        build_metric('Ankle Tremor',       f"{round(avg_tremor, 1)} cm",
                     avg_tremor,     '<1 cm',   5, tremor_class),
    ]

    score  = compute_overall_score(metrics)
    status = overall_status(score)
    coaching = generate_coaching_notes(metrics, [], 'Hollow Body Hold')

    if avg_leg_angle > 45:
        coaching.insert(0,
            f"Leg angle averaging {round(avg_leg_angle,1)}° — core isn't strong enough "
            f"to hold legs low yet. Regress to bent-knee hollow body and progress to straight legs.")
    if avg_tremor > 3:
        coaching.insert(0,
            f"High ankle tremor ({round(avg_tremor,1)} cm) indicates instability — "
            f"brace harder and slow breathing.")

    summary = f"Analysed {len(hold_results)}/3 valid holds."
    if status == 'GOOD':
        summary += " Strong hollow body position — legs low, lumbar flat, hold sustained."
    elif status == 'NEEDS IMPROVEMENT':
        summary += " Partial position achieved — focus on lowering legs while keeping lumbar contact."
    else:
        summary += " Significant position breakdown — regress to bent-knee hollow body."

    stats = {
        'validReps':  f'{len(hold_results)}/3',
        'confidence': f'{conf}%',
        'sides':      'n/a',
        'cameraView': 'OK',
        'passRate':   f'{sum(1 for m in metrics if m["status"] == "good")}/{len(metrics)}',
    }

    # ── Annotated frames — one per hold at the EXTREME (most active) frame ──
    annotated_frames = []
    best_overall_angle = min((r['peak_leg_angle'] for r in hold_results), default=90)

    for hr in hold_results:
        pk = hr['best_frame']
        if pk >= len(frames):
            continue
        lm = frames[pk]['landmarks']
        if lm is None:
            continue

        ang   = hr['peak_leg_angle']
        lum   = hr['lumbar_contact_pct']
        dur   = hr['duration_sec']
        trem  = hr['tremor_cm']
        hi    = hr['hold_num']
        is_b  = (ang == best_overall_angle)

        img = annotate_peak_frame(
            video_path, pk, lm, w, h,
            metric_list=[
                ('Leg Angle',  f"{ang}°",    ang  <= 30),
                ('Lumbar',     f"{lum}%",    lum  >= 90),
                ('Hold',       f"{dur} s",   dur  >= 10),
                ('Tremor',     f"{trem} cm", trem <   1),
            ],
            status=status, score=score,
            rep_num=hi, total_reps=len(hold_results),
            connections=FULL_BODY,
        )
        entry = build_frame_entry(
            f"Hold {hi}" + (" (Best)" if is_b else ""),
            img, hi, 'center', is_b,
            [f"Leg: {ang}°", f"Lumbar: {lum}%",
             f"Hold: {dur}s", f"Tremor: {trem}cm"],
        )
        if entry:
            annotated_frames.append(entry)

    result = build_result(status, score, summary, stats, metrics, [], coaching)
    result['annotated_frames'] = annotated_frames
    result['per_rep'] = [{'rep': r['hold_num'], 'side': 'center', 'metrics': r}
                         for r in hold_results]
    return result


def _fallback(msg):
    return build_result(
        'NEEDS IMPROVEMENT', 50,
        f'Analysis could not complete: {msg}',
        {'validReps': '0/3', 'confidence': '0%',
         'sides': 'n/a', 'cameraView': 'UNKNOWN'},
        [], [],
        [msg, 'Please ensure the video was uploaded correctly.'],
    )
