"""STRENGTH — Overhead Press (Military / Seated Dumbbell Shoulder Press).

Full rewrite per the Biomechanical Assessment Spec (Overhead-press-rewrite.md).

Why OHP is different from bench / deadlift / pull-up / pull
===========================================================
  • Push-press is a HARD CLASSIFIER, not a soft penalty.  Spec §2:
    if knee bend > 8° OR hip-X > 4 cm BEFORE the bar rises 5 cm, the
    rep is reclassified as `push_press` and EXCLUDED from the strict-
    press set average (per user decision: DNC pattern).
  • Three extreme positions per rep — SETUP (bar at clavicle / DB at
    ear), STICKING POINT (velocity minimum at 25–45% bar travel),
    LOCKOUT (top, arms by ears).  Pull-up has 2 extremes; OHP needs 3.
  • Two completely different variants — Military (standing barbell,
    full kinetic chain, ALL safety overrides active including
    knee-flexion + hip-thrust + bar-over-midfoot) vs Seated DB
    (bench-supported, knee/hip overrides skipped, but DB symmetry,
    back contact, DB tempo symmetry become primary safety metrics).
  • Backrest angle for Seated DB selects the threshold column.
    <70° refuses to score under the OHP rubric (route to bench press
    instead) — surfaced as a banner.
  • DBs move independently — each wrist tracked separately, not
    combined.  F3 (DB symmetry) and T6 (DB tempo symmetry) only exist
    for the Seated DB variant.
  • Anthropometry adjustment: long-armed lifters (forearm >0.16 × height)
    get S5 (bar horizontal max) thresholds relaxed by 20%.

Pipeline
========
  1. Resolve four cameras: sagittal (PRIMARY), frontal (CO-PRIMARY for
     seated DB), posterior, oblique (sagittal fallback for occlusion).
  2. Per-view pose extraction + signal derivation.
  3. Backrest validation (Seated DB only): refuse to score if <70°.
  4. Per-view rep detection: state machine on wrist-centre Y +
     elbow-angle, identifies SETUP / STICKING / LOCKOUT frames.
  5. Push-press gate per rep BEFORE scoring: if knee bend > 8° or
     hip-X > 4 cm in the pre-rise window, mark `push_press = True`
     and exclude from set aggregation.
  6. Compute all 38 spec metrics per rep at the correct extreme.
  7. 5-tier sub-scoring per spec §7.1, variant-aware thresholds.
  8. Category subtotals (Safety 45% / Technique 35% / Performance 20%).
  9. Geometric composite (user preference carried over from prior).
 10. 8 hard-fail safety overrides per spec §7.5.
 11. Set aggregation: mean (headline) / worst / last-3 across VALID
     reps only; push-press and frame-exit reps excluded.
 12. Annotated frames: best+worst rep get all 4 cameras × 3 extremes;
     middle reps get sagittal-only × 3 extremes.

Returns the standard ExerciseResult dict augmented with `composite_score`.
"""
from __future__ import annotations

import math
from statistics import mean as _mean

from utils.landmarks import (
    extract_all_landmarks, get_landmark_px, midpoint_px, LM,
    confidence_score,
)
from utils.angles import angle_3pt
from utils.scoring import build_metric, build_result
from utils.frame_annotator import (
    extract_frame_at, frame_to_base64, render_sample_frame,
    draw_skeleton, draw_angle_arc, draw_reference_line,
    draw_callout, draw_phase_label, draw_title_strip, draw_metric_overlay,
    draw_legend, _lm_to_px,
    COL_CYAN,
)
from utils.bar_tracker import (
    track_bar_path, mean_concentric_velocity, estimate_1rm,
)
from utils.muscle_inference import infer_overhead_press

OHP_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
    (0, 11), (0, 12),
]


# ─────────────────────────────────────────────────────────────────────
# 5-tier scoring helpers (spec §7.1). Identical algorithm to prior rewrites.
# ─────────────────────────────────────────────────────────────────────

def _interp(x, lo, hi, lo_score, hi_score):
    if hi == lo:
        return lo_score
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return lo_score + t * (hi_score - lo_score)


def score_one_sided(x, very_good, good, yellow, bad, higher_is_better):
    if x is None:
        return 0.0
    very_bad_width = max(1e-6, abs(bad - yellow))
    if higher_is_better:
        if x >= very_good:
            return 100.0
        if x >= good:
            return _interp(x, good, very_good, 75.0, 90.0)
        if x >= yellow:
            return _interp(x, yellow, good, 60.0, 75.0)
        if x >= bad:
            return _interp(x, bad, yellow, 40.0, 60.0)
        floor_x = bad - very_bad_width
        return max(0.0, _interp(x, floor_x, bad, 0.0, 40.0))
    else:
        if x <= very_good:
            return 100.0
        if x <= good:
            return _interp(x, very_good, good, 90.0, 75.0)
        if x <= yellow:
            return _interp(x, good, yellow, 75.0, 60.0)
        if x <= bad:
            return _interp(x, yellow, bad, 60.0, 40.0)
        ceil_x = bad + very_bad_width
        return max(0.0, _interp(x, bad, ceil_x, 40.0, 0.0))


def score_two_sided(x, ideal, tolerances):
    if x is None:
        return 0.0
    return score_one_sided(abs(x - ideal), *tolerances, higher_is_better=False)


def score_ranged(x, very_good_lo, very_good_hi, good_lo, good_hi,
                 yellow_lo, yellow_hi, bad_lo, bad_hi):
    if x is None:
        return 0.0
    if very_good_lo <= x <= very_good_hi:
        return 100.0
    if good_lo <= x < very_good_lo:
        return _interp(x, good_lo, very_good_lo, 75.0, 90.0)
    if very_good_hi < x <= good_hi:
        return _interp(x, very_good_hi, good_hi, 90.0, 75.0)
    if yellow_lo <= x < good_lo:
        return _interp(x, yellow_lo, good_lo, 60.0, 75.0)
    if good_hi < x <= yellow_hi:
        return _interp(x, good_hi, yellow_hi, 75.0, 60.0)
    if bad_lo <= x < yellow_lo:
        return _interp(x, bad_lo, yellow_lo, 40.0, 60.0)
    if yellow_hi < x <= bad_hi:
        return _interp(x, yellow_hi, bad_hi, 60.0, 40.0)
    if x < bad_lo:
        return max(0.0, _interp(x, bad_lo - (yellow_lo - bad_lo), bad_lo, 0.0, 40.0))
    return max(0.0, _interp(x, bad_hi, bad_hi + (bad_hi - yellow_hi), 40.0, 0.0))


# ─────────────────────────────────────────────────────────────────────
# Spec §7.3 — within-category weights.  Military and Seated DB diverge.
# ─────────────────────────────────────────────────────────────────────

SAFETY_W_MILITARY = {
    'lumbar_arch':       35,
    'hip_thrust':        15,
    'knee_flexion':      15,
    'wrist_angle':       10,
    'bar_over_midfoot':  10,
    'grip_width':         8,
    'elbow_flare':        7,
}

SAFETY_W_SEATED_DB = {
    'lumbar_arch':       30,
    'back_contact':      20,
    'db_symmetry':       15,
    'wrist_angle':       10,
    'elbow_flare':       10,
    'wrist_lateral':      8,
    'db_path_parallel':   7,
}

TECH_W_MILITARY = {
    'bar_horizontal':    20,
    'head_under_bar':    15,
    'elbow_lockout':     15,
    'shoulder_flex_lockout': 12,
    'rom_bottom':        12,
    'setup_quality':     10,
    'lockout_hold':       8,
    'torso_lean_lockout': 8,
}

TECH_W_SEATED_DB = {
    'bar_horizontal':    15,
    'head_under_bar':     5,
    'elbow_lockout':     18,
    'shoulder_flex_lockout': 14,
    'rom_bottom':        14,
    'setup_quality':     14,
    'lockout_hold':      10,
    'torso_lean_lockout': 10,
}

PERF_W_MILITARY = {
    'setup_time':        10,
    'concentric_tempo':  35,
    'eccentric_tempo':   15,
    'ec_ratio':          10,
    'sticking_point':    15,
    'rep_consistency':   15,
}

PERF_W_SEATED_DB = {
    'setup_time':        10,
    'concentric_tempo':  20,
    'eccentric_tempo':   15,
    'ec_ratio':          10,
    'sticking_point':    15,
    'db_tempo_symmetry': 15,
    'rep_consistency':   15,
}

# Global category weights — spec §7.2.  Safety highest for OHP.
CATEGORY_WEIGHTS = {'safety': 0.45, 'technique': 0.35, 'performance': 0.20}


def _safety_weights(variant):
    return SAFETY_W_SEATED_DB if variant == 'seated-db' else SAFETY_W_MILITARY


def _tech_weights(variant):
    return TECH_W_SEATED_DB if variant == 'seated-db' else TECH_W_MILITARY


def _perf_weights(variant):
    return PERF_W_SEATED_DB if variant == 'seated-db' else PERF_W_MILITARY


# ─────────────────────────────────────────────────────────────────────
# Spec §7.5 — hard-fail safety overrides.
# Push-press reclassification is handled separately (BEFORE scoring) as
# a DNC-pattern exclusion, not a cap.  These overrides cap composite.
# ─────────────────────────────────────────────────────────────────────

def _override_specs(variant):
    base = [
        {
            'key': 'lumbar_bow',
            'condition': 'Lumbar hyperextension > 20° (bow-like arch, spinal-load risk)',
            'metric': 'Lumbar arch delta',
            'cap': 55,
            'eval': lambda mv: (mv['lumbar_arch_delta_deg'] > 20,
                                f"{mv['lumbar_arch_delta_deg']:.1f}°"),
        },
        {
            'key': 'bar_forward_lockout',
            'condition': 'Bar / DB forward of head at lockout (shoulder flexion > 28°)',
            'metric': 'Shoulder flexion at lockout',
            'cap': 55,
            'eval': lambda mv: (mv['shoulder_flex_lockout_deg'] > 28,
                                f"{mv['shoulder_flex_lockout_deg']:.1f}°"),
        },
        {
            'key': 'wrist_hyperext',
            'condition': 'Wrist hyperextension > 50° under load',
            'metric': 'Wrist angle (max extension)',
            'cap': 70,    # cap at C (≤70), not D
            'eval': lambda mv: (mv['wrist_ext_deg'] > 50,
                                f"{mv['wrist_ext_deg']:.1f}°"),
        },
        {
            'key': 'failed_lockout',
            'condition': 'Failed lockout (elbow < 150° at peak)',
            'metric': 'Elbow angle at lockout',
            'cap': 55,
            'eval': lambda mv: (mv['elbow_lockout_deg'] < 150,
                                f"{mv['elbow_lockout_deg']:.0f}°"),
        },
    ]
    if variant != 'seated-db':
        base.append({
            'key': 'hip_thrust_kipping',
            'condition': 'Hip-X thrust > 12 cm (kipping equivalent, hard fail)',
            'metric': 'Hip-X thrust during concentric',
            'cap': 55,
            'eval': lambda mv: (mv['hip_thrust_cm'] > 12,
                                f"{mv['hip_thrust_cm']:.1f} cm"),
        })
    else:
        base.append({
            'key': 'unsafe_asymmetry',
            'condition': 'DB asymmetry > 12 cm (unsafe shoulder loading)',
            'metric': 'DB symmetry (peak height delta)',
            'cap': 55,
            'eval': lambda mv: (mv['db_symmetry_cm'] > 12,
                                f"{mv['db_symmetry_cm']:.1f} cm"),
        })
    return base


# ─────────────────────────────────────────────────────────────────────
# Spec §8 — grade mapping
# ─────────────────────────────────────────────────────────────────────

def grade_from_composite(c):
    if c >= 90: return 'A', 'Very Good'
    if c >= 75: return 'B', 'Good'
    if c >= 60: return 'C', 'Yellow Flag'
    if c >= 40: return 'D', 'Bad'
    return 'E', 'Very Bad'


def status_from_grade(letter):
    return {'A': 'GOOD', 'B': 'GOOD', 'C': 'NEEDS IMPROVEMENT',
            'D': 'NEEDS IMPROVEMENT', 'E': 'RESTRICTED'}[letter]


# ─────────────────────────────────────────────────────────────────────
# Per-view feature extraction
# ─────────────────────────────────────────────────────────────────────

def _side_idx(side='left'):
    return {
        'ear':      LM['LEFT_EAR']      if side == 'left' else LM['RIGHT_EAR'],
        'shoulder': LM['LEFT_SHOULDER'] if side == 'left' else LM['RIGHT_SHOULDER'],
        'elbow':    LM['LEFT_ELBOW']    if side == 'left' else LM['RIGHT_ELBOW'],
        'wrist':    LM['LEFT_WRIST']    if side == 'left' else LM['RIGHT_WRIST'],
        'hip':      LM['LEFT_HIP']      if side == 'left' else LM['RIGHT_HIP'],
        'knee':     LM['LEFT_KNEE']     if side == 'left' else LM['RIGHT_KNEE'],
        'ankle':    LM['LEFT_ANKLE']    if side == 'left' else LM['RIGHT_ANKLE'],
        'index':    LM['LEFT_INDEX']    if side == 'left' else LM['RIGHT_INDEX'],
    }


def _pick_near_side(frames):
    lv, rv = [], []
    for f in frames:
        lm = f['landmarks']
        if lm is None:
            continue
        lv.append(lm[LM['LEFT_SHOULDER']][3])
        rv.append(lm[LM['RIGHT_SHOULDER']][3])
    if not lv or not rv:
        return 'left'
    return 'left' if _mean(lv) >= _mean(rv) else 'right'


