"""Exercise 9 — Plank with Shoulder Tap (Core Stability & Anti-Rotation).

Camera: Front-side view, hip height, full body frame
Landmarks: SHOULDER(11/12), HIP(23/24), KNEE(25/26), ANKLE(27/28), WRIST(15/16)

Input: 1 video — 16 reps total (8 left + 8 right), alternating L/R.
Protocol: rest → left tap → rest → right tap → rest → ... ×8 cycles.

Key design:
  The EXTREME frame per tap = frame where the raised wrist is at its MAXIMUM
  elevation above its floor position = the hand is closest to the opposite
  shoulder = the hardest anti-rotation moment = what we want to grade.

  Signal: for each frame, elevation = max(left_elev, right_elev)
    where elev = (floor_wrist_y − wrist_y) / h   (0 at rest, > 0 when raised)
  detect_reps finds 16 peaks; within each segment the frame with max elevation
  is the extreme.  Metrics are measured at that frame only.
"""
import math
import numpy as np
from utils.landmarks import (
    extract_all_landmarks, get_landmark_px, midpoint_px, LM, confidence_score
)
from utils.angles import angle_3pt, estimate_px_per_cm
from utils.rep_detection import detect_reps, moving_average
from utils.scoring import (
    classify, build_metric, build_bilateral, build_result,
    compute_overall_score, overall_status, generate_coaching_notes
)
from analyzers.frame_helpers import annotate_peak_frame, build_frame_entry, FULL_BODY


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _calibrate_px_per_cm(frames, w, h):
    """px/cm from shoulder-to-hip distance (torso ≈ 50 cm)."""
    lengths = []
    sample = frames[:max(len(frames) // 10, 15)]
    for f in sample:
        lm = f['landmarks']
        if lm is None:
            continue
        sh_l = get_landmark_px(lm, LM['LEFT_SHOULDER'],  w, h)
        sh_r = get_landmark_px(lm, LM['RIGHT_SHOULDER'], w, h)
        hp_l = get_landmark_px(lm, LM['LEFT_HIP'],  w, h)
        hp_r = get_landmark_px(lm, LM['RIGHT_HIP'], w, h)
        if sh_l and sh_r and hp_l and hp_r:
            sh_mid = ((sh_l[0]+sh_r[0])/2, (sh_l[1]+sh_r[1])/2)
            hp_mid = ((hp_l[0]+hp_r[0])/2, (hp_l[1]+hp_r[1])/2)
            dist = math.hypot(sh_mid[0]-hp_mid[0], sh_mid[1]-hp_mid[1])
            if dist > 20:
                lengths.append(dist)
    if lengths:
        return (sum(lengths) / len(lengths)) / 50.0
    return estimate_px_per_cm(h)


def _angle_diff(a, b):
    """Angular difference with wrap-around correction (always in [0, 180])."""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def analyse(files):
    """Analyse Plank Shoulder Tap — 16 alternating taps (8L + 8R)."""
    video_path = (files.get('all') or files.get('hold') or
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

    # ── Pass 1: collect raw per-frame values ──────────────────
    left_wrist_y  = []
    right_wrist_y = []
    all_hip_y     = []

    for f in frames:
        lm = f['landmarks']
        if lm is None:
            left_wrist_y.append(None)
            right_wrist_y.append(None)
            all_hip_y.append(None)
            continue

        lw = get_landmark_px(lm, LM['LEFT_WRIST'],  w, h)
        rw = get_landmark_px(lm, LM['RIGHT_WRIST'], w, h)
        hl = get_landmark_px(lm, LM['LEFT_HIP'],  w, h)
        hr = get_landmark_px(lm, LM['RIGHT_HIP'], w, h)

        left_wrist_y.append(lw[1]  if lw else None)
        right_wrist_y.append(rw[1] if rw else None)

        if hl and hr:
            all_hip_y.append((hl[1] + hr[1]) / 2)
        elif hl:
            all_hip_y.append(hl[1])
        elif hr:
            all_hip_y.append(hr[1])
        else:
            all_hip_y.append(None)

    # ── Floor anchors: 85th-percentile Y = resting (on floor) position ──
    # Robust: works regardless of where in the frame the person is.
    def _percentile(vals, pct):
        v = sorted([x for x in vals if x is not None])
        return v[int(len(v) * pct)] if len(v) >= 5 else None

    floor_lw    = _percentile(left_wrist_y,  0.85) or h * 0.90
    floor_rw    = _percentile(right_wrist_y, 0.85) or h * 0.90
    floor_w_avg = (floor_lw + floor_rw) / 2

    # Hip baseline: 85th pct of hip Y = correct plank alignment level
    hip_y_baseline = _percentile(all_hip_y, 0.85) or h * 0.55

    # ── Tap signal: max elevation of either wrist above its floor position ──
    # REST (both wrists on floor)  → signal ≈ 0.0
    # TAP (one wrist raised high)  → signal > 0.0
    tap_signal = []
    for lwy, rwy in zip(left_wrist_y, right_wrist_y):
        l_e = max(0.0, (floor_lw - lwy) / h) if lwy is not None else 0.0
        r_e = max(0.0, (floor_rw - rwy) / h) if rwy is not None else 0.0
        tap_signal.append(max(l_e, r_e))

    # Smooth with 0.25 s window to eliminate single-frame noise
    smooth_window = max(int(fps * 0.25), 3)
    smoothed = moving_average(tap_signal, smooth_window)

    # ── Detect 16 tap peaks ───────────────────────────────────
    reps = detect_reps(smoothed, expected_reps=16, fps=fps, min_hold_sec=0.3)

    # ── Per-tap metrics at TRUE EXTREME (max wrist elevation) ─
    tap_results   = []
    left_metrics  = []
    right_metrics = []

    for tap_i, rep in enumerate(reps):
        seg_start = rep['start_frame']
        seg_end   = min(rep['end_frame'] + 1, len(frames))

        # Find frame within segment with the MAXIMUM tap signal (= wrist highest)
        best_frame = rep['peak_frame']
        best_elev  = tap_signal[best_frame] if best_frame < len(tap_signal) else 0.0
        for fi in range(seg_start, seg_end):
            if fi < len(tap_signal) and tap_signal[fi] > best_elev:
                best_elev = tap_signal[fi]
                best_frame = fi

        if best_frame >= len(frames):
            continue
        lm = frames[best_frame]['landmarks']
        if lm is None:
            continue

        # ── Which hand is raised at the extreme frame? ────────
        lwy = left_wrist_y[best_frame]
        rwy = right_wrist_y[best_frame]
        if lwy is not None and rwy is not None:
            hand = 'left' if lwy < rwy else 'right'   # smaller Y = higher = raised
        else:
            hand = 'left' if tap_i % 2 == 0 else 'right'  # temporal fallback

        # ── Hip drop (cm) ─────────────────────────────────────
        hip_mid = midpoint_px(lm, LM['LEFT_HIP'], LM['RIGHT_HIP'], w, h)
        if hip_mid:
            # Positive = hip dropped below plank baseline (sagging)
            hip_drop_px = max(0.0, hip_mid[1] - hip_y_baseline)
            hip_drop_cm = hip_drop_px / px_per_cm if px_per_cm > 0 else 0.0
        else:
            hip_drop_cm = 0.0

        # ── Hip rotation (°) ──────────────────────────────────
        # Tilt of bilateral hip line vs bilateral shoulder line.
        # ONLY measurable when both lines have real pixel length: from a
        # side-on camera the two hips nearly coincide, and atan2 on a
        # ~5 px line yields garbage (this metric read 100°+ on clean reps).
        hip_l = get_landmark_px(lm, LM['LEFT_HIP'],       w, h)
        hip_r = get_landmark_px(lm, LM['RIGHT_HIP'],      w, h)
        sh_l  = get_landmark_px(lm, LM['LEFT_SHOULDER'],  w, h)
        sh_r  = get_landmark_px(lm, LM['RIGHT_SHOULDER'], w, h)
        hip_rotation = None
        if hip_l and hip_r and sh_l and sh_r:
            hip_len = math.hypot(hip_r[0]-hip_l[0], hip_r[1]-hip_l[1])
            sh_len  = math.hypot(sh_r[0]-sh_l[0],   sh_r[1]-sh_l[1])
            torso   = math.hypot((sh_l[0]+sh_r[0])/2 - (hip_l[0]+hip_r[0])/2,
                                 (sh_l[1]+sh_r[1])/2 - (hip_l[1]+hip_r[1])/2)
            min_len = max(0.15 * max(torso, 1.0), 12.0)
            if hip_len >= min_len and sh_len >= min_len:
                hip_ang = math.degrees(math.atan2(hip_r[1]-hip_l[1], hip_r[0]-hip_l[0]))
                sh_ang  = math.degrees(math.atan2(sh_r[1]-sh_l[1],   sh_r[0]-sh_l[0]))
                hip_rotation = _angle_diff(hip_ang, sh_ang)

        # ── Plank line angle (°) — shoulder–hip–knee ──────────
        sh_mid   = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
        knee_mid = midpoint_px(lm, LM['LEFT_KNEE'],     LM['RIGHT_KNEE'],     w, h)
        plank_angle = (angle_3pt(sh_mid, hip_mid, knee_mid)
                       if sh_mid and hip_mid and knee_mid else 180.0)
        if plank_angle is None:
            plank_angle = 180.0

        # ── Wrist elevation (cm) — how high the raised hand goes ──
        raised_y = lwy if hand == 'left' else rwy
        if raised_y is not None:
            wrist_elev_px = max(0.0, floor_w_avg - raised_y)
            wrist_elev_cm = wrist_elev_px / px_per_cm if px_per_cm > 0 else 0.0
        else:
            wrist_elev_cm = 0.0

        td = {
            'tap_num':       tap_i + 1,
            'hand':          hand,
            'hip_drop_cm':   round(hip_drop_cm,  1),
            'hip_rotation':  round(hip_rotation, 1) if hip_rotation is not None else None,
            'plank_angle':   round(plank_angle,  1),
            'wrist_elev_cm': round(wrist_elev_cm, 1),
            'best_frame':    best_frame,
        }
        tap_results.append(td)
        if hand == 'left':
            left_metrics.append(td)
        else:
            right_metrics.append(td)

    # ── Aggregate ─────────────────────────────────────────────
    all_drops = [t['hip_drop_cm']  for t in tap_results]
    all_rots  = [t['hip_rotation'] for t in tap_results if t['hip_rotation'] is not None]
    all_plank = [t['plank_angle']  for t in tap_results]

    avg_drop     = sum(all_drops) / len(all_drops) if all_drops else 0.0
    max_drop     = max(all_drops)                  if all_drops else 0.0
    avg_rotation = sum(all_rots)  / len(all_rots)  if all_rots  else None
    avg_plank    = sum(all_plank) / len(all_plank) if all_plank else 180.0

    def _avg_or_zero(entries, key):
        vals = [t[key] for t in entries if t.get(key) is not None]
        return sum(vals) / len(vals) if vals else 0.0

    l_avg_drop = _avg_or_zero(left_metrics,  'hip_drop_cm')
    r_avg_drop = _avg_or_zero(right_metrics, 'hip_drop_cm')
    l_avg_rot  = _avg_or_zero(left_metrics,  'hip_rotation')
    r_avg_rot  = _avg_or_zero(right_metrics, 'hip_rotation')

    # ── Scoring ────────────────────────────────────────────────
    drop_class    = classify(avg_drop,      1,   2, higher_is_better=False)
    maxdrop_class = classify(max_drop,      1,   2, higher_is_better=False)
    plank_class   = classify(avg_plank,   170, 160, higher_is_better=True)

    metrics = [
        build_metric('Avg Hip Drop',     f"{round(avg_drop,1)} cm",   avg_drop,     '<1 cm',  5,   drop_class),
        build_metric('Max Hip Drop',     f"{round(max_drop,1)} cm",   max_drop,     '<1 cm',  5,   maxdrop_class),
        build_metric('Plank Line',       f"{round(avg_plank,1)}°",    avg_plank,    '≥170°', 185,  plank_class),
    ]
    # Hip rotation only when the camera angle makes it measurable (fewer
    # than half the taps measurable = oblique/side camera → omit rather
    # than report noise).
    rotation_measurable = len(all_rots) >= max(1, len(tap_results) // 2)
    if rotation_measurable and avg_rotation is not None:
        rot_class = classify(avg_rotation, 3, 8, higher_is_better=False)
        metrics.insert(2, build_metric('Avg Hip Rotation', f"{round(avg_rotation,1)}°",
                                       avg_rotation, '<3°', 20, rot_class))

    bilateral = [
        build_bilateral('Hip Drop', l_avg_drop, r_avg_drop, ' cm', 5),
    ]
    if rotation_measurable:
        bilateral.append(build_bilateral('Hip Rotation', l_avg_rot, r_avg_rot, '°', 20))

    score    = compute_overall_score(metrics)
    status   = overall_status(score)
    coaching = generate_coaching_notes(metrics, bilateral, 'Plank Shoulder Tap')

    if avg_drop > 2:
        coaching.insert(0,
            f"Hip drops {round(avg_drop,1)} cm per tap — brace your core harder "
            f"before lifting the hand.")
    if avg_rotation is not None and avg_rotation > 8:
        coaching.insert(0,
            f"Hip rotates {round(avg_rotation,1)}° during taps — slow each rep "
            f"and widen your foot stance for more stability.")
    if not rotation_measurable:
        coaching.append(
            "Hip rotation could not be measured from this camera angle — film "
            "slightly more from behind (both hips visible) to enable it.")

    summary = (f"Analysed {len(tap_results)}/16 taps "
               f"({len(left_metrics)}L + {len(right_metrics)}R).")
    if status == 'GOOD':
        summary += " Strong anti-rotation control — minimal hip drop and rotation."
    elif status == 'NEEDS IMPROVEMENT':
        summary += " Moderate stability — focus on core brace before each tap."
    else:
        summary += " Significant hip instability detected during taps."

    stats = {
        'validReps':  f'{len(tap_results)}/16',
        'confidence': f'{conf}%',
        'sides':      f'L:{len(left_metrics)} R:{len(right_metrics)}',
        'cameraView': 'OK',
        'passRate':   f'{sum(1 for m in metrics if m["status"] == "good")}/{len(metrics)}',
    }

    # ── Annotated frames — one per tap at the EXTREME position ──
    annotated_frames = []
    best_drop = min((t['hip_drop_cm'] for t in tap_results), default=0)

    for td in tap_results:
        pk = td['best_frame']
        if pk >= len(frames):
            continue
        lm = frames[pk]['landmarks']
        if lm is None:
            continue

        hand    = td['hand']
        drop    = td['hip_drop_cm']
        rot     = td['hip_rotation']
        plank   = td['plank_angle']
        tap_num = td['tap_num']
        is_best = (drop == best_drop)

        overlay = [
            ('Hip Drop',   f"{drop} cm", drop  < 1),
            ('Plank Line', f"{plank}°",  plank >= 170),
        ]
        shown = [f"Drop: {drop}cm", f"Plank: {plank}°"]
        if rot is not None:
            overlay.insert(1, ('Hip Rot.', f"{rot}°", rot < 3))
            shown.insert(1, f"Rot: {rot}°")
        img = annotate_peak_frame(
            video_path, pk, lm, w, h,
            metric_list=overlay,
            status=status, score=score,
            rep_num=tap_num, total_reps=len(tap_results),
            side=hand,
            connections=FULL_BODY,
        )
        entry = build_frame_entry(
            f"{hand.title()} Tap {tap_num}" + (" (Best)" if is_best else ""),
            img, tap_num, hand, is_best,
            shown,
        )
        if entry:
            annotated_frames.append(entry)

    result = build_result(status, score, summary, stats, metrics, bilateral, coaching)
    result['annotated_frames'] = annotated_frames
    result['per_rep'] = [{'rep': t['tap_num'], 'side': t['hand'], 'metrics': t}
                         for t in tap_results]
    return result


def _fallback(msg):
    return build_result(
        'NEEDS IMPROVEMENT', 50,
        f'Analysis could not complete: {msg}',
        {'validReps': '0/16', 'confidence': '0%',
         'sides': 'n/a', 'cameraView': 'UNKNOWN'},
        [], [],
        [msg, 'Please ensure the video was uploaded correctly.'],
    )
