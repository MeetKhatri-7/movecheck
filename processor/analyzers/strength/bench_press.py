"""STRENGTH — Bench Press (Flat / Incline, Powerlifting / Bodybuilding style).

Full rewrite per the Biomechanical Assessment Spec (bench-press-rewrite.md).

Pipeline
========
  1. Resolve four camera files: sagittal (primary), overhead, head-end,
     oblique (sagittal fallback / cross-check).
  2. Extract MediaPipe pose from each video independently — each can have
     its own fps + rep count from the form (`target_reps_*`).
  3. Calibrate the bench plane: rotate landmark coordinates by −θ_bench
     so that "up off the bench" is the positive Y axis. θ_bench is taken
     from `incline_deg` (form) and validated against the auto-detected
     shoulder-to-hip line at the setup frame.
  4. Detect touch frames (the EXTREME POSITION) per rep per view:
        candidate = local minimum of bench-relative wrist-Y
        gated by:  wrist within ~10 cm of the shoulder line at that frame
        for paused reps:    pick the LAST stationary frame at the minimum
        for touch-and-go:   pick the exact velocity zero-crossing
     This is the moment every metric in §3 / §5 is read at.
  5. Compute all 32 spec metrics per rep — each scored into a 0..100
     sub-score via 5-tier linear interpolation (§7.1).
  6. Aggregate into Safety/Technique/Performance categories using the
     spec's within-category weights (§7.2) and style-aware threshold
     columns (PL vs BB on flat; BB-only on incline per §11.6).
  7. Composite = geometric mean (S_safety^0.40 · S_tech^0.35 · S_perf^0.25,
     §7.3). User preference set in the deadlift session carries over.
  8. Apply 10 hard-fail safety overrides (§7.4); cap composite if any
     trigger.
  9. Set aggregation: mean (headline) / worst / last-3, flag deteriorating
     reps (>15 pts below mean, §7.5).
 10. Annotated frames: 4-camera coverage for BEST and WORST reps;
     sagittal-only for middle reps. Every diagram is anchored on the
     touch frame and overlays every metric measurable from that view.
 11. Emit muscle activation (preserved from existing infra).

Returns the standard ExerciseResult dict augmented with `composite_score`
(see frontend/src/data/types.ts) carrying the spec UI payload.
"""
from __future__ import annotations

import math
from statistics import mean as _mean

from utils.landmarks import (
    extract_all_landmarks, get_landmark_px, midpoint_px, LM,
    confidence_score,
)
from utils.angles import angle_3pt
from utils.rep_detection import detect_reps_minima
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
from utils.muscle_inference import infer_bench_press

BENCH_CONNECTIONS = [
    (11, 12), (11, 23), (12, 24), (23, 24),
    (11, 13), (13, 15), (12, 14), (14, 16),
    (23, 25), (25, 27), (24, 26), (26, 28),
    (0, 11), (0, 12),  # head/nose to shoulders
]


# ─────────────────────────────────────────────────────────────────────
# 5-tier scoring helpers (spec §7.1).  Identical algorithm to deadlift —
# kept duplicated here so the analyzer is self-contained.
# ─────────────────────────────────────────────────────────────────────

def _interp(x, lo, hi, lo_score, hi_score):
    if hi == lo:
        return lo_score
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return lo_score + t * (hi_score - lo_score)


def score_one_sided(x, very_good, good, yellow, bad, higher_is_better):
    """5-tier scorer from four thresholds.  Past the Bad edge the score
    decays into the Very Bad band (0..39) over one additional band-width."""
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
    """Symmetric tent scoring.  `tolerances` = (vg, good, yellow, bad)
    half-widths around the ideal point."""
    if x is None:
        return 0.0
    return score_one_sided(abs(x - ideal), *tolerances, higher_is_better=False)


def score_ranged(x, very_good_lo, very_good_hi, good_lo, good_hi,
                 yellow_lo, yellow_hi, bad_lo, bad_hi):
    """Asymmetric ranged scoring — used where the Very Good band is
    flat across [lo, hi] and the lower and upper bad-sides differ in
    width (e.g. touch point: 70..95% on flat-PL).  Outside the Bad band
    decays into Very Bad."""
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
    # Very bad — decay over one extra band-width
    if x < bad_lo:
        return max(0.0, _interp(x, bad_lo - (yellow_lo - bad_lo), bad_lo, 0.0, 40.0))
    return max(0.0, _interp(x, bad_hi, bad_hi + (bad_hi - yellow_hi), 40.0, 0.0))


# ─────────────────────────────────────────────────────────────────────
# Spec §7.2 — category weights (sum to 100 within each category).
# Bench-press uses 40 / 35 / 25 split (vs deadlift's 50 / 35 / 15).
# ─────────────────────────────────────────────────────────────────────

SAFETY_W = {
    'shoulder_abduction': 20,       # §3.7 + §4.4 + §5.3 — elbow flare
    'touch_point_safety': 15,       # §3.2 — bar toward neck = highest risk
    'scapular_retraction': 13,      # §3.13 — foundation
    'bouncing': 12,                 # §3.10 — sternum bounce
    'wrist_position': 10,           # §3.8 — hyperextension
    'press_symmetry': 10,           # §4.3 — L/R divergence
    'bar_tilt': 8,                  # §4.2 + §5.1
    'head_position': 6,             # §3.14 — IPF rule
    'glute_contact': 6,             # §3.15 — IPF rule
}

TECH_W = {
    'bar_path_jcurve': 15,          # §3.1
    'touch_point': 12,              # §3.2
    'forearm_vertical': 12,         # §3.3
    'elbow_bottom': 8,              # §3.4
    'grip_width': 8,                # §4.1
    'arch_height': 8,               # §3.12 (style-aware)
    'bar_path_symmetry': 8,         # §4.3
    'consistency': 8,               # §6.8
    'bar_wobble': 6,                # §3.11
    'wrist_alignment_frontal': 6,   # §4.5
    'hand_spacing_symmetry': 4,     # §4.6
    'heel_contact': 5,              # §3.16
}

PERF_W = {
    'mcv': 22,                      # §6.4
    'sticking_point': 16,           # §6.6
    'lockout_completion': 14,       # §3.17
    'pause_or_tng': 14,             # §3.9 or §3.10
    'rom_completion': 12,           # bar must touch chest + reach lockout
    'eccentric_tempo': 10,          # §6.2
    'setup_time': 6,                # §6.1
    'lockout_hold': 6,              # §6.5
}

# Global category weights — spec §7.2.
CATEGORY_WEIGHTS = {'safety': 0.40, 'technique': 0.35, 'performance': 0.25}


# ─────────────────────────────────────────────────────────────────────
# Spec §7.4 — hard-fail safety overrides.  10 conditions; lowest cap wins.
# ─────────────────────────────────────────────────────────────────────

def _override_specs():
    return [
        {
            'key': 'extreme_flare',
            'condition': 'Shoulder abduction > 90° (extreme flare; rotator-cuff / pec-tear risk)',
            'metric': 'Shoulder abduction at touch',
            'cap': 45,
            'eval': lambda mv: (mv['shoulder_abduction_deg'] > 90,
                                f"{mv['shoulder_abduction_deg']:.1f}°"),
        },
        {
            'key': 'bar_to_neck',
            'condition': 'Bar drifts toward neck (above clavicle on flat / into throat on incline)',
            'metric': 'Touch point on chest',
            'cap': 35,
            'eval': lambda mv: (mv['touch_point_pct'] < -5,
                                f"{mv['touch_point_pct']:.1f}% (above clavicle line)"),
        },
        {
            'key': 'sternum_bounce',
            'condition': 'Sternum bounce (|a| > 35 m/s² at touch with no pause)',
            'metric': 'Bounce detector',
            'cap': 45,
            'eval': lambda mv: (mv['bounce_a_mps2'] > 35
                                and mv['pause_sec'] < 0.1,
                                f"|a|={mv['bounce_a_mps2']:.1f} m/s²"),
        },
        {
            'key': 'lost_retraction',
            'condition': 'Loss of scapular retraction (shoulder-Y drift > 7 cm)',
            'metric': 'Scapular retraction maintenance',
            'cap': 50,
            'eval': lambda mv: (mv['scapular_drift_cm'] > 7,
                                f"{mv['scapular_drift_cm']:.1f} cm"),
        },
        {
            'key': 'wrist_hyperext',
            'condition': 'Wrist hyperextension > 45° under load',
            'metric': 'Wrist position',
            'cap': 50,
            'eval': lambda mv: (mv['wrist_extension_deg'] > 45,
                                f"{mv['wrist_extension_deg']:.1f}°"),
        },
        {
            'key': 'head_lift',
            'condition': 'Head lifts > 7 cm off bench (cervical strain risk)',
            'metric': 'Head position',
            'cap': 55,
            'eval': lambda mv: (mv['head_lift_cm'] > 7,
                                f"{mv['head_lift_cm']:.1f} cm"),
        },
        {
            'key': 'glute_lift',
            'condition': 'Glutes lift > 7 cm off bench (red-light in IPF competition)',
            'metric': 'Glute contact',
            'cap': 55,
            'eval': lambda mv: (mv['glute_lift_cm'] > 7,
                                f"{mv['glute_lift_cm']:.1f} cm"),
        },
        {
            'key': 'press_asymmetry',
            'condition': 'Press asymmetry > 20° (one side significantly higher)',
            'metric': 'Press symmetry L/R',
            'cap': 40,
            'eval': lambda mv: (mv['press_asym_deg'] > 20,
                                f"{mv['press_asym_deg']:.1f}°"),
        },
        {
            'key': 'severe_bar_tilt',
            'condition': 'Bar tilt > 15° at any frame',
            'metric': 'Bar tilt',
            'cap': 50,
            'eval': lambda mv: (mv['bar_tilt_deg'] > 15,
                                f"{mv['bar_tilt_deg']:.1f}°"),
        },
        {
            'key': 'uncontrolled_drop',
            'condition': 'Bar dropped uncontrolled (eccentric < 0.4 s, no deceleration)',
            'metric': 'Eccentric tempo',
            'cap': 30,
            'eval': lambda mv: (mv['eccentric_sec'] < 0.4
                                and mv['bounce_a_mps2'] > 25,
                                f"{mv['eccentric_sec']:.2f} s, |a|={mv['bounce_a_mps2']:.1f}"),
        },
    ]


# ─────────────────────────────────────────────────────────────────────
# Spec §8 — grade mapping.
# ─────────────────────────────────────────────────────────────────────

def grade_from_composite(c):
    if c >= 90:
        return 'A', 'Very Good'
    if c >= 75:
        return 'B', 'Good'
    if c >= 60:
        return 'C', 'Yellow Flag'
    if c >= 40:
        return 'D', 'Bad'
    return 'E', 'Very Bad'


def status_from_grade(letter):
    return {'A': 'GOOD', 'B': 'GOOD', 'C': 'NEEDS IMPROVEMENT',
            'D': 'NEEDS IMPROVEMENT', 'E': 'RESTRICTED'}[letter]


# ─────────────────────────────────────────────────────────────────────
# Per-view feature extraction
#
# For bench press the lifter is supine, so MediaPipe is less reliable
# than upright sports.  We:
#   • prefer the "near-side" landmarks (higher mean visibility)
#   • rotate every (x, y) into bench-relative coordinates before computing
#     velocities, so "up off the bench" is always the positive Y axis,
#     regardless of bench incline.
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
        'heel':     LM['LEFT_HEEL']     if side == 'left' else LM['RIGHT_HEEL'],
        'index':    LM['LEFT_INDEX']    if side == 'left' else LM['RIGHT_INDEX'],
    }


def _pick_near_side(frames):
    """Choose the body side with higher mean visibility."""
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


def _bench_angle_from_setup(sag, frame_idx):
    """Auto-detect θ_bench from the shoulder-to-hip line at a setup frame.
    Returns degrees, in image coordinates. Flat bench ≈ 0°; incline 25–50°."""
    frames = sag['frames']
    w, h = sag['w'], sag['h']
    if not (0 <= frame_idx < len(frames)):
        return 0.0
    lm = frames[frame_idx]['landmarks']
    if lm is None:
        return 0.0
    sh = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
    hp = midpoint_px(lm, LM['LEFT_HIP'], LM['RIGHT_HIP'], w, h)
    if not (sh and hp):
        return 0.0
    # Vector hip→shoulder. For a flat bench this is roughly horizontal in
    # the image (~0°). For incline it tilts upward.
    dx = sh[0] - hp[0]
    dy = hp[1] - sh[1]   # image y goes down → flip
    # Bench angle = angle of this vector from horizontal
    return math.degrees(math.atan2(dy, abs(dx) + 1e-6))


def _rotate(point, theta_rad, origin):
    """Rotate `point` (x,y) by `theta_rad` around `origin`."""
    x, y = point[0] - origin[0], point[1] - origin[1]
    c, s = math.cos(theta_rad), math.sin(theta_rad)
    return (c * x - s * y + origin[0], s * x + c * y + origin[1])


