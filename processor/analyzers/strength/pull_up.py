"""STRENGTH — Pull-Up (Pronated / Supinated / Neutral / Wide grip).

Full rewrite per the Biomechanical Assessment Spec (pullups.md).

Why pull-up is different from bench / deadlift
==============================================
  • The bar is FIXED — wrist landmarks are the (near-)stationary reference.
    Almost every other landmark moves relative to the wrists.
  • Each rep has TWO equally important extreme positions:
        BOTTOM (dead-hang): elbow extension, body line at bottom, hang quality
        TOP    (chin-over-bar): ROM, elbow at top, layback, shoulder symmetry
    Annotated diagrams are rendered for BOTH extremes (not just one).
  • Style is a hard rubric switch (strict / kipping / butterfly / sternum /
    c2b / tactical). Scoring a kipping athlete against the strict rubric
    silently tags them "kipping detected → cap 60" — wrong for kipping
    intent. The form passes the chosen style; the analyzer routes to the
    matching rubric.
  • Grip changes elbow-angle-at-top + elbow-flare thresholds. 4 categories.
  • DNC handling: spec §7.4 says hand-release / fall reps are EXCLUDED
    from the set average, not penalised. The aggregation surfaces "DNC: N"
    separately in the stats banner.
  • MediaPipe is weaker on overhead arm posture. Face landmarks frequently
    occlude at lockout (bar passes in front of nose). Fallback chain for
    chin-over-bar detection per spec §11.11.

Pipeline
========
  1. Resolve four camera files: sagittal (PRIMARY), frontal, posterior,
     oblique (sagittal-side fallback).
  2. Per video: extract MediaPipe pose, build per-frame signals.
  3. Per video: detect dead-hang frames (elbow ≥ 170°, wrist-Y stable) and
     chin-over-bar frames (chin_y < wrist_y) with a Schmitt-trigger state
     machine. Match: rep = TOP → ECCENTRIC → DEAD_HANG → CONCENTRIC cycle.
  4. Per rep, compute ALL 33 spec metrics — those defined "at bottom" use
     the dead-hang frame, those "at top" use the lockout frame, and those
     "across rep" use the full window.
  5. Style-aware scoring: each rep is scored against the rubric matching
     `style`. For strict, the kipping detector enforces the cap. For
     kipping/butterfly, that detector is disabled and a hollow-arch
     consistency metric is added.
  6. Composite = geometric mean (S_safety^0.20 · S_tech^0.45 · S_perf^0.35,
     spec §7.3).
  7. 9 hard-fail safety overrides cap composite per spec §7.4. Hand-release
     events are tagged DNC and excluded from set aggregation.
  8. Annotated diagrams: best + worst rep get all 4 cameras × 2 extremes;
     middle reps get sagittal-only × 2 extremes.

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
from utils.muscle_inference import infer_pull_up

PULL_UP_CONNECTIONS = [
    # Upper body
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    # Torso
    (11, 23), (12, 24), (23, 24),
    # Lower body
    (23, 25), (25, 27), (24, 26), (26, 28),
    # Head / neck
    (0, 11), (0, 12),
]


# ─────────────────────────────────────────────────────────────────────
# 5-tier scoring helpers (spec §7.1). Algorithm identical to bench/deadlift.
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
# Spec §7.2 — category weights.  Pull-up: Safety 20%, Tech 45%, Perf 35%.
# ─────────────────────────────────────────────────────────────────────

SAFETY_W = {
    'dead_hang_quality':    25,
    'eccentric_tempo':      20,
    'shoulder_symmetry':    15,
    'scapular_depression':  15,
    'spinal_alignment':     10,
    'setup_quality':        10,
    'lateral_body_sway':     5,
}

TECH_W_STRICT = {
    'chin_over_bar':              18,
    'elbow_top':                  12,
    'body_line':                  12,
    'scapular_initiation':        10,
    'kipping_detection':          10,
    'body_inclination_top':        8,
    'grip_width':                  7,
    'elbow_flare':                 6,
    'head_neck':                   6,
    'hip_flexion_consistency':     6,
    'knee_position':               5,
}

TECH_W_KIPPING = {
    'chin_over_bar':              22,
    'elbow_top':                  10,
    'hollow_arch_transition':     18,
    'scapular_initiation':         6,
    'body_inclination_top':        8,
    'grip_width':                  8,
    'elbow_flare':                 8,
    'head_neck':                   6,
    'symmetric_cycle':            14,
}

TECH_W_BUTTERFLY = {
    'chin_over_bar':              18,
    'elbow_top':                   8,
    'cycle_continuity':           22,
    'hollow_arch_transition':     16,
    'grip_width':                  8,
    'elbow_flare':                 6,
    'head_neck':                   6,
    'symmetric_cycle':            16,
}

PERF_W_STRICT = {
    'concentric_tempo':    20,
    'pause_top':           10,
    'rep_consistency':     20,
    'rom_completion':      25,
    'symmetric_ascent':    10,
    'sticking_point':      10,
    'bar_path_stability':   5,
}

PERF_W_KIPPING = {
    'concentric_tempo':    14,
    'rep_consistency':     20,
    'rom_completion':      26,
    'symmetric_ascent':    14,
    'cycle_rate':          16,
    'bar_path_stability':  10,
}

CATEGORY_WEIGHTS = {'safety': 0.20, 'technique': 0.45, 'performance': 0.35}


def _tech_weights(style):
    if style == 'kipping':
        return TECH_W_KIPPING
    if style == 'butterfly':
        return TECH_W_BUTTERFLY
    return TECH_W_STRICT


def _perf_weights(style):
    if style in ('kipping', 'butterfly'):
        return PERF_W_KIPPING
    return PERF_W_STRICT


# ─────────────────────────────────────────────────────────────────────
# Spec §7.4 — hard-fail safety overrides.
# Kipping override is suppressed when style is kipping/butterfly.
# Hand-release / fall events are flagged as DNC and excluded from the set.
# ─────────────────────────────────────────────────────────────────────

def _override_specs(style):
    base = [
        {
            'key': 'partial_rom_bottom',
            'condition': 'Dead-hang failure (elbow < 145° at bottom of any rep)',
            'metric': 'Dead-hang elbow angle',
            'cap': 50,
            'eval': lambda mv: (mv['dead_hang_elbow_deg'] < 145,
                                f"{mv['dead_hang_elbow_deg']:.0f}°"),
        },
        {
            'key': 'partial_rom_top',
            'condition': 'No chin over bar (chin at or below wrist line at peak)',
            'metric': 'Chin-over-bar clearance',
            'cap': 50,
            'eval': lambda mv: (mv['chin_clearance_cm'] < 0,
                                f"{mv['chin_clearance_cm']:.1f} cm"),
        },
        {
            'key': 'shoulder_shrug_top',
            'condition': 'Excessive shoulder shrug at top (shoulder within 3 cm of earlobe)',
            'metric': 'Shoulder-to-ear distance',
            'cap': 100,
            'eval': lambda mv: (mv['shoulder_to_ear_cm'] < 3.0,
                                f"{mv['shoulder_to_ear_cm']:.1f} cm"),
            'penalty_per_rep': 10,
        },
        {
            'key': 'free_fall_eccentric',
            'condition': 'Eccentric tempo < 0.5 s (free-fall drop, shoulder-injury risk)',
            'metric': 'Eccentric tempo',
            'cap': 55,
            'eval': lambda mv: (mv['eccentric_sec'] < 0.5,
                                f"{mv['eccentric_sec']:.2f} s"),
        },
        {
            'key': 'asymmetric_ascent',
            'condition': 'Asymmetric pull (> 15° shoulder tilt at top)',
            'metric': 'Shoulder symmetry at top',
            'cap': 60,
            'eval': lambda mv: (mv['shoulder_tilt_deg'] > 15,
                                f"{mv['shoulder_tilt_deg']:.1f}°"),
        },
        {
            'key': 'excessive_swing',
            'condition': 'Excessive body swing (hip-X > 0.80 femur-length, non-kipping style)',
            'metric': 'Hip-X swing',
            'cap': 55,
            'eval': lambda mv: (mv['hip_x_amp_norm'] > 0.80,
                                f"{mv['hip_x_amp_norm']:.2f} femur-length"),
            'suppress_if_style': ('kipping', 'butterfly'),
        },
    ]
    if style in ('strict', 'tactical', 'sternum', 'c2b'):
        base.append({
            'key': 'kipping_on_strict',
            'condition': 'Kipping detected on strict scoring (hip-X swing > 0.40 femur-length)',
            'metric': 'Hip-X swing',
            'cap': 60,
            'eval': lambda mv: (mv['hip_x_amp_norm'] > 0.40,
                                f"{mv['hip_x_amp_norm']:.2f} femur-length"),
        })
    return base


# ─────────────────────────────────────────────────────────────────────
# Spec §8 — grade mapping.
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
        'thumb':    LM['LEFT_THUMB']    if side == 'left' else LM['RIGHT_THUMB'],
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


def _process_view(path, view_name):
    """Extract pose + per-frame signals from one camera video."""
    data = extract_all_landmarks(path)
    frames = data['frames']
    fps = data['fps']
    w, h = data['width'], data['height']

    side = _pick_near_side(frames)
    idx = _side_idx(side)

    wrist_x, wrist_y = [], []
    elbow_x, elbow_y = [], []
    shoulder_x, shoulder_y = [], []
    hip_x, hip_y = [], []
    knee_x, knee_y = [], []
    ankle_x, ankle_y = [], []
    ear_y = []
    nose_x, nose_y = [], []
    mouth_x, mouth_y = [], []
    chin_y = []; chin_visible = []
    thumb_x, thumb_y = [], []
    index_x, index_y = [], []
    lwr_x, lwr_y, rwr_x, rwr_y = [], [], [], []
    lsh_x, lsh_y, rsh_x, rsh_y = [], [], [], []
    lhp_x, lhp_y, rhp_x, rhp_y = [], [], [], []
    lkn_x, lkn_y, rkn_x, rkn_y = [], [], [], []
    elbow_angle = []
    elbow_left_angle = []; elbow_right_angle = []
    hip_flex_angle = []
    body_inclination = []
    body_line_angle = []
    head_neck_dev = []
    shoulder_y_left = []; shoulder_y_right = []

    for f in frames:
        lm = f['landmarks']
        if lm is None:
            for arr in (wrist_x, wrist_y, elbow_x, elbow_y, shoulder_x, shoulder_y,
                        hip_x, hip_y, knee_x, knee_y, ankle_x, ankle_y,
                        ear_y, nose_x, nose_y, mouth_x, mouth_y,
                        thumb_x, thumb_y, index_x, index_y,
                        lwr_x, lwr_y, rwr_x, rwr_y, lsh_x, lsh_y, rsh_x, rsh_y,
                        lhp_x, lhp_y, rhp_x, rhp_y, lkn_x, lkn_y, rkn_x, rkn_y,
                        elbow_angle, elbow_left_angle, elbow_right_angle,
                        hip_flex_angle, body_inclination, body_line_angle,
                        head_neck_dev, shoulder_y_left, shoulder_y_right, chin_y):
                arr.append(None)
            chin_visible.append(False)
            continue
        wr = get_landmark_px(lm, idx['wrist'], w, h)
        el = get_landmark_px(lm, idx['elbow'], w, h)
        sh = get_landmark_px(lm, idx['shoulder'], w, h)
        hp = get_landmark_px(lm, idx['hip'], w, h)
        kn = get_landmark_px(lm, idx['knee'], w, h)
        an = get_landmark_px(lm, idx['ankle'], w, h)
        er = get_landmark_px(lm, idx['ear'], w, h)
        no = get_landmark_px(lm, LM['NOSE'], w, h)
        ml = get_landmark_px(lm, LM['MOUTH_LEFT'], w, h)
        mr = get_landmark_px(lm, LM['MOUTH_RIGHT'], w, h)
        th = get_landmark_px(lm, idx['thumb'], w, h)
        ix = get_landmark_px(lm, idx['index'], w, h)
        lw = get_landmark_px(lm, LM['LEFT_WRIST'], w, h)
        rw = get_landmark_px(lm, LM['RIGHT_WRIST'], w, h)
        ls = get_landmark_px(lm, LM['LEFT_SHOULDER'], w, h)
        rs = get_landmark_px(lm, LM['RIGHT_SHOULDER'], w, h)
        lhp = get_landmark_px(lm, LM['LEFT_HIP'], w, h)
        rhp = get_landmark_px(lm, LM['RIGHT_HIP'], w, h)
        lkn_p = get_landmark_px(lm, LM['LEFT_KNEE'], w, h)
        rkn_p = get_landmark_px(lm, LM['RIGHT_KNEE'], w, h)
        le = get_landmark_px(lm, LM['LEFT_ELBOW'], w, h)
        re_ = get_landmark_px(lm, LM['RIGHT_ELBOW'], w, h)
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
        ear_y.append(er[1] if er else None)
        nose_x.append(no[0] if no else None); nose_y.append(no[1] if no else None)
        thumb_x.append(th[0] if th else None); thumb_y.append(th[1] if th else None)
        index_x.append(ix[0] if ix else None); index_y.append(ix[1] if ix else None)
        lwr_x.append(lw[0] if lw else None); lwr_y.append(lw[1] if lw else None)
        rwr_x.append(rw[0] if rw else None); rwr_y.append(rw[1] if rw else None)
        lsh_x.append(ls[0] if ls else None); lsh_y.append(ls[1] if ls else None)
        rsh_x.append(rs[0] if rs else None); rsh_y.append(rs[1] if rs else None)
        lhp_x.append(lhp[0] if lhp else None); lhp_y.append(lhp[1] if lhp else None)
        rhp_x.append(rhp[0] if rhp else None); rhp_y.append(rhp[1] if rhp else None)
        lkn_x.append(lkn_p[0] if lkn_p else None); lkn_y.append(lkn_p[1] if lkn_p else None)
        rkn_x.append(rkn_p[0] if rkn_p else None); rkn_y.append(rkn_p[1] if rkn_p else None)
        shoulder_y_left.append(ls[1] if ls else None)
        shoulder_y_right.append(rs[1] if rs else None)

        # Mouth centre is the preferred chin-over-bar reference; fallback to nose
        if ml and mr:
            mouth_x.append((ml[0] + mr[0]) / 2.0)
            mouth_y.append((ml[1] + mr[1]) / 2.0)
            chin_y.append((ml[1] + mr[1]) / 2.0)
            chin_visible.append(True)
        elif no:
            mouth_x.append(no[0]); mouth_y.append(no[1])
            chin_y.append(no[1]); chin_visible.append(True)
        else:
            mouth_x.append(None); mouth_y.append(None)
            chin_y.append(None); chin_visible.append(False)

        elbow_left_angle.append(angle_3pt(ls, le, lw) if (ls and le and lw) else None)
        elbow_right_angle.append(angle_3pt(rs, re_, rw) if (rs and re_ and rw) else None)
        elbow_angle.append(angle_3pt(sh, el, wr) if (sh and el and wr) else None)
        hip_flex_angle.append(angle_3pt(sh, hp, kn) if (sh and hp and kn) else None)
        if smid and amid:
            dx, dy = smid[0] - amid[0], amid[1] - smid[1]
            body_inclination.append(math.degrees(math.atan2(dx, abs(dy) + 1e-6)))
        elif smid and kmid:
            dx, dy = smid[0] - kmid[0], kmid[1] - smid[1]
            body_inclination.append(math.degrees(math.atan2(dx, abs(dy) + 1e-6)))
        else:
            body_inclination.append(None)
        body_line_angle.append(angle_3pt(smid, hmid, kmid)
                                if (smid and hmid and kmid) else None)
        if smid and hmid and no:
            dx1, dy1 = no[0] - smid[0], smid[1] - no[1]
            dx2, dy2 = smid[0] - hmid[0], hmid[1] - smid[1]
            ang1 = math.atan2(dx1, abs(dy1) + 1e-6)
            ang2 = math.atan2(dx2, abs(dy2) + 1e-6)
            head_neck_dev.append(abs(math.degrees(ang1 - ang2)))
        else:
            head_neck_dev.append(None)

    return {
        'name': view_name,
        'frames': frames, 'fps': fps, 'w': w, 'h': h, 'side': side, 'idx': idx,
        'wrist_x': wrist_x, 'wrist_y': wrist_y,
        'elbow_x': elbow_x, 'elbow_y': elbow_y,
        'shoulder_x': shoulder_x, 'shoulder_y': shoulder_y,
        'hip_x': hip_x, 'hip_y': hip_y,
        'knee_x': knee_x, 'knee_y': knee_y,
        'ankle_x': ankle_x, 'ankle_y': ankle_y,
        'ear_y': ear_y, 'nose_x': nose_x, 'nose_y': nose_y,
        'mouth_x': mouth_x, 'mouth_y': mouth_y,
        'chin_y': chin_y, 'chin_visible': chin_visible,
        'thumb_x': thumb_x, 'thumb_y': thumb_y,
        'index_x': index_x, 'index_y': index_y,
        'lwr_x': lwr_x, 'lwr_y': lwr_y, 'rwr_x': rwr_x, 'rwr_y': rwr_y,
        'lsh_x': lsh_x, 'lsh_y': lsh_y, 'rsh_x': rsh_x, 'rsh_y': rsh_y,
        'lhp_x': lhp_x, 'lhp_y': lhp_y, 'rhp_x': rhp_x, 'rhp_y': rhp_y,
        'lkn_x': lkn_x, 'lkn_y': lkn_y, 'rkn_x': rkn_x, 'rkn_y': rkn_y,
        'elbow_angle': elbow_angle,
        'elbow_left_angle': elbow_left_angle,
        'elbow_right_angle': elbow_right_angle,
        'hip_flex_angle': hip_flex_angle,
        'body_inclination': body_inclination,
        'body_line_angle': body_line_angle,
        'head_neck_dev': head_neck_dev,
        'shoulder_y_left': shoulder_y_left,
        'shoulder_y_right': shoulder_y_right,
    }


# ─────────────────────────────────────────────────────────────────────
# Rep detection — DUAL EXTREME (dead-hang + chin-over-bar).
# Spec §12.3.3 / §11.12 state machine.
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
    """Schmitt-trigger state machine on chin-over-bar clearance + elbow angle.
    Returns reps with `start`, `dead_hang` (bottom), `top` (chin peak),
    `top_start`, `top_end`, `end`, `top_clearance_px`, `dnc` flag."""
    fps = view['fps']
    target = max(1, int(target_reps or 5))
    chin_y = view['chin_y']
    wrist_y = view['wrist_y']
    elbow_angle = view['elbow_angle']
    fw = float(view['w'])

    clearance = []
    for cy, wy in zip(chin_y, wrist_y):
        if cy is None or wy is None:
            clearance.append(None)
        else:
            clearance.append(wy - cy)   # positive = chin above bar
    filled_cl = _fill_signal(clearance)
    filled_el = _fill_signal(elbow_angle)
    if not filled_cl:
        return []

    above_thresh = fw * 0.005    # ~0.5% of frame width — chin clearly above
    n = len(filled_cl)

    state = 'DEAD_HANG'
    reps = []
    rep_start = 0
    top_start = None; top_frame = None; top_clearance = 0.0
    last_top_end = 0
    dead_hang_frame = 0

    for i in range(n):
        cl = filled_cl[i] if filled_cl[i] is not None else 0.0
        el = filled_el[i] if filled_el[i] is not None else 180.0
        if state == 'DEAD_HANG':
            if cl > 0 or el < 165:
                state = 'CONCENTRIC'
                rep_start = max(0, i - 2)
        elif state == 'CONCENTRIC':
            if cl >= above_thresh:
                state = 'TOP'
                top_start = i; top_frame = i; top_clearance = cl
        elif state == 'TOP':
            if cl > top_clearance:
                top_clearance = cl; top_frame = i
            if cl < above_thresh * 0.5:
                last_top_end = i
                state = 'ECCENTRIC'
        elif state == 'ECCENTRIC':
            if el >= 170:
                dead_hang_frame = i
                refine_end = min(n - 1, i + int(fps * 0.5))
                best_el = el; best_i = i
                for j in range(i, refine_end + 1):
                    if filled_el[j] is not None and filled_el[j] > best_el:
                        best_el = filled_el[j]; best_i = j
                dead_hang_frame = best_i
                reps.append({
                    'idx': len(reps) + 1,
                    'start': rep_start,
                    'dead_hang': dead_hang_frame,
                    'top_start': top_start if top_start is not None else top_frame,
                    'top': top_frame if top_frame is not None else top_start,
                    'top_end': last_top_end,
                    'end': dead_hang_frame,
                    'top_clearance_px': top_clearance,
                    'dnc': False,
                })
                rep_start = dead_hang_frame
                state = 'DEAD_HANG'
                top_start = top_frame = None
                top_clearance = 0.0

    # If video ended mid-rep with a clear top detected, count it
    if top_frame is not None and len(reps) < target:
        reps.append({
            'idx': len(reps) + 1,
            'start': rep_start,
            'dead_hang': dead_hang_frame if dead_hang_frame else n - 1,
            'top_start': top_start or top_frame,
            'top': top_frame,
            'top_end': last_top_end or top_frame,
            'end': n - 1,
            'top_clearance_px': top_clearance,
            'dnc': False,
        })

    # DNC detection: long stretch of None wrist landmarks inside a rep
    for r in reps:
        gap = 0; max_gap = 0
        for fi in range(r['start'], min(r['end'] + 1, len(wrist_y))):
            if wrist_y[fi] is None:
                gap += 1; max_gap = max(max_gap, gap)
            else:
                gap = 0
        if fps > 0 and (max_gap / fps) > 0.2:
            r['dnc'] = True

    # Trim to target by highest clearance (cleanest reps)
    if target and len(reps) > target:
        reps = sorted(reps, key=lambda r: r['top_clearance_px'], reverse=True)[:target]
        reps = sorted(reps, key=lambda r: r['top'])
    for i, r in enumerate(reps):
        r['idx'] = i + 1
    return reps


# ─────────────────────────────────────────────────────────────────────
# Per-rep metric computation — all 33 spec metrics
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


def _length_at(view, idx, y_key_a, y_key_b):
    a = view[y_key_a][idx] if idx < len(view[y_key_a]) else None
    b = view[y_key_b][idx] if idx < len(view[y_key_b]) else None
    if a is None or b is None:
        return None
    return abs(b - a)


def _width_at(view, idx, x_key_a, x_key_b):
    a = view[x_key_a][idx] if idx < len(view[x_key_a]) else None
    b = view[x_key_b][idx] if idx < len(view[x_key_b]) else None
    if a is None or b is None:
        return None
    return abs(b - a)


def _compute_rep_metrics(rep, sag, front, post, obl, grip, style):
    start, dh, top, end = rep['start'], rep['dead_hang'], rep['top'], rep['end']
    fps = sag['fps']
    mv = {}

    # Calibration proxies (pixel lengths at dead-hang)
    torso_px = _length_at(sag, dh, 'shoulder_y', 'hip_y') or 100.0
    femur_px = _length_at(sag, dh, 'hip_y', 'knee_y') or 80.0
    leg_px   = _length_at(sag, dh, 'hip_y', 'ankle_y') or 160.0
    hip_width_px = _width_at(sag, dh, 'lhp_x', 'rhp_x') or 40.0
    cm_per_px = 50.0 / max(1.0, torso_px)   # torso ≈ 50 cm

    # §3.1 Dead-hang elbow angle (bottom)
    mv['dead_hang_elbow_deg'] = _safe_at(sag['elbow_angle'], dh, 175.0)
    # §3.2 Body inclination at bottom
    mv['body_inclination_bottom_deg'] = abs(_safe_at(sag['body_inclination'], dh, 5.0))
    # §3.3 Body inclination at top
    mv['body_inclination_top_deg'] = abs(_safe_at(sag['body_inclination'], top, 5.0))

    # §3.4 Active scapular initiation — ratio of shoulder-Y drop to elbow flexion
    init_win = max(1, int(fps * 0.15))
    init_end = min(dh + init_win, len(sag['shoulder_y']) - 1)
    sy_dh = _safe_at(sag['shoulder_y'], dh, None)
    sy_after = _safe_at(sag['shoulder_y'], init_end, None)
    el_dh = _safe_at(sag['elbow_angle'], dh, None)
    el_after = _safe_at(sag['elbow_angle'], init_end, None)
    if sy_dh is not None and sy_after is not None and el_dh is not None and el_after is not None:
        delta_sy = abs(sy_dh - sy_after)
        delta_el = abs(el_dh - el_after)
        mv['scapular_init_ratio'] = (delta_sy / max(1.0, torso_px)) / max(0.01, delta_el / 90.0)
    else:
        mv['scapular_init_ratio'] = 1.0

    # §3.5 Elbow angle at top
    mv['elbow_top_deg'] = _safe_at(sag['elbow_angle'], top, 70.0)

    # §3.6 Chin-over-bar clearance in cm + hold duration
    mv['chin_clearance_cm'] = rep['top_clearance_px'] * cm_per_px
    if rep.get('top_end') is not None and rep.get('top_start') is not None and fps > 0:
        mv['chin_clearance_hold_sec'] = max(0.0, (rep['top_end'] - rep['top_start']) / fps)
    else:
        mv['chin_clearance_hold_sec'] = 0.0

    # §3.7 Sternum-to-bar (C2B variants only)
    sh_at_top = _safe_at(sag['shoulder_y'], top, None)
    wr_at_top = _safe_at(sag['wrist_y'], top, None)
    if sh_at_top is not None and wr_at_top is not None:
        sternum_y = sh_at_top + 0.10 * torso_px
        mv['sternum_to_bar_cm'] = (sternum_y - wr_at_top) * cm_per_px
    else:
        mv['sternum_to_bar_cm'] = 5.0

    # §3.8 Body line / hollow body SD
    bl = [v for v in sag['body_line_angle'][start:end + 1] if v is not None]
    if len(bl) >= 4:
        m = sum(bl) / len(bl)
        mv['body_line_sd_deg'] = math.sqrt(sum((v - m) ** 2 for v in bl) / len(bl))
    else:
        mv['body_line_sd_deg'] = 3.0

    # §3.9 Hip flexion consistency
    hf = [v for v in sag['hip_flex_angle'][start:end + 1] if v is not None]
    if len(hf) >= 4:
        m = sum(hf) / len(hf)
        mv['hip_flex_sd_deg'] = math.sqrt(sum((v - m) ** 2 for v in hf) / len(hf))
    else:
        mv['hip_flex_sd_deg'] = 5.0

    # §3.10 Knee position / scissor
    seps = []
    for fi in range(start, min(end + 1, len(sag['lkn_x']))):
        if sag['lkn_x'][fi] is not None and sag['rkn_x'][fi] is not None:
            seps.append(abs(sag['lkn_x'][fi] - sag['rkn_x'][fi]))
    knee_sep_avg = _mean(seps) if seps else hip_width_px * 1.2
    mv['knee_sep_ratio'] = knee_sep_avg / max(1.0, hip_width_px)

    # §3.11 Kipping detection — hip-X peak-to-peak / femur length
    hxs = [v for v in sag['hip_x'][start:end + 1] if v is not None]
    mv['hip_x_amp_norm'] = ((max(hxs) - min(hxs)) / max(1.0, femur_px)) if len(hxs) >= 4 else 0.05

    # §3.12 Leg swing — ankle-X / leg length
    axs = [v for v in sag['ankle_x'][start:end + 1] if v is not None]
    mv['ankle_x_amp_norm'] = ((max(axs) - min(axs)) / max(1.0, leg_px)) if len(axs) >= 4 else 0.10

    # §3.13 Bar-path-vs-body (wrist-X drift, % of image width)
    wxs = [v for v in sag['wrist_x'][start:end + 1] if v is not None]
    mv['wrist_x_drift_pct'] = ((max(wxs) - min(wxs)) / float(sag['w']) * 100.0) if len(wxs) >= 4 else 1.5

    # §3.14 Head/neck position (chin-poke) at top
    mv['head_neck_dev_deg'] = abs(_safe_at(sag['head_neck_dev'], top, 8.0))

    # §4.1 Grip width (frontal preferred)
    mv['grip_width_ratio'] = _compute_grip_width(front or sag, dh)

    # §4.2 Hand symmetry
    mv['hand_sym_pct'] = _compute_hand_symmetry(front or sag, dh)

    # §4.3 Shoulder symmetry at top
    mv['shoulder_tilt_deg'], mv['shoulder_y_asym_pct'] = _compute_shoulder_symmetry(
        front or sag, top, torso_px)

    # §4.4 Elbow flare (frontal)
    mv['elbow_flare_deg'] = _compute_elbow_flare(front or sag, top)

    # §4.5 Lateral body sway (frontal)
    if front:
        cxs = []
        a = _nearest_frame(front, start, sag)
        b = _nearest_frame(front, end, sag)
        for fi in range(a, min(b + 1, len(front['lhp_x']))):
            lhx = front['lhp_x'][fi]; rhx = front['rhp_x'][fi]
            if lhx is not None and rhx is not None:
                cxs.append((lhx + rhx) / 2.0)
        mv['lateral_sway_norm'] = ((max(cxs) - min(cxs)) / max(1.0, femur_px)) if len(cxs) >= 4 else 0.05
    else:
        mv['lateral_sway_norm'] = 0.05

    # §4.6 Vertical head alignment
    if front:
        t = _nearest_frame(front, top, sag)
        nx = front['nose_x'][t] if t < len(front['nose_x']) else None
        lwx = front['lwr_x'][t] if t < len(front['lwr_x']) else None
        rwx = front['rwr_x'][t] if t < len(front['rwr_x']) else None
        if nx is not None and lwx is not None and rwx is not None:
            mid = (lwx + rwx) / 2.0
            sep = max(1.0, abs(lwx - rwx))
            mv['head_align_pct'] = abs(nx - mid) / sep * 100.0
        else:
            mv['head_align_pct'] = 5.0
    else:
        mv['head_align_pct'] = 5.0

    # §5.1 Scapular retraction (rear)
    if post:
        d_top = _shoulder_distance(post, _nearest_frame(post, top, sag))
        d_bot = _shoulder_distance(post, _nearest_frame(post, dh, sag))
        if d_top and d_bot and d_bot > 0:
            mv['scap_retraction_pct'] = (d_top - d_bot) / d_bot * 100.0
        else:
            mv['scap_retraction_pct'] = -5.0
    else:
        mv['scap_retraction_pct'] = -5.0

    # §5.2 Scapular depression at top (shoulder-to-ear cm)
    sh_at_top_y = _safe_at(sag['shoulder_y'], top, None)
    ear_at_top = _safe_at(sag['ear_y'], top, None)
    if sh_at_top_y is not None and ear_at_top is not None:
        dist_px = sh_at_top_y - ear_at_top
        mv['shoulder_to_ear_cm'] = max(0.0, dist_px * cm_per_px)
    else:
        mv['shoulder_to_ear_cm'] = 12.0

    # §5.3 Lat flare (posterior)
    if post:
        d_top = _shoulder_distance(post, _nearest_frame(post, top, sag))
        d_bot = _shoulder_distance(post, _nearest_frame(post, dh, sag))
        if d_top and d_bot and d_bot > 0:
            mv['lat_flare_pct'] = (d_top - d_bot) / d_bot * 100.0
        else:
            mv['lat_flare_pct'] = 10.0
    else:
        mv['lat_flare_pct'] = 10.0

    # §5.4 Spinal alignment (rear)
    if post:
        t = _nearest_frame(post, top, sag)
        smid = ((_safe_at(post['lsh_x'], t, 0) + _safe_at(post['rsh_x'], t, 0)) / 2.0,
                (_safe_at(post['lsh_y'], t, 0) + _safe_at(post['rsh_y'], t, 0)) / 2.0)
        hmid = ((_safe_at(post['lhp_x'], t, 0) + _safe_at(post['rhp_x'], t, 0)) / 2.0,
                (_safe_at(post['lhp_y'], t, 0) + _safe_at(post['rhp_y'], t, 0)) / 2.0)
        dx = smid[0] - hmid[0]; dy = hmid[1] - smid[1]
        mv['spinal_lat_deg'] = abs(math.degrees(math.atan2(dx, abs(dy) + 1e-6)))
    else:
        mv['spinal_lat_deg'] = 3.0

    # §5.5 Symmetric ascent — phase lag in frames
    mv['symmetric_ascent_frames'] = _compute_phase_lag(front or sag, start, top)

    # §6.1 Setup quality — motion in 1 s before pull
    setup_start = max(0, start - int(fps * 1.0))
    setup_var = 0.0; cnt = 0
    for fi in range(setup_start, start):
        if fi < len(sag['hip_x']) and sag['hip_x'][fi] is not None:
            hx_next = sag['hip_x'][min(fi + 1, len(sag['hip_x']) - 1)]
            if hx_next is not None:
                setup_var += abs(sag['hip_x'][fi] - hx_next)
                cnt += 1
    mv['setup_motion_px'] = (setup_var / max(1, cnt))

    # §6.2 Concentric tempo (bottom → top)
    mv['concentric_sec'] = max(0.05, (top - dh) / fps) if fps > 0 else 1.5
    # §6.3 Pause at top
    mv['pause_top_sec'] = mv['chin_clearance_hold_sec']
    # §6.4 Eccentric tempo
    mv['eccentric_sec'] = max(0.05, (end - top) / fps) if fps > 0 else 2.0
    # §6.5 Dead-hang reset (same as §3.1 — they reference the same frame)
    mv['dead_hang_reset_deg'] = mv['dead_hang_elbow_deg']
    # §6.6 Sticking-point detection
    mv['sticking_pct'] = _compute_sticking(sag, dh, top)
    return mv


# ─────────────────────────────────────────────────────────────────────
# Scoring (style + grip aware)
# ─────────────────────────────────────────────────────────────────────

def _score_all(mv, grip, style):
    s = {}

    # — Safety —
    s['dead_hang_quality']   = score_one_sided(mv['dead_hang_elbow_deg'], 175, 170, 160, 145, higher_is_better=True)
    s['eccentric_tempo']     = score_ranged(mv['eccentric_sec'], 2.0, 4.0, 1.5, 5.0, 1.0, 6.0, 0.5, 8.0)
    s['shoulder_symmetry']   = score_one_sided(mv['shoulder_y_asym_pct'], 2, 5, 8, 12, higher_is_better=False)
    s['scapular_depression'] = score_one_sided(mv['shoulder_to_ear_cm'], 8, 5, 4, 3, higher_is_better=True)
    s['spinal_alignment']    = score_one_sided(mv['spinal_lat_deg'], 3, 6, 10, 15, higher_is_better=False)
    s['setup_quality']       = score_one_sided(mv['setup_motion_px'], 1, 3, 6, 10, higher_is_better=False)
    s['lateral_body_sway']   = score_one_sided(mv['lateral_sway_norm'], 0.05, 0.10, 0.20, 0.35, higher_is_better=False)

    # — Technique —
    s['chin_over_bar']       = score_one_sided(mv['chin_clearance_cm'], 3, 1, 0, -2, higher_is_better=True)
    # Elbow at top — grip-aware
    if grip == 'supinated':
        s['elbow_top'] = score_one_sided(mv['elbow_top_deg'], 50, 65, 80, 100, higher_is_better=False)
    elif grip == 'wide':
        s['elbow_top'] = score_one_sided(mv['elbow_top_deg'], 80, 95, 105, 120, higher_is_better=False)
    elif grip == 'neutral':
        s['elbow_top'] = score_one_sided(mv['elbow_top_deg'], 55, 70, 85, 105, higher_is_better=False)
    else:
        s['elbow_top'] = score_one_sided(mv['elbow_top_deg'], 60, 75, 90, 105, higher_is_better=False)
    s['body_line']           = score_one_sided(mv['body_line_sd_deg'], 3, 6, 10, 20, higher_is_better=False)
    s['scapular_initiation'] = score_one_sided(mv['scapular_init_ratio'], 1.2, 0.8, 0.4, 0.0, higher_is_better=True)
    s['kipping_detection']   = score_one_sided(mv['hip_x_amp_norm'], 0.10, 0.20, 0.40, 0.80, higher_is_better=False)
    # Body inclination at top
    if style == 'sternum':
        s['body_inclination_top'] = score_ranged(mv['body_inclination_top_deg'],
                                                    45, 70, 35, 75, 25, 80, 10, 85)
    else:
        s['body_inclination_top'] = score_one_sided(mv['body_inclination_top_deg'],
                                                      10, 20, 30, 45, higher_is_better=False)
    # Grip width — grip-aware
    if grip == 'supinated':
        s['grip_width'] = score_ranged(mv['grip_width_ratio'], 0.95, 1.15, 0.85, 1.25, 0.75, 1.40, 0.60, 1.70)
    elif grip == 'wide':
        s['grip_width'] = score_ranged(mv['grip_width_ratio'], 1.50, 2.00, 1.40, 2.10, 1.30, 2.20, 1.10, 2.50)
    elif grip == 'neutral':
        s['grip_width'] = score_ranged(mv['grip_width_ratio'], 1.00, 1.20, 0.90, 1.30, 0.80, 1.45, 0.65, 1.75)
    else:
        s['grip_width'] = score_ranged(mv['grip_width_ratio'], 1.10, 1.35, 1.00, 1.50, 0.85, 1.75, 0.70, 2.00)
    # Elbow flare — grip-aware
    if grip == 'supinated':
        s['elbow_flare'] = score_ranged(mv['elbow_flare_deg'], 0, 15, 0, 25, 0, 40, 0, 55)
    else:
        s['elbow_flare'] = score_ranged(mv['elbow_flare_deg'], 15, 35, 10, 50, 5, 65, 0, 80)
    s['head_neck']               = score_one_sided(mv['head_neck_dev_deg'], 10, 20, 30, 45, higher_is_better=False)
    s['hip_flexion_consistency'] = score_one_sided(mv['hip_flex_sd_deg'], 5, 10, 20, 35, higher_is_better=False)
    s['knee_position']           = score_one_sided(mv['knee_sep_ratio'], 1.2, 1.5, 2.0, 3.0, higher_is_better=False)

    # Kipping/butterfly extras
    if style in ('kipping', 'butterfly'):
        s['hollow_arch_transition'] = score_two_sided(mv['body_line_sd_deg'], 12.0, (4, 8, 14, 22))
        s['symmetric_cycle']        = score_one_sided(mv['symmetric_ascent_frames'], 2, 4, 8, 15, higher_is_better=False)
    if style == 'butterfly':
        s['cycle_continuity'] = score_one_sided(mv['pause_top_sec'], 0.15, 0.30, 0.5, 1.0, higher_is_better=False)

    # — Performance —
    s['concentric_tempo']  = score_ranged(mv['concentric_sec'], 1.0, 2.0, 0.7, 2.5, 0.5, 4.0, 0.3, 6.0)
    s['pause_top']         = score_one_sided(mv['pause_top_sec'], 0.5, 0.3, 0.1, 0.0, higher_is_better=True)
    s['rom_completion']    = score_one_sided(mv['chin_clearance_cm'], 3, 1, 0, -2, higher_is_better=True)
    s['symmetric_ascent']  = score_one_sided(mv['symmetric_ascent_frames'], 2, 4, 8, 15, higher_is_better=False)
    s['sticking_point']    = score_one_sided(mv['sticking_pct'], 15, 25, 35, 50, higher_is_better=False)
    s['bar_path_stability'] = score_one_sided(mv['wrist_x_drift_pct'], 2, 5, 10, 20, higher_is_better=False)
    s['rep_consistency']   = 80.0   # filled in at set level
    if style in ('kipping', 'butterfly'):
        s['cycle_rate'] = 80.0       # filled in at set level
    return s


def _category_scores(sub_scores, style):
    tw = _tech_weights(style)
    pw = _perf_weights(style)
    def _w(weights):
        acc, used = 0.0, 0.0
        for k, w in weights.items():
            v = sub_scores.get(k)
            if v is None:
                continue
            acc += w * float(v); used += w
        return acc / used if used > 0 else 50.0
    return {'safety': _w(SAFETY_W), 'technique': _w(tw), 'performance': _w(pw)}


def _geometric_composite(cat):
    s = max(1e-3, cat['safety'])
    t = max(1e-3, cat['technique'])
    p = max(1e-3, cat['performance'])
    return (s ** CATEGORY_WEIGHTS['safety']) * \
           (t ** CATEGORY_WEIGHTS['technique']) * \
           (p ** CATEGORY_WEIGHTS['performance'])


# ─────────────────────────────────────────────────────────────────────
# Metric helpers (4 view geometry)
# ─────────────────────────────────────────────────────────────────────

def _compute_grip_width(view, frame_idx):
    if view is None:
        return 1.2
    fi = min(frame_idx, len(view['lwr_x']) - 1) if view['lwr_x'] else 0
    lwx = view['lwr_x'][fi]; rwx = view['rwr_x'][fi]
    lsx = view['lsh_x'][fi]; rsx = view['rsh_x'][fi]
    if None in (lwx, rwx, lsx, rsx):
        return 1.2
    wd = math.hypot(lwx - rwx, (view['lwr_y'][fi] or 0) - (view['rwr_y'][fi] or 0))
    sd = math.hypot(lsx - rsx, (view['lsh_y'][fi] or 0) - (view['rsh_y'][fi] or 0))
    return wd / max(1e-3, sd)


def _compute_hand_symmetry(view, frame_idx):
    if view is None:
        return 2.0
    fi = min(frame_idx, len(view['lwr_x']) - 1) if view['lwr_x'] else 0
    lwx = view['lwr_x'][fi]; rwx = view['rwr_x'][fi]
    nx = view['nose_x'][fi] if fi < len(view['nose_x']) else None
    if None in (lwx, rwx) or nx is None:
        return 2.0
    biacromial = _width_at(view, fi, 'lsh_x', 'rsh_x') or 1.0
    left_dist = abs(lwx - nx); right_dist = abs(rwx - nx)
    return abs(left_dist - right_dist) / max(1.0, biacromial) * 100.0


def _compute_shoulder_symmetry(view, frame_idx, torso_px):
    if view is None:
        return 3.0, 2.0
    fi = min(frame_idx, len(view['lsh_y']) - 1) if view['lsh_y'] else 0
    lsy = view['lsh_y'][fi]; rsy = view['rsh_y'][fi]
    lsx = view['lsh_x'][fi]; rsx = view['rsh_x'][fi]
    if None in (lsy, rsy, lsx, rsx):
        return 3.0, 2.0
    dy = abs(lsy - rsy); dx = abs(lsx - rsx) + 1e-6
    tilt = math.degrees(math.atan2(dy, dx))
    asym_pct = dy / max(1.0, torso_px) * 100.0
    return tilt, asym_pct


def _compute_elbow_flare(view, frame_idx):
    """Angle of (shoulder → elbow) from vertical."""
    if view is None:
        return 30.0
    fi = min(frame_idx, len(view['shoulder_x']) - 1) if view['shoulder_x'] else 0
    sx = view['shoulder_x'][fi] if fi < len(view['shoulder_x']) else None
    sy = view['shoulder_y'][fi] if fi < len(view['shoulder_y']) else None
    ex = view['elbow_x'][fi] if fi < len(view['elbow_x']) else None
    ey = view['elbow_y'][fi] if fi < len(view['elbow_y']) else None
    if None in (sx, sy, ex, ey):
        return 30.0
    dx = ex - sx
    dy = ey - sy
    return math.degrees(math.atan2(abs(dx), abs(dy) + 1e-6))


def _shoulder_distance(view, frame_idx):
    if view is None:
        return None
    fi = min(frame_idx, len(view['lsh_x']) - 1) if view['lsh_x'] else 0
    lsx = view['lsh_x'][fi]; lsy = view['lsh_y'][fi]
    rsx = view['rsh_x'][fi]; rsy = view['rsh_y'][fi]
    if None in (lsx, lsy, rsx, rsy):
        return None
    return math.hypot(lsx - rsx, lsy - rsy)


def _compute_phase_lag(view, start, top):
    if view is None or top <= start + 2:
        return 2
    lsy = view['shoulder_y_left']; rsy = view['shoulder_y_right']
    seq_l, seq_r = [], []
    for fi in range(start, min(top + 1, len(lsy), len(rsy))):
        if lsy[fi] is not None and rsy[fi] is not None:
            seq_l.append(lsy[fi]); seq_r.append(rsy[fi])
    n = min(len(seq_l), len(seq_r))
    if n < 6:
        return 2
    best_lag = 0; best_score = -1e9
    for lag in range(-min(5, n // 4), min(5, n // 4) + 1):
        if lag >= 0:
            a = seq_l[:n - lag]; b = seq_r[lag:n]
        else:
            a = seq_l[-lag:n]; b = seq_r[:n + lag]
        if not a or not b:
            continue
        m_a = _mean(a); m_b = _mean(b)
        num = sum((ai - m_a) * (bi - m_b) for ai, bi in zip(a, b))
        if num > best_score:
            best_score = num; best_lag = lag
    return abs(best_lag)


def _compute_sticking(view, dh, top):
    if top <= dh + 2:
        return 20.0
    sh_y = view['shoulder_y']
    vels = []
    for fi in range(dh, top):
        a = sh_y[fi] if fi < len(sh_y) else None
        b = sh_y[fi + 1] if fi + 1 < len(sh_y) else None
        if a is None or b is None:
            vels.append(0.0)
        else:
            vels.append(max(0.0, a - b))   # positive = body moves up in image
    if not vels:
        return 20.0
    peak = max(vels)
    if peak <= 0.01:
        return 50.0
    threshold = 0.30 * peak
    slow = sum(1 for v in vels if v < threshold)
    return slow / len(vels) * 100.0


# ─────────────────────────────────────────────────────────────────────
# Corrective cues (spec §10.5)
# ─────────────────────────────────────────────────────────────────────

CUE_TEMPLATES = {
    'dead_hang_quality': ("Dead-hang quality",
        "Reach full elbow extension at the bottom of every rep (≥170°). "
        "Partial ROM is the #1 cheat — count fewer reps cleanly."),
    'eccentric_tempo': ("Eccentric tempo",
        "Lower under control in 2–4 s. Free-fall drops (< 0.5 s) put the rotator cuff at risk."),
    'shoulder_symmetry': ("Shoulder symmetry at top",
        "One side is leading. Pull evenly with both arms; add single-arm assisted reps on the weak side."),
    'scapular_depression': ("Scapular depression at top",
        "Shoulders are shrugging up to the ears at peak effort. Pull shoulders AWAY from ears — \"long neck\"."),
    'spinal_alignment': ("Spinal alignment",
        "Lateral lean detected from the rear view. Brace the trunk; keep hips and shoulders stacked."),
    'setup_quality': ("Setup quality",
        "Jump and grip introduced residual swing. Step up, then come to MOTIONLESS DEAD HANG for ≥1 s."),
    'lateral_body_sway': ("Lateral body sway",
        "Body is swinging side-to-side. Glutes tight, abs braced — treat the body as a rigid hollow stick."),
    'chin_over_bar': ("Chin-over-bar (ROM)",
        "Chin must clearly break the bar plane. Neck-craning doesn't count — pull chest up, not chin over."),
    'elbow_top': ("Elbow angle at top",
        "Pull higher. Peak should bring the elbow well under 90° (closer to 60–70° pronated, 50–55° chin-up)."),
    'body_line': ("Body line / hollow body",
        "Body line drifted during the rep. Brace abs as for a dead-bug; \"wrinkle the front of your shirt\"."),
    'scapular_initiation': ("Active scapular initiation",
        "Pull is starting with biceps, not lats. Cue: pull shoulder blades DOWN and BACK before the elbow flexes."),
    'kipping_detection': ("Kipping in strict scoring",
        "Hip-X swing detected on a strict attempt. Lower the load (band) or break the set into clusters."),
    'body_inclination_top': ("Body inclination at top",
        "Body is leaning too far back at the top. Cue: vertical body line, chin to bar, not chest to floor."),
    'grip_width': ("Grip width",
        "Grip is outside the band for your variant. Match the spec band for your grip choice."),
    'elbow_flare': ("Elbow flare",
        "Elbows flaring out to the sides. Drive elbows DOWN to your hips — pull-up, not lat-pulldown."),
    'head_neck': ("Head / neck (chin-poke)",
        "Chin-poking detected at top. Hold an imaginary orange between chin and chest; pull chest up."),
    'hip_flexion_consistency': ("Hip flexion consistency",
        "Legs flicking during the rep (hip kick). Lock legs in the chosen position and HOLD it."),
    'knee_position': ("Knee position / scissor",
        "Knees scissoring or splitting wide for momentum. Glue the knees together; cross ankles if helpful."),
    'hollow_arch_transition': ("Hollow-arch transition (kipping)",
        "Hollow → arch cycle inconsistent. Train hollow-body and arch positions in isolation first."),
    'symmetric_cycle': ("Symmetric kip cycle",
        "L/R side out of phase during the kip. Drill the cadence at low rep counts."),
    'cycle_continuity': ("Butterfly cycle continuity",
        "Pause at top is too long — true butterfly is continuous. Athlete drops in FRONT of the bar."),
    'concentric_tempo': ("Concentric tempo",
        "Pull was too fast (jerky) or too slow (grinder). Aim for a controlled 1.0–2.0 s on strict reps."),
    'pause_top': ("Pause at top",
        "No hold at chin-over-bar. Pause and OWN the top position for ≥0.3 s."),
    'rom_completion': ("ROM completion",
        "Some reps didn't clear the bar OR didn't return to dead hang. Earn full reps before counting them."),
    'symmetric_ascent': ("Symmetric ascent",
        "L/R shoulders rose out of phase. Address strength asymmetry with single-arm work."),
    'sticking_point': ("Sticking-point severity",
        "Too long in the sticking region (~90° elbow). Train pin-pull-ups at the sticking height."),
    'bar_path_stability': ("Bar-path stability",
        "Wrist drifted across the bar — hand creep. Re-grip and squeeze hard."),
    'rep_consistency': ("Rep-to-rep consistency",
        "Form drifted across the set. Drop the rep count by 1–2 and rebuild the groove."),
    'cycle_rate': ("Kip cycle rate consistency",
        "Cycle rhythm is irregular. Practise the kip cadence in a low-rep cluster."),
}


def _coaching_for(slug, sub_score):
    name, body = CUE_TEMPLATES.get(slug, (slug, "Work on this metric."))
    return {'metric': name, 'sub_score': round(float(sub_score), 1), 'cue': body}


# ─────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────

def analyse(files, weight_max=None, reps_max=None, target_reps=None,
            target_reps_sagittal=None, target_reps_frontal=None,
            target_reps_posterior=None, target_reps_oblique=None,
            grip='pronated', style='strict',
            athlete_height_cm=None):
    """Analyze a pull-up set across four camera views.

    Required: files['sagittal'] (back-compat aliases: 'front' or 'side').
    Recommended: files['frontal'], files['posterior'], files['oblique'].
    """
    # Normalise legacy grip values to the spec's 4 categories
    g = (grip or 'pronated').lower()
    if g in ('pronated-wide',):
        g = 'wide'
    elif g in ('pronated-medium', 'pronated-narrow', 'pronated-shoulder'):
        g = 'pronated'
    elif g in ('parallel',):
        g = 'neutral'
    if g not in ('pronated', 'supinated', 'neutral', 'wide'):
        g = 'pronated'
    grip = g

    style = (style or 'strict').lower()
    if style not in ('strict', 'kipping', 'butterfly', 'sternum', 'c2b', 'tactical'):
        style = 'strict'

    legacy_default = target_reps or 5
    counts = {
        'sagittal':  target_reps_sagittal  or legacy_default,
        'frontal':   target_reps_frontal   or legacy_default,
        'posterior': target_reps_posterior or legacy_default,
        'oblique':   target_reps_oblique   or legacy_default,
    }

    sag_path = (files or {}).get('sagittal') or (files or {}).get('front') or (files or {}).get('side')
    front_path = (files or {}).get('frontal') or (files or {}).get('front')
    if front_path == sag_path:
        front_path = None
    post_path = (files or {}).get('posterior') or (files or {}).get('rear')
    obl_path = (files or {}).get('oblique')
    if not sag_path and files:
        sag_path = list(files.values())[0]
    if not sag_path:
        return _fallback('No sagittal video uploaded.')

    try:
        sag = _process_view(sag_path, 'sagittal')
    except Exception as e:
        return _fallback(f'Sagittal pose extraction failed: {e}')
    front = _process_view(front_path, 'frontal') if front_path else None
    post = _process_view(post_path, 'posterior') if post_path else None
    obl = _process_view(obl_path, 'oblique') if obl_path else None

    conf = confidence_score(sag['frames'])

    # Detect reps per view (each video uses its own user-supplied rep count)
    reps_by_view = {'sagittal': _detect_reps(sag, counts['sagittal'])}
    if front: reps_by_view['frontal']   = _detect_reps(front, counts['frontal'])
    if post:  reps_by_view['posterior'] = _detect_reps(post, counts['posterior'])
    if obl:   reps_by_view['oblique']   = _detect_reps(obl, counts['oblique'])

    sag_reps = reps_by_view['sagittal']
    if not sag_reps:
        return _fallback('No pull-up reps detected on the sagittal video.')

    # Per-rep metrics + sub-scores
    per_rep = []
    for rep in sag_reps:
        mv = _compute_rep_metrics(rep, sag, front, post, obl, grip, style)
        subs = _score_all(mv, grip, style)
        per_rep.append({
            'rep_num': rep['idx'],
            'sag_rep': rep,
            'dnc': rep['dnc'],
            'metric_values': mv,
            'sub_scores': subs,
        })

    # Set-level consistency
    cv_pct = _consistency_cv(per_rep)
    consistency_score = score_one_sided(cv_pct, 4, 8, 14, 22, higher_is_better=False)
    for r in per_rep:
        r['sub_scores']['rep_consistency'] = consistency_score
        if style in ('kipping', 'butterfly'):
            r['sub_scores']['cycle_rate'] = consistency_score

    for r in per_rep:
        r['categories'] = _category_scores(r['sub_scores'], style)
        r['composite'] = _geometric_composite(r['categories'])

    # Hard-fail overrides
    set_overrides = []
    shrug_count = 0
    for spec in _override_specs(style):
        if spec.get('suppress_if_style') and style in spec['suppress_if_style']:
            continue
        triggered = False; worst_val = None; worst_rep = None
        for r in per_rep:
            if r['dnc']:
                continue
            t, vs = spec['eval'](r['metric_values'])
            if t:
                triggered = True
                if worst_val is None:
                    worst_val = vs; worst_rep = r['rep_num']
                if spec.get('penalty_per_rep'):
                    shrug_count += 1
        cap = spec['cap'] if spec['cap'] < 100 else None
        if spec.get('penalty_per_rep'):
            cap = None
        set_overrides.append({
            'condition': spec['condition'], 'cap': cap,
            'triggered': bool(triggered),
            'triggering_metric': spec['metric'],
            'triggering_value': (f"rep {worst_rep}: {worst_val}" if triggered else None),
        })

    triggered_caps = [o['cap'] for o in set_overrides if o['triggered'] and o['cap']]
    active_cap = min(triggered_caps) if triggered_caps else None
    shrug_penalty = shrug_count * 10
    for r in per_rep:
        if active_cap is not None:
            r['composite'] = min(r['composite'], active_cap)
        if shrug_penalty:
            r['composite'] = max(0.0, r['composite'] - shrug_penalty)

    # DNC exclusion (spec §7.4) — separate from set average
    valid_reps = [r for r in per_rep if not r['dnc']]
    dnc_reps   = [r for r in per_rep if r['dnc']]
    if not valid_reps:
        return _fallback(f"All {len(per_rep)} reps detected as DNC (hand release / fall). "
                          f"No valid reps to score.")

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

    metrics_list = _build_legacy_metrics(valid_reps, grip, style, sub_mean)

    coaching = []
    for o in set_overrides:
        if o['triggered']:
            tail = ""
            if o['cap']:
                tail = f" Composite capped at {o['cap']}."
            elif shrug_penalty:
                tail = f" {shrug_penalty}-point penalty applied."
            coaching.append(
                f"🚩 {o['condition']} — {o['triggering_metric']}"
                + (f" ({o['triggering_value']})" if o['triggering_value'] else "")
                + tail
            )
    for cue in lowest_cues:
        coaching.append(f"Fix: {cue['metric']} ({cue['sub_score']}/100). {cue['cue']}")
    if not coaching:
        coaching.append("Clean strict reps. Add load or lengthen the set for the next session.")
    if deteriorating:
        coaching.append(
            f"Rep{'s' if len(deteriorating) > 1 else ''} {', '.join(str(n) for n in deteriorating)} "
            f"deteriorated > 15 pts below the set mean — fatigue or form drift.")
    if dnc_reps:
        coaching.append(
            f"⚠️ {len(dnc_reps)} rep{'s' if len(dnc_reps) != 1 else ''} marked DNC "
            f"(hand release / mid-rep fall) and excluded from the set average.")

    annotated = _render_frames(
        per_rep, valid_reps, best_idx, worst_idx,
        sag_path, sag, front_path, front, post_path, post, obl_path, obl,
        grip, style, status, headline,
    )

    n_reps_total = counts['sagittal']
    stats = {
        'validReps':   f'{len(valid_reps)}/{n_reps_total}',
        'dncReps':     f'{len(dnc_reps)} DNC' if dnc_reps else '0 DNC',
        'confidence':  f'{conf}%',
        'sides':       sag['side'],
        'cameraView':  'Sagittal + Frontal + Posterior + Oblique',
        'grip':        grip,
        'style':       style,
        'composite':   f'{headline} ({grade})',
        'load':        f'{weight_max} kg added' if weight_max else 'Bodyweight',
    }

    composite_score = {
        'composite': headline,
        'grade': grade,
        'label': label,
        'composite_method': 'geometric',
        'categories': [
            {'name': 'Safety',      'weight': 0.20, 'score': round(cat_means['safety'], 1)},
            {'name': 'Technique',   'weight': 0.45, 'score': round(cat_means['technique'], 1)},
            {'name': 'Performance', 'weight': 0.35, 'score': round(cat_means['performance'], 1)},
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
        'variant': f"{grip} · {style}",
    }

    summary = (f"{label} ({grade}) · composite {headline}/100. "
               f"Safety {round(cat_means['safety'])}, Technique {round(cat_means['technique'])}, "
               f"Performance {round(cat_means['performance'])}.")
    if active_cap is not None:
        summary = f"⚠️ {summary} Capped at {active_cap} by a safety override."
    if dnc_reps:
        summary += f" {len(dnc_reps)} rep(s) DNC."

    result = build_result(status, headline, summary, stats, metrics_list, [], coaching)
    result['annotated_frames'] = annotated
    result['per_rep'] = [
        {'rep': r['rep_num'], 'side': 'center',
         'metrics': _flatten_per_rep_for_ui(r)}
        for r in per_rep
    ]
    result['composite_score'] = composite_score
    result['muscle_activation'] = infer_pull_up(
        grip=grip,
        grip_width_ratio=_mean(r['metric_values']['grip_width_ratio'] for r in valid_reps),
        scapular_initiation=_mean(r['metric_values']['scapular_init_ratio'] for r in valid_reps) > 1.0,
        hip_swing_cm=_mean(r['metric_values']['hip_x_amp_norm'] for r in valid_reps) * 30.0,
    )
    result['meta'] = {
        'camera_view': 'sagittal+frontal+posterior+oblique',
        'camera_view_confidence': round(min(1.0, conf / 100.0), 2),
        'camera_view_warning': None,
        'analyzer_version': 'pull-up-2026-05-20-spec',
    }
    return result


# ─────────────────────────────────────────────────────────────────────
# Annotated frames — DUAL EXTREME per camera
# ─────────────────────────────────────────────────────────────────────

def _render_frames(per_rep, valid_reps, best_idx, worst_idx,
                   sag_path, sag, front_path, front, post_path, post,
                   obl_path, obl, grip, style, status, score):
    """Best + worst valid rep: 4 cameras × 2 extremes = 8 frames each.
    Middle reps: sagittal × 2 extremes = 2 frames each.
    DNC reps: skipped."""
    out = []
    if not per_rep:
        fb = render_sample_frame(sag_path, sag['frames'], sag['w'], sag['h'],
                                 'Pull-Up', 'No reps detected.',
                                 connections=PULL_UP_CONNECTIONS)
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

        # Sagittal × 2 extremes — always
        for extreme in ('dead_hang', 'top'):
            try:
                img = _annotate_sagittal(sag_path, sag, r, extreme, grip, style,
                                          status, score, len(per_rep))
                if img:
                    lbl = f"Rep {r['rep_num']} · Sagittal · {_extreme_label(extreme)}"
                    if is_best:  lbl += " ⭐"
                    if is_worst: lbl += " ⚠"
                    out.append({
                        'label': lbl, 'image_base64': img,
                        'rep_num': r['rep_num'], 'side': f'sagittal-{extreme}',
                        'is_best': is_best,
                        'metrics_shown': _summary_for_overlay(r, 'sagittal', extreme),
                    })
            except Exception as e:
                print(f"[pullup.render] sagittal {extreme} rep {r['rep_num']} failed: {e}")

        # Best + worst rep: other three views × 2 extremes
        if is_rich:
            for view_name, view, path in (
                ('frontal',   front, front_path),
                ('posterior', post,  post_path),
                ('oblique',   obl,   obl_path),
            ):
                if not view or not path:
                    continue
                for extreme in ('dead_hang', 'top'):
                    try:
                        img = _annotate_secondary(path, view, view_name, r, extreme,
                                                    grip, style, status, score,
                                                    len(per_rep), sag)
                        if img:
                            lbl = f"Rep {r['rep_num']} · {_view_label(view_name)} · {_extreme_label(extreme)}"
                            if is_best:  lbl += " ⭐"
                            if is_worst: lbl += " ⚠"
                            out.append({
                                'label': lbl, 'image_base64': img,
                                'rep_num': r['rep_num'],
                                'side': f'{view_name}-{extreme}',
                                'is_best': is_best,
                                'metrics_shown': _summary_for_overlay(r, view_name, extreme),
                            })
                    except Exception as e:
                        print(f"[pullup.render] {view_name} {extreme} rep {r['rep_num']} failed: {e}")

    if not out:
        fb = render_sample_frame(sag_path, sag['frames'], sag['w'], sag['h'],
                                 'Pull-Up', 'Reps detected but frames could not be rendered.',
                                 connections=PULL_UP_CONNECTIONS)
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
    return 'Dead-Hang (bottom)' if name == 'dead_hang' else 'Chin-Over-Bar (top)'


def _summary_for_overlay(r, view_name, extreme):
    mv = r['metric_values']
    if extreme == 'dead_hang':
        if view_name == 'sagittal':
            return [
                f"Composite: {r['composite']:.0f}/100",
                f"Dead-hang elbow: {mv['dead_hang_elbow_deg']:.0f}°",
                f"Body incline (bottom): {mv['body_inclination_bottom_deg']:.1f}°",
                f"Hip-X swing: {mv['hip_x_amp_norm']:.2f}",
            ]
        if view_name == 'frontal':
            return [
                f"Grip width: {mv['grip_width_ratio']:.2f}× BAW",
                f"Hand sym: {mv['hand_sym_pct']:.1f}%",
                f"Lateral sway: {mv['lateral_sway_norm']:.2f}",
            ]
        if view_name == 'posterior':
            return [
                f"Spinal align: {mv['spinal_lat_deg']:.1f}°",
                f"Shoulder dist baseline",
            ]
        return [f"Composite: {r['composite']:.0f}/100"]
    # top
    if view_name == 'sagittal':
        return [
            f"Composite: {r['composite']:.0f}/100",
            f"Chin clearance: {mv['chin_clearance_cm']:.1f} cm",
            f"Elbow @ top: {mv['elbow_top_deg']:.0f}°",
            f"Layback: {mv['body_inclination_top_deg']:.1f}°",
        ]
    if view_name == 'frontal':
        return [
            f"Shoulder tilt: {mv['shoulder_tilt_deg']:.1f}°",
            f"Elbow flare: {mv['elbow_flare_deg']:.0f}°",
            f"Head align: {mv['head_align_pct']:.1f}%",
        ]
    if view_name == 'posterior':
        return [
            f"Scap retract: {mv['scap_retraction_pct']:.1f}%",
            f"Lat flare: {mv['lat_flare_pct']:.1f}%",
            f"Symmetric ascent: {mv['symmetric_ascent_frames']} fr",
        ]
    return [f"Composite: {r['composite']:.0f}/100"]


def _annotate_sagittal(path, sag, rep, extreme, grip, style, status, score, total):
    sag_rep = rep['sag_rep']
    frame_idx = sag_rep['dead_hang'] if extreme == 'dead_hang' else sag_rep['top']
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
    smid = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)

    draw_skeleton(frame, lm, w, h, connections=PULL_UP_CONNECTIONS)
    if wr:
        draw_reference_line(frame, y=wr[1], color=COL_CYAN,
                            label='Bar (wrist line)')

    mv = rep['metric_values']
    if sh and el and wr:
        if extreme == 'dead_hang':
            val = mv['dead_hang_elbow_deg']
            elbow_status = 'good' if val >= 175 else ('warn' if val >= 160 else 'bad')
        else:
            val = mv['elbow_top_deg']
            target_lo = 50 if grip == 'supinated' else (80 if grip == 'wide' else 60)
            target_hi = 65 if grip == 'supinated' else (95 if grip == 'wide' else 75)
            elbow_status = ('good' if target_lo <= val <= target_hi
                            else 'warn' if val <= target_hi + 15 else 'bad')
        draw_angle_arc(frame, el, sh, wr, val,
                       label=f"Elbow {val:.0f}°", radius=50, status=elbow_status)
    if sh and hp and kn:
        hf = _safe_at(sag['hip_flex_angle'], frame_idx, 175.0)
        draw_angle_arc(frame, hp, sh, kn, hf,
                       label=f"Hip {hf:.0f}°", radius=42, status='good')

    if extreme == 'top' and smid:
        cc_status = ('good' if mv['chin_clearance_cm'] >= 3
                     else 'warn' if mv['chin_clearance_cm'] >= 0 else 'bad')
        draw_callout(frame, smid, f"Chin clearance {mv['chin_clearance_cm']:.1f} cm",
                     status=cc_status, offset=(120, -40))
    elif extreme == 'dead_hang' and smid:
        draw_callout(frame, smid, f"Body incline {mv['body_inclination_bottom_deg']:.1f}°",
                     status='good', offset=(120, 30))

    draw_title_strip(frame, f"Pull-Up ({grip} · {style})", rep['rep_num'], total,
                     status=status, score=score)
    draw_phase_label(frame, _extreme_label(extreme))

    if extreme == 'dead_hang':
        overlay = [
            {'label': 'Composite', 'value': f"{rep['composite']:.0f}/100",
             'status': 'good' if rep['composite'] >= 75 else ('warn' if rep['composite'] >= 60 else 'bad')},
            {'label': 'Safety',      'value': f"{rep['categories']['safety']:.0f}", 'status': 'good'},
            {'label': 'Technique',   'value': f"{rep['categories']['technique']:.0f}", 'status': 'good'},
            {'label': 'Performance', 'value': f"{rep['categories']['performance']:.0f}", 'status': 'good'},
            {'label': 'Dead-hang elbow', 'value': f"{mv['dead_hang_elbow_deg']:.0f}°",
             'status': 'good' if mv['dead_hang_elbow_deg'] >= 170 else 'bad'},
            {'label': 'Body incline (bottom)', 'value': f"{mv['body_inclination_bottom_deg']:.1f}°", 'status': 'good'},
            {'label': 'Hip-X swing', 'value': f"{mv['hip_x_amp_norm']:.2f}",
             'status': 'good' if mv['hip_x_amp_norm'] < 0.20 else 'bad'},
            {'label': 'Ankle-X swing', 'value': f"{mv['ankle_x_amp_norm']:.2f}", 'status': 'good'},
            {'label': 'Body line SD',  'value': f"{mv['body_line_sd_deg']:.1f}°", 'status': 'good'},
            {'label': 'Hip flex SD',   'value': f"{mv['hip_flex_sd_deg']:.1f}°", 'status': 'good'},
            {'label': 'Knee sep',      'value': f"{mv['knee_sep_ratio']:.2f}×", 'status': 'good'},
            {'label': 'Bar drift',     'value': f"{mv['wrist_x_drift_pct']:.1f}%", 'status': 'good'},
            {'label': 'Setup motion',  'value': f"{mv['setup_motion_px']:.1f} px", 'status': 'good'},
            {'label': 'Eccentric',     'value': f"{mv['eccentric_sec']:.2f} s",
             'status': 'good' if mv['eccentric_sec'] >= 1.5 else 'warn'},
        ]
        title = f"REP {rep['rep_num']} · DEAD-HANG"
    else:
        overlay = [
            {'label': 'Composite', 'value': f"{rep['composite']:.0f}/100", 'status': 'good'},
            {'label': 'Chin clearance', 'value': f"{mv['chin_clearance_cm']:.1f} cm",
             'status': 'good' if mv['chin_clearance_cm'] >= 1 else 'bad'},
            {'label': 'Elbow @ top', 'value': f"{mv['elbow_top_deg']:.0f}°", 'status': 'good'},
            {'label': 'Layback', 'value': f"{mv['body_inclination_top_deg']:.1f}°", 'status': 'good'},
            {'label': 'Sternum-to-bar', 'value': f"{mv['sternum_to_bar_cm']:.1f} cm", 'status': 'good'},
            {'label': 'Scap init', 'value': f"{mv['scapular_init_ratio']:.2f}",
             'status': 'good' if mv['scapular_init_ratio'] >= 0.8 else 'warn'},
            {'label': 'Shoulder-to-ear', 'value': f"{mv['shoulder_to_ear_cm']:.1f} cm",
             'status': 'good' if mv['shoulder_to_ear_cm'] >= 5 else 'bad'},
            {'label': 'Head/neck', 'value': f"{mv['head_neck_dev_deg']:.1f}°", 'status': 'good'},
            {'label': 'Pause @ top', 'value': f"{mv['pause_top_sec']:.2f} s", 'status': 'good'},
            {'label': 'Concentric', 'value': f"{mv['concentric_sec']:.2f} s", 'status': 'good'},
            {'label': 'Sticking', 'value': f"{mv['sticking_pct']:.0f}%", 'status': 'good'},
        ]
        title = f"REP {rep['rep_num']} · CHIN-OVER-BAR"

    draw_metric_overlay(frame, overlay, position='top-right', title=title)
    draw_legend(frame, position='bottom-left')
    return frame_to_base64(frame)


def _annotate_secondary(path, view, view_name, rep, extreme, grip, style,
                          status, score, total, sag):
    sag_rep = rep['sag_rep']
    sag_frame = sag_rep['dead_hang'] if extreme == 'dead_hang' else sag_rep['top']
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

    draw_skeleton(frame, lm, w, h, connections=PULL_UP_CONNECTIONS)
    mv = rep['metric_values']

    if view_name == 'frontal':
        ls = _lm_to_px(lm, LM['LEFT_SHOULDER'], w, h)
        rs = _lm_to_px(lm, LM['RIGHT_SHOULDER'], w, h)
        if ls and rs:
            mid = ((ls[0] + rs[0]) // 2, (ls[1] + rs[1]) // 2)
            gw_status = 'good' if 1.0 <= mv['grip_width_ratio'] <= 1.5 else 'warn'
            draw_callout(frame, mid,
                         f"Grip {mv['grip_width_ratio']:.2f}× BAW",
                         status=gw_status, offset=(0, 40))
        if extreme == 'top' and ls and rs:
            tilt_status = 'good' if mv['shoulder_tilt_deg'] < 5 else 'bad'
            mid = ((ls[0] + rs[0]) // 2, (ls[1] + rs[1]) // 2)
            draw_callout(frame, mid, f"Sh tilt {mv['shoulder_tilt_deg']:.1f}°",
                         status=tilt_status, offset=(80, -30))

        if extreme == 'dead_hang':
            overlay = [
                {'label': 'Grip width', 'value': f"{mv['grip_width_ratio']:.2f}× BAW", 'status': 'good'},
                {'label': 'Hand sym',   'value': f"{mv['hand_sym_pct']:.1f}%", 'status': 'good'},
                {'label': 'Lateral sway', 'value': f"{mv['lateral_sway_norm']:.2f}", 'status': 'good'},
            ]
        else:
            overlay = [
                {'label': 'Shoulder tilt', 'value': f"{mv['shoulder_tilt_deg']:.1f}°",
                 'status': 'good' if mv['shoulder_tilt_deg'] < 5 else 'bad'},
                {'label': 'Shoulder Y asym', 'value': f"{mv['shoulder_y_asym_pct']:.1f}%", 'status': 'good'},
                {'label': 'Elbow flare', 'value': f"{mv['elbow_flare_deg']:.0f}°",
                 'status': 'good' if mv['elbow_flare_deg'] < 50 else 'bad'},
                {'label': 'Head align', 'value': f"{mv['head_align_pct']:.1f}%", 'status': 'good'},
            ]
        title = f"REP {rep['rep_num']} · FRONTAL · {_extreme_label(extreme).upper()}"
    elif view_name == 'posterior':
        if extreme == 'dead_hang':
            overlay = [
                {'label': 'Spinal align', 'value': f"{mv['spinal_lat_deg']:.1f}°",
                 'status': 'good' if mv['spinal_lat_deg'] < 6 else 'bad'},
                {'label': 'Shoulder distance', 'value': 'baseline', 'status': 'good'},
            ]
        else:
            overlay = [
                {'label': 'Scap retraction', 'value': f"{mv['scap_retraction_pct']:.1f}%",
                 'status': 'good' if mv['scap_retraction_pct'] <= -5 else 'bad'},
                {'label': 'Lat flare', 'value': f"{mv['lat_flare_pct']:.1f}%",
                 'status': 'good' if mv['lat_flare_pct'] >= 10 else 'warn'},
                {'label': 'Spinal lat dev', 'value': f"{mv['spinal_lat_deg']:.1f}°", 'status': 'good'},
                {'label': 'Symmetric ascent', 'value': f"{mv['symmetric_ascent_frames']} fr",
                 'status': 'good' if mv['symmetric_ascent_frames'] <= 4 else 'bad'},
            ]
        title = f"REP {rep['rep_num']} · POSTERIOR · {_extreme_label(extreme).upper()}"
    else:  # oblique
        overlay = [
            {'label': 'Composite', 'value': f"{rep['composite']:.0f}/100", 'status': 'good'},
            {'label': '(Note)', 'value': 'Oblique — backup view', 'status': 'good'},
        ]
        if extreme == 'dead_hang':
            overlay.insert(1, {'label': 'Dead-hang elbow',
                                'value': f"{mv['dead_hang_elbow_deg']:.0f}°", 'status': 'good'})
        else:
            overlay.insert(1, {'label': 'Chin clearance',
                                'value': f"{mv['chin_clearance_cm']:.1f} cm", 'status': 'good'})
        title = f"REP {rep['rep_num']} · OBLIQUE · {_extreme_label(extreme).upper()}"

    draw_title_strip(frame, f"Pull-Up ({grip} · {style})", rep['rep_num'],
                     total, status=status, score=score)
    draw_phase_label(frame, _extreme_label(extreme))
    draw_metric_overlay(frame, overlay, position='top-right', title=title)
    draw_legend(frame, position='bottom-left')
    return frame_to_base64(frame)


# ─────────────────────────────────────────────────────────────────────
# Per-rep flatten for the UI accordion
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
    }
    for k, v in mv.items():
        if isinstance(v, (int, float)):
            out[k] = round(v, 2)
    for k, v in subs.items():
        if isinstance(v, (int, float)):
            out[f'sub_{k}'] = round(v, 1)
    return out


def _consistency_cv(per_rep):
    keys = ('concentric_sec', 'chin_clearance_cm', 'body_line_sd_deg')
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
    return sum(cvs) / len(cvs) if cvs else 5.0


# ─────────────────────────────────────────────────────────────────────
# Legacy metrics list
# ─────────────────────────────────────────────────────────────────────

def _legacy_status(sub_score):
    if sub_score >= 75:
        return 'GOOD'
    if sub_score >= 60:
        return 'NEEDS IMPROVEMENT'
    return 'RESTRICTED'


def _build_legacy_metrics(per_rep, grip, style, sub_mean):
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
    out.append(m('Dead-hang elbow extension', mv['dead_hang_elbow_deg'],
                 f"{mv['dead_hang_elbow_deg']:.0f}°", '≥170°', 180, 'dead_hang_quality'))
    out.append(m('Eccentric tempo', mv['eccentric_sec'],
                 f"{mv['eccentric_sec']:.2f} s", '2.0–4.0 s', 8, 'eccentric_tempo'))
    out.append(m('Shoulder Y asymmetry (top)', mv['shoulder_y_asym_pct'],
                 f"{mv['shoulder_y_asym_pct']:.1f}%", '<2%', 20, 'shoulder_symmetry'))
    out.append(m('Shoulder-to-ear distance', mv['shoulder_to_ear_cm'],
                 f"{mv['shoulder_to_ear_cm']:.1f} cm", '≥5 cm', 25, 'scapular_depression'))
    out.append(m('Spinal lateral deviation', mv['spinal_lat_deg'],
                 f"{mv['spinal_lat_deg']:.1f}°", '<3°', 25, 'spinal_alignment'))
    out.append(m('Setup motion', mv['setup_motion_px'],
                 f"{mv['setup_motion_px']:.1f} px", 'motionless', 50, 'setup_quality'))
    out.append(m('Lateral body sway', mv['lateral_sway_norm'],
                 f"{mv['lateral_sway_norm']:.2f} femur", '<0.05', 0.5, 'lateral_body_sway'))

    # Technique
    out.append(m('Chin-over-bar clearance', mv['chin_clearance_cm'],
                 f"{mv['chin_clearance_cm']:.1f} cm", '≥3 cm above', 30, 'chin_over_bar'))
    out.append(m('Elbow angle at top', mv['elbow_top_deg'],
                 f"{mv['elbow_top_deg']:.0f}°",
                 '≤50°' if grip == 'supinated' else '≤80°' if grip == 'wide' else '≤60°',
                 180, 'elbow_top'))
    out.append(m('Body line SD (hollow body)', mv['body_line_sd_deg'],
                 f"{mv['body_line_sd_deg']:.1f}°", '<3°', 30, 'body_line'))
    out.append(m('Scapular initiation ratio', mv['scapular_init_ratio'],
                 f"{mv['scapular_init_ratio']:.2f}", '>1.0', 5, 'scapular_initiation'))
    if style in ('strict', 'tactical', 'sternum', 'c2b'):
        out.append(m('Kipping detection (hip-X swing)', mv['hip_x_amp_norm'],
                     f"{mv['hip_x_amp_norm']:.2f} femur", '<0.10', 1.5, 'kipping_detection'))
    out.append(m('Body inclination at top', mv['body_inclination_top_deg'],
                 f"{mv['body_inclination_top_deg']:.1f}°",
                 '45–70°' if style == 'sternum' else '≤10°', 90, 'body_inclination_top'))
    out.append(m('Grip width (× biacromial)', mv['grip_width_ratio'],
                 f"{mv['grip_width_ratio']:.2f}×",
                 '1.10–1.35' if grip == 'pronated' else
                 '0.95–1.15' if grip == 'supinated' else
                 '1.50–2.00' if grip == 'wide' else '1.00–1.20',
                 3, 'grip_width'))
    out.append(m('Elbow flare (frontal)', mv['elbow_flare_deg'],
                 f"{mv['elbow_flare_deg']:.0f}°",
                 '0–15°' if grip == 'supinated' else '15–35°',
                 90, 'elbow_flare'))
    out.append(m('Head/neck deviation (chin-poke)', mv['head_neck_dev_deg'],
                 f"{mv['head_neck_dev_deg']:.1f}°", '<10°', 60, 'head_neck'))
    out.append(m('Hip flexion SD', mv['hip_flex_sd_deg'],
                 f"{mv['hip_flex_sd_deg']:.1f}°", '<5°', 45, 'hip_flexion_consistency'))
    out.append(m('Knee separation', mv['knee_sep_ratio'],
                 f"{mv['knee_sep_ratio']:.2f}× hip", '<1.2×', 4, 'knee_position'))
    out.append(m('Ankle-X swing', mv['ankle_x_amp_norm'],
                 f"{mv['ankle_x_amp_norm']:.2f} leg", '<0.15', 1.5, 'kipping_detection'))
    out.append(m('Bar-path stability', mv['wrist_x_drift_pct'],
                 f"{mv['wrist_x_drift_pct']:.1f}%", '<2%', 25, 'bar_path_stability'))
    out.append(m('Sternum-to-bar', mv['sternum_to_bar_cm'],
                 f"{mv['sternum_to_bar_cm']:.1f} cm", 'C2B variants', 30, 'chin_over_bar'))
    out.append(m('Hand symmetry', mv['hand_sym_pct'],
                 f"{mv['hand_sym_pct']:.1f}%", '<2%', 25, 'grip_width'))

    # Posterior
    out.append(m('Scapular retraction (rear)', mv['scap_retraction_pct'],
                 f"{mv['scap_retraction_pct']:.1f}%", '−10 to −15%', 30, 'scapular_depression'))
    out.append(m('Lat flare', mv['lat_flare_pct'],
                 f"{mv['lat_flare_pct']:.1f}%", '≥15%', 30, 'scapular_depression'))

    # Performance
    out.append(m('Concentric tempo', mv['concentric_sec'],
                 f"{mv['concentric_sec']:.2f} s", '1.0–2.0 s', 8, 'concentric_tempo'))
    out.append(m('Pause at top', mv['pause_top_sec'],
                 f"{mv['pause_top_sec']:.2f} s", '≥0.5 s', 3, 'pause_top'))
    out.append(m('ROM completion (chin clearance)', mv['chin_clearance_cm'],
                 f"{mv['chin_clearance_cm']:.1f} cm", '>0 cm above', 30, 'rom_completion'))
    out.append(m('Symmetric ascent', mv['symmetric_ascent_frames'],
                 f"{mv['symmetric_ascent_frames']} frames", '<2 fr @ 60 fps', 20, 'symmetric_ascent'))
    out.append(m('Sticking-point severity', mv['sticking_pct'],
                 f"{mv['sticking_pct']:.0f}%", '<15%', 100, 'sticking_point'))
    out.append(m('Rep-to-rep consistency', mv.get('concentric_sec', 1.5),
                 f"CV {_consistency_cv(per_rep):.1f}%", '<4%', 50, 'rep_consistency'))

    return out


def _fallback(msg):
    return build_result(
        'NEEDS IMPROVEMENT', 50,
        f'Analysis could not complete: {msg}',
        {'validReps': '0/0', 'confidence': '0%', 'sides': 'n/a',
         'cameraView': 'UNKNOWN'},
        [], [], [msg],
    )
