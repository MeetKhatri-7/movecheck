"""Exercise 10 — Prone Y-T-W Raise (Scapular Control & Upper Back).

Cameras:
  Camera 1 (overhead):  top-down view, measures raise angle in the plane of the body
  Camera 2 (foot-side): 45° foot-end elevation, confirms angle and detects shrug

Inputs: 6 videos — Y/T/W × overhead/foot-side, 3 reps each.
Protocol per video: rest → raise (hold 1-2 s) → rest × 3

Extreme frame per rep = frame where wrists are at MAXIMUM elevation above their
resting (on-floor) position = the deepest/highest hold = what we score.

Metrics (per shape, at the extreme frame):
  Overhead:  raise angle of each arm from the body's longitudinal axis
             symmetry (|left − right|)
  Foot-side: shrug compensation (ear→shoulder distance decrease in cm)
             arm elevation angle above horizontal (confirmation)

Frontend receives:
  metrics         – flat list (for radar / table)
  metric_sections – { "Y": [...], "T": [...], "W": [...], "combined": [...] }
  annotated_frames – best rep per camera per shape (6 frames)
"""
import math
import numpy as np
from utils.landmarks import (
    extract_all_landmarks, get_landmark_px, midpoint_px, LM, confidence_score
)
from utils.angles import angle_3pt, angle_to_vertical, estimate_px_per_cm
from utils.rep_detection import detect_reps, moving_average
from utils.scoring import (
    classify, classify_range, classify_band, build_metric, build_bilateral,
    build_result, compute_overall_score, overall_status, generate_coaching_notes
)
from analyzers.frame_helpers import annotate_peak_frame, build_frame_entry, UPPER_BODY


# ─────────────────────────────────────────────────────────────
# Geometry helpers
# ─────────────────────────────────────────────────────────────

def _percentile(vals, pct):
    v = sorted([x for x in vals if x is not None])
    return v[int(len(v) * pct)] if len(v) >= 5 else None


def _arm_raise_angle_overhead(shoulder, wrist, hip_mid, shoulder_mid):
    """Angle of the arm from the body's longitudinal axis (overhead view).

    Dot-product of (hip→shoulder axis) and (shoulder→wrist arm direction).
    Y ≈ 30–45°, T ≈ 80–100°, W upper-arm ≈ 80–100°.
    """
    if not all([shoulder, wrist, hip_mid, shoulder_mid]):
        return 0.0
    bx = shoulder_mid[0] - hip_mid[0]
    by = shoulder_mid[1] - hip_mid[1]
    ax = wrist[0] - shoulder[0]
    ay = wrist[1] - shoulder[1]
    b_len = math.hypot(bx, by)
    a_len = math.hypot(ax, ay)
    if b_len < 1 or a_len < 1:
        return 0.0
    dot = (bx / b_len) * (ax / a_len) + (by / b_len) * (ay / a_len)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def _arm_elevation_footside(shoulder, wrist):
    """Elevation angle of the arm above horizontal (foot-side view).

    angle_to_vertical gives 0°=down, 90°=horizontal, 180°=up.
    elevation_above_horizontal = angle_to_vertical(sh, wr) − 90°.
    """
    if not shoulder or not wrist:
        return 0.0
    atv = angle_to_vertical(shoulder, wrist)
    if atv is None:
        return 0.0
    return max(0.0, atv - 90.0)