def _process_view(path, view_name, plate_size_kg=None, theta_bench_deg=0.0):
    """Extract pose + per-frame signals from one camera video.

    Returns a dict carrying:
      • frames, fps, w, h, side
      • bench-relative wrist-y / shoulder-y / hip-y / nose-y / heel-y signals
      • bench-relative wrist-x trajectory (for J-curve)
      • elbow / shoulder-flexion / wrist-angle / forearm-vertical signals
      • bar_x_blend, bar_y_blend  (plate-centroid + wrist-centre blend)
      • theta_bench_rad (the rotation applied)
    """
    data = extract_all_landmarks(path)
    frames = data['frames']
    fps = data['fps']
    w, h = data['width'], data['height']

    side = _pick_near_side(frames)
    idx = _side_idx(side)

    # Bench-angle: form input + auto-detect average across first few frames
    sample_frame = next((i for i, f in enumerate(frames) if f['landmarks']), 0)
    auto_bench = 0.0
    if view_name == 'sagittal':
        # Image-coord angle from shoulder-to-hip; positive = tilted up
        lm = frames[sample_frame]['landmarks'] if sample_frame < len(frames) else None
        if lm:
            sh = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
            hp = midpoint_px(lm, LM['LEFT_HIP'], LM['RIGHT_HIP'], w, h)
            if sh and hp:
                # Image-frame: head is to the left or right; we measure tilt.
                # Use absolute value because the bench can face either way.
                auto_bench = abs(math.degrees(math.atan2(hp[1] - sh[1], sh[0] - hp[0])))
                # Normalise: a flat-horizontal lifter looks like 0° from shoulder→hip
                # direction; we want the angle from horizontal.
                auto_bench = min(auto_bench, 180.0 - auto_bench)
    # Prefer the form value when it's >= 10° (incline) or 0 (flat)
    if abs(theta_bench_deg) >= 5:
        theta_used = theta_bench_deg
    else:
        theta_used = auto_bench if auto_bench >= 15 else 0.0
    theta_rad = math.radians(theta_used)

    # Bar tracking on the sagittal view only (plate centroid)
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

    # Per-frame signals (raw image coords)
    wrist_x, wrist_y = [], []
    elbow_x, elbow_y = [], []
    shoulder_x, shoulder_y = [], []
    hip_x, hip_y = [], []
    nose_y = []
    heel_y = []
    index_x, index_y = [], []
    lwr_x, lwr_y, rwr_x, rwr_y = [], [], [], []
    lsh_x, lsh_y, rsh_x, rsh_y = [], [], [], []
    elbow_angle = []        # shoulder-elbow-wrist
    forearm_v_deg = []      # forearm angle from gravity vertical
    wrist_flex_deg = []     # elbow-wrist-index angle from straight
    shoulder_flex_deg = []  # torso-shoulder-elbow angle
    shoulder_abd_deg = []   # frontal-plane humerus-vs-torso (head-end view best)
    plate_x = [c[0] if c else None for c in centres]
    plate_y = [c[1] if c else None for c in centres]

    for f in frames:
        lm = f['landmarks']
        if lm is None:
            for arr in (wrist_x, wrist_y, elbow_x, elbow_y, shoulder_x, shoulder_y,
                        hip_x, hip_y, nose_y, heel_y, index_x, index_y,
                        lwr_x, lwr_y, rwr_x, rwr_y, lsh_x, lsh_y, rsh_x, rsh_y,
                        elbow_angle, forearm_v_deg, wrist_flex_deg,
                        shoulder_flex_deg, shoulder_abd_deg):
                arr.append(None)
            continue
        wr = get_landmark_px(lm, idx['wrist'], w, h)
        el = get_landmark_px(lm, idx['elbow'], w, h)
        sh = get_landmark_px(lm, idx['shoulder'], w, h)
        hp = get_landmark_px(lm, idx['hip'], w, h)
        no = get_landmark_px(lm, LM['NOSE'], w, h)
        hl = get_landmark_px(lm, idx['heel'], w, h)
        ix = get_landmark_px(lm, idx['index'], w, h)
        lw = get_landmark_px(lm, LM['LEFT_WRIST'], w, h)
        rw = get_landmark_px(lm, LM['RIGHT_WRIST'], w, h)
        ls = get_landmark_px(lm, LM['LEFT_SHOULDER'], w, h)
        rs = get_landmark_px(lm, LM['RIGHT_SHOULDER'], w, h)

        wrist_x.append(wr[0] if wr else None)
        wrist_y.append(wr[1] if wr else None)
        elbow_x.append(el[0] if el else None)
        elbow_y.append(el[1] if el else None)
        shoulder_x.append(sh[0] if sh else None)
        shoulder_y.append(sh[1] if sh else None)
        hip_x.append(hp[0] if hp else None)
        hip_y.append(hp[1] if hp else None)
        nose_y.append(no[1] if no else None)
        heel_y.append(hl[1] if hl else None)
        index_x.append(ix[0] if ix else None)
        index_y.append(ix[1] if ix else None)
        lwr_x.append(lw[0] if lw else None); lwr_y.append(lw[1] if lw else None)
        rwr_x.append(rw[0] if rw else None); rwr_y.append(rw[1] if rw else None)
        lsh_x.append(ls[0] if ls else None); lsh_y.append(ls[1] if ls else None)
        rsh_x.append(rs[0] if rs else None); rsh_y.append(rs[1] if rs else None)

        # Elbow angle
        elbow_angle.append(angle_3pt(sh, el, wr) if (sh and el and wr) else None)
        # Forearm from gravity-vertical (image-down = +y)
        if el and wr:
            dx, dy = wr[0] - el[0], wr[1] - el[1]
            # vertical reference is (0, +1)
            forearm_v_deg.append(abs(math.degrees(math.atan2(dx, abs(dy) + 1e-6))))
        else:
            forearm_v_deg.append(None)
        # Wrist flexion (elbow-wrist-index angle; 180 = straight)
        if el and wr and ix:
            wrist_flex_deg.append(180.0 - angle_3pt(el, wr, ix))
        else:
            wrist_flex_deg.append(None)
        # Shoulder flexion (torso vector vs humerus)
        shoulder_flex_deg.append(angle_3pt(hp, sh, el) if (hp and sh and el) else None)
        # Shoulder abduction (frontal-plane angle of humerus from torso) —
        # for sagittal this is approximate; head-end / posterior is cleaner.
        # Use the angle between (shoulder→elbow) and (hip→shoulder) projected.
        if hp and sh and el:
            tx, ty = sh[0] - hp[0], sh[1] - hp[1]
            ex, ey = el[0] - sh[0], el[1] - sh[1]
            # Cross product gives signed angle; we take the absolute.
            ang = math.degrees(math.atan2(abs(tx * ey - ty * ex),
                                          (tx * ex + ty * ey)))
            shoulder_abd_deg.append(ang)
        else:
            shoulder_abd_deg.append(None)

    # Bench-relative wrist-Y (after rotation): "up off bench" = larger value.
    # We rotate around the hip centre (stable origin) by −θ_bench.
    bench_wrist_y = []
    bench_wrist_x = []
    bench_shoulder_y = []
    bench_shoulder_x = []
    bench_hip_y = []
    bench_hip_x = []
    for i, f in enumerate(frames):
        lm = f['landmarks']
        if lm is None or wrist_x[i] is None:
            bench_wrist_y.append(None)
            bench_wrist_x.append(None)
            bench_shoulder_y.append(None)
            bench_shoulder_x.append(None)
            bench_hip_y.append(None)
            bench_hip_x.append(None)
            continue
        hp_pt = (hip_x[i], hip_y[i]) if hip_x[i] is not None else (w / 2, h / 2)
        # Image y → "up off bench" means decreasing image y → flip sign.
        wr_b = _rotate((wrist_x[i], wrist_y[i]), -theta_rad, hp_pt)
        sh_b = _rotate((shoulder_x[i], shoulder_y[i]), -theta_rad, hp_pt) \
                if shoulder_x[i] is not None else (None, None)
        bench_wrist_x.append(wr_b[0])
        bench_wrist_y.append(-wr_b[1])  # flip so up = positive
        bench_shoulder_y.append(-sh_b[1] if sh_b[1] is not None else None)
        bench_shoulder_x.append(sh_b[0])
        bench_hip_y.append(-hp_pt[1])
        bench_hip_x.append(hp_pt[0])

    # Bar X/Y blend: plate centroid + wrist-centre (50/50 baseline weight)
    bar_x_blend, bar_y_blend = [], []
    for i in range(len(frames)):
        wx = wrist_x[i]
        wy = wrist_y[i]
        px = plate_x[i] if i < len(plate_x) else None
        py = plate_y[i] if i < len(plate_y) else None
        bq = bar_quality[i] if i < len(bar_quality) else 0.0
        if px is not None and wx is not None:
            bx = (px * bq + wx * 0.4) / (bq + 0.4) if (bq + 0.4) > 0 else wx
            by = (py * bq + wy * 0.4) / (bq + 0.4) if (bq + 0.4) > 0 else wy
        elif px is not None:
            bx, by = px, py
        elif wx is not None:
            bx, by = wx, wy
        else:
            bx, by = None, None
        bar_x_blend.append(bx)
        bar_y_blend.append(by)

    return {
        'name': view_name,
        'frames': frames, 'fps': fps, 'w': w, 'h': h, 'side': side, 'idx': idx,
        'theta_bench_rad': theta_rad, 'theta_bench_deg': math.degrees(theta_rad),
        'centres': centres, 'bar_quality': bar_quality, 'bar_med_q': bar_med_q,
        'px_per_cm': px_per_cm,
        'plate_x': plate_x, 'plate_y': plate_y,
        'bar_x': bar_x_blend, 'bar_y': bar_y_blend,
        'wrist_x': wrist_x, 'wrist_y': wrist_y,
        'elbow_x': elbow_x, 'elbow_y': elbow_y,
        'shoulder_x': shoulder_x, 'shoulder_y': shoulder_y,
        'hip_x': hip_x, 'hip_y': hip_y,
        'nose_y': nose_y, 'heel_y': heel_y,
        'index_x': index_x, 'index_y': index_y,
        'lwr_x': lwr_x, 'lwr_y': lwr_y, 'rwr_x': rwr_x, 'rwr_y': rwr_y,
        'lsh_x': lsh_x, 'lsh_y': lsh_y, 'rsh_x': rsh_x, 'rsh_y': rsh_y,
        'bench_wrist_y': bench_wrist_y, 'bench_wrist_x': bench_wrist_x,
        'bench_shoulder_y': bench_shoulder_y, 'bench_hip_y': bench_hip_y,
        'bench_shoulder_x': bench_shoulder_x, 'bench_hip_x': bench_hip_x,
        'elbow_angle': elbow_angle,
        'forearm_v_deg': forearm_v_deg,
        'wrist_flex_deg': wrist_flex_deg,
        'shoulder_flex_deg': shoulder_flex_deg,
        'shoulder_abd_deg': shoulder_abd_deg,
    }


# ─────────────────────────────────────────────────────────────────────
# Rep detection — touch frame is the EXTREME position.
# Spec §12.3.3: touch = bench-relative wrist-Y MINIMUM gated by chest
# proximity (wrist within ~10 cm of shoulder line).
# ─────────────────────────────────────────────────────────────────────

def _detect_touch_frames(view, target_reps, paused=True):
    """Return list of dicts per rep: {start, touch, lockout, end, idx}.

    Algorithm:
      1. Find local minima of bench-relative wrist-Y (the lowest bar
         position per rep).  detect_reps_minima handles plateau holds.
      2. For each detected minimum, refine to the LAST stationary frame
         at that minimum (paused) or the velocity zero-crossing (TnG).
      3. Validate chest proximity: bench-relative |wrist_y - shoulder_y|
         must be small (within ~10 cm in pixels, scaled by torso length).
    """
    fps = view['fps']
    bwy = view['bench_wrist_y']
    bsy = view['bench_shoulder_y']
    bhy = view['bench_hip_y']
    target = max(1, int(target_reps or 3))

    # Build filled signal (NaN replaced with neighbours) for minima search
    filled = []
    last = None
    for v in bwy:
        if v is None:
            filled.append(last if last is not None else 0.0)
        else:
            filled.append(v); last = v
    if not filled or all(v == 0 for v in filled):
        return []

    # detect_reps_minima expects "lower = peak" signal
    candidates = detect_reps_minima(filled, expected_reps=target,
                                     fps=fps, min_hold_sec=0.2)

    # Strict top-N by minimum depth (lowest bench-relative position = touch)
    if target and len(candidates) > target:
        candidates = sorted(candidates,
                            key=lambda r: filled[r['peak_frame']]
                                          if r['peak_frame'] < len(filled) else 1e9
                            )[:target]
        candidates = sorted(candidates, key=lambda r: r['peak_frame'])

    # Compute torso length proxy for the chest-proximity gate (in pixels).
    torso_lens = []
    for s, h in zip(bsy, bhy):
        if s is not None and h is not None:
            torso_lens.append(abs(s - h))
    torso_px = _mean(torso_lens) if torso_lens else 100.0
    chest_gate_px = max(20.0, torso_px * 0.25)   # ~25% of torso length

    out = []
    for ri, c in enumerate(candidates):
        start = c['start_frame']
        end = c['end_frame']
        peak = c['peak_frame']

        # Refine touch frame
        touch = _refine_touch_frame(filled, start, end, peak, paused, fps)

        # Chest-proximity gate
        if (touch < len(bwy) and touch < len(bsy)
                and bwy[touch] is not None and bsy[touch] is not None):
            gap_px = abs(bwy[touch] - bsy[touch])
            chest_ok = gap_px <= chest_gate_px * 3.0  # generous gate
        else:
            chest_ok = True   # don't reject when landmarks missing

        # Lockout = local maximum AFTER touch within rep window
        lockout = touch
        best_y = filled[touch] if touch < len(filled) else -1e9
        for fi in range(touch, min(end + 1, len(filled))):
            if filled[fi] > best_y:
                best_y = filled[fi]; lockout = fi

        out.append({
            'idx': ri + 1,
            'start': start, 'touch': touch, 'lockout': lockout, 'end': end,
            'chest_ok': chest_ok,
        })
    return out