def _process_view(path, view_name, plate_size_kg=None):
    """Extract pose + per-frame signals from one camera video.

    Returns a dict carrying raw landmark series + derived signals used
    for rep detection (state machine on wrist-centre-Y / elbow-angle)
    and the 38 spec metrics.
    """
    data = extract_all_landmarks(path)
    frames = data['frames']
    fps = data['fps']
    w, h = data['width'], data['height']

    side = _pick_near_side(frames)
    idx = _side_idx(side)

    # Bar tracking on the sagittal view only (plate centroid + wrist blend)
    bar_data = None
    if view_name == 'sagittal' and plate_size_kg is not None:
        try:
            bar_data = track_bar_path(path, plate_size_kg=plate_size_kg)
        except Exception:
            bar_data = None
    centres = bar_data['centres'] if bar_data else [None] * len(frames)
    bar_quality = bar_data.get('quality', [0.0] * len(centres)) if bar_data else [0.0] * len(centres)
    bar_med_q = float(bar_data.get('median_quality', 0.0)) if bar_data else 0.0
    px_per_cm = bar_data.get('px_per_cm', 0.0) if bar_data else 0.0

    # Per-frame signals (one near-side primary + bilateral series for symmetry)
    wrist_x, wrist_y = [], []
    elbow_x, elbow_y = [], []
    shoulder_x, shoulder_y = [], []
    hip_x, hip_y = [], []
    knee_x, knee_y = [], []
    ankle_x, ankle_y = [], []
    ear_x, ear_y = [], []
    nose_x, nose_y = [], []
    index_x, index_y = [], []
    lwr_x, lwr_y, rwr_x, rwr_y = [], [], [], []
    lel_x, lel_y, rel_x, rel_y = [], [], [], []
    lsh_x, lsh_y, rsh_x, rsh_y = [], [], [], []
    lhp_x, lhp_y, rhp_x, rhp_y = [], [], [], []
    lkn_x, lkn_y, rkn_x, rkn_y = [], [], [], []
    lan_x, lan_y, ran_x, ran_y = [], [], [], []
    plate_x = [c[0] if c else None for c in centres]
    plate_y = [c[1] if c else None for c in centres]
    # Wrist-centre (averaged L/R) for barbell rep detection.
    # For dumbbells the analyzer will use L and R independently downstream.
    wc_x, wc_y = [], []
    elbow_angle = []
    elbow_left_angle = []; elbow_right_angle = []
    knee_angle = []
    hip_angle = []
    wrist_flex_deg = []   # elbow-wrist-index, deviation from 180
    torso_lean_deg = []   # hip→shoulder vs vertical
    body_inclination = [] # ankle→shoulder vs vertical (standing)
    backrest_angle_deg = []  # seated-only proxy = same as torso_lean

    for f in frames:
        lm = f['landmarks']
        if lm is None:
            for arr in (wrist_x, wrist_y, elbow_x, elbow_y, shoulder_x, shoulder_y,
                        hip_x, hip_y, knee_x, knee_y, ankle_x, ankle_y,
                        ear_x, ear_y, nose_x, nose_y, index_x, index_y,
                        lwr_x, lwr_y, rwr_x, rwr_y, lel_x, lel_y, rel_x, rel_y,
                        lsh_x, lsh_y, rsh_x, rsh_y, lhp_x, lhp_y, rhp_x, rhp_y,
                        lkn_x, lkn_y, rkn_x, rkn_y, lan_x, lan_y, ran_x, ran_y,
                        wc_x, wc_y,
                        elbow_angle, elbow_left_angle, elbow_right_angle,
                        knee_angle, hip_angle, wrist_flex_deg,
                        torso_lean_deg, body_inclination, backrest_angle_deg):
                arr.append(None)
            continue
        wr = get_landmark_px(lm, idx['wrist'], w, h)
        el = get_landmark_px(lm, idx['elbow'], w, h)
        sh = get_landmark_px(lm, idx['shoulder'], w, h)
        hp = get_landmark_px(lm, idx['hip'], w, h)
        kn = get_landmark_px(lm, idx['knee'], w, h)
        an = get_landmark_px(lm, idx['ankle'], w, h)
        er = get_landmark_px(lm, idx['ear'], w, h)
        no = get_landmark_px(lm, LM['NOSE'], w, h)
        ix = get_landmark_px(lm, idx['index'], w, h)
        lw = get_landmark_px(lm, LM['LEFT_WRIST'], w, h)
        rw = get_landmark_px(lm, LM['RIGHT_WRIST'], w, h)
        le = get_landmark_px(lm, LM['LEFT_ELBOW'], w, h)
        re_ = get_landmark_px(lm, LM['RIGHT_ELBOW'], w, h)
        ls = get_landmark_px(lm, LM['LEFT_SHOULDER'], w, h)
        rs = get_landmark_px(lm, LM['RIGHT_SHOULDER'], w, h)
        lhp = get_landmark_px(lm, LM['LEFT_HIP'], w, h)
        rhp = get_landmark_px(lm, LM['RIGHT_HIP'], w, h)
        lkn_p = get_landmark_px(lm, LM['LEFT_KNEE'], w, h)
        rkn_p = get_landmark_px(lm, LM['RIGHT_KNEE'], w, h)
        lan_p = get_landmark_px(lm, LM['LEFT_ANKLE'], w, h)
        ran_p = get_landmark_px(lm, LM['RIGHT_ANKLE'], w, h)
        smid = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
        hmid = midpoint_px(lm, LM['LEFT_HIP'], LM['RIGHT_HIP'], w, h)
        amid = midpoint_px(lm, LM['LEFT_ANKLE'], LM['RIGHT_ANKLE'], w, h)
        kmid = midpoint_px(lm, LM['LEFT_KNEE'], LM['RIGHT_KNEE'], w, h)

        wrist_x.append(wr[0] if wr else None); wrist_y.append(wr[1] if wr else None)
        elbow_x.append(el[0] if el else None); elbow_y.append(el[1] if el else None)
        shoulder_x.append(sh[0] if sh else None); shoulder_y.append(sh[1] if sh else None)
        hip_x.append(hp[0] if hp else None); hip_y.append(hp[1] if hp else None)
        knee_x.append(kn[0] if kn else None); knee_y.append(kn[1] if kn else None)
        ankle_x.append(an[0] if an else None); ankle_y.append(an[1] if an else None)
        ear_x.append(er[0] if er else None); ear_y.append(er[1] if er else None)
        nose_x.append(no[0] if no else None); nose_y.append(no[1] if no else None)
        index_x.append(ix[0] if ix else None); index_y.append(ix[1] if ix else None)
        lwr_x.append(lw[0] if lw else None); lwr_y.append(lw[1] if lw else None)
        rwr_x.append(rw[0] if rw else None); rwr_y.append(rw[1] if rw else None)
        lel_x.append(le[0] if le else None); lel_y.append(le[1] if le else None)
        rel_x.append(re_[0] if re_ else None); rel_y.append(re_[1] if re_ else None)
        lsh_x.append(ls[0] if ls else None); lsh_y.append(ls[1] if ls else None)
        rsh_x.append(rs[0] if rs else None); rsh_y.append(rs[1] if rs else None)
        lhp_x.append(lhp[0] if lhp else None); lhp_y.append(lhp[1] if lhp else None)
        rhp_x.append(rhp[0] if rhp else None); rhp_y.append(rhp[1] if rhp else None)
        lkn_x.append(lkn_p[0] if lkn_p else None); lkn_y.append(lkn_p[1] if lkn_p else None)
        rkn_x.append(rkn_p[0] if rkn_p else None); rkn_y.append(rkn_p[1] if rkn_p else None)
        lan_x.append(lan_p[0] if lan_p else None); lan_y.append(lan_p[1] if lan_p else None)
        ran_x.append(ran_p[0] if ran_p else None); ran_y.append(ran_p[1] if ran_p else None)
        # Wrist centre = midpoint of L/R wrist; for DB this is misleading
        # for symmetry metrics but fine for phase detection.
        if lw and rw:
            wc_x.append((lw[0] + rw[0]) / 2.0)
            wc_y.append((lw[1] + rw[1]) / 2.0)
        elif wr:
            wc_x.append(wr[0]); wc_y.append(wr[1])
        else:
            wc_x.append(None); wc_y.append(None)

        elbow_left_angle.append(angle_3pt(ls, le, lw) if (ls and le and lw) else None)
        elbow_right_angle.append(angle_3pt(rs, re_, rw) if (rs and re_ and rw) else None)
        elbow_angle.append(angle_3pt(sh, el, wr) if (sh and el and wr) else None)
        knee_angle.append(angle_3pt(hp, kn, an) if (hp and kn and an) else None)
        hip_angle.append(angle_3pt(sh, hp, kn) if (sh and hp and kn) else None)
        if el and wr and ix:
            wrist_flex_deg.append(180.0 - angle_3pt(el, wr, ix))
        else:
            wrist_flex_deg.append(None)
        # Torso lean: hip → shoulder vector from vertical (posterior = +)
        if smid and hmid:
            dx = smid[0] - hmid[0]
            dy = hmid[1] - smid[1]   # image y down → +dy means shoulder higher
            torso_lean_deg.append(math.degrees(math.atan2(dx, abs(dy) + 1e-6)))
        else:
            torso_lean_deg.append(None)
        # Body inclination: ankle → shoulder from vertical (standing only)
        if smid and amid:
            dx = smid[0] - amid[0]
            dy = amid[1] - smid[1]
            body_inclination.append(math.degrees(math.atan2(dx, abs(dy) + 1e-6)))
        else:
            body_inclination.append(None)
        # Backrest angle proxy (seated): same torso lean signal
        backrest_angle_deg.append(torso_lean_deg[-1])

    return {
        'name': view_name,
        'frames': frames, 'fps': fps, 'w': w, 'h': h, 'side': side, 'idx': idx,
        'centres': centres, 'bar_quality': bar_quality, 'bar_med_q': bar_med_q,
        'px_per_cm': px_per_cm,
        'plate_x': plate_x, 'plate_y': plate_y,
        'wrist_x': wrist_x, 'wrist_y': wrist_y,
        'elbow_x': elbow_x, 'elbow_y': elbow_y,
        'shoulder_x': shoulder_x, 'shoulder_y': shoulder_y,
        'hip_x': hip_x, 'hip_y': hip_y,
        'knee_x': knee_x, 'knee_y': knee_y,
        'ankle_x': ankle_x, 'ankle_y': ankle_y,
        'ear_x': ear_x, 'ear_y': ear_y, 'nose_x': nose_x, 'nose_y': nose_y,
        'index_x': index_x, 'index_y': index_y,
        'lwr_x': lwr_x, 'lwr_y': lwr_y, 'rwr_x': rwr_x, 'rwr_y': rwr_y,
        'lel_x': lel_x, 'lel_y': lel_y, 'rel_x': rel_x, 'rel_y': rel_y,
        'lsh_x': lsh_x, 'lsh_y': lsh_y, 'rsh_x': rsh_x, 'rsh_y': rsh_y,
        'lhp_x': lhp_x, 'lhp_y': lhp_y, 'rhp_x': rhp_x, 'rhp_y': rhp_y,
        'lkn_x': lkn_x, 'lkn_y': lkn_y, 'rkn_x': rkn_x, 'rkn_y': rkn_y,
        'lan_x': lan_x, 'lan_y': lan_y, 'ran_x': ran_x, 'ran_y': ran_y,
        'wc_x': wc_x, 'wc_y': wc_y,
        'elbow_angle': elbow_angle,
        'elbow_left_angle': elbow_left_angle, 'elbow_right_angle': elbow_right_angle,
        'knee_angle': knee_angle, 'hip_angle': hip_angle,
        'wrist_flex_deg': wrist_flex_deg,
        'torso_lean_deg': torso_lean_deg,
        'body_inclination': body_inclination,
        'backrest_angle_deg': backrest_angle_deg,
    }


# ─────────────────────────────────────────────────────────────────────
# Rep detection — TRIPLE EXTREME (setup / sticking / lockout).
# Spec §12.3 state machine on wrist-centre-Y + elbow_angle.
# ─────────────────────────────────────────────────────────────────────

def _fill_signal(arr):
    out = []; last = None
    for v in arr:
        if v is None:
            out.append(last if last is not None else 0.0)
        else:
            out.append(v); last = v
    return out