def _calibrate_px_per_cm(frames, w, h):
    """px/cm from shoulder–hip vertical distance (≈50 cm, lying prone)."""
    dists = []
    sample = frames[:max(len(frames) // 10, 15)]
    for f in sample:
        lm = f['landmarks']
        if lm is None:
            continue
        sh_m = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
        hp_m = midpoint_px(lm, LM['LEFT_HIP'],      LM['RIGHT_HIP'],      w, h)
        if sh_m and hp_m:
            d = math.hypot(sh_m[0]-hp_m[0], sh_m[1]-hp_m[1])
            if d > 20:
                dists.append(d)
    if dists:
        return (sum(dists) / len(dists)) / 50.0
    return estimate_px_per_cm(h)


# ─────────────────────────────────────────────────────────────
# Per-video analysis (shared detection logic)
# ─────────────────────────────────────────────────────────────

def _analyse_overhead(video_path, shape):
    """3-rep overhead analysis — raise angle per arm, symmetry."""
    if not video_path:
        return None

    data   = extract_all_landmarks(video_path)
    frames = data['frames']
    fps    = data['fps']
    w, h   = data['width'], data['height']
    conf   = confidence_score(frames)

    # ── Per-frame raw wrist Y, raise angles, ear–shoulder gap ─
    all_lwy = []
    all_rwy = []
    l_angles = []
    r_angles = []
    all_ear_sh = []   # ear→shoulder distance — shrug detection (top-down
                      # this gap is measured in the body plane and is NOT
                      # subject to the foreshortening that broke it in the
                      # foot-side view)

    for f in frames:
        lm = f['landmarks']
        if lm is None:
            all_lwy.append(None)
            all_rwy.append(None)
            l_angles.append(0.0)
            r_angles.append(0.0)
            all_ear_sh.append(None)
            continue

        hp_m  = midpoint_px(lm, LM['LEFT_HIP'],      LM['RIGHT_HIP'],      w, h)
        sh_m  = midpoint_px(lm, LM['LEFT_SHOULDER'],  LM['RIGHT_SHOULDER'], w, h)
        l_sh  = get_landmark_px(lm, LM['LEFT_SHOULDER'],  w, h)
        r_sh  = get_landmark_px(lm, LM['RIGHT_SHOULDER'], w, h)
        l_wr  = get_landmark_px(lm, LM['LEFT_WRIST'],  w, h)
        r_wr  = get_landmark_px(lm, LM['RIGHT_WRIST'], w, h)
        l_el  = get_landmark_px(lm, LM['LEFT_ELBOW'],  w, h)
        r_el  = get_landmark_px(lm, LM['RIGHT_ELBOW'], w, h)

        # For W use elbow as endpoint; Y/T use wrist
        l_end = l_el if shape == 'W' else l_wr
        r_end = r_el if shape == 'W' else r_wr

        l_ang = _arm_raise_angle_overhead(l_sh, l_end, hp_m, sh_m)
        r_ang = _arm_raise_angle_overhead(r_sh, r_end, hp_m, sh_m)
        l_angles.append(l_ang)
        r_angles.append(r_ang)

        all_lwy.append(l_wr[1] if l_wr else None)
        all_rwy.append(r_wr[1] if r_wr else None)

        ear_l = get_landmark_px(lm, LM['LEFT_EAR'],  w, h)
        ear_r = get_landmark_px(lm, LM['RIGHT_EAR'], w, h)
        gaps = []
        if ear_l and l_sh:
            gaps.append(math.hypot(ear_l[0]-l_sh[0], ear_l[1]-l_sh[1]))
        if ear_r and r_sh:
            gaps.append(math.hypot(ear_r[0]-r_sh[0], ear_r[1]-r_sh[1]))
        all_ear_sh.append(sum(gaps)/len(gaps) if gaps else None)

    # ── Wrist elevation signal for rep detection ──────────────
    floor_lw = _percentile(all_lwy, 0.85) or h * 0.85
    floor_rw = _percentile(all_rwy, 0.85) or h * 0.85
    shrug_baseline = _percentile(all_ear_sh, 0.85) or 0.0

    tap_sig = []
    for lwy, rwy in zip(all_lwy, all_rwy):
        l_e = max(0.0, (floor_lw - lwy) / h) if lwy is not None else 0.0
        r_e = max(0.0, (floor_rw - rwy) / h) if rwy is not None else 0.0
        tap_sig.append((l_e + r_e) / 2)

    sm = moving_average(tap_sig, max(int(fps * 0.3), 3))
    reps = detect_reps(sm, expected_reps=3, fps=fps, min_hold_sec=0.5)

    # ── Per-rep: find EXTREME frame (max combined elevation) ──
    rep_results = []
    for rep_i, rep in enumerate(reps):
        seg_s = rep['start_frame']
        seg_e = min(rep['end_frame'] + 1, len(frames))

        best_frame = rep['peak_frame']
        best_elev  = tap_sig[best_frame] if best_frame < len(tap_sig) else 0.0
        for fi in range(seg_s, seg_e):
            if fi < len(tap_sig) and tap_sig[fi] > best_elev:
                best_elev = tap_sig[fi]
                best_frame = fi

        if best_frame >= len(frames):
            continue
        lm = frames[best_frame]['landmarks']
        if lm is None:
            continue

        # Shrug at the extreme: % shortening of the ear→shoulder gap vs its
        # relaxed baseline (scale-free, valid in this top-down projection).
        ear_sh = all_ear_sh[best_frame]
        if ear_sh is not None and shrug_baseline > 0:
            shrug_pct = max(0.0, (shrug_baseline - ear_sh) / shrug_baseline * 100.0)
        else:
            shrug_pct = 0.0

        la = l_angles[best_frame]
        ra = r_angles[best_frame]
        rep_results.append({
            'rep_num':    rep_i + 1,
            'left_angle': round(la, 1),
            'right_angle': round(ra, 1),
            'symmetry':   round(abs(la - ra), 1),
            'shrug_pct':  round(shrug_pct, 1),
            'best_frame': best_frame,
        })

    # Best rep = one closest to target (smallest angle deviation from target midpoint)
    return {
        'view':         'overhead',
        'shape':        shape,
        'frames':       frames,
        'video_path':   video_path,
        'w': w, 'h': h, 'fps': fps,
        'confidence':   conf,
        'rep_results':  rep_results,
    }


def _analyse_footside(video_path, shape):
    """3-rep foot-side analysis — arm elevation angle, shrug compensation."""
    if not video_path:
        return None

    data   = extract_all_landmarks(video_path)
    frames = data['frames']
    fps    = data['fps']
    w, h   = data['width'], data['height']
    conf   = confidence_score(frames)
    px_per_cm = _calibrate_px_per_cm(frames, w, h)

    # ── Per-frame raw values ──────────────────────────────────
    all_lwy = []
    all_rwy = []
    all_ear_sh_dist = []   # ear→shoulder distance for shrug detection

    for f in frames:
        lm = f['landmarks']
        if lm is None:
            all_lwy.append(None)
            all_rwy.append(None)
            all_ear_sh_dist.append(None)
            continue

        lw = get_landmark_px(lm, LM['LEFT_WRIST'],  w, h)
        rw = get_landmark_px(lm, LM['RIGHT_WRIST'], w, h)
        all_lwy.append(lw[1] if lw else None)
        all_rwy.append(rw[1] if rw else None)

        # Ear–shoulder distance (decreases when shrugging)
        ear_l = get_landmark_px(lm, LM['LEFT_EAR'],       w, h)
        ear_r = get_landmark_px(lm, LM['RIGHT_EAR'],      w, h)
        sh_l  = get_landmark_px(lm, LM['LEFT_SHOULDER'],  w, h)
        sh_r  = get_landmark_px(lm, LM['RIGHT_SHOULDER'], w, h)
        ear   = ear_l or ear_r
        sh    = sh_l  or sh_r
        if ear and sh:
            dx = ear[0]-sh[0]; dy = ear[1]-sh[1]
            all_ear_sh_dist.append(math.hypot(dx, dy))
        else:
            all_ear_sh_dist.append(None)

    # ── Floor anchors and shrug baseline ─────────────────────
    floor_lw  = _percentile(all_lwy, 0.85) or h * 0.85
    floor_rw  = _percentile(all_rwy, 0.85) or h * 0.85
    # Baseline ear–shoulder distance = 85th pct (largest = no shrug)
    shrug_baseline = _percentile(all_ear_sh_dist, 0.85) or 0.0

    # ── Rep detection signal: avg wrist elevation above floor ─
    tap_sig = []
    for lwy, rwy in zip(all_lwy, all_rwy):
        l_e = max(0.0, (floor_lw - lwy) / h) if lwy is not None else 0.0
        r_e = max(0.0, (floor_rw - rwy) / h) if rwy is not None else 0.0
        tap_sig.append((l_e + r_e) / 2)

    sm = moving_average(tap_sig, max(int(fps * 0.3), 3))
    reps = detect_reps(sm, expected_reps=3, fps=fps, min_hold_sec=0.5)

    # ── Per-rep at EXTREME frame ──────────────────────────────
    rep_results = []
    for rep_i, rep in enumerate(reps):
        seg_s = rep['start_frame']
        seg_e = min(rep['end_frame'] + 1, len(frames))

        best_frame = rep['peak_frame']
        best_elev  = tap_sig[best_frame] if best_frame < len(tap_sig) else 0.0
        for fi in range(seg_s, seg_e):
            if fi < len(tap_sig) and tap_sig[fi] > best_elev:
                best_elev = tap_sig[fi]
                best_frame = fi

        if best_frame >= len(frames):
            continue
        lm = frames[best_frame]['landmarks']
        if lm is None:
            continue

        # Arm elevation angle from horizontal (confirmation)
        sh_l = get_landmark_px(lm, LM['LEFT_SHOULDER'],  w, h)
        sh_r = get_landmark_px(lm, LM['RIGHT_SHOULDER'], w, h)
        lw   = get_landmark_px(lm, LM['LEFT_WRIST'],  w, h)
        rw   = get_landmark_px(lm, LM['RIGHT_WRIST'], w, h)
        l_elev = _arm_elevation_footside(sh_l, lw)
        r_elev = _arm_elevation_footside(sh_r, rw)
        elev_angle = (l_elev + r_elev) / 2 if (sh_l or sh_r) else 0.0

        # Lift height at the extreme — max wrist rise above its floor rest,
        # as % of the visible shoulder width. Vertical motion survives the
        # foot-side foreshortening intact and shoulder width gives an
        # in-view scale, unlike the ear→shoulder "shrug" gap and the
        # torso-length px/cm calibration, which both collapse in this
        # projection (they produced 60–84% phantom shrugs / 70 cm values).
        sh_width = None
        if sh_l and sh_r:
            sh_width = math.hypot(sh_l[0]-sh_r[0], sh_l[1]-sh_r[1])
        lifts = []
        lw_pt = get_landmark_px(lm, LM['LEFT_WRIST'],  w, h)
        rw_pt = get_landmark_px(lm, LM['RIGHT_WRIST'], w, h)
        if lw_pt: lifts.append(max(0.0, floor_lw - lw_pt[1]))
        if rw_pt: lifts.append(max(0.0, floor_rw - rw_pt[1]))
        if lifts and sh_width and sh_width > 10:
            lift_pct = (sum(lifts) / len(lifts)) / sh_width * 100.0
        else:
            lift_pct = 0.0

        rep_results.append({
            'rep_num':    rep_i + 1,
            'elev_angle': round(elev_angle, 1),
            'lift_pct':   round(lift_pct, 1),
            'best_frame': best_frame,
        })

    return {
        'view':        'footside',
        'shape':       shape,
        'frames':      frames,
        'video_path':  video_path,
        'w': w, 'h': h, 'fps': fps,
        'confidence':  conf,
        'px_per_cm':   px_per_cm,
        'rep_results': rep_results,
        'shrug_baseline': shrug_baseline,
    }


# ─────────────────────────────────────────────────────────────
# Shape-level scoring + metric building
# ─────────────────────────────────────────────────────────────

def _score_shape(shape, oh, fs, target_min, target_max):
    """Build metrics and bilateral for one shape. Returns (metrics, bilateral, section)."""
    metrics = []
    bilateral = []

    # ── Overhead metrics ──────────────────────────────────────
    if oh and oh['rep_results']:
        reps   = oh['rep_results']
        best_l = max(r['left_angle']  for r in reps)
        best_r = max(r['right_angle'] for r in reps)
        sym    = min(r['symmetry']    for r in reps)

        if shape == 'W':
            # W: upper arm sweeps below the T-line — 100–140° from the
            # head-axis is the natural W band (elbow endpoint).
            l_class = classify_band(best_l, 100, 140, 85, 155)
            r_class = classify_band(best_r, 100, 140, 85, 155)
            tgt_str = '100–140°'
        else:
            # FORMATION metric: the target is a closed band. Overshooting
            # (e.g. a 'T' swept 40° toward the feet) is a form fault, not
            # extra credit — classify_range graded 131° as a GOOD 'T'.
            l_class = classify_band(best_l, target_min, target_max,
                                    target_min - 15, target_max + 15)
            r_class = classify_band(best_r, target_min, target_max,
                                    target_min - 15, target_max + 15)
            tgt_str = f'{target_min}–{target_max}°'

        metrics.append(build_metric(f'{shape} Left Arm',  f'{best_l}°', best_l, tgt_str,
                                    target_max + 20, l_class))
        metrics.append(build_metric(f'{shape} Right Arm', f'{best_r}°', best_r, tgt_str,
                                    target_max + 20, r_class))

        sym_class = classify(sym, 10, 15, higher_is_better=False)
        metrics.append(build_metric(f'{shape} Symmetry', f'{sym}° diff', sym,
                                    '<10°', 30, sym_class))

        # Shrug — measured from the OVERHEAD camera, where the ear→shoulder
        # gap lies in the image plane. (From the foot-side camera this gap
        # collapses under foreshortening and read 60–84% on packed shoulders.)
        shrugs = [r['shrug_pct'] for r in reps if r.get('shrug_pct') is not None]
        if shrugs:
            avg_shrug = sum(shrugs) / len(shrugs)
            shrug_class = classify(avg_shrug, 15, 30, higher_is_better=False)
            metrics.append(build_metric(f'{shape} Shoulder Shrug', f'{round(avg_shrug,1)}%',
                                        avg_shrug, '<15%', 60, shrug_class))

        bilateral.append(build_bilateral(f'{shape} Arm Angle', best_l, best_r,
                                         '°', target_max + 20))
    else:
        best_l = best_r = sym = 0.0

    # Foot-side camera: no reliable in-plane scale exists in that heavily
    # foreshortened projection (both the ear–shoulder gap and shoulder width
    # collapse), so it contributes the annotated visual confirmation only —
    # no scored metric.
    return metrics, bilateral


# ─────────────────────────────────────────────────────────────
# Annotated frame builder
# ─────────────────────────────────────────────────────────────

def _best_rep_frame(rep_results, oh_or_fs, shape, target_min, target_max, view_label,
                    all_metrics_for_shape, score, status):
    """Generate 1 annotated image for the best rep in this camera/shape."""
    if not rep_results or not oh_or_fs:
        return None

    frames     = oh_or_fs['frames']
    video_path = oh_or_fs['video_path']
    w, h       = oh_or_fs['w'], oh_or_fs['h']

    # Pick best rep:
    # For overhead: closest arm angle to target midpoint
    # For foot-side: lowest shrug
    if oh_or_fs['view'] == 'overhead':
        target_mid = (target_min + target_max) / 2
        best_rep = min(rep_results,
                       key=lambda r: abs((r['left_angle']+r['right_angle'])/2 - target_mid))
        pk = best_rep['best_frame']
        if pk >= len(frames):
            return None
        lm = frames[pk]['landmarks']
        if lm is None:
            return None

        la = best_rep['left_angle']
        ra = best_rep['right_angle']
        is_good_l = target_min <= la <= target_max + 10
        is_good_r = target_min <= ra <= target_max + 10
        metric_list = [
            (f'L Arm ({shape})',  f'{la}°',    is_good_l),
            (f'R Arm ({shape})',  f'{ra}°',    is_good_r),
            ('Symmetry',         f'{best_rep["symmetry"]}°', best_rep['symmetry'] <= 10),
        ]
    else:
        best_rep = max(rep_results, key=lambda r: r.get('lift_pct', 0.0))
        pk = best_rep['best_frame']
        if pk >= len(frames):
            return None
        lm = frames[pk]['landmarks']
        if lm is None:
            return None

        lift = best_rep.get('lift_pct', 0.0)
        metric_list = [
            ('Lift Height', f'{lift}%', lift >= 25),
        ]

    img = annotate_peak_frame(
        video_path, pk, lm, w, h,
        metric_list=metric_list,
        status=status, score=score,
        rep_num=best_rep['rep_num'], total_reps=len(rep_results),
        connections=UPPER_BODY,
    )
    label = f'{shape} – {view_label} (Best)'
    entry = build_frame_entry(label, img, best_rep['rep_num'], view_label, True,
                              [m[0] + ': ' + m[1] for m in metric_list])
    return entry


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def analyse(files):
    """Analyse all 6 Y-T-W videos (overhead + foot-side × Y/T/W)."""
    SHAPES = {
        'Y': {'overhead': 'y-overhead', 'footside': 'y-footside', 'target': (30, 45)},
        'T': {'overhead': 't-overhead', 'footside': 't-footside', 'target': (80, 100)},
        'W': {'overhead': 'w-overhead', 'footside': 'w-footside', 'target': (80, 100)},
    }

    all_metrics   = []
    all_bilateral = []
    metric_sections = {}       # { 'Y': [...], 'T': [...], 'W': [...] }
    annotated_frames = []
    total_valid = 0
    total_conf  = 0
    n_conf_vids = 0

    for shape_name, cfg in SHAPES.items():
        oh_path = files.get(cfg['overhead'], '')
        fs_path = files.get(cfg['footside'], '')

        if not oh_path and not fs_path:
            continue

        tgt_min, tgt_max = cfg['target']

        oh = _analyse_overhead(oh_path, shape_name) if oh_path else None
        fs = _analyse_footside(fs_path, shape_name) if fs_path else None

        if oh:
            total_valid += len(oh['rep_results'])
            total_conf  += oh['confidence']
            n_conf_vids += 1
        if fs:
            total_conf  += fs['confidence']
            n_conf_vids += 1

        shape_metrics, shape_bilateral = _score_shape(
            shape_name, oh, fs, tgt_min, tgt_max
        )

        all_metrics.extend(shape_metrics)
        all_bilateral.extend(shape_bilateral)
        metric_sections[shape_name] = shape_metrics

        # ── Score (used for frame annotation) ─────────────────
        shape_score  = compute_overall_score(shape_metrics)
        shape_status = overall_status(shape_score)

        # ── Annotated frames: 1 best per camera per shape ─────
        if oh and oh['rep_results']:
            entry = _best_rep_frame(oh['rep_results'], oh, shape_name,
                                    tgt_min, tgt_max, 'Overhead',
                                    shape_metrics, shape_score, shape_status)
            if entry:
                annotated_frames.append(entry)

        if fs and fs['rep_results']:
            entry = _best_rep_frame(fs['rep_results'], fs, shape_name,
                                    tgt_min, tgt_max, 'Foot-Side',
                                    shape_metrics, shape_score, shape_status)
            if entry:
                annotated_frames.append(entry)

    # ── Combined / overall ─────────────────────────────────────
    score    = compute_overall_score(all_metrics)
    status   = overall_status(score)
    coaching = generate_coaching_notes(all_metrics, all_bilateral, 'Prone Y-T-W Raise')

    avg_conf    = (total_conf // n_conf_vids) if n_conf_vids else 0
    shapes_done = sum(1 for s in SHAPES if (files.get(SHAPES[s]['overhead']) or
                                            files.get(SHAPES[s]['footside'])))

    # ── Combined metrics (cross-shape averages) ──────────────
    combined_metrics = []
    for s in ['Y', 'T', 'W']:
        sec = metric_sections.get(s, [])
        for m in sec:
            if 'Shoulder Shrug' in m['name']:
                combined_metrics.append(
                    build_metric(f'Overall Shrug ({s})', m['value'], m['raw'],
                                 m['target'], m['max'],
                                 'GOOD' if m['status'] == 'good' else 'RESTRICTED'))
    metric_sections['Combined'] = combined_metrics

    summary = f"Analysed {total_valid}/{shapes_done*3} reps across {shapes_done} shapes."
    if status == 'GOOD':
        summary += " Good scapular control across all shapes."
    elif status == 'NEEDS IMPROVEMENT':
        summary += " Partial scapular control — some shapes show asymmetry."
    else:
        summary += " Scapular control deficit — prioritise posterior rotator cuff work."

    stats = {
        'validReps':  f'{total_valid}/{shapes_done * 3}',
        'confidence': f'{avg_conf}%',
        'sides':      'bilateral',
        'cameraView': 'OK',
        'passRate':   f'{sum(1 for m in all_metrics if m["status"] == "good")}/{len(all_metrics)}',
    }

    result = build_result(status, score, summary, stats,
                          all_metrics, all_bilateral, coaching)
    result['annotated_frames'] = annotated_frames
    result['metric_sections']  = metric_sections
    result['per_rep'] = []   # per-rep data omitted (6 videos × 3 reps is handled above)
    return result