def _refine_touch_frame(filled, start, end, peak, paused, fps):
    """Refine the touch frame:
       • paused: pick the LAST frame within ε of the minimum before
         velocity becomes positive (i.e. concentric begins).
       • touch-and-go: pick the velocity zero-crossing (negative→positive).
    """
    end = min(end, len(filled) - 1)
    start = max(0, start)
    if peak >= len(filled):
        peak = end
    floor_val = filled[peak]
    eps = max(3.0, abs(floor_val) * 0.02)   # 2% of magnitude or 3 px

    if paused:
        # Walk forward from peak — stay at/near minimum while velocity ≈ 0
        last_in_basin = peak
        for fi in range(peak, end + 1):
            if abs(filled[fi] - floor_val) <= eps:
                last_in_basin = fi
            else:
                break
        return last_in_basin
    else:
        # Touch-and-go: velocity zero-crossing
        if fps <= 0:
            return peak
        # Smooth derivative across ±2 frames
        def _vel(i):
            a = max(0, i - 1); b = min(len(filled) - 1, i + 1)
            return (filled[b] - filled[a]) / max(1e-6, (b - a) / fps)
        # Scan from start to end; find first negative→positive crossing
        prev_v = None
        for fi in range(start, end + 1):
            v = _vel(fi)
            if prev_v is not None and prev_v <= 0 and v > 0:
                return fi
            prev_v = v
        return peak


# ─────────────────────────────────────────────────────────────────────
# Per-rep metric computation (the heart of the spec — 32 metrics)
# ─────────────────────────────────────────────────────────────────────

def _compute_rep_metrics(rep, sag, over, head, obl, variant, style, paused,
                         px_per_cm_global):
    """Compute every spec metric for ONE rep at the touch frame.
    Sagittal view is the primary reference; other views fill in their
    specific metrics.  Returns a dict of raw values keyed by spec slug.
    """
    start, touch, lockout, end = rep['start'], rep['touch'], rep['lockout'], rep['end']
    fps = sag['fps']
    mv = {}

    # ── §3.1 Bar path J-curve horizontal displacement (cm or % torso) ──
    bxs = sag['bench_wrist_x']
    if bxs[touch] is not None:
        # Maximum head-ward (positive x) excursion from touch to lockout
        head_drift = 0.0
        for fi in range(touch, min(lockout + 1, len(bxs))):
            v = bxs[fi]
            if v is not None:
                head_drift = max(head_drift, v - bxs[touch])
        # Maximum forward (toward feet) excursion = bad direction
        forward_drift = 0.0
        for fi in range(touch, min(lockout + 1, len(bxs))):
            v = bxs[fi]
            if v is not None:
                forward_drift = max(forward_drift, bxs[touch] - v)
        # Convert to cm if calibrated
        if px_per_cm_global > 0:
            mv['jcurve_cm'] = head_drift / px_per_cm_global
            mv['forward_drift_cm'] = forward_drift / px_per_cm_global
        else:
            # Use % of torso length as fallback
            torso_lens = [abs(s - h) for s, h in zip(sag['bench_shoulder_y'],
                                                       sag['bench_hip_y'])
                          if s is not None and h is not None]
            tlen = _mean(torso_lens) if torso_lens else 100.0
            mv['jcurve_cm'] = (head_drift / max(1e-6, tlen)) * 50.0  # rough cm
            mv['forward_drift_cm'] = (forward_drift / max(1e-6, tlen)) * 50.0
    else:
        mv['jcurve_cm'] = 8.0
        mv['forward_drift_cm'] = 0.0

    # ── §3.2 Touch point on chest (% torso, suprasternal=0% xiphoid=100%) ──
    # Use bench-relative coordinates: at touch, wrist sits between the
    # shoulder line and the hip line.  0% = at shoulder line.
    bwy = sag['bench_wrist_y']
    # Touch point = where ALONG the torso (shoulder→hip axis of the bench
    # plane) the bar meets the chest: 0% at the shoulder/clavicle line,
    # 100% at the hip, negative = above the clavicle toward the neck.
    # The previous formula divided by the HEIGHT-OFF-BENCH difference
    # between hip and shoulder — near zero for anyone lying flat — which
    # exploded to 894% on a clean touch.
    bswx = sag['bench_wrist_x']
    bsx = sag['bench_shoulder_x']
    bhx = sag['bench_hip_x']
    if (touch < len(bswx) and bswx[touch] is not None
            and bsx[touch] is not None and bhx[touch] is not None):
        denom = bhx[touch] - bsx[touch]
        if abs(denom) > 1e-3:
            mv['touch_point_pct'] = (bswx[touch] - bsx[touch]) / denom * 100.0
        else:
            mv['touch_point_pct'] = 75.0
    else:
        mv['touch_point_pct'] = 75.0

    # ── §3.3 Forearm vertical at touch (deg from vertical) ──
    mv['forearm_vertical_deg'] = _safe_at(sag['forearm_v_deg'], touch, 5.0)

    # ── §3.4 Elbow angle at bottom (touch) ──
    mv['elbow_touch_deg'] = _safe_at(sag['elbow_angle'], touch, 75.0)

    # ── §3.5 Elbow angle at lockout ──
    mv['elbow_lockout_deg'] = _safe_at(sag['elbow_angle'], lockout, 175.0)

    # ── §3.6 Shoulder flexion at bottom ──
    mv['shoulder_flex_deg'] = _safe_at(sag['shoulder_flex_deg'], touch, 75.0)

    # ── §3.7 Shoulder abduction / elbow flare ──
    # Prefer head-end view, fallback to sagittal proxy.
    abd = None
    if head:
        v = _safe_at(head['shoulder_abd_deg'], _nearest_frame(head, touch, sag), None)
        if v is not None:
            abd = v
    if abd is None:
        abd = _safe_at(sag['shoulder_abd_deg'], touch, 60.0)
    mv['shoulder_abduction_deg'] = abd

    # ── §3.8 Wrist position (extension deg) ──
    mv['wrist_extension_deg'] = abs(_safe_at(sag['wrist_flex_deg'], touch, 12.0))

    # ── §3.9 Pause quality (duration of motionless at minimum) ──
    pause_sec, pause_max_vel = _compute_pause(sag['bench_wrist_y'], touch, fps)
    mv['pause_sec'] = pause_sec
    mv['pause_max_vel_mps'] = pause_max_vel

    # ── §3.10 Touch-and-go quality (peak |a| at touch) ──
    mv['bounce_a_mps2'] = _compute_touch_accel(sag['bench_wrist_y'], touch, fps,
                                                px_per_cm_global)

    # ── §3.11 Bar wobble (RMS lateral deviation from poly-fit path) ──
    mv['bar_wobble_cm'] = _compute_bar_wobble(sag, start, end, px_per_cm_global)

    # ── §3.12 Arch height (% torso, style-aware) ──
    # Proxy: perpendicular displacement of shoulder centre from the
    # bench-line proxy through setup-frame SC and HC.
    arch_pct = _compute_arch_height_pct(sag, start, touch)
    mv['arch_pct'] = arch_pct

    # ── §3.13 Scapular retraction maintenance (shoulder-Y drift, cm) ──
    drift_cm = _compute_scapular_drift(sag, start, end, px_per_cm_global)
    mv['scapular_drift_cm'] = drift_cm

    # ── §3.14 Head position (max nose-Y lift from baseline, cm) ──
    mv['head_lift_cm'] = _compute_head_lift(sag, start, end, px_per_cm_global)

    # ── §3.15 Glute contact (max hip-Y rise, cm) ──
    mv['glute_lift_cm'] = _compute_glute_lift(sag, start, end, px_per_cm_global)

    # ── §3.16 Heel contact (max heel-Y change, cm) ──
    mv['heel_lift_cm'] = _compute_heel_lift(sag, start, end, px_per_cm_global)

    # ── §3.17 Lockout completion (elbow at top + hold duration) ──
    mv['lockout_elbow_deg'] = _safe_at(sag['elbow_angle'], lockout, 175.0)
    hold_sec = _compute_lockout_hold(sag['bench_wrist_y'], lockout, fps)
    mv['lockout_hold_sec'] = hold_sec

    # ── §4.1 Grip width (% biacromial, prefers overhead view) ──
    grip_pct = _compute_grip_width(over or head or sag, touch, sag)
    mv['grip_pct_biacromial'] = grip_pct

    # ── §4.2 Bar tilt (worst frame, prefers overhead/head-end) ──
    tilt = _compute_bar_tilt(over, head, sag, start, end)
    mv['bar_tilt_deg'] = tilt

    # ── §4.3 Bar path symmetry L/R (overhead view) ──
    sym = _compute_bar_path_symmetry(over or sag, start, end)
    mv['bar_path_sym_pct'] = sym

    # ── §4.5 Wrist alignment (frontal-plane ulnar/radial deviation) ──
    # Approximate from overhead view if available.
    mv['wrist_align_deg'] = _safe_at((over or head or sag)['forearm_v_deg'],
                                     _nearest_frame((over or head or sag), touch, sag),
                                     7.0)

    # ── §4.6 Hand spacing symmetry (overhead view) ──
    mv['hand_spacing_asym_cm'] = _compute_hand_spacing_asym(
        over or head or sag, touch, px_per_cm_global)

    # ── §4.7 Bar drift in frontal plane (lateral excursion from midline) ──
    mv['bar_frontal_drift_cm'] = _compute_frontal_drift(over or head, sag, start, end,
                                                        px_per_cm_global)

    # ── §5.2 Shoulder symmetry (Y-difference at touch, head-end view) ──
    mv['shoulder_y_asym_pct'] = _compute_shoulder_y_asym(head or sag, touch)

    # ── §5.4 Bar centre vs torso midline (head-end view) ──
    mv['bar_centering_cm'] = mv['bar_frontal_drift_cm']  # same metric, different view

    # ── §4.3 Press symmetry (L/R wrist Y timing at lockout) ──
    mv['press_asym_deg'] = _compute_press_asymmetry(over or head or sag, touch, lockout)

    # ── §6 Tempo metrics ──
    mv['eccentric_sec'] = max(0.01, (touch - start) / fps) if fps > 0 else 2.0
    mv['concentric_sec'] = max(0.01, (lockout - touch) / fps) if fps > 0 else 1.5
    mv['setup_sec'] = max(0.0, (start) / fps) if fps > 0 else 3.0
    # MCV (bar speed) — concentric, in m/s if calibrated
    if px_per_cm_global > 0 and lockout > touch:
        mv['mcv_mps'] = mean_concentric_velocity(sag['centres'], touch, lockout,
                                                   fps, px_per_cm_global)
    else:
        # Fallback: pixel-velocity scaled by an assumed bar length
        d = abs((sag['bench_wrist_y'][lockout] or 0)
                 - (sag['bench_wrist_y'][touch] or 0))
        mv['mcv_mps'] = (d / max(1, lockout - touch) * fps) / 1000.0

    # ── §6.6 Sticking-point duration & position ──
    s_dur, s_pos = _compute_sticking_point(sag['bench_wrist_y'], touch, lockout, fps)
    mv['sticking_duration_sec'] = s_dur
    mv['sticking_position_pct'] = s_pos

    # ── ROM completion: bar must reach chest at touch AND elbow extend at lockout ──
    rom_ok = rep['chest_ok'] and mv['lockout_elbow_deg'] >= 165
    mv['rom_ok'] = 1.0 if rom_ok else 0.0

    # ── Pause vs touch-and-go quality (single performance slot) ──
    if paused:
        mv['pause_or_tng_quality'] = mv['pause_sec']
    else:
        # TnG: lower bounce_a = better. Invert into a 0..2 quality scalar.
        mv['pause_or_tng_quality'] = max(0.0, 2.0 - mv['bounce_a_mps2'] / 15.0)

    return mv


# ─────────────────────────────────────────────────────────────────────
# Sub-scoring (style-aware threshold tables)
# ─────────────────────────────────────────────────────────────────────