def _detect_reps(view, target_reps):
    """Return list of dicts per rep:
       {idx, start, setup, sticking, lockout, end, frame_exit, push_press_candidate}.

    Push-press detection is NOT done here — it requires the knee/hip
    pre-rise window which is computed in `_compute_rep_metrics`.
    """
    fps = view['fps']
    target = max(1, int(target_reps or 3))
    wc_y = view['wc_y']
    elbow_angle = view['elbow_angle']
    h = view['h']

    filled_wy = _fill_signal(wc_y)
    filled_el = _fill_signal(elbow_angle)
    if not filled_wy:
        return []

    n = len(filled_wy)

    # State machine: REST → SETUP → CONCENTRIC → LOCKOUT → ECCENTRIC → REST.
    # SETUP = elbow ∈ [70, 120], wrist-Y stable + below "lockout band"
    # CONCENTRIC = wrist-Y decreasing (in image coords); elbow flexion -> extension
    # LOCKOUT = elbow > 170 AND wrist-Y at local minimum
    # ECCENTRIC = wrist-Y increasing
    # We refine SETUP / STICKING / LOCKOUT per rep after the state machine.

    state = 'WAIT_SETUP'
    rep_start = 0
    setup_frame = 0
    lockout_frame = 0
    sticking_frame = 0
    reps = []

    for i in range(n):
        wy = filled_wy[i]
        el = filled_el[i]
        if state == 'WAIT_SETUP':
            # Look for a stable setup: elbow ~85-110, wrist near shoulder
            if 70 <= el <= 120:
                # Wait for stability
                stable = True
                w_lo = max(0, i - 5)
                for k in range(w_lo, i + 1):
                    if abs(filled_wy[k] - wy) > h * 0.02:
                        stable = False; break
                if stable:
                    state = 'SETUP'
                    setup_frame = i
                    rep_start = i
        elif state == 'SETUP':
            # Look for the bar to rise: wrist_y decreasing significantly
            if wy < filled_wy[setup_frame] - h * 0.05:
                state = 'CONCENTRIC'
        elif state == 'CONCENTRIC':
            # Track for lockout: elbow > 170 AND wrist at local minimum
            if el >= 170:
                # Confirm wrist at local minimum
                refine_end = min(n - 1, i + int(fps * 0.3))
                best_y = wy; best_i = i
                for j in range(i, refine_end + 1):
                    if filled_wy[j] < best_y:
                        best_y = filled_wy[j]; best_i = j
                lockout_frame = best_i
                # Compute sticking point: velocity minimum during concentric
                sticking_frame = _find_sticking(filled_wy, setup_frame, lockout_frame, fps)
                state = 'LOCKOUT_HOLD'
        elif state == 'LOCKOUT_HOLD':
            # Wait for wrist-y to start rising (bar coming down)
            if wy > filled_wy[lockout_frame] + h * 0.02:
                state = 'ECCENTRIC'
        elif state == 'ECCENTRIC':
            # Wait for elbow to return to setup range
            if el <= 120 and wy >= filled_wy[setup_frame] - h * 0.03:
                end = i
                # Detect frame exit: wc_y near top of frame at lockout
                frame_exit = filled_wy[lockout_frame] < h * 0.05
                reps.append({
                    'idx': len(reps) + 1,
                    'start': rep_start,
                    'setup': setup_frame,
                    'sticking': sticking_frame,
                    'lockout': lockout_frame,
                    'end': end,
                    'frame_exit': frame_exit,
                    # Filled later
                    'push_press': False,
                    'dnc': False,
                })
                state = 'WAIT_SETUP'

    # If we ended mid-rep with a confirmed lockout, count it
    if state in ('LOCKOUT_HOLD', 'ECCENTRIC') and lockout_frame > 0:
        reps.append({
            'idx': len(reps) + 1,
            'start': rep_start,
            'setup': setup_frame,
            'sticking': sticking_frame,
            'lockout': lockout_frame,
            'end': n - 1,
            'frame_exit': filled_wy[lockout_frame] < h * 0.05,
            'push_press': False,
            'dnc': False,
        })

    # Trim to target count by deepest lockout (lowest wrist-y at lockout)
    if target and len(reps) > target:
        reps = sorted(reps,
                      key=lambda r: filled_wy[r['lockout']] if r['lockout'] < len(filled_wy) else 1e9
                      )[:target]
        reps = sorted(reps, key=lambda r: r['lockout'])
    for i, r in enumerate(reps):
        r['idx'] = i + 1
    return reps


def _find_sticking(wy_signal, setup, lockout, fps):
    """Find the frame of velocity minimum during concentric (the sticking point).
    Returns the frame index closest to 25-45% of bar travel ideal."""
    if lockout <= setup + 2:
        return setup
    # Vertical velocity (in image coords, upward = decreasing y)
    vels = []
    for fi in range(setup, lockout):
        v0 = wy_signal[fi]; v1 = wy_signal[fi + 1]
        # Upward velocity is positive
        vels.append(v0 - v1)
    if not vels:
        return (setup + lockout) // 2
    # Smooth: 5-frame window
    smoothed = []
    for i in range(len(vels)):
        a = max(0, i - 2); b = min(len(vels), i + 3)
        smoothed.append(_mean(vels[a:b]))
    # Sticking = frame of minimum positive velocity (slowest upward motion)
    min_v = float('inf'); min_i = (lockout - setup) // 2
    for i, v in enumerate(smoothed):
        if v > 0 and v < min_v:
            min_v = v; min_i = i
    return setup + min_i


# ─────────────────────────────────────────────────────────────────────
# Push-press detection (HARD CLASSIFIER per spec §2)
# ─────────────────────────────────────────────────────────────────────

def _detect_push_press(sag, rep, variant):
    """Spec §2: if knee bend > 8° OR hip-X > 4 cm BEFORE wrist rises 5 cm
    from setup, classify as push_press.  Returns (is_push_press, diagnostic).

    Seated DB exempted: no knee/hip kinetic chain to "drive" the rep.
    """
    if variant == 'seated-db':
        return False, None
    fps = sag['fps']
    setup = rep['setup']; lockout = rep['lockout']
    wc_y = sag['wc_y']; knee_angle = sag['knee_angle']
    hip_x = sag['hip_x']; px_per_cm = sag['px_per_cm']

    setup_wy = wc_y[setup] if setup < len(wc_y) else None
    if setup_wy is None:
        return False, None
    setup_knee = knee_angle[setup] if setup < len(knee_angle) else None
    setup_hip_x = hip_x[setup] if setup < len(hip_x) else None
    if setup_knee is None or setup_hip_x is None:
        return False, None

    # 5 cm in pixels — use px_per_cm if available, otherwise fall back to
    # 5% of frame height (rough proxy for a 100 cm-tall framing window)
    rise_5cm_px = (px_per_cm * 5.0) if px_per_cm > 0 else (sag['h'] * 0.05)

    # Scan from setup to the point where wrist has risen 5 cm
    for fi in range(setup, min(lockout + 1, len(wc_y))):
        wy = wc_y[fi]
        if wy is None:
            continue
        # Has bar risen 5 cm? (image y decreasing → up)
        if (setup_wy - wy) >= rise_5cm_px:
            return False, None   # passed the 5 cm gate without push-press detection
        # Check knee bend
        kn = knee_angle[fi] if fi < len(knee_angle) else None
        if kn is not None and (setup_knee - kn) > 8:
            return True, f"knee bent {setup_knee - kn:.1f}° before bar rose 5 cm"
        # Check hip thrust (X displacement)
        hx = hip_x[fi] if fi < len(hip_x) else None
        if hx is not None:
            hip_disp_cm = abs(hx - setup_hip_x) / max(1e-3, (px_per_cm if px_per_cm > 0 else 10))
            if hip_disp_cm > 4.0:
                return True, f"hip thrust {hip_disp_cm:.1f} cm before bar rose 5 cm"
    return False, None


# ─────────────────────────────────────────────────────────────────────
# Per-rep metric computation — all 38 spec metrics
# ─────────────────────────────────────────────────────────────────────

def _safe_at(arr, idx, default=0.0):
    if 0 <= idx < len(arr) and arr[idx] is not None:
        return arr[idx]
    return default


def _nearest_frame(view, target_frame, sag_ref):
    if view is None or not view['frames']:
        return target_frame
    sag_total = len(sag_ref['frames'])
    if sag_total == 0:
        return 0
    fr = int(target_frame / sag_total * len(view['frames']))
    return max(0, min(fr, len(view['frames']) - 1))


def _compute_rep_metrics(rep, sag, front, post, obl, variant, stance,
                          backrest_deg, athlete_height_cm):
    """Compute every spec metric for ONE rep.
    SETUP-frame metrics: S1, S2, S3, S4, F1, F4
    LOCKOUT-frame metrics: S7, S11, S12, S13, S15
    Across-rep metrics: S5, S6, S8, S9, S10, S14, S16, S17, S18, F2, F3,
                        F5, F6, F7, P2, P3, P4, T1-T7
    """
    setup, sticking, lockout, end = rep['setup'], rep['sticking'], rep['lockout'], rep['end']
    fps = sag['fps']
    px_per_cm = sag['px_per_cm']
    mv = {}

    # Pixel-to-cm scale (fallback to athlete height proxy)
    if px_per_cm > 0:
        cm_per_px = 1.0 / px_per_cm
    else:
        # Use athlete height / image height ratio
        if athlete_height_cm and athlete_height_cm > 0:
            cm_per_px = athlete_height_cm / float(sag['h'])
        else:
            cm_per_px = 170.0 / float(sag['h'])

    # ── S1: Bar start vs clavicle (wrist_y vs shoulder_y at SETUP) ──
    wy_setup = _safe_at(sag['wc_y'], setup, None)
    sy_setup = _safe_at(sag['shoulder_y'], setup, None)
    if wy_setup is not None and sy_setup is not None:
        # Image y down → wrist below shoulder if wy > sy. Spec measures
        # bar offset from clavicle — positive = bar above/floating, negative = on rack.
        mv['s1_bar_offset_cm'] = abs(wy_setup - sy_setup) * cm_per_px
    else:
        mv['s1_bar_offset_cm'] = 2.0

    # ── S2: Forearm vertical at start ──
    # Angle of (elbow → wrist) vector from gravity-down
    el_setup = (_safe_at(sag['elbow_x'], setup, None),
                _safe_at(sag['elbow_y'], setup, None))
    wr_setup = (_safe_at(sag['wrist_x'], setup, None),
                _safe_at(sag['wrist_y'], setup, None))
    if None not in el_setup and None not in wr_setup:
        dx = wr_setup[0] - el_setup[0]
        dy = wr_setup[1] - el_setup[1]   # image y down, gravity points to +y
        mv['s2_forearm_vert_deg'] = abs(math.degrees(math.atan2(dx, abs(dy) + 1e-6)))
    else:
        mv['s2_forearm_vert_deg'] = 5.0

    # ── S3: Elbow angle at start ──
    mv['s3_elbow_setup_deg'] = _safe_at(sag['elbow_angle'], setup, 95.0)

    # ── S4: Torso lean at start ──
    mv['s4_torso_lean_setup_deg'] = abs(_safe_at(sag['torso_lean_deg'], setup, 3.0))
    # Subtract backrest baseline for seated DB (so the user's deviation
    # from the bench's pad angle, not the pad's angle itself, is scored).
    if variant == 'seated-db' and backrest_deg and backrest_deg > 0:
        # 90° backrest = 0° baseline lean; 75° backrest = 15° baseline lean
        baseline = 90.0 - float(backrest_deg)
        mv['s4_torso_lean_setup_deg'] = max(0.0, mv['s4_torso_lean_setup_deg'] - baseline)

    # ── S5: Bar / DB horizontal max displacement (max |Δx| from setup) ──
    bxs = sag['wc_x']
    setup_x = bxs[setup] if setup < len(bxs) else None
    if setup_x is not None:
        max_dx_px = 0.0
        for fi in range(setup, min(end + 1, len(bxs))):
            v = bxs[fi]
            if v is not None:
                max_dx_px = max(max_dx_px, abs(v - setup_x))
        mv['s5_bar_horizontal_cm'] = max_dx_px * cm_per_px
    else:
        mv['s5_bar_horizontal_cm'] = 3.0
    # Anthropometry adjustment: long-arm lifters get 20% relaxation.
    # Forearm length proxy: elbow_y - wrist_y at setup
    if athlete_height_cm and el_setup[1] is not None and wr_setup[1] is not None:
        forearm_px = abs(wr_setup[1] - el_setup[1])
        forearm_cm = forearm_px * cm_per_px
        if forearm_cm / athlete_height_cm > 0.16:
            mv['s5_long_arm_relaxed'] = True
            mv['s5_bar_horizontal_cm_adjusted'] = mv['s5_bar_horizontal_cm'] * 0.8
        else:
            mv['s5_long_arm_relaxed'] = False
            mv['s5_bar_horizontal_cm_adjusted'] = mv['s5_bar_horizontal_cm']
    else:
        mv['s5_long_arm_relaxed'] = False
        mv['s5_bar_horizontal_cm_adjusted'] = mv['s5_bar_horizontal_cm']

    # ── S6: Head under bar (nose-X delta SETUP → LOCKOUT, signed) ──
    nx_setup = _safe_at(sag['nose_x'], setup, None)
    nx_lock = _safe_at(sag['nose_x'], lockout, None)
    # Fall back to ear if nose occluded
    if nx_setup is None:
        nx_setup = _safe_at(sag['ear_x'], setup, None)
    if nx_lock is None:
        nx_lock = _safe_at(sag['ear_x'], lockout, None)
    if nx_setup is not None and nx_lock is not None and setup_x is not None:
        # Toward bar column = positive. Bar column = setup_x.
        # If bar is "in front of" setup_nose, +x; head moving "toward bar" = +x
        dir_to_bar = 1.0 if setup_x >= nx_setup else -1.0
        mv['s6_head_under_bar_cm'] = (nx_lock - nx_setup) * dir_to_bar * cm_per_px
    else:
        mv['s6_head_under_bar_cm'] = 1.5

    # ── S7: Torso lean at lockout (max posterior during upper-half) ──
    half_start = (setup + lockout) // 2
    worst_lean = 0.0
    for fi in range(half_start, min(lockout + 1, len(sag['torso_lean_deg']))):
        v = sag['torso_lean_deg'][fi]
        if v is not None:
            worst_lean = max(worst_lean, abs(v))
    if variant == 'seated-db' and backrest_deg and backrest_deg > 0:
        baseline = 90.0 - float(backrest_deg)
        worst_lean = max(0.0, worst_lean - baseline)
    mv['s7_torso_lean_lockout_deg'] = worst_lean

    # ── S8: Lumbar arch delta (shoulder-hip-knee three-point Δ from setup) ──
    setup_lumbar = _safe_at(sag['hip_angle'], setup, 180.0)
    worst_arch = 0.0
    for fi in range(setup, min(lockout + 1, len(sag['hip_angle']))):
        v = sag['hip_angle'][fi]
        if v is not None:
            # More extension = angle opening past 180° → setup - v < 0 = extension
            # Take the WORST extension = most negative Δ
            d = setup_lumbar - v
            if d < 0:
                worst_arch = max(worst_arch, -d)
    mv['lumbar_arch_delta_deg'] = worst_arch
    mv['s8_lumbar_arch_delta_deg'] = worst_arch

    # ── S9: Knee flexion during press (max Δ from setup, standing only) ──
    if variant != 'seated-db':
        setup_knee = _safe_at(sag['knee_angle'], setup, 178.0)
        max_knee_flex = 0.0
        for fi in range(setup, min(lockout + 1, len(sag['knee_angle']))):
            v = sag['knee_angle'][fi]
            if v is not None:
                # Flexion = knee angle decreasing
                max_knee_flex = max(max_knee_flex, setup_knee - v)
        mv['s9_knee_flex_deg'] = max(0.0, max_knee_flex)
    else:
        mv['s9_knee_flex_deg'] = 0.0

    # ── S10: Hip-X thrust (forward displacement during concentric) ──
    if variant != 'seated-db':
        setup_hx = _safe_at(sag['hip_x'], setup, None)
        max_hip_thrust_cm = 0.0
        if setup_hx is not None:
            for fi in range(setup, min(lockout + 1, len(sag['hip_x']))):
                v = sag['hip_x'][fi]
                if v is not None:
                    max_hip_thrust_cm = max(max_hip_thrust_cm,
                                             abs(v - setup_hx) * cm_per_px)
        mv['hip_thrust_cm'] = max_hip_thrust_cm
        mv['s10_hip_thrust_cm'] = max_hip_thrust_cm
    else:
        mv['hip_thrust_cm'] = 0.0
        mv['s10_hip_thrust_cm'] = 0.0

    # ── S11: Elbow extension at lockout ──
    mv['elbow_lockout_deg'] = _safe_at(sag['elbow_angle'], lockout, 175.0)
    mv['s11_elbow_lockout_deg'] = mv['elbow_lockout_deg']

    # ── S12: Shoulder flexion at lockout (humerus from vertical, sagittal) ──
    sh_lock = (_safe_at(sag['shoulder_x'], lockout, None),
                _safe_at(sag['shoulder_y'], lockout, None))
    el_lock = (_safe_at(sag['elbow_x'], lockout, None),
                _safe_at(sag['elbow_y'], lockout, None))
    if None not in sh_lock and None not in el_lock:
        dx = el_lock[0] - sh_lock[0]
        dy = sh_lock[1] - el_lock[1]   # elbow ABOVE shoulder at lockout → dy positive
        # Vertical reference is straight up (dx=0, dy>0). Angle from that.
        mv['shoulder_flex_lockout_deg'] = abs(math.degrees(math.atan2(dx, abs(dy) + 1e-6)))
    else:
        mv['shoulder_flex_lockout_deg'] = 5.0
    mv['s12_shoulder_flex_lockout_deg'] = mv['shoulder_flex_lockout_deg']

    # ── S13: Bar over mid-foot at lockout (standing only) ──
    if variant != 'seated-db':
        wx_lock = _safe_at(sag['wc_x'], lockout, None)
        ax_lock_l = _safe_at(sag['lan_x'], lockout, None)
        ax_lock_r = _safe_at(sag['ran_x'], lockout, None)
        if wx_lock is not None and ax_lock_l is not None and ax_lock_r is not None:
            mid_foot = (ax_lock_l + ax_lock_r) / 2.0
            mv['s13_bar_over_midfoot_cm'] = abs(wx_lock - mid_foot) * cm_per_px
        else:
            mv['s13_bar_over_midfoot_cm'] = 3.0
    else:
        mv['s13_bar_over_midfoot_cm'] = 0.0

    # ── S14: Wrist angle (max extension across rep) ──
    worst_wrist = 0.0
    for fi in range(setup, min(end + 1, len(sag['wrist_flex_deg']))):
        v = sag['wrist_flex_deg'][fi]
        if v is not None:
            worst_wrist = max(worst_wrist, abs(v))
    mv['wrist_ext_deg'] = worst_wrist
    mv['s14_wrist_ext_deg'] = worst_wrist

    # ── S15: Lockout hold (frames at elbow > 170°, wrist-Y stable) ──
    hold = 0
    if lockout < len(sag['elbow_angle']):
        wy_lock = sag['wc_y'][lockout]
        for fi in range(lockout, min(end + 1, len(sag['elbow_angle']))):
            ea = sag['elbow_angle'][fi]
            wy = sag['wc_y'][fi]
            if ea is None or wy is None or wy_lock is None:
                break
            if ea > 170 and abs(wy - wy_lock) < sag['h'] * 0.015:
                hold += 1
            else:
                break
    mv['s15_lockout_hold_sec'] = hold / fps if fps > 0 else 0.4

    # ── S16: ROM completion at bottom (eccentric — lowest wrist position) ──
    # In image coords, "lowest" body position = wrist_y back to setup level.
    # Setup wrist_y = bar at clavicle. ROM short = bar didn't return to setup.
    setup_wy = sag['wc_y'][setup] if setup < len(sag['wc_y']) else None
    lowest_post_lockout = setup_wy if setup_wy is not None else 0
    if setup_wy is not None:
        for fi in range(lockout, min(end + 1, len(sag['wc_y']))):
            v = sag['wc_y'][fi]
            if v is not None and v > lowest_post_lockout:
                lowest_post_lockout = v
        # Bar should return to AT LEAST setup_wy. Short = setup_wy - achieved.
        rom_short_cm = max(0.0, (setup_wy - lowest_post_lockout)) * cm_per_px
        # Bar reached BELOW setup_wy → rom_short = 0, but actually the SETUP
        # is the highest point of starting position (clavicle), and the ROM
        # bottom = wrist below clavicle is good. Reframe: rom_short = absolute
        # of setup_wy - lowest reached, positive means did NOT return.
        if lowest_post_lockout < setup_wy:
            rom_short_cm = max(0.0, (setup_wy - lowest_post_lockout)) * cm_per_px
        else:
            rom_short_cm = 0.0
    else:
        rom_short_cm = 1.5
    mv['s16_rom_short_cm'] = rom_short_cm

    # ── S17: Back contact with pad (seated DB only — hip-Y stability) ──
    if variant == 'seated-db':
        hys = [v for v in sag['hip_y'][setup:end + 1] if v is not None]
        if len(hys) >= 2:
            mv['s17_back_dev_cm'] = (max(hys) - min(hys)) * cm_per_px
        else:
            mv['s17_back_dev_cm'] = 0.5
    else:
        mv['s17_back_dev_cm'] = 0.0

    # ── S18: Feet contact (seated DB only — ankle-Y stability per side) ──
    if variant == 'seated-db':
        l_ays = [v for v in sag['lan_y'][setup:end + 1] if v is not None]
        r_ays = [v for v in sag['ran_y'][setup:end + 1] if v is not None]
        l_dev = (max(l_ays) - min(l_ays)) if len(l_ays) >= 2 else 0.0
        r_dev = (max(r_ays) - min(r_ays)) if len(r_ays) >= 2 else 0.0
        mv['s18_feet_dev_cm'] = max(l_dev, r_dev) * cm_per_px
    else:
        mv['s18_feet_dev_cm'] = 0.0

    # ── F1: Grip width (military) — % biacromial ──
    if variant != 'seated-db' and front:
        t = _nearest_frame(front, setup, sag)
        mv['f1_grip_width_ratio'] = _compute_grip_width(front, t)
    else:
        mv['f1_grip_width_ratio'] = 1.4

    # ── F2: Bar tilt (military, frontal — angle of L/R wrist line) ──
    if variant != 'seated-db' and front:
        worst_tilt = 0.0
        for fi in range(_nearest_frame(front, setup, sag),
                         min(_nearest_frame(front, end, sag) + 1, len(front['lwr_x']))):
            lwx = front['lwr_x'][fi]; lwy = front['lwr_y'][fi]
            rwx = front['rwr_x'][fi]; rwy = front['rwr_y'][fi]
            if None in (lwx, lwy, rwx, rwy):
                continue
            dy = lwy - rwy; dx = abs(lwx - rwx) + 1e-6
            worst_tilt = max(worst_tilt, abs(math.degrees(math.atan2(dy, dx))))
        mv['f2_bar_tilt_deg'] = worst_tilt
    else:
        mv['f2_bar_tilt_deg'] = 1.5

    # ── F3: DB symmetry (seated DB only) — peak wrist-Y delta ──
    if variant == 'seated-db' and front:
        worst_dy = 0.0
        for fi in range(_nearest_frame(front, setup, sag),
                         min(_nearest_frame(front, end, sag) + 1, len(front['lwr_y']))):
            lwy = front['lwr_y'][fi]; rwy = front['rwr_y'][fi]
            if lwy is None or rwy is None:
                continue
            worst_dy = max(worst_dy, abs(lwy - rwy))
        # Convert to cm — use frontal view's image height as athlete-height proxy
        f_cm_per_px = cm_per_px
        mv['db_symmetry_cm'] = worst_dy * f_cm_per_px
    else:
        mv['db_symmetry_cm'] = 0.0
    mv['f3_db_symmetry_cm'] = mv['db_symmetry_cm']

    # ── F4: Elbow flare at setup (humerus-trunk angle, frontal) ──
    if front:
        t = _nearest_frame(front, setup, sag)
        mv['f4_elbow_flare_deg'] = _compute_elbow_flare(front, t)
    else:
        mv['f4_elbow_flare_deg'] = 35.0

    # ── F5: Wrist lateral break (frontal) ──
    if front:
        t = _nearest_frame(front, lockout, sag)
        # Approximate: lateral wrist deviation from elbow-axis projection
        mv['f5_wrist_lat_deg'] = _compute_wrist_lateral(front, t)
    else:
        mv['f5_wrist_lat_deg'] = 4.0

    # ── F6: Head lateral tilt (nose-X offset from shoulder centre) ──
    if front:
        t = _nearest_frame(front, lockout, sag)
        nx = front['nose_x'][t] if t < len(front['nose_x']) else None
        lsx = front['lsh_x'][t] if t < len(front['lsh_x']) else None
        rsx = front['rsh_x'][t] if t < len(front['rsh_x']) else None
        if nx is not None and lsx is not None and rsx is not None:
            biacr = max(1e-3, abs(lsx - rsx))
            sc = (lsx + rsx) / 2.0
            mv['f6_head_lat_pct'] = abs(nx - sc) / biacr * 100.0
        else:
            mv['f6_head_lat_pct'] = 2.0
    else:
        mv['f6_head_lat_pct'] = 2.0

    # ── F7: DB path parallelism (seated DB only) — angular divergence ──
    if variant == 'seated-db' and front:
        mv['f7_db_path_div_deg'] = _compute_db_path_divergence(front, setup, end, sag)
    else:
        mv['f7_db_path_div_deg'] = 0.0

    # ── P2: Shoulder symmetry (posterior, % biacromial) ──
    if post:
        t = _nearest_frame(post, lockout, sag)
        lsy = post['lsh_y'][t] if t < len(post['lsh_y']) else None
        rsy = post['rsh_y'][t] if t < len(post['rsh_y']) else None
        lsx = post['lsh_x'][t] if t < len(post['lsh_x']) else None
        rsx = post['rsh_x'][t] if t < len(post['rsh_x']) else None
        if None not in (lsy, rsy, lsx, rsx):
            biacr = max(1e-3, abs(lsx - rsx))
            mv['p2_shoulder_sym_pct'] = abs(lsy - rsy) / biacr * 100.0
        else:
            mv['p2_shoulder_sym_pct'] = 2.5
    else:
        mv['p2_shoulder_sym_pct'] = 2.5

    # ── P3: Lateral lean (posterior / frontal) ──
    if post:
        t = _nearest_frame(post, lockout, sag)
        smid = ((_safe_at(post['lsh_x'], t, 0) + _safe_at(post['rsh_x'], t, 0)) / 2.0,
                (_safe_at(post['lsh_y'], t, 0) + _safe_at(post['rsh_y'], t, 0)) / 2.0)
        hmid = ((_safe_at(post['lhp_x'], t, 0) + _safe_at(post['rhp_x'], t, 0)) / 2.0,
                (_safe_at(post['lhp_y'], t, 0) + _safe_at(post['rhp_y'], t, 0)) / 2.0)
        dx = smid[0] - hmid[0]; dy = hmid[1] - smid[1]
        mv['p3_lateral_lean_deg'] = abs(math.degrees(math.atan2(dx, abs(dy) + 1e-6)))
    else:
        mv['p3_lateral_lean_deg'] = 2.0

    # ── P4: Hip alignment (posterior) ──
    if variant != 'seated-db' and post:
        t = _nearest_frame(post, lockout, sag)
        lhy = post['lhp_y'][t] if t < len(post['lhp_y']) else None
        rhy = post['rhp_y'][t] if t < len(post['rhp_y']) else None
        lsx = post['lsh_x'][t] if t < len(post['lsh_x']) else None
        rsx = post['rsh_x'][t] if t < len(post['rsh_x']) else None
        if None not in (lhy, rhy, lsx, rsx):
            biacr = max(1e-3, abs(lsx - rsx))
            mv['p4_hip_align_pct'] = abs(lhy - rhy) / biacr * 100.0
        else:
            mv['p4_hip_align_pct'] = 1.5
    else:
        mv['p4_hip_align_pct'] = 0.0

    # ── T1: Pre-rep setup time ──
    mv['t1_setup_time_sec'] = max(0.0, (setup - rep['start']) / fps) if fps > 0 else 2.0

    # ── T2: Concentric duration ──
    mv['t2_concentric_sec'] = max(0.01, (lockout - setup) / fps) if fps > 0 else 1.5

    # ── T3: Eccentric duration ──
    mv['t3_eccentric_sec'] = max(0.01, (end - lockout) / fps) if fps > 0 else 2.0

    # ── T4: E:C ratio ──
    mv['t4_ec_ratio'] = mv['t3_eccentric_sec'] / max(0.05, mv['t2_concentric_sec'])

    # ── T5: Sticking-point location (% bar travel) ──
    bar_travel = max(1, lockout - setup)
    sticking_offset = sticking - setup
    mv['t5_sticking_pct'] = (sticking_offset / bar_travel) * 100.0

    # ── T6: DB tempo symmetry (seated DB only) — L vs R wrist lockout-frame diff ──
    if variant == 'seated-db' and front:
        # Find L-wrist lockout (Y minimum) and R-wrist lockout independently
        t_setup = _nearest_frame(front, setup, sag)
        t_end = _nearest_frame(front, end, sag)
        l_lockout_fi = _find_lockout_per_wrist(front['lwr_y'], t_setup, t_end)
        r_lockout_fi = _find_lockout_per_wrist(front['rwr_y'], t_setup, t_end)
        front_fps = front.get('fps', fps)
        mv['t6_db_tempo_sym_ms'] = abs(l_lockout_fi - r_lockout_fi) / max(1.0, front_fps) * 1000.0
    else:
        mv['t6_db_tempo_sym_ms'] = 0.0

    return mv


# ─────────────────────────────────────────────────────────────────────
# Scoring (variant-aware thresholds)
# ─────────────────────────────────────────────────────────────────────