def _score_all(mv, variant, style, paused):
    """Map raw metric values → per-metric sub-scores (0..100).

    Variant + style choose the threshold column per spec §2 / §3.
    """
    s = {}
    is_incline = (variant == 'incline')
    is_pl = (style == 'powerlifting') and not is_incline   # incline → BB-only

    # — Safety —
    # Shoulder abduction / elbow flare
    if is_incline:
        s['shoulder_abduction'] = score_two_sided(mv['shoulder_abduction_deg'], 40.0, (10, 15, 25, 40))
    elif is_pl:
        s['shoulder_abduction'] = score_two_sided(mv['shoulder_abduction_deg'], 45.0, (10, 15, 25, 40))
    else:
        s['shoulder_abduction'] = score_two_sided(mv['shoulder_abduction_deg'], 55.0, (10, 15, 25, 40))
    # Touch-point safety (negative = toward neck = bad; >115% = belly)
    if mv['touch_point_pct'] < 0:
        s['touch_point_safety'] = max(0.0, 30.0 + mv['touch_point_pct'] * 3)
    elif mv['touch_point_pct'] > 115:
        s['touch_point_safety'] = max(0.0, 100.0 - (mv['touch_point_pct'] - 115) * 4)
    else:
        s['touch_point_safety'] = 100.0
    # Scapular retraction
    s['scapular_retraction'] = score_one_sided(mv['scapular_drift_cm'], 1, 2, 4, 7, higher_is_better=False)
    # Bouncing — only penalised when paused and bounce_a is high
    if paused:
        s['bouncing'] = score_one_sided(mv['bounce_a_mps2'], 12, 18, 25, 35, higher_is_better=False)
    else:
        # Touch-and-go: mild bounce OK, severe is bad
        s['bouncing'] = score_one_sided(mv['bounce_a_mps2'], 18, 25, 30, 40, higher_is_better=False)
    # Wrist position
    s['wrist_position'] = score_one_sided(mv['wrist_extension_deg'], 10, 20, 30, 45, higher_is_better=False)
    # Press symmetry L/R
    s['press_symmetry'] = score_one_sided(mv['press_asym_deg'], 2, 5, 10, 18, higher_is_better=False)
    # Bar tilt
    s['bar_tilt'] = score_one_sided(mv['bar_tilt_deg'], 2, 4, 7, 12, higher_is_better=False)
    # Head position
    s['head_position'] = score_one_sided(mv['head_lift_cm'], 0.5, 2.0, 4.0, 7.0, higher_is_better=False)
    # Glute contact
    s['glute_contact'] = score_one_sided(mv['glute_lift_cm'], 0.5, 2.0, 4.0, 7.0, higher_is_better=False)

    # — Technique —
    # Bar path J-curve (head-ward distance; flat = larger band, incline = smaller)
    if is_incline:
        s['bar_path_jcurve'] = score_ranged(mv['jcurve_cm'],
                                             3, 8, 1, 12, 0, 18, -5, 25)
    else:
        s['bar_path_jcurve'] = score_ranged(mv['jcurve_cm'],
                                             5, 12, 3, 18, 1, 25, -5, 35)
    # Forward drift is always bad; penalise if > 1 cm
    if mv['forward_drift_cm'] > 1.0:
        s['bar_path_jcurve'] = min(s['bar_path_jcurve'], 40.0)
    # Touch point on chest (variant + style)
    if is_incline:
        # Incline: upper sternum (5–25%), spec §3.2
        s['touch_point'] = score_ranged(mv['touch_point_pct'],
                                         5, 25, 0, 35, -5, 45, -15, 60)
    elif is_pl:
        # Flat PL: lower sternum (70–95%)
        s['touch_point'] = score_ranged(mv['touch_point_pct'],
                                         70, 95, 60, 105, 50, 115, 30, 130)
    else:
        # Flat BB: mid sternum (45–70%)
        s['touch_point'] = score_ranged(mv['touch_point_pct'],
                                         45, 70, 35, 80, 25, 95, 0, 110)
    # Forearm vertical
    s['forearm_vertical'] = score_one_sided(mv['forearm_vertical_deg'], 5, 10, 15, 25, higher_is_better=False)
    # Elbow at bottom
    if is_incline:
        s['elbow_bottom'] = score_two_sided(mv['elbow_touch_deg'], 70.0, (10, 15, 22, 32))
    else:
        s['elbow_bottom'] = score_two_sided(mv['elbow_touch_deg'], 65.0, (10, 15, 22, 32))
    # Grip width
    if is_incline:
        s['grip_width'] = score_ranged(mv['grip_pct_biacromial'],
                                        110, 150, 100, 170, 90, 185, 70, 200)
    elif is_pl:
        s['grip_width'] = score_ranged(mv['grip_pct_biacromial'],
                                        165, 200, 150, 210, 130, 220, 100, 240)
    else:
        s['grip_width'] = score_ranged(mv['grip_pct_biacromial'],
                                        130, 170, 115, 185, 100, 200, 70, 220)
    # Arch height (style-aware)
    if is_incline:
        s['arch_height'] = score_ranged(mv['arch_pct'], 0, 3, 0, 5, 0, 7, 0, 10)
    elif is_pl:
        s['arch_height'] = score_ranged(mv['arch_pct'], 8, 20, 6, 25, 4, 30, 2, 35)
    else:
        s['arch_height'] = score_ranged(mv['arch_pct'], 2, 6, 0, 10, -1, 13, -5, 18)
    # Bar path symmetry
    s['bar_path_symmetry'] = score_one_sided(mv['bar_path_sym_pct'], 2, 4, 7, 12, higher_is_better=False)
    # Bar wobble
    s['bar_wobble'] = score_one_sided(mv['bar_wobble_cm'], 1, 2, 4, 7, higher_is_better=False)
    # Wrist alignment (frontal)
    s['wrist_alignment_frontal'] = score_one_sided(mv['wrist_align_deg'], 5, 10, 15, 25, higher_is_better=False)
    # Hand spacing symmetry
    s['hand_spacing_symmetry'] = score_one_sided(mv['hand_spacing_asym_cm'], 1, 2, 4, 7, higher_is_better=False)
    # Heel contact
    s['heel_contact'] = score_one_sided(mv['heel_lift_cm'], 0.5, 2.0, 3.0, 5.0, higher_is_better=False)
    # Consistency — filled in at the set level
    s['consistency'] = 80.0  # placeholder

    # — Performance —
    # MCV (the heavier the load, the lower the MCV — assume ~75-85% 1RM working set)
    s['mcv'] = score_one_sided(mv['mcv_mps'], 0.40, 0.30, 0.20, 0.10, higher_is_better=True)
    # Sticking-point duration (at 1RM band)
    s['sticking_point'] = score_one_sided(mv['sticking_duration_sec'], 0.6, 0.9, 1.3, 2.0, higher_is_better=False)
    # Lockout completion (elbow ≥175° + ≥0.5s hold)
    s['lockout_completion'] = score_one_sided(mv['lockout_elbow_deg'], 175, 170, 165, 155, higher_is_better=True)
    # Pause or TnG quality
    if paused:
        s['pause_or_tng'] = score_ranged(mv['pause_sec'], 0.8, 1.5, 0.5, 2.0, 0.3, 3.0, 0.1, 4.0)
    else:
        # Higher quality scalar = smoother reversal
        s['pause_or_tng'] = score_one_sided(mv['pause_or_tng_quality'], 1.5, 1.0, 0.6, 0.2, higher_is_better=True)
    # ROM completion (binary 0/1)
    s['rom_completion'] = 100.0 if mv['rom_ok'] >= 0.5 else 40.0
    # Eccentric tempo
    s['eccentric_tempo'] = score_two_sided(mv['eccentric_sec'], 2.25, (0.75, 1.25, 2.25, 4.0))
    # Setup time
    s['setup_time'] = score_two_sided(mv['setup_sec'], 3.5, (1.5, 2.5, 5.5, 14.0))
    # Lockout hold
    s['lockout_hold'] = score_one_sided(mv['lockout_hold_sec'], 0.5, 0.3, 0.15, 0.0, higher_is_better=True)

    return s


def _category_scores(sub_scores):
    """Weighted means → S_safety, S_technique, S_performance."""
    def _weighted(weights):
        total_w = sum(weights.values())
        if total_w <= 0:
            return 50.0
        acc, used = 0.0, 0.0
        for k, w in weights.items():
            v = sub_scores.get(k)
            if v is None:
                continue
            acc += w * float(v); used += w
        return acc / used if used > 0 else 50.0
    return {
        'safety': _weighted(SAFETY_W),
        'technique': _weighted(TECH_W),
        'performance': _weighted(PERF_W),
    }


def _geometric_composite(cat):
    """Spec §7.3 geometric mean: S_safety^0.40 · S_tech^0.35 · S_perf^0.25."""
    s = max(1e-3, cat['safety'])
    t = max(1e-3, cat['technique'])
    p = max(1e-3, cat['performance'])
    return (s ** CATEGORY_WEIGHTS['safety']) * \
           (t ** CATEGORY_WEIGHTS['technique']) * \
           (p ** CATEGORY_WEIGHTS['performance'])


# ─────────────────────────────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────────────────────────────

def _safe_at(arr, idx, default=0.0):
    if 0 <= idx < len(arr) and arr[idx] is not None:
        return arr[idx]
    return default


def _nearest_frame(view, target_frame, sag_ref):
    """Map a sagittal frame index to the nearest valid frame in another view.
    Cameras may have different fps — we scale proportionally."""
    if view is None or not view['frames']:
        return target_frame
    sag_total = len(sag_ref['frames'])
    if sag_total == 0:
        return 0
    fr = int(target_frame / sag_total * len(view['frames']))
    return max(0, min(fr, len(view['frames']) - 1))


def _compute_pause(bench_wy, touch, fps):
    """Duration of motionless frames at the touch minimum + max velocity."""
    if not bench_wy or fps <= 0:
        return 0.0, 0.0
    # Walk forward and backward from touch, count contiguous frames with
    # velocity below 0.05 m/s (in pixel units this is small).
    floor = bench_wy[touch]
    if floor is None:
        return 0.0, 0.0
    eps = 5.0   # ≈ 5 pixels of jitter tolerance
    # backward
    a = touch
    while a > 0 and bench_wy[a - 1] is not None \
            and abs(bench_wy[a - 1] - floor) <= eps:
        a -= 1
    # forward
    b = touch
    while b < len(bench_wy) - 1 and bench_wy[b + 1] is not None \
            and abs(bench_wy[b + 1] - floor) <= eps:
        b += 1
    dur = (b - a) / fps
    # Max velocity inside the window
    max_v = 0.0
    for fi in range(a, b):
        v0 = bench_wy[fi]; v1 = bench_wy[fi + 1]
        if v0 is not None and v1 is not None:
            max_v = max(max_v, abs(v1 - v0) * fps)
    return dur, max_v / 1000.0   # rough m/s scale (px → cm assumed via tracker)


def _compute_touch_accel(bench_wy, touch, fps, px_per_cm):
    """Peak |acceleration| in a ±100 ms window around touch."""
    if fps <= 0 or not bench_wy:
        return 5.0
    win = max(1, int(fps * 0.1))
    a = max(1, touch - win)
    b = min(len(bench_wy) - 2, touch + win)
    px_per_m = (px_per_cm * 100.0) if px_per_cm > 0 else 1000.0  # rough
    max_a = 0.0
    for fi in range(a, b):
        v0 = bench_wy[fi]; v1 = bench_wy[fi + 1]; v2 = bench_wy[fi + 2] \
            if fi + 2 < len(bench_wy) else None
        if None in (v0, v1, v2):
            continue
        # Second derivative
        a_val = ((v2 - 2 * v1 + v0) * fps * fps) / px_per_m
        max_a = max(max_a, abs(a_val))
    return max_a


def _compute_bar_wobble(sag, start, end, px_per_cm):
    """RMS lateral wobble of bar X relative to a linear fit."""
    xs = []
    for fi in range(start, min(end + 1, len(sag['bench_wrist_x']))):
        v = sag['bench_wrist_x'][fi]
        if v is not None:
            xs.append((fi, v))
    if len(xs) < 4:
        return 1.0
    # Linear regression on (frame, x) → residual RMS
    n = len(xs)
    mx = _mean(p[0] for p in xs)
    my = _mean(p[1] for p in xs)
    num = sum((p[0] - mx) * (p[1] - my) for p in xs)
    den = sum((p[0] - mx) ** 2 for p in xs)
    slope = num / den if abs(den) > 1e-9 else 0.0
    rms = math.sqrt(sum((p[1] - (my + slope * (p[0] - mx))) ** 2 for p in xs) / n)
    return (rms / px_per_cm) if px_per_cm > 0 else (rms / 10.0)


def _compute_arch_height_pct(sag, start, touch):
    """Perpendicular displacement of shoulder centre from the setup-frame
    bench line, normalised by torso length."""
    bsy = sag['bench_shoulder_y']
    bhy = sag['bench_hip_y']
    if (start >= len(bsy) or bsy[start] is None
            or touch >= len(bsy) or bsy[touch] is None
            or bhy[start] is None):
        return 3.0
    torso = abs(bsy[start] - bhy[start])
    if torso < 1e-3:
        return 3.0
    arch = (bsy[touch] - bsy[start]) / torso * 100.0
    return max(-5.0, arch)