def _score_all(mv, variant, stance):
    s = {}
    is_seated = (variant == 'seated-db')

    # — Safety —
    s['lumbar_arch'] = score_one_sided(mv['s8_lumbar_arch_delta_deg'], 3, 7, 12, 20,
                                         higher_is_better=False)
    if not is_seated:
        s['hip_thrust'] = score_one_sided(mv['s10_hip_thrust_cm'], 2, 4, 7, 12,
                                            higher_is_better=False)
        s['knee_flexion'] = score_one_sided(mv['s9_knee_flex_deg'], 2, 5, 8, 15,
                                              higher_is_better=False)
        s['bar_over_midfoot'] = score_one_sided(mv['s13_bar_over_midfoot_cm'], 3, 6, 10, 15,
                                                  higher_is_better=False)
        s['grip_width'] = score_ranged(mv['f1_grip_width_ratio'],
                                         1.3, 1.5, 1.15, 1.65, 1.0, 1.8, 0.85, 2.0)
        # Elbow flare — military: 35-55° (strict) or 25-40° (true military)
        if stance == 'military_true':
            s['elbow_flare'] = score_ranged(mv['f4_elbow_flare_deg'], 25, 40, 15, 55, 0, 70, 0, 85)
        else:
            s['elbow_flare'] = score_ranged(mv['f4_elbow_flare_deg'], 35, 55, 25, 70, 10, 80, 0, 90)
    else:
        s['back_contact'] = score_one_sided(mv['s17_back_dev_cm'], 1, 2, 4, 7,
                                              higher_is_better=False)
        s['db_symmetry'] = score_one_sided(mv['f3_db_symmetry_cm'], 2, 4, 7, 12,
                                             higher_is_better=False)
        s['elbow_flare'] = score_ranged(mv['f4_elbow_flare_deg'], 35, 55, 25, 70, 10, 85, 0, 95)
        s['wrist_lateral'] = score_one_sided(mv['f5_wrist_lat_deg'], 5, 10, 18, 28,
                                               higher_is_better=False)
        s['db_path_parallel'] = score_one_sided(mv['f7_db_path_div_deg'], 3, 7, 12, 20,
                                                  higher_is_better=False)
    s['wrist_angle'] = score_one_sided(mv['s14_wrist_ext_deg'], 10, 20, 35, 50,
                                         higher_is_better=False)

    # — Technique —
    # S5 bar horizontal — use adjusted value for long-arm lifters
    s['bar_horizontal'] = score_one_sided(mv['s5_bar_horizontal_cm_adjusted'],
                                            3, 6, 10, 15, higher_is_better=False)
    # S6 head under bar (higher = better, ≥+3 cm forward is Very Good)
    s['head_under_bar'] = score_one_sided(mv['s6_head_under_bar_cm'], 3, 1, -1, -3,
                                            higher_is_better=True)
    # S11 elbow at lockout — closer to 180 = better
    s['elbow_lockout'] = score_one_sided(mv['s11_elbow_lockout_deg'], 175, 168, 160, 150,
                                           higher_is_better=True)
    # S12 shoulder flex at lockout — lower (arms by ears) = better
    s['shoulder_flex_lockout'] = score_one_sided(mv['s12_shoulder_flex_lockout_deg'],
                                                    5, 10, 18, 28, higher_is_better=False)
    # S16 ROM bottom — lower (full ROM) = better
    s['rom_bottom'] = score_one_sided(mv['s16_rom_short_cm'], 2, 5, 10, 15,
                                        higher_is_better=False)
    # Setup quality = average of S1, S2, S3 sub-scores
    s1_sub = score_one_sided(mv['s1_bar_offset_cm'], 2, 5, 10, 15, higher_is_better=False)
    s2_sub = score_one_sided(mv['s2_forearm_vert_deg'], 5, 10, 20, 35, higher_is_better=False)
    if is_seated:
        s3_sub = score_two_sided(mv['s3_elbow_setup_deg'], 90, (10, 20, 30, 40))
    else:
        s3_sub = score_two_sided(mv['s3_elbow_setup_deg'], 95, (10, 20, 30, 40))
    s['setup_quality'] = _mean([s1_sub, s2_sub, s3_sub])
    # Lockout hold (≥0.5 s sustained = Very Good)
    s['lockout_hold'] = score_one_sided(mv['s15_lockout_hold_sec'], 0.5, 0.3, 0.15, 0.05,
                                          higher_is_better=True)
    # Torso lean at lockout
    if is_seated:
        s['torso_lean_lockout'] = score_one_sided(mv['s7_torso_lean_lockout_deg'],
                                                     5, 9, 14, 20, higher_is_better=False)
    else:
        s['torso_lean_lockout'] = score_one_sided(mv['s7_torso_lean_lockout_deg'],
                                                     8, 13, 20, 30, higher_is_better=False)

    # — Performance —
    s['setup_time'] = score_ranged(mv['t1_setup_time_sec'], 1.0, 3.0, 0.5, 5.0, 0.2, 8.0, 0.0, 15.0)
    if is_seated:
        s['concentric_tempo'] = score_ranged(mv['t2_concentric_sec'],
                                               1.0, 2.0, 0.7, 3.0, 0.4, 4.0, 0.0, 6.0)
    else:
        s['concentric_tempo'] = score_ranged(mv['t2_concentric_sec'],
                                               1.2, 3.0, 0.8, 4.0, 0.5, 6.0, 0.0, 10.0)
    s['eccentric_tempo'] = score_ranged(mv['t3_eccentric_sec'],
                                          1.5, 3.0, 1.0, 4.0, 0.6, 6.0, 0.0, 8.0)
    s['ec_ratio'] = score_ranged(mv['t4_ec_ratio'], 1.0, 2.0, 0.8, 2.5, 0.5, 3.5, 0.2, 5.0)
    s['sticking_point'] = score_ranged(mv['t5_sticking_pct'], 25, 45, 20, 55, 10, 70, 0, 100)
    if is_seated:
        s['db_tempo_symmetry'] = score_one_sided(mv['t6_db_tempo_sym_ms'],
                                                    50, 100, 200, 400, higher_is_better=False)
    s['rep_consistency'] = 80.0   # filled in at set level
    return s


def _category_scores(sub_scores, variant):
    sw = _safety_weights(variant)
    tw = _tech_weights(variant)
    pw = _perf_weights(variant)
    def _w(weights):
        acc, used = 0.0, 0.0
        for k, w in weights.items():
            v = sub_scores.get(k)
            if v is None:
                continue
            acc += w * float(v); used += w
        return acc / used if used > 0 else 50.0
    return {'safety': _w(sw), 'technique': _w(tw), 'performance': _w(pw)}


def _geometric_composite(cat):
    s = max(1e-3, cat['safety'])
    t = max(1e-3, cat['technique'])
    p = max(1e-3, cat['performance'])
    return (s ** CATEGORY_WEIGHTS['safety']) * \
           (t ** CATEGORY_WEIGHTS['technique']) * \
           (p ** CATEGORY_WEIGHTS['performance'])


# ─────────────────────────────────────────────────────────────────────
# Geometry helpers
# ─────────────────────────────────────────────────────────────────────

def _compute_grip_width(view, fi):
    if view is None or fi >= len(view['lwr_x']):
        return 1.4
    lwx = view['lwr_x'][fi]; rwx = view['rwr_x'][fi]
    lsx = view['lsh_x'][fi]; rsx = view['rsh_x'][fi]
    if None in (lwx, rwx, lsx, rsx):
        return 1.4
    wd = math.hypot(lwx - rwx, (view['lwr_y'][fi] or 0) - (view['rwr_y'][fi] or 0))
    sd = math.hypot(lsx - rsx, (view['lsh_y'][fi] or 0) - (view['rsh_y'][fi] or 0))
    return wd / max(1e-3, sd)


def _compute_elbow_flare(view, fi):
    """Frontal-plane angle between humerus and torso."""
    if view is None or fi >= len(view['lsh_x']):
        return 35.0
    ls = (view['lsh_x'][fi], view['lsh_y'][fi])
    le = (view['lel_x'][fi], view['lel_y'][fi])
    lh = (view['lhp_x'][fi], view['lhp_y'][fi])
    if None in ls or None in le or None in lh:
        return 35.0
    # Vectors: humerus (shoulder→elbow), trunk (hip→shoulder)
    hx, hy = le[0] - ls[0], le[1] - ls[1]
    tx, ty = ls[0] - lh[0], ls[1] - lh[1]
    norm_h = math.hypot(hx, hy) + 1e-6
    norm_t = math.hypot(tx, ty) + 1e-6
    cos_t = (hx * tx + hy * ty) / (norm_h * norm_t)
    cos_t = max(-1.0, min(1.0, cos_t))
    return math.degrees(math.acos(cos_t))


def _compute_wrist_lateral(view, fi):
    """Frontal-view lateral deviation of wrist from elbow-projected line."""
    if view is None or fi >= len(view['lel_x']):
        return 4.0
    le = (view['lel_x'][fi], view['lel_y'][fi])
    lw = (view['lwr_x'][fi], view['lwr_y'][fi])
    if None in le or None in lw:
        return 4.0
    dx = lw[0] - le[0]; dy = le[1] - lw[1]   # wrist above elbow expected
    return abs(math.degrees(math.atan2(abs(dx), abs(dy) + 1e-6)))


def _compute_db_path_divergence(view, start, end, sag_ref):
    """Angular divergence between L and R wrist linear-fit trajectories."""
    a = _nearest_frame(view, start, sag_ref)
    b = _nearest_frame(view, end, sag_ref)
    l_pts = []; r_pts = []
    for fi in range(a, min(b + 1, len(view['lwr_x']))):
        lx = view['lwr_x'][fi]; ly = view['lwr_y'][fi]
        rx = view['rwr_x'][fi]; ry = view['rwr_y'][fi]
        if None not in (lx, ly, rx, ry):
            l_pts.append((lx, ly)); r_pts.append((rx, ry))
    if len(l_pts) < 4:
        return 2.0
    def _fit_angle(pts):
        n = len(pts)
        mx = _mean(p[0] for p in pts)
        my = _mean(p[1] for p in pts)
        num = sum((p[0] - mx) * (p[1] - my) for p in pts)
        den = sum((p[0] - mx) ** 2 for p in pts)
        slope = num / den if abs(den) > 1e-9 else 0.0
        return math.degrees(math.atan(slope))
    return abs(_fit_angle(l_pts) - _fit_angle(r_pts))


def _find_lockout_per_wrist(wrist_y_signal, start, end):
    """Find frame of minimum wrist_y (highest in image) per wrist."""
    best_y = float('inf'); best_i = start
    for fi in range(start, min(end + 1, len(wrist_y_signal))):
        v = wrist_y_signal[fi]
        if v is not None and v < best_y:
            best_y = v; best_i = fi
    return best_i


# ─────────────────────────────────────────────────────────────────────
# Corrective cues (spec §11)
# ─────────────────────────────────────────────────────────────────────

CUE_TEMPLATES = {
    'lumbar_arch': ("Lumbar hyperextension",
        "Ribs are tilting up to 'press' the bar through. Cue: 'ribs DOWN, glutes squeezed'. "
        "Drop intensity 10% if the arch worsens past rep 3 — strict pressing should not "
        "require lumbar substitution."),
    'hip_thrust': ("Hip thrust",
        "Forward hip motion detected before the bar travelled. This is a push-press / "
        "kipping pattern. Drop the load until you can press strictly without hip drive."),
    'knee_flexion': ("Knee flexion (push-press tell)",
        "Knees bent during the press. Knees stay LOCKED throughout the strict press; "
        "any bend reclassifies the rep as push-press, not strict press."),
    'wrist_angle': ("Wrist hyperextension",
        "Wrists are bending back under the load. Cue: 'punch the ceiling with the heel "
        "of your palm.' Consider wrist wraps for working sets above ~75% 1RM."),
    'bar_over_midfoot': ("Bar over mid-foot at lockout",
        "Bar is forward of the mid-foot at lockout. Move the head THROUGH the window once "
        "the bar passes the forehead — the bar should land directly over mid-foot."),
    'grip_width': ("Grip width",
        "Grip is outside the 1.3–1.5× biacromial Very Good band. Wider increases impingement "
        "risk; narrower forces excessive elbow tuck. Adjust to keep forearms vertical at "
        "the press position."),
    'elbow_flare': ("Elbow flare",
        "Elbows are flared too wide or too narrow at setup. Strict press: ~35–55° from trunk. "
        "Excess flare loads the rotator cuff; too tucked turns it into a close-grip press."),
    'back_contact': ("Back contact (seated DB)",
        "Lower back is peeling off the pad. Cue: 'feet hard into the floor, brace abs, "
        "drive the back into the pad.' If you cannot keep contact at this load, it's too heavy "
        "for the seated variant."),
    'db_symmetry': ("DB symmetry",
        "Dumbbells are pressing at different heights. Train the weaker side unilaterally; "
        "if the asymmetry persists, drop the load until both sides can press in lockstep."),
    'wrist_lateral': ("Wrist lateral break (frontal)",
        "Wrist is breaking out sideways under load. Stack the wrist over the forearm in BOTH "
        "the sagittal and frontal planes; wrist wraps help."),
    'db_path_parallel': ("DB path parallelism",
        "Left and right DBs are tracking divergent paths. Cue: 'press straight up'; visualise "
        "two parallel rails."),
    'bar_horizontal': ("Bar / DB horizontal displacement",
        "Bar drifted >6 cm from setup at some point in the press. Cue: vertical bar path, "
        "feet locked, head moves not the bar. (For long-arm lifters, thresholds are relaxed.)"),
    'head_under_bar': ("Head under bar",
        "Head is not coming THROUGH the window at lockout. Cue: 'lean back to let the bar pass, "
        "then poke the head forward at lockout.' Failure to do this leaves the bar over the "
        "forehead instead of over the shoulders."),
    'elbow_lockout': ("Elbow extension at lockout",
        "Elbows are not fully extended at the top. Lock the elbows; soft lockouts cost points "
        "and look unfinished."),
    'shoulder_flex_lockout': ("Shoulder flexion at lockout",
        "Bar / DBs ending in front of the head, not over. Cue: 'arms by ears at the top.' "
        "Likely a mobility constraint if persistent — test passive shoulder flexion ≥165°."),
    'rom_bottom': ("ROM completion at bottom",
        "Bar / DB didn't return to setup at the bottom of the rep. Earn full reps before "
        "counting them — partial reps don't build the lift."),
    'setup_quality': ("Setup quality",
        "Bar offset from clavicle, forearm angle, or elbow angle at setup is outside range. "
        "Take 2–3 s of deliberate setup before each rep."),
    'lockout_hold': ("Lockout hold",
        "No clear pause at the top. Hold for ≥0.3 s before descent — own the lockout."),
    'torso_lean_lockout': ("Torso lean at lockout",
        "Excessive layback at the top. For strict press, torso lean at lockout should stay "
        "≤8°; this is the difference between strict press and standing incline bench."),
    'setup_time': ("Setup time",
        "Rushed or overlong setup. Aim for 1–3 s of deliberate brace before the first rep."),
    'concentric_tempo': ("Concentric tempo",
        "Press was too fast (suspect push press) or too slow (grinding). Strict-press working "
        "sets: 1.2–3.0 s. <0.5 s on a strict attempt is almost always a missed push-press call."),
    'eccentric_tempo': ("Eccentric tempo",
        "Descent was too fast (drop) or too slow. Aim for 1.5–3.0 s controlled."),
    'ec_ratio': ("Eccentric:concentric ratio",
        "Tempo ratio is off. Healthy E:C is 1.0–2.0 (descent ≥ ascent in duration)."),
    'sticking_point': ("Sticking-point location",
        "Sticking point is outside the expected 25–45% bar-travel band. >70% suggests triceps "
        "weakness at lockout; <25% suggests stalling off the chest — train accordingly."),
    'db_tempo_symmetry': ("DB tempo symmetry",
        "Left and right DBs reached lockout at different times. >200 ms gap suggests one side "
        "is leading the rep — address strength asymmetry with single-arm work."),
    'rep_consistency': ("Rep-to-rep consistency",
        "Form drifted across the set. Drop the rep count by 1–2 and rebuild the groove."),
}


def _coaching_for(slug, sub_score):
    name, body = CUE_TEMPLATES.get(slug, (slug, "Work on this metric."))
    return {'metric': name, 'sub_score': round(float(sub_score), 1), 'cue': body}


# ─────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────

def analyse(files, plate_size_kg=None, weight_max=None, reps_max=None,
            target_reps=None, target_reps_sagittal=None, target_reps_frontal=None,
            target_reps_posterior=None, target_reps_oblique=None,
            variant='military', stance='strict', backrest_deg=None,
            athlete_height_cm=None):
    """Analyze an OHP set across four camera views.

    Required: files['sagittal'] (back-compat alias: 'side').
    Recommended: files['frontal'], files['posterior'], files['oblique'].
    """
    variant = (variant or 'military').lower()
    # Back-compat aliases
    if variant in ('standing-barbell', 'standing_barbell'):
        variant = 'military'
    elif variant in ('seated-barbell', 'standing-db', 'pike-pushup', 'pike-push-up'):
        variant = 'seated-db'
    if variant not in ('military', 'seated-db'):
        variant = 'military'

    stance = (stance or 'strict').lower()
    if stance not in ('strict', 'military_true'):
        stance = 'strict'

    # Backrest validation for seated DB — refuse if <70°
    if variant == 'seated-db' and backrest_deg is not None:
        try:
            backrest = float(backrest_deg)
            if backrest < 70:
                return _fallback(
                    f"Detected {backrest:.0f}° backrest — this is an incline bench press, not a "
                    f"shoulder press. Re-upload under Bench Press (Incline)."
                )
        except (TypeError, ValueError):
            backrest_deg = 90.0

    legacy_default = target_reps or 3
    counts = {
        'sagittal':  target_reps_sagittal  or legacy_default,
        'frontal':   target_reps_frontal   or legacy_default,
        'posterior': target_reps_posterior or legacy_default,
        'oblique':   target_reps_oblique   or legacy_default,
    }

    # File resolution
    sag_path = (files or {}).get('sagittal') or (files or {}).get('side')
    front_path = (files or {}).get('frontal') or (files or {}).get('front')
    post_path = (files or {}).get('posterior') or (files or {}).get('rear')
    obl_path = (files or {}).get('oblique')
    if not sag_path and files:
        sag_path = list(files.values())[0]
    if not sag_path:
        return _fallback('No sagittal video uploaded.')

    try:
        sag = _process_view(sag_path, 'sagittal', plate_size_kg)
    except Exception as e:
        return _fallback(f'Sagittal pose extraction failed: {e}')
    front = _process_view(front_path, 'frontal', None) if front_path else None
    post = _process_view(post_path, 'posterior', None) if post_path else None
    obl = _process_view(obl_path, 'oblique', None) if obl_path else None

    fps_sag = sag['fps']
    conf = confidence_score(sag['frames'])

    # Detect reps per view
    reps_by_view = {'sagittal': _detect_reps(sag, counts['sagittal'])}
    if front: reps_by_view['frontal']   = _detect_reps(front, counts['frontal'])
    if post:  reps_by_view['posterior'] = _detect_reps(post, counts['posterior'])
    if obl:   reps_by_view['oblique']   = _detect_reps(obl, counts['oblique'])

    sag_reps = reps_by_view['sagittal']
    if not sag_reps:
        return _fallback('No OHP reps detected on the sagittal video.')

    # Push-press detection + per-rep metrics
    per_rep = []
    for rep in sag_reps:
        is_push_press, pp_reason = _detect_push_press(sag, rep, variant)
        rep['push_press'] = is_push_press
        rep['push_press_reason'] = pp_reason
        # Frame-exit DNC: if bar exits frame at lockout, mark DNC
        if rep['frame_exit']:
            rep['dnc'] = True
            rep['dnc_reason'] = 'bar/DB exited frame at lockout'
        elif is_push_press:
            rep['dnc'] = True
            rep['dnc_reason'] = f'push-press detected ({pp_reason})'
        mv = _compute_rep_metrics(rep, sag, front, post, obl, variant, stance,
                                   backrest_deg, athlete_height_cm)
        subs = _score_all(mv, variant, stance)
        per_rep.append({
            'rep_num': rep['idx'],
            'sag_rep': rep,
            'push_press': rep['push_press'],
            'dnc': rep['dnc'],
            'dnc_reason': rep.get('dnc_reason'),
            'metric_values': mv,
            'sub_scores': subs,
        })

    # Set-level consistency
    cv_pct = _consistency_cv(per_rep)
    consistency_score = score_one_sided(cv_pct, 10, 15, 25, 40, higher_is_better=False)
    for r in per_rep:
        r['sub_scores']['rep_consistency'] = consistency_score

    for r in per_rep:
        r['categories'] = _category_scores(r['sub_scores'], variant)
        r['composite'] = _geometric_composite(r['categories'])

    # Hard-fail overrides
    set_overrides = []
    for spec in _override_specs(variant):
        triggered = False; worst_val = None; worst_rep = None
        for r in per_rep:
            if r['dnc']:
                continue
            t, vs = spec['eval'](r['metric_values'])
            if t:
                triggered = True
                if worst_val is None:
                    worst_val = vs; worst_rep = r['rep_num']
        set_overrides.append({
            'condition': spec['condition'], 'cap': spec['cap'],
            'triggered': bool(triggered),
            'triggering_metric': spec['metric'],
            'triggering_value': (f"rep {worst_rep}: {worst_val}" if triggered else None),
        })

    triggered_caps = [o['cap'] for o in set_overrides if o['triggered']]
    active_cap = min(triggered_caps) if triggered_caps else None
    for r in per_rep:
        if active_cap is not None:
            r['composite'] = min(r['composite'], active_cap)

    # DNC + push-press exclusion from set aggregate
    valid_reps = [r for r in per_rep if not r['dnc']]
    dnc_reps   = [r for r in per_rep if r['dnc'] and not r['push_press']]
    pp_reps    = [r for r in per_rep if r['push_press']]
    if not valid_reps:
        return _fallback(
            f"All {len(per_rep)} reps excluded (push-press: {len(pp_reps)}, "
            f"DNC: {len(dnc_reps)}). No strict-press reps to score."
        )

    composites = [r['composite'] for r in valid_reps]
    set_mean = _mean(composites)
    set_worst = min(composites)
    last3 = composites[-3:] if len(composites) >= 3 else composites
    set_last3 = _mean(last3)
    deteriorating = [r['rep_num'] for r in valid_reps if r['composite'] < (set_mean - 15)]
    cat_means = {k: _mean(r['categories'][k] for r in valid_reps)
                 for k in ('safety', 'technique', 'performance')}

    sub_mean = {}
    all_keys = set()
    for r in valid_reps:
        all_keys.update(r['sub_scores'].keys())
    for k in all_keys:
        vals = [r['sub_scores'].get(k) for r in valid_reps
                if r['sub_scores'].get(k) is not None]
        if vals:
            sub_mean[k] = _mean(vals)
    lowest = sorted(sub_mean.items(), key=lambda kv: kv[1])[:2]
    lowest_cues = [_coaching_for(k, v) for k, v in lowest]

    headline = round(set_mean)
    grade, label = grade_from_composite(set_mean)
    status = status_from_grade(grade)

    best_idx  = max(range(len(valid_reps)), key=lambda i: valid_reps[i]['composite'])
    worst_idx = min(range(len(valid_reps)), key=lambda i: valid_reps[i]['composite'])

    metrics_list = _build_legacy_metrics(valid_reps, variant, stance, sub_mean)

    coaching = []
    for o in set_overrides:
        if o['triggered']:
            coaching.append(
                f"🚩 {o['condition']} — {o['triggering_metric']}"
                + (f" ({o['triggering_value']})" if o['triggering_value'] else "")
                + f". Composite capped at {o['cap']}."
            )
    for cue in lowest_cues:
        coaching.append(f"Fix: {cue['metric']} ({cue['sub_score']}/100). {cue['cue']}")
    if not coaching:
        coaching.append("Clean strict press. Add load or progress to a higher-volume protocol next session.")
    if deteriorating:
        coaching.append(
            f"Rep{'s' if len(deteriorating) > 1 else ''} {', '.join(str(n) for n in deteriorating)} "
            f"deteriorated > 15 pts below the set mean — fatigue or form drift.")
    if pp_reps:
        details = '; '.join(f"rep {r['rep_num']}: {r['dnc_reason']}" for r in pp_reps[:3])
        coaching.append(
            f"⚠️ {len(pp_reps)} rep{'s' if len(pp_reps) != 1 else ''} reclassified as push-press "
            f"and excluded from the strict-press set average ({details})."
        )
    if dnc_reps:
        coaching.append(
            f"⚠️ {len(dnc_reps)} rep{'s' if len(dnc_reps) != 1 else ''} marked DNC "
            f"({dnc_reps[0]['dnc_reason']}) and excluded from the set average.")

    # Annotated frames — best+worst × 4 cams × 3 extremes; middle reps × sagittal × 3
    annotated = _render_frames(
        per_rep, valid_reps, best_idx, worst_idx,
        sag_path, sag, front_path, front, post_path, post, obl_path, obl,
        variant, stance, status, headline,
    )

    n_reps_total = counts['sagittal']
    stats = {
        'validReps':   f'{len(valid_reps)}/{n_reps_total}',
        'pushPressReps': f'{len(pp_reps)} PP' if pp_reps else '0 PP',
        'dncReps':     f'{len(dnc_reps)} DNC' if dnc_reps else '0 DNC',
        'confidence':  f'{conf}%',
        'sides':       sag['side'],
        'cameraView':  'Sagittal + Frontal + Posterior + Oblique',
        'variant':     variant,
        'stance':      stance if variant != 'seated-db' else '—',
        'backrest':    f"{backrest_deg:.0f}°" if (variant == 'seated-db' and backrest_deg) else '—',
        'composite':   f'{headline} ({grade})',
        'load':        f'{weight_max} kg' if weight_max else '—',
    }

    composite_score = {
        'composite': headline,
        'grade': grade,
        'label': label,
        'composite_method': 'geometric',
        'categories': [
            {'name': 'Safety',      'weight': 0.45, 'score': round(cat_means['safety'], 1)},
            {'name': 'Technique',   'weight': 0.35, 'score': round(cat_means['technique'], 1)},
            {'name': 'Performance', 'weight': 0.20, 'score': round(cat_means['performance'], 1)},
        ],
        'overrides': set_overrides,
        'active_cap': active_cap,
        'lowest_sub_scores': lowest_cues,
        'aggregation': {
            'mean': round(set_mean, 1),
            'worst': round(set_worst, 1),
            'last_three': round(set_last3, 1),
            'deteriorating_rep_nums': deteriorating,
        },
        'variant': f"{variant}" + (f" · {stance}" if variant != 'seated-db' else ""),
    }

    summary = (f"{label} ({grade}) · composite {headline}/100. "
               f"Safety {round(cat_means['safety'])}, Technique {round(cat_means['technique'])}, "
               f"Performance {round(cat_means['performance'])}.")
    if active_cap is not None:
        summary = f"⚠️ {summary} Capped at {active_cap} by a safety override."
    if pp_reps:
        summary += f" {len(pp_reps)} rep(s) reclassified as push-press."

    result = build_result(status, headline, summary, stats, metrics_list, [], coaching)
    result['annotated_frames'] = annotated
    result['per_rep'] = [
        {'rep': r['rep_num'], 'side': 'center',
         'metrics': _flatten_per_rep_for_ui(r)}
        for r in per_rep
    ]
    result['composite_score'] = composite_score
    result['muscle_activation'] = infer_overhead_press(
        trunk_lean_deg=_mean(r['metric_values']['s7_torso_lean_lockout_deg'] for r in valid_reps),
        bar_path_rms_cm=_mean(r['metric_values']['s5_bar_horizontal_cm'] for r in valid_reps),
        grip_ratio=(_mean(r['metric_values']['f1_grip_width_ratio'] for r in valid_reps)
                     if variant != 'seated-db' else 1.4),
        variant=variant,
    )
    result['meta'] = {
        'camera_view': 'sagittal+frontal+posterior+oblique',
        'camera_view_confidence': round(min(1.0, conf / 100.0), 2),
        'camera_view_warning': None,
        'analyzer_version': 'overhead-press-2026-05-20-spec',
    }
    return result