def _compute_scapular_drift(sag, start, end, px_per_cm):
    bsy = sag['bench_shoulder_y']
    vals = [v for v in bsy[start:end + 1] if v is not None]
    if len(vals) < 2:
        return 0.5
    drift_px = max(vals) - min(vals)
    return (drift_px / px_per_cm) if px_per_cm > 0 else (drift_px / 10.0)


def _compute_head_lift(sag, start, end, px_per_cm):
    ny = sag['nose_y']
    vals = [v for v in ny[start:end + 1] if v is not None]
    if len(vals) < 2:
        return 0.5
    # In image coords, higher = smaller y. "Lift" = decreasing y from baseline.
    baseline = vals[0]
    lift_px = max(0.0, baseline - min(vals))
    return (lift_px / px_per_cm) if px_per_cm > 0 else (lift_px / 10.0)


def _compute_glute_lift(sag, start, end, px_per_cm):
    hy = sag['hip_y']
    vals = [v for v in hy[start:end + 1] if v is not None]
    if len(vals) < 2:
        return 0.5
    baseline = vals[0]
    lift_px = max(0.0, baseline - min(vals))
    return (lift_px / px_per_cm) if px_per_cm > 0 else (lift_px / 10.0)


def _compute_heel_lift(sag, start, end, px_per_cm):
    hy = sag['heel_y']
    vals = [v for v in hy[start:end + 1] if v is not None]
    if len(vals) < 2:
        return 0.3
    baseline = vals[0]
    lift_px = max(0.0, baseline - min(vals))
    return (lift_px / px_per_cm) if px_per_cm > 0 else (lift_px / 10.0)


def _compute_lockout_hold(bench_wy, lockout, fps):
    """Frames at near-max wrist-Y after lockout."""
    if fps <= 0 or lockout >= len(bench_wy):
        return 0.4
    floor = bench_wy[lockout]
    if floor is None:
        return 0.4
    eps = 5.0
    b = lockout
    while b < len(bench_wy) - 1 and bench_wy[b + 1] is not None \
            and abs(bench_wy[b + 1] - floor) <= eps:
        b += 1
    return (b - lockout) / fps


def _compute_grip_width(view, touch, sag_ref):
    """Grip width as % biacromial.  Best from overhead view."""
    if view is None:
        return 145.0
    t = _nearest_frame(view, touch, sag_ref)
    lw = (view['lwr_x'][t] if t < len(view['lwr_x']) else None,
          view['lwr_y'][t] if t < len(view['lwr_y']) else None)
    rw = (view['rwr_x'][t] if t < len(view['rwr_x']) else None,
          view['rwr_y'][t] if t < len(view['rwr_y']) else None)
    ls = (view['lsh_x'][t] if t < len(view['lsh_x']) else None,
          view['lsh_y'][t] if t < len(view['lsh_y']) else None)
    rs = (view['rsh_x'][t] if t < len(view['rsh_x']) else None,
          view['rsh_y'][t] if t < len(view['rsh_y']) else None)
    if None in lw or None in rw or None in ls or None in rs:
        return 145.0
    wrist_dist = math.hypot(lw[0] - rw[0], lw[1] - rw[1])
    biacromial = math.hypot(ls[0] - rs[0], ls[1] - rs[1])
    if biacromial < 1e-3:
        return 145.0
    return wrist_dist / biacromial * 100.0


def _compute_bar_tilt(over, head, sag, start, end):
    """Worst absolute bar tilt (deg) across the rep. Prefer overhead, then
    head-end, then sagittal."""
    candidates = [v for v in (over, head, sag) if v is not None]
    if not candidates:
        return 1.0
    view = candidates[0]
    worst = 0.0
    for fi in range(start, min(end + 1, len(view['lwr_x']))):
        lw_x = view['lwr_x'][fi]; lw_y = view['lwr_y'][fi]
        rw_x = view['rwr_x'][fi]; rw_y = view['rwr_y'][fi]
        if None in (lw_x, lw_y, rw_x, rw_y):
            continue
        dy = lw_y - rw_y
        dx = abs(lw_x - rw_x) + 1e-6
        worst = max(worst, abs(math.degrees(math.atan2(dy, dx))))
    return worst


def _compute_bar_path_symmetry(view, start, end):
    """Pointwise L/R wrist X divergence, normalised by mean torso length."""
    if view is None:
        return 2.0
    diffs = []
    for fi in range(start, min(end + 1, len(view['lwr_x']))):
        lwx = view['lwr_x'][fi]; rwx = view['rwr_x'][fi]
        if lwx is None or rwx is None:
            continue
        diffs.append(abs(lwx + rwx) / 2.0 - 0.0)   # not great — placeholder
    # Compute integrated L vs R Y-trajectory divergence instead
    n = 0; total = 0.0
    lyx = view['lwr_y']; ryx = view['rwr_y']
    for fi in range(start, min(end + 1, min(len(lyx), len(ryx)))):
        if lyx[fi] is not None and ryx[fi] is not None:
            total += abs(lyx[fi] - ryx[fi])
            n += 1
    if n == 0:
        return 2.0
    # Normalise by biacromial-equivalent width (use mean L/R shoulder distance)
    sh_widths = []
    for fi in range(start, min(end + 1, len(view.get('lsh_x', [])))):
        lsx = view['lsh_x'][fi]; rsx = view['rsh_x'][fi]
        if lsx is not None and rsx is not None:
            sh_widths.append(abs(lsx - rsx))
    ref = _mean(sh_widths) if sh_widths else 100.0
    avg = total / n
    return avg / max(1e-3, ref) * 100.0


def _compute_hand_spacing_asym_cm(view, touch, px_per_cm):
    return _compute_hand_spacing_asym(view, touch, px_per_cm)


def _compute_hand_spacing_asym(view, touch, px_per_cm):
    """Difference between |L wrist - bar centre| and |R wrist - bar centre|."""
    if view is None:
        return 1.0
    t = _nearest_frame(view, touch, view)
    lwx = view['lwr_x'][t] if t < len(view['lwr_x']) else None
    rwx = view['rwr_x'][t] if t < len(view['rwr_x']) else None
    if lwx is None or rwx is None:
        return 1.0
    centre = (lwx + rwx) / 2.0
    diff_px = abs(abs(lwx - centre) - abs(rwx - centre))
    return (diff_px / px_per_cm) if px_per_cm > 0 else (diff_px / 10.0)


def _compute_frontal_drift(view, sag_ref, start, end, px_per_cm):
    """Max lateral excursion of bar centre from torso midline."""
    if view is None:
        return 1.5
    worst = 0.0
    for fi in range(start, min(end + 1, len(view['lwr_x']))):
        lwx = view['lwr_x'][fi]; rwx = view['rwr_x'][fi]
        lsx = view['lsh_x'][fi]; rsx = view['rsh_x'][fi]
        if None in (lwx, rwx, lsx, rsx):
            continue
        bar_mid = (lwx + rwx) / 2.0
        torso_mid = (lsx + rsx) / 2.0
        worst = max(worst, abs(bar_mid - torso_mid))
    return (worst / px_per_cm) if px_per_cm > 0 else (worst / 10.0)


def _compute_shoulder_y_asym(view, touch):
    """|L shoulder Y − R shoulder Y| / biacromial, at touch."""
    if view is None:
        return 2.0
    t = _nearest_frame(view, touch, view)
    lsy = view['lsh_y'][t] if t < len(view['lsh_y']) else None
    rsy = view['rsh_y'][t] if t < len(view['rsh_y']) else None
    lsx = view['lsh_x'][t] if t < len(view['lsh_x']) else None
    rsx = view['rsh_x'][t] if t < len(view['rsh_x']) else None
    if None in (lsy, rsy, lsx, rsx):
        return 2.0
    biacromial = max(1e-3, abs(lsx - rsx))
    return abs(lsy - rsy) / biacromial * 100.0


def _compute_press_asymmetry(view, touch, lockout):
    """Angular L/R asymmetry of bar tilt at lockout."""
    if view is None:
        return 1.0
    t = _nearest_frame(view, lockout, view)
    lwx = view['lwr_x'][t] if t < len(view['lwr_x']) else None
    lwy = view['lwr_y'][t] if t < len(view['lwr_y']) else None
    rwx = view['rwr_x'][t] if t < len(view['rwr_x']) else None
    rwy = view['rwr_y'][t] if t < len(view['rwr_y']) else None
    if None in (lwx, lwy, rwx, rwy):
        return 1.0
    dy = lwy - rwy
    dx = abs(lwx - rwx) + 1e-6
    return abs(math.degrees(math.atan2(dy, dx)))


def _compute_sticking_point(bench_wy, touch, lockout, fps):
    """Sticking-point duration + position. Find vmax1, vmin after touch."""
    if fps <= 0 or lockout <= touch + 2:
        return 0.5, 35.0
    # Compute velocity series
    vels = []
    for fi in range(touch, lockout):
        if fi + 1 < len(bench_wy) and bench_wy[fi] is not None \
                and bench_wy[fi + 1] is not None:
            vels.append((bench_wy[fi + 1] - bench_wy[fi]) * fps)
        else:
            vels.append(0.0)
    if not vels:
        return 0.5, 35.0
    # First local max of upward velocity (positive in our bench-up convention)
    vmax1_i = 0
    for i in range(1, len(vels) - 1):
        if vels[i] > vels[i - 1] and vels[i] >= vels[i + 1]:
            vmax1_i = i; break
    # Subsequent local min
    vmin_i = vmax1_i
    vmin_v = vels[vmax1_i]
    for i in range(vmax1_i + 1, len(vels)):
        if vels[i] < vmin_v:
            vmin_v = vels[i]; vmin_i = i
        elif vels[i] > vmin_v + 1.0:
            break   # past sticking point
    dur = (vmin_i - vmax1_i) / fps
    # Position: where in ROM did vmin occur?
    range_total = max(1e-6, lockout - touch)
    pos_pct = (vmin_i / range_total) * 100.0
    return max(0.0, dur), max(0.0, min(100.0, pos_pct))


# ─────────────────────────────────────────────────────────────────────
# Corrective cues (spec §11.5 — surface the two lowest sub-scores)
# ─────────────────────────────────────────────────────────────────────

CUE_TEMPLATES = {
    'shoulder_abduction': (
        "Shoulder abduction (elbow flare)",
        "Tuck the elbows — feel for ~45–55° on flat (powerlifting) or ~60–75° "
        "(bodybuilding); on incline ~35–50°. Flaring past 90° is rotator-cuff territory."),
    'touch_point_safety': (
        "Touch point safety",
        "Bar drifted toward your neck. Stop the lift. Lower bar should touch "
        "lower sternum (PL flat) or upper sternum / clavicular pec (incline) — never the throat."),
    'scapular_retraction': (
        "Scapular retraction",
        "Set scapulae BEFORE you unrack: pinch shoulder blades back and down, "
        "then have a spotter hand you the bar. Letting them shift mid-set kills the foundation."),
    'bouncing': (
        "Bounce at touch",
        "You bounced the bar off your chest. Add a deliberate 1 s pause for "
        "two weeks to break the habit — bounce-loading is the #1 mechanism of pec / sternum injury."),
    'wrist_position': (
        "Wrist hyperextension",
        "Grip the bar lower in the palm and squeeze hard. Wrist should be "
        "stacked over the forearm, not bent back like a flopping flag."),
    'press_symmetry': (
        "Press symmetry L/R",
        "One arm is leading. Check grip evenness and scapular set, then drop "
        "back to a load you can grind clean with both sides for 2–3 weeks."),
    'bar_tilt': (
        "Bar tilt",
        "Re-grip until it feels balanced. Visible tilt for > 300 ms is a fault — "
        "reset, don't grind through it."),
    'head_position': (
        "Head lifting off bench",
        "Eyes track the bar with eyeballs only — head stays on the bench. "
        "Lifting the head loses scapular retraction and shifts your line."),
    'glute_contact': (
        "Glute lift",
        "Glutes off the bench is a red light in IPF. Drive your heels and "
        "squeeze your glutes throughout — they shouldn't separate from the bench."),
    'bar_path_jcurve': (
        "Bar path J-curve",
        "Bar should descend roughly vertical to the chest, then arc back-and-up "
        "toward the shoulder line on the press. Vertical-only paths cost you the elite J."),
    'touch_point': (
        "Touch point on chest",
        "On flat-PL aim for lower sternum (70–95% torso); flat-BB mid sternum "
        "(45–70%); incline upper sternum (5–25%)."),
    'forearm_vertical': (
        "Forearm vertical at touch",
        "Forearm should be near-vertical (within 10°) at the touch frame. "
        "Mismatch between grip width and touch point causes the lean."),
    'elbow_bottom': (
        "Elbow angle at touch",
        "Target ~65° (flat) / ~70° (incline) at the chest. Going below 50° "
        "crushes the elbow; over 95° usually means insufficient ROM."),
    'grip_width': (
        "Grip width",
        "Flat-PL: 165–200% biacromial (cap 81 cm IPF). Flat-BB: 130–170%. "
        "Incline: 110–150%. Mismatched grip kills the J-curve."),
    'arch_height': (
        "Arch height",
        "Style-specific: PL allows max arch (8–20% torso); BB minimal arch (2–6%); "
        "incline near-flat (0–3%). Match your style or lose points either way."),
    'bar_path_symmetry': (
        "Bar path symmetry L/R",
        "Left and right wrists are tracking different paths. Squeeze the bar "
        "evenly; check for forearm imbalance."),
    'bar_wobble': (
        "Bar wobble",
        "RMS lateral jitter is high. Tighten your grip; \"bend the bar in "
        "half\" creates the rigid platform that stops wobble."),
    'wrist_alignment_frontal': (
        "Wrist alignment (frontal)",
        "Ulnar/radial deviation under load is a sprain risk. Stack the wrist "
        "over the forearm in BOTH planes."),
    'hand_spacing_symmetry': (
        "Hand spacing symmetry",
        "Use the bar's knurling marks every rep. Mismatched hand spacing "
        "creates uneven leverage and bar tilt."),
    'heel_contact': (
        "Heel contact",
        "Heels stay down. Foot lift loses leg drive and risks an IPF red light."),
    'consistency': (
        "Rep-to-rep consistency",
        "Touch point drifting between reps means tension is decaying. "
        "Drop load 10%, rebuild the groove."),
    'mcv': (
        "Mean concentric velocity",
        "Bar speed below 0.20 m/s on working reps suggests the load is too "
        "heavy for clean technique. Velocity-prescribe at higher percentages."),
    'sticking_point': (
        "Sticking-point duration",
        "Sticking lasts > 0.9 s. Train pin-press or pause-bench at the sticking "
        "height for 4 weeks to recruit through it."),
    'lockout_completion': (
        "Lockout completion",
        "Elbows must reach ≥175°. Soft lockouts are leaving points on the table — "
        "and look unfinished."),
    'pause_or_tng': (
        "Pause / touch-and-go quality",
        "Paused reps: motionless 0.8–1.5 s with no sink. TnG: smooth reversal, "
        "no bounce. Pick a protocol and execute it cleanly."),
    'rom_completion': (
        "ROM completion",
        "Either the bar didn't touch the chest or didn't lock out. Earn full "
        "reps before counting them."),
    'eccentric_tempo': (
        "Eccentric tempo",
        "Descend in 1.5–3 s. Faster than 1 s means free-fall; slower than 4 s "
        "wastes tension."),
    'setup_time': (
        "Setup time",
        "Take 2–5 s of deliberate setup: foot set, brace, leg drive engaged, "
        "scapulae locked. Rushing the setup costs you everything else."),
    'lockout_hold': (
        "Lockout hold",
        "Hold the top for 0.3–0.5 s. \"Pause and own it\" before lowering."),
}