# ─────────────────────────────────────────────────────────────────────
# Annotated frames — TRIPLE EXTREME per camera
# ─────────────────────────────────────────────────────────────────────

def _render_frames(per_rep, valid_reps, best_idx, worst_idx,
                   sag_path, sag, front_path, front, post_path, post,
                   obl_path, obl, variant, stance, status, score):
    """Best + worst valid rep: 4 cams × 3 extremes = 12 frames each.
    Middle valid reps: sagittal × 3 extremes = 3 frames each.
    DNC / push-press reps: skipped."""
    out = []
    if not per_rep:
        fb = render_sample_frame(sag_path, sag['frames'], sag['w'], sag['h'],
                                 'Overhead Press', 'No reps detected.',
                                 connections=OHP_CONNECTIONS)
        if fb:
            out.append({'label': 'Sample Frame', 'image_base64': fb,
                        'rep_num': 0, 'side': 'center', 'is_best': False,
                        'metrics_shown': ['No reps detected']})
        return out

    rich_rep_nums = set()
    if valid_reps:
        rich_rep_nums = {valid_reps[best_idx]['rep_num'], valid_reps[worst_idx]['rep_num']}

    for r in per_rep:
        if r['dnc']:
            continue
        is_best  = bool(valid_reps and r['rep_num'] == valid_reps[best_idx]['rep_num'])
        is_worst = bool(valid_reps and r['rep_num'] == valid_reps[worst_idx]['rep_num'])
        is_rich  = (r['rep_num'] in rich_rep_nums)

        # Sagittal × 3 extremes — always
        for extreme in ('setup', 'sticking', 'lockout'):
            try:
                img = _annotate_sagittal(sag_path, sag, r, extreme, variant, stance,
                                          status, score, len(per_rep))
                if img:
                    lbl = f"Rep {r['rep_num']} · Sagittal · {_extreme_label(extreme)}"
                    if is_best: lbl += " ⭐"
                    if is_worst: lbl += " ⚠"
                    out.append({
                        'label': lbl, 'image_base64': img,
                        'rep_num': r['rep_num'], 'side': f'sagittal-{extreme}',
                        'is_best': is_best,
                        'metrics_shown': _summary_for_overlay(r, 'sagittal', extreme),
                    })
            except Exception as e:
                print(f"[ohp.render] sagittal {extreme} rep {r['rep_num']} failed: {e}")

        # Best + worst rep: other three views × 3 extremes
        if is_rich:
            for view_name, view, path in (
                ('frontal',   front, front_path),
                ('posterior', post,  post_path),
                ('oblique',   obl,   obl_path),
            ):
                if not view or not path:
                    continue
                for extreme in ('setup', 'sticking', 'lockout'):
                    try:
                        img = _annotate_secondary(path, view, view_name, r, extreme,
                                                    variant, stance, status, score,
                                                    len(per_rep), sag)
                        if img:
                            lbl = f"Rep {r['rep_num']} · {_view_label(view_name)} · {_extreme_label(extreme)}"
                            if is_best: lbl += " ⭐"
                            if is_worst: lbl += " ⚠"
                            out.append({
                                'label': lbl, 'image_base64': img,
                                'rep_num': r['rep_num'],
                                'side': f'{view_name}-{extreme}',
                                'is_best': is_best,
                                'metrics_shown': _summary_for_overlay(r, view_name, extreme),
                            })
                    except Exception as e:
                        print(f"[ohp.render] {view_name} {extreme} rep {r['rep_num']} failed: {e}")

    if not out:
        fb = render_sample_frame(sag_path, sag['frames'], sag['w'], sag['h'],
                                 'Overhead Press', 'Reps detected but frames could not be rendered.',
                                 connections=OHP_CONNECTIONS)
        if fb:
            out.append({'label': 'Sample Frame', 'image_base64': fb,
                        'rep_num': 0, 'side': 'center', 'is_best': False,
                        'metrics_shown': ['Frame extraction failed']})
    return out


def _view_label(name):
    return {'frontal': 'Frontal',
            'posterior': 'Posterior',
            'oblique': 'Oblique (45°)'}.get(name, name)


def _extreme_label(name):
    return {'setup': 'Setup (rack)',
            'sticking': 'Sticking Point',
            'lockout': 'Lockout (top)'}.get(name, name)


def _summary_for_overlay(r, view_name, extreme):
    mv = r['metric_values']
    if extreme == 'setup':
        if view_name == 'sagittal':
            return [
                f"Composite: {r['composite']:.0f}/100",
                f"Forearm vert: {mv['s2_forearm_vert_deg']:.1f}°",
                f"Elbow @ setup: {mv['s3_elbow_setup_deg']:.0f}°",
                f"Torso lean: {mv['s4_torso_lean_setup_deg']:.1f}°",
            ]
        if view_name == 'frontal':
            return [
                f"Grip width: {mv['f1_grip_width_ratio']:.2f}× BAW",
                f"Elbow flare: {mv['f4_elbow_flare_deg']:.0f}°",
            ]
        return [f"Composite: {r['composite']:.0f}/100"]
    if extreme == 'sticking':
        return [
            f"Composite: {r['composite']:.0f}/100",
            f"Sticking @ {mv['t5_sticking_pct']:.0f}% travel",
            f"Bar horizontal: {mv['s5_bar_horizontal_cm']:.1f} cm",
            f"Lumbar Δ: {mv['s8_lumbar_arch_delta_deg']:.1f}°",
        ]
    # lockout
    if view_name == 'sagittal':
        return [
            f"Composite: {r['composite']:.0f}/100",
            f"Elbow lockout: {mv['s11_elbow_lockout_deg']:.0f}°",
            f"Shoulder flex: {mv['s12_shoulder_flex_lockout_deg']:.1f}°",
            f"Bar-over-midfoot: {mv['s13_bar_over_midfoot_cm']:.1f} cm",
            f"Head under bar: {mv['s6_head_under_bar_cm']:.1f} cm",
        ]
    if view_name == 'frontal':
        return [
            f"Bar tilt: {mv['f2_bar_tilt_deg']:.1f}°",
            f"DB symmetry: {mv['f3_db_symmetry_cm']:.1f} cm",
            f"Head lateral: {mv['f6_head_lat_pct']:.1f}%",
        ]
    if view_name == 'posterior':
        return [
            f"Shoulder sym: {mv['p2_shoulder_sym_pct']:.1f}%",
            f"Lateral lean: {mv['p3_lateral_lean_deg']:.1f}°",
            f"Hip alignment: {mv['p4_hip_align_pct']:.1f}%",
        ]
    return [f"Composite: {r['composite']:.0f}/100"]


def _annotate_sagittal(path, sag, rep, extreme, variant, stance, status, score, total):
    sag_rep = rep['sag_rep']
    frame_idx = sag_rep[extreme] if extreme in sag_rep else sag_rep['lockout']
    frames = sag['frames']; w, h = sag['w'], sag['h']; idx = sag['idx']
    if frame_idx >= len(frames):
        return None
    lm = frames[frame_idx]['landmarks']
    if lm is None:
        return None
    frame = extract_frame_at(path, frame_idx)
    if frame is None:
        return None

    sh = _lm_to_px(lm, idx['shoulder'], w, h)
    el = _lm_to_px(lm, idx['elbow'], w, h)
    wr = _lm_to_px(lm, idx['wrist'], w, h)
    hp = _lm_to_px(lm, idx['hip'], w, h)
    kn = _lm_to_px(lm, idx['knee'], w, h)
    an = _lm_to_px(lm, idx['ankle'], w, h)
    amid = midpoint_px(lm, LM['LEFT_ANKLE'], LM['RIGHT_ANKLE'], w, h)

    draw_skeleton(frame, lm, w, h, connections=OHP_CONNECTIONS)
    # Mid-foot vertical reference (standing)
    if variant != 'seated-db' and amid:
        draw_reference_line(frame, x=amid[0], color=COL_CYAN, label='Mid-foot (bar reference)')

    mv = rep['metric_values']
    # Elbow arc
    if sh and el and wr:
        ea = _safe_at(sag['elbow_angle'], frame_idx, 90.0)
        if extreme == 'lockout':
            es = 'good' if ea >= 168 else ('warn' if ea >= 160 else 'bad')
        else:
            es = 'good'
        draw_angle_arc(frame, el, sh, wr, ea, label=f"Elbow {ea:.0f}°",
                       radius=52, status=es)
    # Hip angle (lumbar) arc
    if sh and hp and kn:
        ha = _safe_at(sag['hip_angle'], frame_idx, 180.0)
        lumbar_status = ('bad' if mv['s8_lumbar_arch_delta_deg'] > 12
                         else 'warn' if mv['s8_lumbar_arch_delta_deg'] > 7 else 'good')
        draw_angle_arc(frame, hp, sh, kn, ha, label=f"Lumbar Δ {mv['s8_lumbar_arch_delta_deg']:.1f}°",
                       radius=44, status=lumbar_status)

    if extreme == 'lockout' and sh:
        sf_status = ('good' if mv['s12_shoulder_flex_lockout_deg'] < 10
                     else 'warn' if mv['s12_shoulder_flex_lockout_deg'] < 18 else 'bad')
        draw_callout(frame, sh, f"Sh flex {mv['s12_shoulder_flex_lockout_deg']:.1f}°",
                     status=sf_status, offset=(140, -40))
    if extreme == 'setup' and sh:
        draw_callout(frame, sh, f"Torso lean {mv['s4_torso_lean_setup_deg']:.1f}°",
                     status='good', offset=(140, 30))

    draw_title_strip(frame, f"OHP ({variant})", rep['rep_num'], total,
                     status=status, score=score)
    draw_phase_label(frame, _extreme_label(extreme))

    if extreme == 'setup':
        overlay = [
            {'label': 'Composite', 'value': f"{rep['composite']:.0f}/100",
             'status': 'good' if rep['composite'] >= 75 else ('warn' if rep['composite'] >= 60 else 'bad')},
            {'label': 'Safety',      'value': f"{rep['categories']['safety']:.0f}", 'status': 'good'},
            {'label': 'Technique',   'value': f"{rep['categories']['technique']:.0f}", 'status': 'good'},
            {'label': 'Performance', 'value': f"{rep['categories']['performance']:.0f}", 'status': 'good'},
            {'label': 'Bar offset',  'value': f"{mv['s1_bar_offset_cm']:.1f} cm", 'status': 'good'},
            {'label': 'Forearm vert', 'value': f"{mv['s2_forearm_vert_deg']:.1f}°", 'status': 'good'},
            {'label': 'Elbow @ setup', 'value': f"{mv['s3_elbow_setup_deg']:.0f}°", 'status': 'good'},
            {'label': 'Torso lean (setup)', 'value': f"{mv['s4_torso_lean_setup_deg']:.1f}°", 'status': 'good'},
            {'label': 'Setup time',  'value': f"{mv['t1_setup_time_sec']:.2f} s", 'status': 'good'},
        ]
        title = f"REP {rep['rep_num']} · SETUP"
    elif extreme == 'sticking':
        overlay = [
            {'label': 'Composite',         'value': f"{rep['composite']:.0f}/100", 'status': 'good'},
            {'label': 'Sticking position', 'value': f"{mv['t5_sticking_pct']:.0f}%", 'status': 'good'},
            {'label': 'Bar horizontal',    'value': f"{mv['s5_bar_horizontal_cm']:.1f} cm",
             'status': 'good' if mv['s5_bar_horizontal_cm'] < 6 else 'warn'},
            {'label': 'Lumbar Δ',          'value': f"{mv['s8_lumbar_arch_delta_deg']:.1f}°",
             'status': 'good' if mv['s8_lumbar_arch_delta_deg'] < 7 else 'bad'},
            {'label': 'Knee flex',         'value': f"{mv['s9_knee_flex_deg']:.1f}°",
             'status': 'good' if mv['s9_knee_flex_deg'] < 5 else 'bad'},
            {'label': 'Hip thrust',        'value': f"{mv['s10_hip_thrust_cm']:.1f} cm",
             'status': 'good' if mv['s10_hip_thrust_cm'] < 4 else 'bad'},
            {'label': 'Concentric tempo',  'value': f"{mv['t2_concentric_sec']:.2f} s", 'status': 'good'},
            {'label': 'Wrist ext max',     'value': f"{mv['s14_wrist_ext_deg']:.0f}°",
             'status': 'good' if mv['s14_wrist_ext_deg'] < 20 else 'bad'},
        ]
        title = f"REP {rep['rep_num']} · STICKING POINT"
    else:  # lockout
        overlay = [
            {'label': 'Composite', 'value': f"{rep['composite']:.0f}/100", 'status': 'good'},
            {'label': 'Elbow lockout',   'value': f"{mv['s11_elbow_lockout_deg']:.0f}°",
             'status': 'good' if mv['s11_elbow_lockout_deg'] >= 175 else ('warn' if mv['s11_elbow_lockout_deg'] >= 165 else 'bad')},
            {'label': 'Shoulder flex',   'value': f"{mv['s12_shoulder_flex_lockout_deg']:.1f}°",
             'status': 'good' if mv['s12_shoulder_flex_lockout_deg'] < 10 else 'bad'},
            {'label': 'Bar-over-midfoot', 'value': f"{mv['s13_bar_over_midfoot_cm']:.1f} cm",
             'status': 'good' if mv['s13_bar_over_midfoot_cm'] < 6 else 'bad'},
            {'label': 'Head under bar',  'value': f"{mv['s6_head_under_bar_cm']:.1f} cm",
             'status': 'good' if mv['s6_head_under_bar_cm'] >= 1 else 'warn'},
            {'label': 'Torso lean (top)', 'value': f"{mv['s7_torso_lean_lockout_deg']:.1f}°",
             'status': 'good' if mv['s7_torso_lean_lockout_deg'] < 13 else 'bad'},
            {'label': 'Lockout hold',    'value': f"{mv['s15_lockout_hold_sec']:.2f} s",
             'status': 'good' if mv['s15_lockout_hold_sec'] >= 0.3 else 'warn'},
            {'label': 'ROM bottom',      'value': f"{mv['s16_rom_short_cm']:.1f} cm short",
             'status': 'good' if mv['s16_rom_short_cm'] < 5 else 'bad'},
            {'label': 'Eccentric',       'value': f"{mv['t3_eccentric_sec']:.2f} s", 'status': 'good'},
        ]
        title = f"REP {rep['rep_num']} · LOCKOUT"

    draw_metric_overlay(frame, overlay, position='top-right', title=title)
    draw_legend(frame, position='bottom-left')
    return frame_to_base64(frame)


def _annotate_secondary(path, view, view_name, rep, extreme, variant, stance,
                          status, score, total, sag):
    sag_rep = rep['sag_rep']
    sag_frame = sag_rep.get(extreme, sag_rep['lockout'])
    view_frame = _nearest_frame(view, sag_frame, sag)
    frames = view['frames']; w, h = view['w'], view['h']
    if view_frame >= len(frames):
        return None
    lm = frames[view_frame]['landmarks']
    if lm is None:
        return None
    frame = extract_frame_at(path, view_frame)
    if frame is None:
        return None

    draw_skeleton(frame, lm, w, h, connections=OHP_CONNECTIONS)
    mv = rep['metric_values']

    if view_name == 'frontal':
        if extreme == 'setup':
            overlay = [
                {'label': 'Grip width', 'value': f"{mv['f1_grip_width_ratio']:.2f}× BAW",
                 'status': 'good' if 1.3 <= mv['f1_grip_width_ratio'] <= 1.5 else 'warn'},
                {'label': 'Elbow flare', 'value': f"{mv['f4_elbow_flare_deg']:.0f}°",
                 'status': 'good' if 35 <= mv['f4_elbow_flare_deg'] <= 55 else 'warn'},
            ]
        elif extreme == 'sticking':
            overlay = [
                {'label': 'Bar tilt', 'value': f"{mv['f2_bar_tilt_deg']:.1f}°",
                 'status': 'good' if mv['f2_bar_tilt_deg'] < 4 else 'bad'},
                {'label': 'DB symmetry', 'value': f"{mv['f3_db_symmetry_cm']:.1f} cm",
                 'status': 'good' if mv['f3_db_symmetry_cm'] < 4 else 'bad'},
            ]
        else:  # lockout
            overlay = [
                {'label': 'Bar tilt', 'value': f"{mv['f2_bar_tilt_deg']:.1f}°",
                 'status': 'good' if mv['f2_bar_tilt_deg'] < 4 else 'bad'},
                {'label': 'DB symmetry', 'value': f"{mv['f3_db_symmetry_cm']:.1f} cm",
                 'status': 'good' if mv['f3_db_symmetry_cm'] < 4 else 'bad'},
                {'label': 'Head lateral', 'value': f"{mv['f6_head_lat_pct']:.1f}%", 'status': 'good'},
                {'label': 'DB path divergence', 'value': f"{mv['f7_db_path_div_deg']:.1f}°", 'status': 'good'},
                {'label': 'Wrist lateral', 'value': f"{mv['f5_wrist_lat_deg']:.1f}°", 'status': 'good'},
            ]
        title = f"REP {rep['rep_num']} · FRONTAL · {_extreme_label(extreme).upper()}"
    elif view_name == 'posterior':
        if extreme == 'setup':
            overlay = [
                {'label': 'Spinal lean (rear)', 'value': f"{mv['p3_lateral_lean_deg']:.1f}°", 'status': 'good'},
            ]
        else:
            overlay = [
                {'label': 'Shoulder symmetry', 'value': f"{mv['p2_shoulder_sym_pct']:.1f}%",
                 'status': 'good' if mv['p2_shoulder_sym_pct'] < 6 else 'bad'},
                {'label': 'Lateral lean', 'value': f"{mv['p3_lateral_lean_deg']:.1f}°",
                 'status': 'good' if mv['p3_lateral_lean_deg'] < 6 else 'bad'},
                {'label': 'Hip alignment', 'value': f"{mv['p4_hip_align_pct']:.1f}%",
                 'status': 'good' if mv['p4_hip_align_pct'] < 4 else 'bad'},
            ]
        title = f"REP {rep['rep_num']} · POSTERIOR · {_extreme_label(extreme).upper()}"
    else:  # oblique
        overlay = [
            {'label': 'Composite', 'value': f"{rep['composite']:.0f}/100", 'status': 'good'},
            {'label': '(Note)', 'value': 'Oblique — backup view', 'status': 'good'},
        ]
        if extreme == 'lockout':
            overlay.insert(1, {'label': 'Elbow lockout',
                                'value': f"{mv['s11_elbow_lockout_deg']:.0f}°", 'status': 'good'})
        title = f"REP {rep['rep_num']} · OBLIQUE · {_extreme_label(extreme).upper()}"

    draw_title_strip(frame, f"OHP ({variant})", rep['rep_num'],
                     total, status=status, score=score)
    draw_phase_label(frame, _extreme_label(extreme))
    draw_metric_overlay(frame, overlay, position='top-right', title=title)
    draw_legend(frame, position='bottom-left')
    return frame_to_base64(frame)


# ─────────────────────────────────────────────────────────────────────
# Per-rep flatten for UI accordion + consistency + legacy metrics
# ─────────────────────────────────────────────────────────────────────

def _flatten_per_rep_for_ui(rep):
    mv = rep['metric_values']
    subs = rep['sub_scores']
    cats = rep.get('categories', {'safety': 0, 'technique': 0, 'performance': 0})
    out = {
        'composite': round(rep['composite'], 1) if not rep['dnc'] else 0,
        'safety_score': round(cats.get('safety', 0), 1),
        'technique_score': round(cats.get('technique', 0), 1),
        'performance_score': round(cats.get('performance', 0), 1),
        'dnc': 1 if rep['dnc'] else 0,
        'push_press': 1 if rep['push_press'] else 0,
    }
    for k, v in mv.items():
        if isinstance(v, (int, float)):
            out[k] = round(v, 2)
    for k, v in subs.items():
        if isinstance(v, (int, float)):
            out[f'sub_{k}'] = round(v, 1)
    return out


def _consistency_cv(per_rep):
    """CV% across concentric_sec + s5_bar_horizontal_cm + s11_elbow_lockout_deg."""
    keys = ('t2_concentric_sec', 's5_bar_horizontal_cm', 's11_elbow_lockout_deg')
    cvs = []
    for k in keys:
        vals = [r['metric_values'].get(k) for r in per_rep
                if isinstance(r['metric_values'].get(k), (int, float))]
        if len(vals) < 2:
            continue
        m = sum(vals) / len(vals)
        if abs(m) < 1e-6:
            continue
        var = sum((v - m) ** 2 for v in vals) / len(vals)
        cvs.append(math.sqrt(var) / abs(m) * 100.0)
    return sum(cvs) / len(cvs) if cvs else 8.0


def _legacy_status(sub_score):
    if sub_score >= 75:
        return 'GOOD'
    if sub_score >= 60:
        return 'NEEDS IMPROVEMENT'
    return 'RESTRICTED'


def _build_legacy_metrics(per_rep, variant, stance, sub_mean):
    if not per_rep:
        return []
    n_reps = len(per_rep)
    mv = {k: _mean(r['metric_values'][k] for r in per_rep
                    if isinstance(r['metric_values'].get(k), (int, float)))
          for k in per_rep[0]['metric_values']
          if isinstance(per_rep[0]['metric_values'].get(k), (int, float))}

    def m(name, raw, value_fmt, target, max_val, slug):
        sub = sub_mean.get(slug, 60.0)
        return build_metric(name, value_fmt, raw, target, max_val,
                            _legacy_status(sub), n_reps=n_reps)

    out = []
    # Safety
    out.append(m('Lumbar arch delta (worst)', mv['s8_lumbar_arch_delta_deg'],
                 f"{mv['s8_lumbar_arch_delta_deg']:.1f}°", '<7°', 30, 'lumbar_arch'))
    if variant != 'seated-db':
        out.append(m('Hip-X thrust', mv['s10_hip_thrust_cm'],
                     f"{mv['s10_hip_thrust_cm']:.1f} cm", '<4 cm', 25, 'hip_thrust'))
        out.append(m('Knee flexion delta', mv['s9_knee_flex_deg'],
                     f"{mv['s9_knee_flex_deg']:.1f}°", '<5°', 30, 'knee_flexion'))
        out.append(m('Bar over mid-foot @ lockout', mv['s13_bar_over_midfoot_cm'],
                     f"{mv['s13_bar_over_midfoot_cm']:.1f} cm", '<6 cm', 25, 'bar_over_midfoot'))
        out.append(m('Grip width (× BAW)', mv['f1_grip_width_ratio'],
                     f"{mv['f1_grip_width_ratio']:.2f}×", '1.3–1.5', 3, 'grip_width'))
    else:
        out.append(m('Back contact (hip-Y dev)', mv['s17_back_dev_cm'],
                     f"{mv['s17_back_dev_cm']:.1f} cm", '<1 cm', 15, 'back_contact'))
        out.append(m('DB symmetry (peak height delta)', mv['f3_db_symmetry_cm'],
                     f"{mv['f3_db_symmetry_cm']:.1f} cm", '<2 cm', 20, 'db_symmetry'))
        out.append(m('Wrist lateral break', mv['f5_wrist_lat_deg'],
                     f"{mv['f5_wrist_lat_deg']:.1f}°", '<5°', 45, 'wrist_lateral'))
        out.append(m('DB path divergence', mv['f7_db_path_div_deg'],
                     f"{mv['f7_db_path_div_deg']:.1f}°", '<3°', 30, 'db_path_parallel'))
    out.append(m('Elbow flare @ setup', mv['f4_elbow_flare_deg'],
                 f"{mv['f4_elbow_flare_deg']:.0f}°", '35–55°', 90, 'elbow_flare'))
    out.append(m('Wrist extension (worst)', mv['s14_wrist_ext_deg'],
                 f"{mv['s14_wrist_ext_deg']:.0f}°", '≤10°', 90, 'wrist_angle'))

    # Technique
    long_arm_note = ' (long-arm relaxed)' if mv.get('s5_long_arm_relaxed', 0) > 0.5 else ''
    out.append(m(f'Bar/DB horizontal max{long_arm_note}', mv['s5_bar_horizontal_cm'],
                 f"{mv['s5_bar_horizontal_cm']:.1f} cm", '≤3 cm', 30, 'bar_horizontal'))
    out.append(m('Head under bar (Δ)', mv['s6_head_under_bar_cm'],
                 f"{mv['s6_head_under_bar_cm']:.1f} cm", '≥+3 cm', 15, 'head_under_bar'))
    out.append(m('Elbow extension @ lockout', mv['s11_elbow_lockout_deg'],
                 f"{mv['s11_elbow_lockout_deg']:.0f}°", '175–180°', 180, 'elbow_lockout'))
    out.append(m('Shoulder flexion @ lockout', mv['s12_shoulder_flex_lockout_deg'],
                 f"{mv['s12_shoulder_flex_lockout_deg']:.1f}°", '≤5°', 60, 'shoulder_flex_lockout'))
    out.append(m('ROM completion (bottom)', mv['s16_rom_short_cm'],
                 f"{mv['s16_rom_short_cm']:.1f} cm short", '≤2 cm short', 30, 'rom_bottom'))
    out.append(m('Lockout hold', mv['s15_lockout_hold_sec'],
                 f"{mv['s15_lockout_hold_sec']:.2f} s", '≥0.5 s', 3, 'lockout_hold'))
    out.append(m('Torso lean @ lockout', mv['s7_torso_lean_lockout_deg'],
                 f"{mv['s7_torso_lean_lockout_deg']:.1f}°",
                 '≤5°' if variant == 'seated-db' else '≤8°', 45, 'torso_lean_lockout'))

    # Performance
    out.append(m('Setup time', mv['t1_setup_time_sec'],
                 f"{mv['t1_setup_time_sec']:.2f} s", '1–3 s', 30, 'setup_time'))
    out.append(m('Concentric tempo', mv['t2_concentric_sec'],
                 f"{mv['t2_concentric_sec']:.2f} s",
                 '1.0–2.0 s' if variant == 'seated-db' else '1.2–3.0 s',
                 12, 'concentric_tempo'))
    out.append(m('Eccentric tempo', mv['t3_eccentric_sec'],
                 f"{mv['t3_eccentric_sec']:.2f} s", '1.5–3.0 s', 10, 'eccentric_tempo'))
    out.append(m('E:C ratio', mv['t4_ec_ratio'],
                 f"{mv['t4_ec_ratio']:.2f}", '1.0–2.0', 5, 'ec_ratio'))
    out.append(m('Sticking-point location', mv['t5_sticking_pct'],
                 f"{mv['t5_sticking_pct']:.0f}% of bar travel", '25–45%', 100, 'sticking_point'))
    if variant == 'seated-db':
        out.append(m('DB tempo symmetry', mv['t6_db_tempo_sym_ms'],
                     f"{mv['t6_db_tempo_sym_ms']:.0f} ms", '<50 ms', 600, 'db_tempo_symmetry'))
    out.append(m('Rep-to-rep consistency', mv.get('t2_concentric_sec', 1.5),
                 f"CV {_consistency_cv(per_rep):.1f}%", '<10%', 50, 'rep_consistency'))

    return out


def _fallback(msg):
    return build_result(
        'NEEDS IMPROVEMENT', 50,
        f'Analysis could not complete: {msg}',
        {'validReps': '0/0', 'confidence': '0%', 'sides': 'n/a',
         'cameraView': 'UNKNOWN'},
        [], [], [msg],
    )