def _coaching_for(slug, sub_score):
    name, body = CUE_TEMPLATES.get(slug, (slug, "Work on this metric."))
    return {'metric': name, 'sub_score': round(float(sub_score), 1), 'cue': body}


# ─────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────

def analyse(files, plate_size_kg=None, weight_max=None, reps_max=None,
            target_reps=None, target_reps_sagittal=None, target_reps_overhead=None,
            target_reps_head_end=None, target_reps_oblique=None,
            variant='flat', style='powerlifting', paused='paused',
            incline_deg=None, athlete_height_cm=None):
    """Analyze a bench press across four camera views.

    Required: files['sagittal'] (back-compat alias: 'side').
    Recommended: files['overhead'], files['headEnd'], files['oblique'].
    """
    variant = (variant or 'flat').lower()
    if variant not in ('flat', 'incline'):
        variant = 'flat'
    style = (style or 'powerlifting').lower()
    if variant == 'incline':
        # Spec §11.6: incline is always BB-style
        style = 'bodybuilding'
    paused_mode = (paused or 'paused').lower() in ('paused', 'true', '1', 'yes')

    # Per-view rep counts — fall back to legacy `target_reps` for back-compat
    legacy_default = target_reps or 3
    counts = {
        'sagittal': target_reps_sagittal or legacy_default,
        'overhead': target_reps_overhead or legacy_default,
        'headEnd':  target_reps_head_end  or legacy_default,
        'oblique':  target_reps_oblique  or legacy_default,
    }

    # File resolution (back-compat aliases)
    sag_path = (files or {}).get('sagittal') or (files or {}).get('side')
    over_path = (files or {}).get('overhead')
    head_path = (files or {}).get('headEnd') or (files or {}).get('head_end') \
                or (files or {}).get('posterior')
    obl_path = (files or {}).get('oblique')
    if not sag_path and files:
        sag_path = list(files.values())[0]
    if not sag_path:
        return _fallback('No sagittal video uploaded.')

    bench_deg = float(incline_deg) if (variant == 'incline' and incline_deg) else 0.0

    # Process each view
    try:
        sag = _process_view(sag_path, 'sagittal', plate_size_kg, bench_deg)
    except Exception as e:
        return _fallback(f'Sagittal pose extraction failed: {e}')
    over = _process_view(over_path, 'overhead', None, 0.0) if over_path else None
    head = _process_view(head_path, 'headEnd', None, 0.0) if head_path else None
    obl  = _process_view(obl_path,  'oblique',  None, bench_deg) if obl_path else None

    fps_sag = sag['fps']
    conf = confidence_score(sag['frames'])

    # Detect touch frames per view (each video uses its own rep count)
    reps_by_view = {
        'sagittal': _detect_touch_frames(sag, counts['sagittal'], paused=paused_mode),
    }
    if over: reps_by_view['overhead'] = _detect_touch_frames(over, counts['overhead'], paused=paused_mode)
    if head: reps_by_view['headEnd']  = _detect_touch_frames(head, counts['headEnd'],  paused=paused_mode)
    if obl:  reps_by_view['oblique']  = _detect_touch_frames(obl,  counts['oblique'],  paused=paused_mode)

    sag_reps = reps_by_view['sagittal']
    if not sag_reps:
        return _fallback('No reps detected on the sagittal video.')

    # Per-rep metric computation: indexed by SAGITTAL rep order; other views
    # are matched by rank.
    px_per_cm_global = sag['px_per_cm']
    per_rep = []
    for ri, rep in enumerate(sag_reps):
        # Build a synced rep view from each camera (by rank order)
        synced_over = (reps_by_view.get('overhead') or [None] * len(sag_reps))[ri] \
                      if over and ri < len(reps_by_view.get('overhead', [])) else None
        synced_head = (reps_by_view.get('headEnd')  or [None] * len(sag_reps))[ri] \
                      if head and ri < len(reps_by_view.get('headEnd', [])) else None
        mv = _compute_rep_metrics(rep, sag, over, head, obl, variant, style, paused_mode,
                                  px_per_cm_global)
        subs = _score_all(mv, variant, style, paused_mode)
        per_rep.append({
            'rep_num': rep['idx'],
            'sag_rep': rep,
            'over_rep': synced_over,
            'head_rep': synced_head,
            'metric_values': mv,
            'sub_scores': subs,
        })

    # Consistency CV across reps
    cv_pct = _consistency_cv(per_rep)
    consistency_score = score_one_sided(cv_pct, 3, 6, 10, 15, higher_is_better=False)
    for r in per_rep:
        r['sub_scores']['consistency'] = consistency_score

    # Category + composite per rep
    for r in per_rep:
        r['categories'] = _category_scores(r['sub_scores'])
        r['composite'] = _geometric_composite(r['categories'])

    # Hard-fail overrides (set-level; trigger if ANY rep trips it)
    set_overrides = []
    for spec in _override_specs():
        triggered = False
        worst_val = None
        worst_rep = None
        for r in per_rep:
            t, vs = spec['eval'](r['metric_values'])
            if t and worst_val is None:
                triggered = True
                worst_val = vs; worst_rep = r['rep_num']
            elif t:
                triggered = True
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

    # Set aggregation
    composites = [r['composite'] for r in per_rep]
    set_mean = _mean(composites)
    set_worst = min(composites)
    last3 = composites[-3:] if len(composites) >= 3 else composites
    set_last3 = _mean(last3)
    deteriorating = [r['rep_num'] for r in per_rep if r['composite'] < (set_mean - 15)]

    # Category means
    cat_means = {k: _mean(r['categories'][k] for r in per_rep)
                 for k in ('safety', 'technique', 'performance')}

    # Lowest sub-scores
    sub_mean = {}
    all_keys = set()
    for r in per_rep:
        all_keys.update(r['sub_scores'].keys())
    for k in all_keys:
        vals = [r['sub_scores'].get(k) for r in per_rep
                if r['sub_scores'].get(k) is not None]
        if vals:
            sub_mean[k] = _mean(vals)
    lowest = sorted(sub_mean.items(), key=lambda kv: kv[1])[:2]
    lowest_cues = [_coaching_for(k, v) for k, v in lowest]

    # Grade
    headline = round(set_mean)
    grade, label = grade_from_composite(set_mean)
    status = status_from_grade(grade)

    # Identify best + worst rep indices for the rich annotated coverage
    best_idx = max(range(len(per_rep)), key=lambda i: per_rep[i]['composite'])
    worst_idx = min(range(len(per_rep)), key=lambda i: per_rep[i]['composite'])

    # Build legacy metrics list
    metrics_list = _build_legacy_metrics(per_rep, variant, style, sub_mean,
                                          sag['bar_med_q'])

    # Coaching: overrides first, then top fixes
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
        coaching.append("Clean press. Maintain scapular retraction and bar-over-shoulder lockout next session.")
    if deteriorating:
        coaching.append(
            f"Rep{'s' if len(deteriorating) > 1 else ''} {', '.join(str(n) for n in deteriorating)} "
            f"deteriorated > 15 pts below the set mean — fatigue or form drift.")

    # Optional 1RM estimate
    if weight_max and reps_max:
        try:
            est = estimate_1rm(weight_max, reps_max)
            metrics_list.append(build_metric('Estimated 1RM (Epley)', f"{est['epley']} kg",
                                             est['epley'], '—', max(est['epley']*1.2, 100), 'GOOD'))
            metrics_list.append(build_metric('Estimated 1RM (Brzycki)', f"{est['brzycki']} kg",
                                             est['brzycki'], '—', max(est['brzycki']*1.2, 100), 'GOOD'))
        except Exception:
            pass

    # Annotated frames: 4-camera coverage for best + worst; sagittal only for others
    annotated = _render_frames(
        per_rep, best_idx, worst_idx,
        sag_path, sag, over_path, over, head_path, head, obl_path, obl,
        variant, style, status, headline, paused_mode,
    )

    # Stats banner
    n_reps_total = counts['sagittal']
    valid_reps = sum(1 for r in per_rep if r['composite'] >= 40)
    stats = {
        'validReps': f'{valid_reps}/{n_reps_total}',
        'confidence': f'{conf}%',
        'sides': sag['side'],
        'cameraView': 'Sagittal + Overhead + Head-end + Oblique',
        'variant': variant,
        'style': style,
        'paused': 'paused' if paused_mode else 'touch-and-go',
        'composite': f'{headline} ({grade})',
        'load': f'{weight_max} kg' if weight_max else '—',
        'benchAngle': f"{sag['theta_bench_deg']:.0f}°" if variant == 'incline' else '0° (flat)',
        'calibration': 'plate' if sag['px_per_cm'] > 0 else 'fallback',
        'barTrackQuality': f'{int(sag["bar_med_q"]*100)}%',
    }

    # Composite-score payload for the spec UI
    composite_score = {
        'composite': headline,
        'grade': grade,
        'label': label,
        'composite_method': 'geometric',
        'categories': [
            {'name': 'Safety',      'weight': 0.40, 'score': round(cat_means['safety'], 1)},
            {'name': 'Technique',   'weight': 0.35, 'score': round(cat_means['technique'], 1)},
            {'name': 'Performance', 'weight': 0.25, 'score': round(cat_means['performance'], 1)},
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
        'variant': f"{variant} · {style}",
    }

    summary = (f"{label} ({grade}) · composite {headline}/100. "
               f"Safety {round(cat_means['safety'])}, Technique {round(cat_means['technique'])}, "
               f"Performance {round(cat_means['performance'])}.")
    if active_cap is not None:
        summary = f"⚠️ {summary} Capped at {active_cap} by a safety override."

    result = build_result(status, headline, summary, stats, metrics_list, [], coaching)
    result['annotated_frames'] = annotated
    result['per_rep'] = [
        {'rep': r['rep_num'], 'side': 'center',
         'metrics': _flatten_per_rep_for_ui(r)}
        for r in per_rep
    ]
    result['composite_score'] = composite_score
    result['muscle_activation'] = infer_bench_press(
        elbow_flare_deg=_mean(r['metric_values']['shoulder_abduction_deg']
                              for r in per_rep),
        variant=variant,
        grip_ratio=_mean(r['metric_values']['grip_pct_biacromial']
                         for r in per_rep) / 100.0,
        incline_deg=sag['theta_bench_deg'] if variant == 'incline' else 0.0,
    )
    result['meta'] = {
        'camera_view': 'sagittal+overhead+headEnd+oblique',
        'camera_view_confidence': round(min(1.0, conf / 100.0), 2),
        'camera_view_warning': None,
        'bar_track_quality_median': round(sag['bar_med_q'], 2),
        'analyzer_version': 'bench-press-2026-05-20-spec',
    }
    return result


# ─────────────────────────────────────────────────────────────────────
# Annotated frames per rep per camera
# ─────────────────────────────────────────────────────────────────────

def _render_frames(per_rep, best_idx, worst_idx,
                   sag_path, sag, over_path, over, head_path, head,
                   obl_path, obl, variant, style, status, score, paused):
    """4-cam frames for best + worst reps; sagittal-only for the rest.

    Each diagram is anchored on the touch frame (the EXTREME position).
    """
    out = []
    if not per_rep:
        fb = render_sample_frame(sag_path, sag['frames'], sag['w'], sag['h'],
                                 'Bench Press', 'No reps detected.',
                                 connections=BENCH_CONNECTIONS)
        if fb:
            out.append({'label': 'Sample Frame', 'image_base64': fb,
                        'rep_num': 0, 'side': 'center', 'is_best': False,
                        'metrics_shown': ['No reps detected']})
        return out

    rich_reps = {best_idx, worst_idx}

    for ri, r in enumerate(per_rep):
        # Always: sagittal at the touch frame
        try:
            frame = _annotate_sagittal(sag_path, sag, r, variant, style, status,
                                       score, paused, len(per_rep))
            if frame:
                is_best = (ri == best_idx)
                is_worst = (ri == worst_idx)
                lbl = f"Rep {r['rep_num']} · Sagittal"
                if is_best: lbl += " ⭐ Best"
                if is_worst: lbl += " ⚠ Worst"
                out.append({
                    'label': lbl, 'image_base64': frame,
                    'rep_num': r['rep_num'], 'side': 'sagittal',
                    'is_best': is_best,
                    'metrics_shown': _summary_for_overlay(r, 'sagittal'),
                })
        except Exception as e:
            print(f"[bench.render] sagittal rep {r['rep_num']} failed: {e}")

        # For best + worst rep only: render the other three views too
        if ri in rich_reps:
            for view_name, view, path in (
                ('overhead', over, over_path),
                ('headEnd', head, head_path),
                ('oblique', obl, obl_path),
            ):
                if not view or not path:
                    continue
                try:
                    frame = _annotate_secondary(path, view, view_name, r,
                                                  variant, style, status, score,
                                                  len(per_rep), sag)
                    if frame:
                        lbl = f"Rep {r['rep_num']} · {_view_label(view_name)}"
                        if ri == best_idx: lbl += " ⭐"
                        if ri == worst_idx: lbl += " ⚠"
                        out.append({
                            'label': lbl, 'image_base64': frame,
                            'rep_num': r['rep_num'], 'side': view_name,
                            'is_best': (ri == best_idx),
                            'metrics_shown': _summary_for_overlay(r, view_name),
                        })
                except Exception as e:
                    print(f"[bench.render] {view_name} rep {r['rep_num']} failed: {e}")

    if not out:
        fb = render_sample_frame(sag_path, sag['frames'], sag['w'], sag['h'],
                                 'Bench Press', 'Reps detected but frames could not be rendered.',
                                 connections=BENCH_CONNECTIONS)
        if fb:
            out.append({'label': 'Sample Frame', 'image_base64': fb,
                        'rep_num': 0, 'side': 'center', 'is_best': False,
                        'metrics_shown': ['Frame extraction failed']})
    return out


def _view_label(name):
    return {'overhead': 'Overhead',
            'headEnd': 'Head-end',
            'oblique': 'Oblique (45°)'}.get(name, name)


def _summary_for_overlay(r, view_name):
    mv = r['metric_values']
    if view_name == 'sagittal':
        return [
            f"Composite: {r['composite']:.0f}/100",
            f"Touch pt: {mv['touch_point_pct']:.0f}%",
            f"Elbow @ touch: {mv['elbow_touch_deg']:.0f}°",
            f"J-curve: {mv['jcurve_cm']:.1f} cm",
        ]
    if view_name == 'overhead':
        return [
            f"Grip: {mv['grip_pct_biacromial']:.0f}% biacromial",
            f"Bar tilt: {mv['bar_tilt_deg']:.1f}°",
            f"Symmetry: {mv['bar_path_sym_pct']:.1f}%",
            f"Frontal drift: {mv['bar_frontal_drift_cm']:.1f} cm",
        ]
    if view_name == 'headEnd':
        return [
            f"Flare: {mv['shoulder_abduction_deg']:.0f}°",
            f"Shoulder asym: {mv['shoulder_y_asym_pct']:.1f}%",
            f"Bar centring: {mv['bar_centering_cm']:.1f} cm",
            f"Bar tilt: {mv['bar_tilt_deg']:.1f}°",
        ]
    return [f"Composite: {r['composite']:.0f}/100"]


def _annotate_sagittal(path, sag, rep, variant, style, status, score, paused, total):
    """Render the sagittal touch frame with every sagittal-view metric."""
    sag_rep = rep['sag_rep']
    touch = sag_rep['touch']
    frames = sag['frames']
    w, h = sag['w'], sag['h']
    idx = sag['idx']
    if touch >= len(frames):
        return None
    lm = frames[touch]['landmarks']
    if lm is None:
        return None
    frame = extract_frame_at(path, touch)
    if frame is None:
        return None

    ear = _lm_to_px(lm, idx['ear'], w, h)
    sh  = _lm_to_px(lm, idx['shoulder'], w, h)
    el  = _lm_to_px(lm, idx['elbow'], w, h)
    wr  = _lm_to_px(lm, idx['wrist'], w, h)
    hp  = _lm_to_px(lm, idx['hip'], w, h)
    kn  = _lm_to_px(lm, idx['knee'], w, h)
    an  = _lm_to_px(lm, idx['ankle'], w, h)
    smid = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
    hmid = midpoint_px(lm, LM['LEFT_HIP'], LM['RIGHT_HIP'], w, h)

    draw_skeleton(frame, lm, w, h, connections=BENCH_CONNECTIONS)
    if smid and hmid:
        draw_reference_line(frame, x=smid[0], color=COL_CYAN,
                            label='Shoulder midline')

    mv = rep['metric_values']
    # Elbow angle arc
    if sh and el and wr:
        elbow_status = ('good' if 55 <= mv['elbow_touch_deg'] <= 85
                        else 'warn' if 45 <= mv['elbow_touch_deg'] <= 95 else 'bad')
        draw_angle_arc(frame, el, sh, wr, mv['elbow_touch_deg'],
                       label=f"Elbow {mv['elbow_touch_deg']:.0f}°",
                       radius=52, status=elbow_status)
    # Shoulder flexion arc
    if hp and sh and el:
        sf_status = ('good' if 60 <= mv['shoulder_flex_deg'] <= 90
                     else 'warn' if 50 <= mv['shoulder_flex_deg'] <= 105 else 'bad')
        draw_angle_arc(frame, sh, hp, el, mv['shoulder_flex_deg'],
                       label=f"Sh-Flex {mv['shoulder_flex_deg']:.0f}°",
                       radius=44, status=sf_status)
    # Touch point callout
    if wr:
        tp_status = ('good' if -3 <= mv['touch_point_pct'] <= 100
                     else 'warn' if -10 <= mv['touch_point_pct'] <= 115 else 'bad')
        draw_callout(frame, wr, f"Touch {mv['touch_point_pct']:.0f}%",
                     status=tp_status, offset=(120, 30))
    # Forearm vertical callout
    if el and wr:
        fv_status = 'good' if mv['forearm_vertical_deg'] < 10 else \
                    ('warn' if mv['forearm_vertical_deg'] < 20 else 'bad')
        draw_callout(frame, wr, f"FA-Vert {mv['forearm_vertical_deg']:.1f}°",
                     status=fv_status, offset=(-180, 30))

    draw_title_strip(frame, f"Bench ({variant} · {style})", rep['rep_num'], total,
                     status=status, score=score)
    draw_phase_label(frame, 'Touch (extreme position)')

    overlay = [
        {'label': 'Composite', 'value': f"{rep['composite']:.0f}/100",
         'status': 'good' if rep['composite'] >= 75 else ('warn' if rep['composite'] >= 60 else 'bad')},
        {'label': 'Safety',      'value': f"{rep['categories']['safety']:.0f}",
         'status': 'good' if rep['categories']['safety'] >= 75 else 'warn'},
        {'label': 'Technique',   'value': f"{rep['categories']['technique']:.0f}",
         'status': 'good' if rep['categories']['technique'] >= 75 else 'warn'},
        {'label': 'Performance', 'value': f"{rep['categories']['performance']:.0f}",
         'status': 'good' if rep['categories']['performance'] >= 75 else 'warn'},
        {'label': 'Bar path J',  'value': f"{mv['jcurve_cm']:.1f} cm", 'status': 'good'},
        {'label': 'Touch pt',    'value': f"{mv['touch_point_pct']:.0f}%", 'status': 'good'},
        {'label': 'Elbow @ touch', 'value': f"{mv['elbow_touch_deg']:.0f}°", 'status': 'good'},
        {'label': 'Forearm vert', 'value': f"{mv['forearm_vertical_deg']:.1f}°", 'status': 'good'},
        {'label': 'Shoulder flex', 'value': f"{mv['shoulder_flex_deg']:.0f}°", 'status': 'good'},
        {'label': 'Lockout elbow', 'value': f"{mv['lockout_elbow_deg']:.0f}°", 'status': 'good'},
        {'label': 'Wrist hyper',  'value': f"{mv['wrist_extension_deg']:.0f}°",
         'status': 'good' if mv['wrist_extension_deg'] < 20 else 'bad'},
        {'label': 'Arch height',  'value': f"{mv['arch_pct']:.1f}%", 'status': 'good'},
        {'label': 'Scap drift',   'value': f"{mv['scapular_drift_cm']:.1f} cm",
         'status': 'good' if mv['scapular_drift_cm'] < 2 else 'bad'},
        {'label': 'Head lift',    'value': f"{mv['head_lift_cm']:.1f} cm",
         'status': 'good' if mv['head_lift_cm'] < 2 else 'bad'},
        {'label': 'Glute lift',   'value': f"{mv['glute_lift_cm']:.1f} cm",
         'status': 'good' if mv['glute_lift_cm'] < 2 else 'bad'},
        {'label': 'Heel lift',    'value': f"{mv['heel_lift_cm']:.1f} cm",
         'status': 'good' if mv['heel_lift_cm'] < 1 else 'bad'},
        {'label': 'Bar wobble',   'value': f"{mv['bar_wobble_cm']:.1f} cm", 'status': 'good'},
        {'label': 'Eccentric',    'value': f"{mv['eccentric_sec']:.2f} s", 'status': 'good'},
        {'label': 'Concentric',   'value': f"{mv['concentric_sec']:.2f} s", 'status': 'good'},
        {'label': 'MCV',          'value': f"{mv['mcv_mps']:.2f} m/s",
         'status': 'good' if mv['mcv_mps'] >= 0.3 else 'warn'},
        {'label': 'Sticking',     'value': f"{mv['sticking_duration_sec']:.2f} s",
         'status': 'good' if mv['sticking_duration_sec'] < 0.9 else 'warn'},
        {'label': ('Pause' if paused else 'TnG'),
         'value': (f"{mv['pause_sec']:.2f} s" if paused else f"|a|={mv['bounce_a_mps2']:.0f}"),
         'status': 'good'},
    ]
    draw_metric_overlay(frame, overlay, position='top-right',
                        title=f"REP {rep['rep_num']} · SAGITTAL")
    draw_legend(frame, position='bottom-left')
    return frame_to_base64(frame)


def _annotate_secondary(path, view, view_name, rep, variant, style, status,
                          score, total, sag):
    """Render the touch frame for overhead / head-end / oblique with the
    view-specific metrics overlaid."""
    sag_rep = rep['sag_rep']
    sag_touch = sag_rep['touch']
    view_touch = _nearest_frame(view, sag_touch, sag)
    frames = view['frames']
    w, h = view['w'], view['h']
    if view_touch >= len(frames):
        return None
    lm = frames[view_touch]['landmarks']
    if lm is None:
        return None
    frame = extract_frame_at(path, view_touch)
    if frame is None:
        return None

    draw_skeleton(frame, lm, w, h, connections=BENCH_CONNECTIONS)
    mv = rep['metric_values']

    # View-specific arcs
    if view_name == 'overhead':
        lw = _lm_to_px(lm, LM['LEFT_WRIST'], w, h)
        rw = _lm_to_px(lm, LM['RIGHT_WRIST'], w, h)
        ls = _lm_to_px(lm, LM['LEFT_SHOULDER'], w, h)
        rs = _lm_to_px(lm, LM['RIGHT_SHOULDER'], w, h)
        if lw and rw:
            # Bar tilt arc — draw a line between wrists with the tilt angle
            mid = ((lw[0] + rw[0]) // 2, (lw[1] + rw[1]) // 2)
            tilt_status = ('good' if mv['bar_tilt_deg'] < 4
                           else 'warn' if mv['bar_tilt_deg'] < 7 else 'bad')
            draw_callout(frame, mid, f"Bar tilt {mv['bar_tilt_deg']:.1f}°",
                         status=tilt_status, offset=(60, -30))
        if lw and rw and ls and rs:
            ls_mid = ((ls[0] + rs[0]) // 2, (ls[1] + rs[1]) // 2)
            grip_status = 'good' if 130 <= mv['grip_pct_biacromial'] <= 200 else 'warn'
            draw_callout(frame, ls_mid,
                         f"Grip {mv['grip_pct_biacromial']:.0f}% BAW",
                         status=grip_status, offset=(0, 40))
        overlay = [
            {'label': 'Grip width', 'value': f"{mv['grip_pct_biacromial']:.0f}% BAW", 'status': 'good'},
            {'label': 'Bar tilt',   'value': f"{mv['bar_tilt_deg']:.1f}°",
             'status': 'good' if mv['bar_tilt_deg'] < 4 else 'bad'},
            {'label': 'Symmetry',   'value': f"{mv['bar_path_sym_pct']:.1f}%", 'status': 'good'},
            {'label': 'Frontal drift', 'value': f"{mv['bar_frontal_drift_cm']:.1f} cm", 'status': 'good'},
            {'label': 'Hand spacing asym', 'value': f"{mv['hand_spacing_asym_cm']:.1f} cm", 'status': 'good'},
            {'label': 'Wrist align', 'value': f"{mv['wrist_align_deg']:.1f}°", 'status': 'good'},
        ]
        title = f"REP {rep['rep_num']} · OVERHEAD"
    elif view_name == 'headEnd':
        # Elbow flare cleanest measurement view
        ls = _lm_to_px(lm, LM['LEFT_SHOULDER'], w, h)
        rs = _lm_to_px(lm, LM['RIGHT_SHOULDER'], w, h)
        le = _lm_to_px(lm, LM['LEFT_ELBOW'], w, h)
        re_ = _lm_to_px(lm, LM['RIGHT_ELBOW'], w, h)
        if ls and le:
            flare_status = ('good' if 30 <= mv['shoulder_abduction_deg'] <= 75
                            else 'bad')
            draw_callout(frame, le, f"Flare {mv['shoulder_abduction_deg']:.0f}°",
                         status=flare_status, offset=(-180, 30))
        if ls and rs:
            asym_status = ('good' if mv['shoulder_y_asym_pct'] < 6 else 'bad')
            mid = ((ls[0] + rs[0]) // 2, (ls[1] + rs[1]) // 2)
            draw_callout(frame, mid, f"Sh asym {mv['shoulder_y_asym_pct']:.1f}%",
                         status=asym_status, offset=(0, 50))
        overlay = [
            {'label': 'Shoulder abduction', 'value': f"{mv['shoulder_abduction_deg']:.0f}°",
             'status': 'good' if 30 <= mv['shoulder_abduction_deg'] <= 75 else 'bad'},
            {'label': 'Shoulder Y asym', 'value': f"{mv['shoulder_y_asym_pct']:.1f}%", 'status': 'good'},
            {'label': 'Bar centring', 'value': f"{mv['bar_centering_cm']:.1f} cm", 'status': 'good'},
            {'label': 'Bar tilt', 'value': f"{mv['bar_tilt_deg']:.1f}°", 'status': 'good'},
        ]
        title = f"REP {rep['rep_num']} · HEAD-END"
    else:  # oblique
        overlay = [
            {'label': 'Composite', 'value': f"{rep['composite']:.0f}/100", 'status': 'good'},
            {'label': 'Touch pt',  'value': f"{mv['touch_point_pct']:.0f}%", 'status': 'good'},
            {'label': 'Elbow @ touch', 'value': f"{mv['elbow_touch_deg']:.0f}°", 'status': 'good'},
            {'label': 'Forearm vert', 'value': f"{mv['forearm_vertical_deg']:.1f}°", 'status': 'good'},
            {'label': '(Note)', 'value': 'Oblique — backup view', 'status': 'good'},
        ]
        title = f"REP {rep['rep_num']} · OBLIQUE"

    draw_title_strip(frame, f"Bench ({variant} · {style})", rep['rep_num'],
                     total, status=status, score=score)
    draw_phase_label(frame, 'Touch (extreme position)')
    draw_metric_overlay(frame, overlay, position='top-right', title=title)
    draw_legend(frame, position='bottom-left')
    return frame_to_base64(frame)


# ─────────────────────────────────────────────────────────────────────
# Per-rep flatten for the existing per-rep accordion in the UI
# ─────────────────────────────────────────────────────────────────────

def _flatten_per_rep_for_ui(rep):
    mv = rep['metric_values']
    subs = rep['sub_scores']
    cats = rep['categories']
    out = {
        'composite': round(rep['composite'], 1),
        'safety_score': round(cats['safety'], 1),
        'technique_score': round(cats['technique'], 1),
        'performance_score': round(cats['performance'], 1),
    }
    for k, v in mv.items():
        if isinstance(v, (int, float)):
            out[k] = round(v, 2)
    for k, v in subs.items():
        if isinstance(v, (int, float)):
            out[f'sub_{k}'] = round(v, 1)
    return out


def _consistency_cv(per_rep):
    """CV% across touch_point_pct, jcurve_cm, concentric_sec (spec §6.8)."""
    keys = ('touch_point_pct', 'jcurve_cm', 'concentric_sec')
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
    return sum(cvs) / len(cvs) if cvs else 4.0


# ─────────────────────────────────────────────────────────────────────
# Legacy metrics list
# ─────────────────────────────────────────────────────────────────────

def _legacy_status(sub_score):
    if sub_score >= 75:
        return 'GOOD'
    if sub_score >= 60:
        return 'NEEDS IMPROVEMENT'
    return 'RESTRICTED'


def _build_legacy_metrics(per_rep, variant, style, sub_mean, bar_q):
    n_reps = len(per_rep)
    mv = {k: _mean(r['metric_values'][k] for r in per_rep
                   if isinstance(r['metric_values'].get(k), (int, float)))
          for k in per_rep[0]['metric_values']
          if isinstance(per_rep[0]['metric_values'].get(k), (int, float))}

    def m(name, raw, value_fmt, target, max_val, slug):
        sub = sub_mean.get(slug, 60.0)
        return build_metric(name, value_fmt, raw, target, max_val,
                            _legacy_status(sub), n_reps=n_reps,
                            confidence=min(1.0, bar_q + 0.4))

    out = []
    # Safety
    out.append(m('Shoulder abduction (flare)', mv.get('shoulder_abduction_deg', 50),
                 f"{mv.get('shoulder_abduction_deg', 50):.1f}°",
                 ('45–55°' if (variant == 'flat' and style == 'powerlifting')
                  else '60–75°' if variant == 'flat' else '35–50°'),
                 120, 'shoulder_abduction'))
    out.append(m('Touch point on chest', mv.get('touch_point_pct', 75),
                 f"{mv.get('touch_point_pct', 75):.0f}%",
                 ('70–95%' if (variant == 'flat' and style == 'powerlifting')
                  else '45–70%' if variant == 'flat' else '5–25%'),
                 150, 'touch_point_safety'))
    out.append(m('Scapular retraction drift', mv.get('scapular_drift_cm', 1),
                 f"{mv.get('scapular_drift_cm', 1):.1f} cm", '<1 cm', 10, 'scapular_retraction'))
    out.append(m('Bounce |a|', mv.get('bounce_a_mps2', 10),
                 f"{mv.get('bounce_a_mps2', 10):.1f} m/s²", '<12 m/s²', 50, 'bouncing'))
    out.append(m('Wrist extension', mv.get('wrist_extension_deg', 12),
                 f"{mv.get('wrist_extension_deg', 12):.0f}°", '<10°', 90, 'wrist_position'))
    out.append(m('Press asymmetry L/R', mv.get('press_asym_deg', 2),
                 f"{mv.get('press_asym_deg', 2):.1f}°", '<2°', 25, 'press_symmetry'))
    out.append(m('Bar tilt', mv.get('bar_tilt_deg', 1.5),
                 f"{mv.get('bar_tilt_deg', 1.5):.1f}°", '<2°', 20, 'bar_tilt'))
    out.append(m('Head lift', mv.get('head_lift_cm', 0.5),
                 f"{mv.get('head_lift_cm', 0.5):.1f} cm", '<0.5 cm', 10, 'head_position'))
    out.append(m('Glute lift', mv.get('glute_lift_cm', 0.5),
                 f"{mv.get('glute_lift_cm', 0.5):.1f} cm", '<0.5 cm', 10, 'glute_contact'))

    # Technique
    out.append(m('Bar path J-curve', mv.get('jcurve_cm', 9),
                 f"{mv.get('jcurve_cm', 9):.1f} cm",
                 ('5–12 cm' if variant == 'flat' else '3–8 cm'),
                 40, 'bar_path_jcurve'))
    out.append(m('Forearm vertical @ touch', mv.get('forearm_vertical_deg', 5),
                 f"{mv.get('forearm_vertical_deg', 5):.1f}°", '<5°', 45, 'forearm_vertical'))
    out.append(m('Elbow angle @ touch', mv.get('elbow_touch_deg', 70),
                 f"{mv.get('elbow_touch_deg', 70):.0f}°",
                 ('55–75°' if variant == 'flat' else '60–80°'),
                 180, 'elbow_bottom'))
    out.append(m('Grip width (% BAW)', mv.get('grip_pct_biacromial', 145),
                 f"{mv.get('grip_pct_biacromial', 145):.0f}%",
                 ('165–200%' if (variant == 'flat' and style == 'powerlifting')
                  else '130–170%' if variant == 'flat' else '110–150%'),
                 250, 'grip_width'))
    out.append(m('Arch height (% torso)', mv.get('arch_pct', 5),
                 f"{mv.get('arch_pct', 5):.1f}%",
                 ('8–20%' if (variant == 'flat' and style == 'powerlifting')
                  else '2–6%' if variant == 'flat' else '0–3%'),
                 30, 'arch_height'))
    out.append(m('Bar path symmetry', mv.get('bar_path_sym_pct', 2.5),
                 f"{mv.get('bar_path_sym_pct', 2.5):.1f}%", '<2%', 20, 'bar_path_symmetry'))
    out.append(m('Bar wobble (RMS)', mv.get('bar_wobble_cm', 1.0),
                 f"{mv.get('bar_wobble_cm', 1.0):.1f} cm", '<1 cm', 15, 'bar_wobble'))
    out.append(m('Wrist alignment (frontal)', mv.get('wrist_align_deg', 6),
                 f"{mv.get('wrist_align_deg', 6):.1f}°", '<5°', 45, 'wrist_alignment_frontal'))
    out.append(m('Hand spacing asym', mv.get('hand_spacing_asym_cm', 0.8),
                 f"{mv.get('hand_spacing_asym_cm', 0.8):.1f} cm", '<1 cm', 15, 'hand_spacing_symmetry'))
    out.append(m('Heel lift', mv.get('heel_lift_cm', 0.3),
                 f"{mv.get('heel_lift_cm', 0.3):.1f} cm", '<0.5 cm', 8, 'heel_contact'))
    out.append(m('Frontal bar drift', mv.get('bar_frontal_drift_cm', 1.5),
                 f"{mv.get('bar_frontal_drift_cm', 1.5):.1f} cm", '<2 cm', 20, 'bar_path_symmetry'))

    # Performance
    out.append(m('Mean concentric velocity', mv.get('mcv_mps', 0.4),
                 f"{mv.get('mcv_mps', 0.4):.2f} m/s", '≥0.30 m/s', 1.5, 'mcv'))
    out.append(m('Sticking-point duration', mv.get('sticking_duration_sec', 0.7),
                 f"{mv.get('sticking_duration_sec', 0.7):.2f} s", '<0.6 s', 3, 'sticking_point'))
    out.append(m('Lockout elbow extension', mv.get('lockout_elbow_deg', 175),
                 f"{mv.get('lockout_elbow_deg', 175):.0f}°", '≥175°', 180, 'lockout_completion'))
    out.append(m('Eccentric tempo', mv.get('eccentric_sec', 2.2),
                 f"{mv.get('eccentric_sec', 2.2):.2f} s", '1.5–3.0 s', 8, 'eccentric_tempo'))
    out.append(m('Concentric tempo', mv.get('concentric_sec', 1.5),
                 f"{mv.get('concentric_sec', 1.5):.2f} s", '0.8–3.0 s', 8, 'mcv'))
    out.append(m('Setup time', mv.get('setup_sec', 3.5),
                 f"{mv.get('setup_sec', 3.5):.2f} s", '2–5 s', 30, 'setup_time'))
    out.append(m('Lockout hold', mv.get('lockout_hold_sec', 0.4),
                 f"{mv.get('lockout_hold_sec', 0.4):.2f} s", '≥0.5 s', 3, 'lockout_hold'))
    out.append(m('Pause duration' if mv.get('pause_sec', 0.4) > 0.1 else 'TnG quality',
                 mv.get('pause_sec', 0.4),
                 f"{mv.get('pause_sec', 0.4):.2f} s", '0.8–1.5 s', 3, 'pause_or_tng'))

    return out


def _fallback(msg):
    return build_result(
        'NEEDS IMPROVEMENT', 50,
        f'Analysis could not complete: {msg}',
        {'validReps': '0/0', 'confidence': '0%', 'sides': 'n/a',
         'cameraView': 'UNKNOWN'},
        [], [], [msg],
    )
