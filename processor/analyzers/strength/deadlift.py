"""STRENGTH — Deadlift (Conventional / Romanian).

Full rewrite per the Biomechanical Assessment Spec (compass_artifact_*.md).

Pipeline:
  1. Resolve four camera files: sagittal, frontal, posterior, oblique.
     Sagittal is the load-bearing view; oblique is a sagittal fallback when
     the strong-side hip/shoulder is occluded.
  2. Extract MediaPipe pose from each view. Track the bar on the sagittal
     view (plate-centroid → wrist-centre weighted blend, spec §12.5.3).
  3. Detect reps on the sagittal view (wrist-y / plate-y peaks for
     conventional; eccentric-first wrist-y minima for Romanian). Within each
     rep, the LIFTOFF (bar leaves the floor) and LOCKOUT (topmost point) are
     found by body extension + bar height, so every "at lockout" metric is
     measured when the lifter is standing tall — never at a bent setup frame.
  4. Compute the 32 spec metrics per rep across the four views, each scored
     into a 0–100 sub-score via linear tier-band interpolation (spec §7.1).
  5. Aggregate into Safety/Technique/Performance category scores using
     variant-specific weights (spec §7.2). Composite = geometric mean
     (S_safety^0.50 · S_tech^0.35 · S_perf^0.15, spec §7.3).
  6. Apply hard-fail safety overrides (spec §7.4); cap composite if any
     trigger.
  7. Set aggregation: mean (headline) / worst / last-3, flag deteriorating
     reps (>15 pts below mean, spec §7.5).
  8. Render annotated frames on the sagittal view (one per rep at lockout).
  9. Emit muscle-activation card (kept from existing infra).

Returns the standard ExerciseResult dict augmented with `composite_score`
(see frontend/src/data/types.ts) carrying the spec UI payload.
"""
from __future__ import annotations

import math
from statistics import mean as _mean

from utils.landmarks import (
    extract_all_landmarks, get_landmark_px, get_lm, midpoint_px, LM,
    confidence_score, landmark_quality,
)
from utils.angles import angle_3pt, multipoint_spine_curvature
from utils.rep_detection import detect_reps, detect_reps_minima
from utils.scoring import build_metric, build_result
from utils.frame_annotator import (
    extract_frame_at, frame_to_base64, render_sample_frame,
    draw_skeleton, draw_angle_arc, draw_reference_line,
    draw_callout, draw_phase_label, draw_title_strip, draw_metric_overlay,
    draw_legend, draw_valgus_callout, _lm_to_px,
    COL_CYAN,
)
from utils.bar_tracker import (
    track_bar_path, mean_concentric_velocity,
    bar_path_horizontal_drift_cm, estimate_1rm,
)
from utils.muscle_inference import infer_deadlift

DEADLIFT_CONNECTIONS = [
    (7, 11), (8, 12), (11, 12), (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
    (11, 13), (13, 15), (12, 14), (14, 16),
]

# ─────────────────────────────────────────────────────────────────────
# Spec §3-§6 — tier-band tables.
#
# Each band describes a metric's tier boundaries for ONE variant. Form:
#   one_sided  → (good_lo, good_hi) define the "Very Good" band.
#                Optional `wider` band defines "Good"; outside Good is
#                downgraded by distance.  `higher_is_better`/`lower` tells
#                the linear interpolator which direction is bad.
#   two_sided  → ideal point ± tolerances. Symmetric tent function.
#   ranged     → (good_lo, good_hi) + (yellow_lo, yellow_hi). Useful for
#                metrics like torso angle that have a high-and-low fail mode.
#   asym       → asymmetric band; the spec's "lean back vs forward" cases.
# ─────────────────────────────────────────────────────────────────────


def _interp(x, lo, hi, lo_score, hi_score):
    """Linear interpolation between (lo,lo_score) and (hi,hi_score).
    Clamps `x` to [lo, hi] and returns a score in [min(lo_score,hi_score),
    max(lo_score,hi_score)]."""
    if hi == lo:
        return lo_score
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return lo_score + t * (hi_score - lo_score)


def score_ranged(x, bands):
    """5-tier scoring for a metric with explicit band edges.

    `bands` = dict with keys 'very_good', 'good', 'yellow', 'bad'. Each is
    a tuple (lo, hi). Anything below 'bad' lo or above 'bad' hi is Very Bad.

    Returns a sub-score 0..100 with linear interpolation inside each tier:
        Very Good band → 90..100  (centre = 100, edges = 90)
        Good band      → 75..89
        Yellow         → 60..74
        Bad            → 40..59
        Very Bad       → 0..39
    """
    if x is None:
        return 0.0
    vg = bands.get('very_good')
    gd = bands.get('good')
    yl = bands.get('yellow')
    bd = bands.get('bad')

    def in_band(b):
        return b is not None and b[0] <= x <= b[1]

    def edge_score(b, top, bot):
        # Score is `top` at the band centre and `bot` at the band edges.
        c = 0.5 * (b[0] + b[1])
        half = max(1e-6, (b[1] - b[0]) / 2.0)
        d = abs(x - c) / half  # 0 at centre, 1 at edge
        return top - d * (top - bot)

    if vg and in_band(vg):
        return float(edge_score(vg, 100.0, 90.0))
    if gd and in_band(gd):
        return float(edge_score(gd, 89.0, 75.0))
    if yl and in_band(yl):
        return float(edge_score(yl, 74.0, 60.0))
    if bd and in_band(bd):
        return float(edge_score(bd, 59.0, 40.0))
    # Very Bad — interp from bad-edge distance, floor 0
    if bd:
        outside = min(abs(x - bd[0]), abs(x - bd[1]))
        span = max(1e-6, bd[1] - bd[0])
        return max(0.0, 39.0 - 39.0 * min(1.0, outside / span))
    return 0.0


def score_one_sided(x, very_good, good, yellow, bad, higher_is_better):
    """Build a 5-tier scorer from one-sided thresholds (spec §7.1).

    Anchors define the band edges:
      very_good → 90, good → 75, yellow → 60, bad → 40.
    Inside the Very Good band the score interpolates 90 → 100 (centre).
    Past the Bad edge the score interpolates 40 → 0 with one extra
    band-width of headroom (the Very Bad floor is therefore 0 once x is
    two Bad-widths past the bad threshold).
    """
    if x is None:
        return 0.0
    # Bad-side band width — defines the Very Bad decay slope.
    very_bad_width = max(1e-6, abs(bad - yellow))
    if higher_is_better:
        # Higher = better. Past `very_good` is even better → cap at 100.
        if x >= very_good:
            # Inside Very Good: interpolate centre→edge as 100→90 over the
            # range [very_good, very_good + width]. With no upper bound,
            # treat everything above very_good as full 100.
            return 100.0
        if x >= good:
            return _interp(x, good, very_good, 75.0, 90.0)
        if x >= yellow:
            return _interp(x, yellow, good, 60.0, 75.0)
        if x >= bad:
            return _interp(x, bad, yellow, 40.0, 60.0)
        # Below bad → Very Bad band, decays to 0
        floor_x = bad - very_bad_width
        return max(0.0, _interp(x, floor_x, bad, 0.0, 40.0))
    else:
        # Lower = better.
        if x <= very_good:
            return 100.0
        if x <= good:
            return _interp(x, very_good, good, 90.0, 75.0)
        if x <= yellow:
            return _interp(x, good, yellow, 75.0, 60.0)
        if x <= bad:
            return _interp(x, yellow, bad, 60.0, 40.0)
        # Above bad → Very Bad band, decays to 0 over `very_bad_width`
        ceil_x = bad + very_bad_width
        return max(0.0, _interp(x, bad, ceil_x, 40.0, 0.0))


def score_two_sided(x, ideal, tolerances):
    """Symmetric tent scoring. `tolerances` = (vg, good, yellow, bad) half-widths.
    e.g. tolerances=(3, 7, 12, 20) → ±3 = vg, ±7 = good, ±12 = yellow, ±20 = bad.
    """
    if x is None:
        return 0.0
    d = abs(x - ideal)
    return score_one_sided(d, *tolerances, higher_is_better=False)


# ─────────────────────────────────────────────────────────────────────
# Spec §7.2 — category weights (sum to 100 within each category).
# ─────────────────────────────────────────────────────────────────────

SAFETY_W = {
    'conventional': {
        'lumbar_flex': 30, 'thoracic': 10, 'hip_lockout': 12,
        'spinal_lat_dev': 10, 'knee_valgus': 10, 'hip_shoulder_timing': 13,
        'bar_drift': 10, 'heel_contact': 5,
    },
    'romanian': {
        'lumbar_flex': 35, 'thoracic': 12, 'hip_lockout': 12,
        'spinal_lat_dev': 10, 'knee_valgus': 8,
        'bar_drift': 13, 'heel_contact': 5, 'lateral_hip_shift': 5,
    },
}

TECH_W = {
    'conventional': {
        'torso_start': 15, 'knee_start': 12, 'shin_angle': 8,
        'bar_thigh_prox': 15, 'bar_path': 12, 'neck_head': 4,
        'stance_width': 8, 'foot_angle': 5, 'grip_width': 5,
        'pull_symmetry': 8, 'bar_tilt': 5, 'knee_lockout': 3,
    },
    'romanian': {
        'torso_bottom': 18, 'knee_constant': 15, 'bar_thigh_prox': 18,
        'bar_path': 10, 'neck_head': 4, 'stance_width': 8,
        'foot_angle': 5, 'grip_width': 6, 'pull_symmetry': 8,
        'bar_tilt': 5, 'rdl_rom': 3,
    },
}

PERF_W = {
    'conventional': {
        'concentric_tempo': 30, 'eccentric_tempo': 20, 'setup_time': 15,
        'lockout_hold': 15, 'consistency': 20,
    },
    'romanian': {
        'concentric_tempo': 25, 'eccentric_tempo': 35, 'setup_time': 10,
        'lockout_hold': 15, 'consistency': 15,
    },
}

CATEGORY_WEIGHTS = {'safety': 0.50, 'technique': 0.35, 'performance': 0.15}


# ─────────────────────────────────────────────────────────────────────
# Spec §7.4 — hard-fail safety overrides. `eval` returns (triggered, value_str).
# ─────────────────────────────────────────────────────────────────────

def _override_specs():
    """Return the override table (re-built each call so eval lambdas close
    over fresh state if extended later)."""
    return [
        {
            'key': 'lumbar_rounding_vb',
            'condition': 'Visible lumbar rounding (>20° deviation; Very Bad)',
            'metric': 'Lumbar flexion proxy',
            'cap': 40,
            'eval': lambda mv: (mv['lumbar_flex_dev'] > 20, f"{mv['lumbar_flex_dev']:.1f}°"),
        },
        {
            'key': 'lumbar_progressive',
            'condition': 'Progressive lumbar worsening across the set',
            'metric': 'Lumbar flexion trend',
            'cap': 30,
            # Triggers on the SET, not the rep. Set on aggregation.
            'eval': None,
        },
        {
            'key': 'bar_drift_vb',
            'condition': 'Bar drift away from body (>9% of lifter height; Very Bad)',
            'metric': 'Bar path deviation',
            'cap': 45,
            'eval': lambda mv: (mv['bar_drift_pct'] > 9.0, f"{mv['bar_drift_pct']:.1f}%"),
        },
        {
            'key': 'stripper_timing',
            'condition': 'Hip-shoulder timing R > 2.2 (stripper deadlift, conventional)',
            'metric': 'Hip-shoulder timing',
            'cap': 45,
            'eval': lambda mv: (mv.get('hip_shoulder_R') is not None and mv['hip_shoulder_R'] > 2.2,
                                f"R={mv.get('hip_shoulder_R', 0):.2f}"),
        },
        {
            'key': 'hyperextension',
            'condition': 'Hyperextension at lockout (>15° backward lean)',
            'metric': 'Torso angle at lockout',
            'cap': 50,
            'eval': lambda mv: (mv['lockout_back_lean'] > 15, f"{mv['lockout_back_lean']:.1f}° back"),
        },
        {
            'key': 'knee_valgus_vb',
            'condition': 'Knee valgus FPPA >22° at any frame',
            'metric': 'Knee FPPA',
            'cap': 50,
            'eval': lambda mv: (mv['knee_fppa_max'] > 22, f"{mv['knee_fppa_max']:.1f}°"),
        },
        {
            'key': 'heel_lift_loaded',
            'condition': 'Heel lift sustained >500 ms during loaded portion',
            'metric': 'Heel contact',
            'cap': 55,
            'eval': lambda mv: (mv['heel_lift_ms'] > 500, f"{mv['heel_lift_ms']:.0f} ms"),
        },
        {
            'key': 'pull_asymmetry',
            'condition': 'Pull asymmetry >18° L/R',
            'metric': 'Symmetry of pull',
            'cap': 55,
            'eval': lambda mv: (mv['pull_asym_deg'] > 18, f"{mv['pull_asym_deg']:.1f}°"),
        },
        {
            'key': 'lat_dev_and_tilt_bad',
            'condition': 'Spinal lateral deviation + bar tilt both in Bad+ tiers',
            'metric': 'Spinal lateral deviation × bar tilt',
            'cap': 50,
            'eval': lambda mv: (mv['spinal_lat_dev_pct'] > 7.0 and mv['bar_tilt_deg'] > 7.0,
                                f"{mv['spinal_lat_dev_pct']:.1f}% / {mv['bar_tilt_deg']:.1f}°"),
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
# ─────────────────────────────────────────────────────────────────────

def _side_idx(side='left'):
    return {
        'ear':      LM['LEFT_EAR']      if side == 'left' else LM['RIGHT_EAR'],
        'shoulder': LM['LEFT_SHOULDER'] if side == 'left' else LM['RIGHT_SHOULDER'],
        'hip':      LM['LEFT_HIP']      if side == 'left' else LM['RIGHT_HIP'],
        'knee':     LM['LEFT_KNEE']     if side == 'left' else LM['RIGHT_KNEE'],
        'ankle':    LM['LEFT_ANKLE']    if side == 'left' else LM['RIGHT_ANKLE'],
        'heel':     LM['LEFT_HEEL']     if side == 'left' else LM['RIGHT_HEEL'],
        'foot':     LM['LEFT_FOOT_INDEX'] if side == 'left' else LM['RIGHT_FOOT_INDEX'],
        'wrist':    LM['LEFT_WRIST']    if side == 'left' else LM['RIGHT_WRIST'],
    }


def _pick_camera_side(frames, w, h):
    """Pick the body side facing the camera by average z-depth (closer = lower z)."""
    lz, rz = [], []
    for f in frames:
        lm = f['landmarks']
        if lm is None:
            continue
        if lm[LM['LEFT_HIP']][2] is not None:
            lz.append(lm[LM['LEFT_HIP']][2])
        if lm[LM['RIGHT_HIP']][2] is not None:
            rz.append(lm[LM['RIGHT_HIP']][2])
    if not lz or not rz:
        return 'left'
    return 'left' if (sum(lz) / len(lz)) < (sum(rz) / len(rz)) else 'right'


def _process_sagittal(path, plate_size_kg, variant):
    """Extract pose + bar track + per-frame signals from the sagittal video."""
    data = extract_all_landmarks(path)
    frames = data['frames']
    fps = data['fps']
    w, h = data['width'], data['height']

    bar = track_bar_path(path, plate_size_kg=plate_size_kg)
    centres = bar['centres']
    px_per_cm = bar['px_per_cm']
    bar_quality = bar.get('quality', [0.0] * len(centres))
    bar_med_q = float(bar.get('median_quality', 0.0))

    side = _pick_camera_side(frames, w, h)
    idx = _side_idx(side)

    # Per-frame signals
    plate_x = [c[0] if c else None for c in centres]
    plate_y = [c[1] if c else None for c in centres]
    wrist_y, wrist_x = [], []
    hip_y, hip_x = [], []
    shoulder_y, shoulder_x = [], []
    knee_y, knee_x = [], []
    ankle_x, ankle_y = [], []
    heel_y = []
    torso_angle = []          # from horizontal; 90 = upright
    hip_angle, knee_angle = [], []
    spine_3pt = []            # legacy EAR-SHOULDER-HIP angle
    spine_curv = []           # 4-pt curvature (spec §3.10 proxy)
    cervical_angle = []
    shin_angle_vertical = []  # forward deg from vertical

    for f in frames:
        lm = f['landmarks']
        if lm is None:
            for arr in (wrist_y, wrist_x, hip_y, hip_x, shoulder_y, shoulder_x,
                        knee_y, knee_x, ankle_x, ankle_y, heel_y,
                        torso_angle, hip_angle, knee_angle, spine_3pt, spine_curv,
                        cervical_angle, shin_angle_vertical):
                arr.append(None)
            continue
        ear  = get_landmark_px(lm, idx['ear'], w, h)
        sh   = get_landmark_px(lm, idx['shoulder'], w, h)
        hp   = get_landmark_px(lm, idx['hip'], w, h)
        kn   = get_landmark_px(lm, idx['knee'], w, h)
        an   = get_landmark_px(lm, idx['ankle'], w, h)
        hl   = get_landmark_px(lm, idx['heel'], w, h)
        wr   = get_landmark_px(lm, idx['wrist'], w, h)
        smid = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
        hmid = midpoint_px(lm, LM['LEFT_HIP'], LM['RIGHT_HIP'], w, h)

        wrist_x.append(wr[0] if wr else None)
        wrist_y.append(wr[1] if wr else None)
        hip_x.append(hp[0] if hp else None)
        hip_y.append(hp[1] if hp else None)
        shoulder_x.append(sh[0] if sh else None)
        shoulder_y.append(sh[1] if sh else None)
        knee_x.append(kn[0] if kn else None)
        knee_y.append(kn[1] if kn else None)
        ankle_x.append(an[0] if an else None)
        ankle_y.append(an[1] if an else None)
        # Heel is captured only when clearly VISIBLE (vis ≥ 0.6): the plate
        # occludes the feet during the pull and MediaPipe hallucinates a
        # heel tens of px off, which read as ~0.7–1.8 s of phantom lift.
        hl_strict = get_lm(lm, idx['heel'], w, h, min_vis=0.6)
        heel_y.append(hl_strict[1] if hl_strict else None)

        # Torso angle FROM HORIZONTAL: 90 = upright, 0 = parallel
        if sh and hp:
            dx, dy = sh[0] - hp[0], hp[1] - sh[1]  # image-y goes down → flip
            torso_angle.append(math.degrees(math.atan2(dy, abs(dx) + 1e-6)))
        else:
            torso_angle.append(None)
        hip_angle.append(angle_3pt(sh, hp, kn) if (sh and hp and kn) else None)
        knee_angle.append(angle_3pt(hp, kn, an) if (hp and kn and an) else None)
        spine_3pt.append(angle_3pt(ear, smid, hmid) if (ear and smid and hmid) else None)
        spine_curv.append(multipoint_spine_curvature(ear, smid, hmid)
                          if (ear and smid and hmid) else None)
        # Cervical: EAR vs SHOULDER vertical (positive = head up)
        if ear and sh:
            dx, dy = ear[0] - sh[0], ear[1] - sh[1]
            cervical_angle.append(math.degrees(math.atan2(dx, -dy)))
        else:
            cervical_angle.append(None)
        # Shin angle from vertical: KNEE-ANKLE vector, positive forward
        if kn and an:
            dx, dy = kn[0] - an[0], an[1] - kn[1]
            shin_angle_vertical.append(math.degrees(math.atan2(dx, abs(dy) + 1e-6)))
        else:
            shin_angle_vertical.append(None)

    # Bar X with weighted blend: plate centroid (high weight when tracked)
    # + wrist X (always available). Spec §12.5.3 + user choice "Both, with weighted blend".
    #
    # Temporal continuity filter on the plate track first: spare plates
    # lying on the floor hijack the detector for single frames, teleporting
    # the "bar" sideways (this alone produced ~20 cm of phantom drift/gap).
    # A real plate cannot jump more than ~half its radius between frames.
    plate_r_px = None
    if px_per_cm and px_per_cm > 0:
        plate_r_px = 22.5 * px_per_cm          # 45 cm plate → radius in px
    last_px = None
    for i in range(len(plate_x)):
        if plate_x[i] is None:
            continue
        if last_px is not None and plate_r_px is not None and \
                abs(plate_x[i] - last_px) > 0.5 * plate_r_px:
            plate_x[i] = None
            plate_y[i] = None
            continue
        last_px = plate_x[i]

    bar_x_blend = []
    bar_y_blend = []
    for i in range(len(frames)):
        px = plate_x[i] if i < len(plate_x) else None
        py = plate_y[i] if i < len(plate_y) else None
        wx = wrist_x[i]
        wy = wrist_y[i]
        bq = bar_quality[i] if i < len(bar_quality) else 0.0
        if px is not None and wx is not None:
            # Plate tracker: blend with confidence. wq fixed at 0.4 baseline.
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
        'frames': frames, 'fps': fps, 'w': w, 'h': h,
        'side': side, 'idx': idx,
        'centres': centres, 'bar_quality': bar_quality, 'bar_med_q': bar_med_q,
        'px_per_cm': px_per_cm,
        'plate_x': plate_x, 'plate_y': plate_y,
        'bar_x': bar_x_blend, 'bar_y': bar_y_blend,
        'wrist_x': wrist_x, 'wrist_y': wrist_y,
        'hip_x': hip_x, 'hip_y': hip_y,
        'shoulder_x': shoulder_x, 'shoulder_y': shoulder_y,
        'knee_x': knee_x, 'knee_y': knee_y,
        'ankle_x': ankle_x, 'ankle_y': ankle_y, 'heel_y': heel_y,
        'torso_angle': torso_angle,
        'hip_angle': hip_angle, 'knee_angle': knee_angle,
        'spine_3pt': spine_3pt, 'spine_curv': spine_curv,
        'cervical_angle': cervical_angle,
        'shin_angle_vertical': shin_angle_vertical,
    }


def _norm_series(sig):
    """Min-max normalise a signal to [0,1] over its valid range (None-safe)."""
    vals = [v for v in sig if v is not None]
    if not vals:
        return [None] * len(sig)
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) if hi > lo else 1.0
    return [((v - lo) / rng) if v is not None else None for v in sig]


def _view_standing_and_lockout(frames, w, h):
    """Lockout (bar-at-top) frame for an auxiliary view, plus the bottom
    (setup/most-hinged) frame. Returns (combined_signal, bottom, lockout).

    Uses a BLEND of two view-independent "how locked-out is this frame" cues,
    each normalised to [0,1] and averaged, so occlusion of either one can't
    break detection:

      1. BAR / HAND HEIGHT  (−wrist_centre.y) — the hands grip the bar, which
         rises from the floor (hands lowest) to the hip at lockout (hands
         highest). This is the most direct "bar lifted to the top" signal and
         is ALWAYS in frame (hands never leave the shot).
      2. STANDING HEIGHT  (ankle_line.y − shoulder_line.y) — the lifter is
         tallest at lockout, shortest when hinged over at setup.

    Both peak at lockout and are immune to the out-of-plane hip hinge that
    makes 2D joint angles (and hip height) useless from a head-on frontal /
    posterior view. Lockout = max combined score AFTER the bottom.
    """
    bar_up, stand = [], []
    for f in frames:
        lm = f.get('landmarks')
        if lm is None:
            bar_up.append(None); stand.append(None); continue
        wr = midpoint_px(lm, LM['LEFT_WRIST'], LM['RIGHT_WRIST'], w, h)
        top = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
        if top is None:                       # fallback top marker: the head
            top = get_landmark_px(lm, LM['NOSE'], w, h)
        base = midpoint_px(lm, LM['LEFT_ANKLE'], LM['RIGHT_ANKLE'], w, h)
        if base is None:                      # fallback base marker: the heels
            base = midpoint_px(lm, LM['LEFT_HEEL'], LM['RIGHT_HEEL'], w, h)
        # image-y increases downward → higher in frame = smaller y.
        bar_up.append((-wr[1]) if wr else None)                 # hands higher = larger
        stand.append((base[1] - top[1]) if (top and base) else None)  # taller = larger

    nb, ns = _norm_series(bar_up), _norm_series(stand)
    combined = []
    for i in range(len(frames)):
        parts = [x for x in (nb[i], ns[i]) if x is not None]
        combined.append(sum(parts) / len(parts) if parts else None)

    valid = [i for i, v in enumerate(combined) if v is not None]
    if not valid:
        return combined, None, None
    bottom = min(valid, key=lambda i: combined[i])   # lowest = setup / bar on floor
    pool = [i for i in valid if i >= bottom] or valid
    lockout = max(pool, key=lambda i: combined[i])    # highest after bottom = lockout
    return combined, bottom, lockout


def _window_median(arr, center, half=3):
    """Median of `arr` in a small window around `center` (skips None). Used to
    sample an aux-view metric AT the lockout frame robustly, instead of taking
    a max across the whole clip (which includes degenerate deep-bent frames)."""
    if center is None or not arr:
        return None
    lo, hi = max(0, center - half), min(len(arr), center + half + 1)
    vals = [arr[i] for i in range(lo, hi) if arr[i] is not None]
    if not vals:
        return None
    return sorted(vals)[len(vals) // 2]


def _window_max(arr, lo, hi):
    """Max of `arr` over [lo, hi] (skips None); for worst-case tracking limited
    to the pull window so pre/post-lift and degenerate frames don't pollute."""
    if lo is None or hi is None or not arr:
        return None
    a, b = max(0, min(lo, hi)), min(len(arr), max(lo, hi) + 1)
    vals = [arr[i] for i in range(a, b) if arr[i] is not None]
    return max(vals) if vals else None


def _process_frontal(path):
    """Frontal-view metrics: stance, foot angle, grip, bar tilt, lateral
    hip shift, FPPA. Spec §4."""
    if not path:
        return None
    data = extract_all_landmarks(path)
    frames = data['frames']
    w, h = data['width'], data['height']

    stance_widths = []        # pixels
    biacromial = []           # pixels (for ratio)
    bar_tilt_deg = []         # |angle between wrists| from horizontal
    grip_widths_cm = []       # uses biacromial as cm ref via athlete height
    foot_angle_l, foot_angle_r = [], []
    hip_centre_x = []
    knee_fppa_l, knee_fppa_r = [], []
    pull_left_y, pull_right_y = [], []

    for f in frames:
        lm = f['landmarks']
        if lm is None:
            for arr in (stance_widths, biacromial, bar_tilt_deg, grip_widths_cm,
                        foot_angle_l, foot_angle_r, hip_centre_x,
                        knee_fppa_l, knee_fppa_r, pull_left_y, pull_right_y):
                arr.append(None)
            continue

        lhp = get_landmark_px(lm, LM['LEFT_HIP'], w, h)
        rhp = get_landmark_px(lm, LM['RIGHT_HIP'], w, h)
        lan = get_landmark_px(lm, LM['LEFT_ANKLE'], w, h)
        ran = get_landmark_px(lm, LM['RIGHT_ANKLE'], w, h)
        lhl = get_landmark_px(lm, LM['LEFT_HEEL'], w, h)
        rhl = get_landmark_px(lm, LM['RIGHT_HEEL'], w, h)
        ltoe = get_landmark_px(lm, LM['LEFT_FOOT_INDEX'], w, h)
        rtoe = get_landmark_px(lm, LM['RIGHT_FOOT_INDEX'], w, h)
        lsh = get_landmark_px(lm, LM['LEFT_SHOULDER'], w, h)
        rsh = get_landmark_px(lm, LM['RIGHT_SHOULDER'], w, h)
        lwr = get_landmark_px(lm, LM['LEFT_WRIST'], w, h)
        rwr = get_landmark_px(lm, LM['RIGHT_WRIST'], w, h)
        lkn = get_landmark_px(lm, LM['LEFT_KNEE'], w, h)
        rkn = get_landmark_px(lm, LM['RIGHT_KNEE'], w, h)

        stance_widths.append(abs(lan[0] - ran[0]) if (lan and ran) else None)
        biacromial.append(abs(lsh[0] - rsh[0]) if (lsh and rsh) else None)
        # Bar tilt: angle between L/R wrists
        if lwr and rwr:
            dy = lwr[1] - rwr[1]
            dx = abs(lwr[0] - rwr[0]) + 1e-6
            bar_tilt_deg.append(abs(math.degrees(math.atan2(dy, dx))))
        else:
            bar_tilt_deg.append(None)
        grip_widths_cm.append(abs(lwr[0] - rwr[0]) if (lwr and rwr) else None)
        # Foot/toe-out angle (from forward = camera direction).
        # A knee-height frontal camera foreshortens the foot's depth (y)
        # component to nearly nothing, which inflates a normal 10–15°
        # toe-out toward 60–90°. When the visible x-extent dominates, the
        # projection carries no usable angle — record unmeasurable.
        if lhl and ltoe:
            dx, dy = ltoe[0] - lhl[0], abs(ltoe[1] - lhl[1])
            foot_angle_l.append(None if abs(dx) > dy else
                                math.degrees(math.atan2(abs(dx), dy + 1e-6)))
        else:
            foot_angle_l.append(None)
        if rhl and rtoe:
            dx, dy = rtoe[0] - rhl[0], abs(rtoe[1] - rhl[1])
            foot_angle_r.append(None if abs(dx) > dy else
                                math.degrees(math.atan2(abs(dx), dy + 1e-6)))
        else:
            foot_angle_r.append(None)
        # Hip centre X (for lateral shift)
        if lhp and rhp:
            hip_centre_x.append(0.5 * (lhp[0] + rhp[0]))
        else:
            hip_centre_x.append(None)
        # FPPA = signed lateral offset of knee from hip→ankle line.
        # Approx: |knee_x - hip_x| in degrees by atan2 with thigh length.
        def _fppa(hp, kn, an):
            if not (hp and kn and an):
                return None
            # Project knee onto hip→ankle line and measure perpendicular dx
            ax, ay = an[0] - hp[0], an[1] - hp[1]
            bx, by = kn[0] - hp[0], kn[1] - hp[1]
            len2 = ax * ax + ay * ay
            if len2 < 1e-6:
                return 0.0
            t = (bx * ax + by * ay) / len2
            proj_x = ax * t
            proj_y = ay * t
            perp = math.hypot(bx - proj_x, by - proj_y)
            return math.degrees(math.atan2(perp, math.sqrt(len2)))
        knee_fppa_l.append(_fppa(lhp, lkn, lan))
        knee_fppa_r.append(_fppa(rhp, rkn, ran))
        pull_left_y.append(lsh[1] if lsh else None)
        pull_right_y.append(rsh[1] if rsh else None)

    standing, bottom_idx, lockout_idx = _view_standing_and_lockout(frames, w, h)
    return {
        'frames': frames, 'w': w, 'h': h, 'fps': data['fps'],
        'standing': standing, 'bottom_idx': bottom_idx, 'lockout_idx': lockout_idx,
        'stance_widths': stance_widths, 'biacromial': biacromial,
        'bar_tilt_deg': bar_tilt_deg, 'grip_widths_cm': grip_widths_cm,
        'foot_angle_l': foot_angle_l, 'foot_angle_r': foot_angle_r,
        'hip_centre_x': hip_centre_x,
        'knee_fppa_l': knee_fppa_l, 'knee_fppa_r': knee_fppa_r,
        'pull_left_y': pull_left_y, 'pull_right_y': pull_right_y,
    }


def _process_posterior(path):
    """Posterior-view metrics: spinal lateral deviation, shoulder/hip
    symmetry, bar tilt cross-check. Spec §5."""
    if not path:
        return None
    data = extract_all_landmarks(path)
    frames = data['frames']
    w, h = data['width'], data['height']

    spinal_lat_dev_pct = []
    shoulder_tilt_deg = []
    hip_tilt_deg = []
    bar_tilt_deg = []

    for f in frames:
        lm = f['landmarks']
        if lm is None:
            for arr in (spinal_lat_dev_pct, shoulder_tilt_deg, hip_tilt_deg, bar_tilt_deg):
                arr.append(None)
            continue
        lhp = get_landmark_px(lm, LM['LEFT_HIP'], w, h)
        rhp = get_landmark_px(lm, LM['RIGHT_HIP'], w, h)
        lsh = get_landmark_px(lm, LM['LEFT_SHOULDER'], w, h)
        rsh = get_landmark_px(lm, LM['RIGHT_SHOULDER'], w, h)
        lwr = get_landmark_px(lm, LM['LEFT_WRIST'], w, h)
        rwr = get_landmark_px(lm, LM['RIGHT_WRIST'], w, h)
        # Vertical through hip centre; offset of shoulder centre
        if lhp and rhp and lsh and rsh:
            hip_cx = 0.5 * (lhp[0] + rhp[0])
            sh_cx = 0.5 * (lsh[0] + rsh[0])
            torso_len = max(1e-6, abs(0.5 * (lsh[1] + rsh[1]) - 0.5 * (lhp[1] + rhp[1])))
            spinal_lat_dev_pct.append(abs(sh_cx - hip_cx) / torso_len * 100.0)
        else:
            spinal_lat_dev_pct.append(None)
        if lsh and rsh:
            dy = lsh[1] - rsh[1]
            dx = abs(lsh[0] - rsh[0]) + 1e-6
            shoulder_tilt_deg.append(abs(math.degrees(math.atan2(dy, dx))))
        else:
            shoulder_tilt_deg.append(None)
        if lhp and rhp:
            dy = lhp[1] - rhp[1]
            dx = abs(lhp[0] - rhp[0]) + 1e-6
            hip_tilt_deg.append(abs(math.degrees(math.atan2(dy, dx))))
        else:
            hip_tilt_deg.append(None)
        if lwr and rwr:
            dy = lwr[1] - rwr[1]
            dx = abs(lwr[0] - rwr[0]) + 1e-6
            bar_tilt_deg.append(abs(math.degrees(math.atan2(dy, dx))))
        else:
            bar_tilt_deg.append(None)

    standing, bottom_idx, lockout_idx = _view_standing_and_lockout(frames, w, h)
    return {
        'frames': frames, 'w': w, 'h': h, 'fps': data['fps'],
        'standing': standing, 'bottom_idx': bottom_idx, 'lockout_idx': lockout_idx,
        'spinal_lat_dev_pct': spinal_lat_dev_pct,
        'shoulder_tilt_deg': shoulder_tilt_deg,
        'hip_tilt_deg': hip_tilt_deg,
        'bar_tilt_deg': bar_tilt_deg,
    }


def _process_oblique(path):
    """Oblique view — used as a sagittal fallback when the primary side
    occludes (spec §1.1 row 4). Keep the pose data; we'll pick metrics
    only when the sagittal value is missing on a given rep frame."""
    if not path:
        return None
    return _process_sagittal(path, plate_size_kg=None, variant=None)


# ─────────────────────────────────────────────────────────────────────
# Rep detection (variant-aware)
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# Liftoff + lockout detection (spec §12.3 phase detection).
#
# The bar must be measured at the TOP of the pull, not at setup. Relying on
# the wrist-y peak window alone is fragile (occluded wrists / a spurious
# micro-peak can localise the "rep" to the floor). These helpers instead find
# the lockout by BODY EXTENSION — at a true lockout the hips and knees are
# provably straight — gated to where the bar is in the upper part of its
# travel, so they answer directly: "bar lifted from rest → topmost point."
# ─────────────────────────────────────────────────────────────────────

def _extension_signal(sag):
    """Per-frame body-extension signal = hip_angle + knee_angle (≈360 when
    standing locked out, ≈190 at a bent setup). None where either is missing."""
    ha, ka = sag['hip_angle'], sag['knee_angle']
    out = []
    for i in range(len(ha)):
        h, k = ha[i], ka[i]
        if h is None or k is None:
            out.append(None)
        else:
            # Cap near-straight so hyperextension noise can't inflate the score.
            out.append(min(h, 190.0) + min(k, 190.0))
    return out


def _find_liftoff(sag, start, end):
    """First frame in [start, end] where the bar has clearly left the floor —
    risen ≥15% of its in-window travel above the resting (floor) baseline."""
    bar_y = sag['bar_y']
    lo, hi = max(0, start), min(len(bar_y), end + 1)
    win = [(i, bar_y[i]) for i in range(lo, hi) if bar_y[i] is not None]
    if len(win) < 2:
        return start
    ys = [v for _, v in win]
    floor_y, top_y = max(ys), min(ys)          # image-y: floor = largest y
    rom = max(1.0, floor_y - top_y)
    thresh = floor_y - 0.15 * rom
    for i, v in win:
        if v < thresh:
            return i
    return start


def _find_lockout(sag, start, end, ceiling=None):
    """Robust lockout/top frame = maximum body extension where the bar is in
    the upper part of its travel. Searches [start, end]; if nothing there is a
    genuine lockout (hip angle never reaches ~150°), widens forward to
    `ceiling` (next rep's start / clip end) to recover the real standing frame.
    """
    ext = _extension_signal(sag)
    hip_a = sag['hip_angle']
    bar_y = sag['bar_y']
    n = len(ext)

    def _search(lo, hi):
        lo, hi = max(0, lo), min(n, hi + 1)
        win = [bar_y[i] for i in range(lo, hi)
               if i < len(bar_y) and bar_y[i] is not None]
        gate_y = None
        if win:
            floor_y, top_y = max(win), min(win)
            rom = max(1.0, floor_y - top_y)
            gate_y = top_y + 0.40 * rom          # bar must be in top 40% of travel
        best_i, best_e = None, None
        for i in range(lo, hi):
            if ext[i] is None:
                continue
            if gate_y is not None:
                by = bar_y[i] if i < len(bar_y) else None
                if by is not None and by > gate_y:
                    continue                     # bar still low → not a lockout
            if best_e is None or ext[i] > best_e:
                best_e, best_i = ext[i], i
        if best_i is None:                       # nothing passed gate → pure ext max
            cand = [(ext[i], i) for i in range(lo, hi) if ext[i] is not None]
            best_i = max(cand)[1] if cand else lo
        return best_i

    li = _search(start, end)
    # Genuine lockout must be substantially extended; else widen the search.
    if _safe_at(hip_a, li, 0.0) < 150.0 and ceiling and ceiling > end:
        li2 = _search(end, ceiling)
        if _safe_at(hip_a, li2, 0.0) > _safe_at(hip_a, li, 0.0):
            li = li2
    return li


def _detect_reps_for_variant(sag, variant, target_reps):
    """Return list of {start, peak, end, setup} frame indices per rep."""
    fps = sag['fps']
    target = target_reps or 3
    # Choose signal: wrist_y (always present), invert so up = peak.
    wy = sag['wrist_y']
    # Fill missing
    filled = []
    last = None
    for v in wy:
        if v is None:
            filled.append(last if last is not None else 0)
        else:
            filled.append(v); last = v

    if variant == 'romanian':
        # RDL: eccentric first → bar descends, then rises. Rep "peak" =
        # bar at top (wrist_y minimum in image coords). Use minima detector.
        reps = detect_reps_minima(filled, expected_reps=target, fps=fps, min_hold_sec=0.3)
    else:
        # Conventional: lockouts are peaks of -wrist_y
        inv = [-v for v in filled]
        reps = detect_reps(inv, expected_reps=target, fps=fps, min_hold_sec=0.4)

    # Trim to target count by strongest peak
    if target and len(reps) > target:
        sig = (filled if variant == 'romanian' else [-v for v in filled])
        reps = sorted(reps,
                      key=lambda r: sig[r['peak_frame']] if r['peak_frame'] < len(sig) else -1,
                      reverse=True)[:target]
        reps = sorted(reps, key=lambda r: r['peak_frame'])

    # Augment each rep with setup / liftoff / lockout frames. Lockout is found
    # by body extension + bar-height (see _find_lockout) so metrics are always
    # measured at the true top of the pull, never at a bent setup frame.
    hip_y = sag['hip_y']
    n_frames = len(sag['frames'])
    out = []
    for ri, r in enumerate(reps):
        start, peak, end = r['start_frame'], r['peak_frame'], r['end_frame']
        # Ceiling for widening the lockout search = next rep's start, else clip end.
        ceiling = reps[ri + 1]['start_frame'] if ri + 1 < len(reps) else n_frames - 1
        if variant == 'romanian':
            setup_idx = start  # bar at top, eccentric begins
            # Bottom of eccentric = wrist_y maximum within [start, end]
            bot_idx = start; bot = float('-inf')
            for fi in range(start, min(end + 1, len(filled))):
                if filled[fi] > bot:
                    bot = filled[fi]; bot_idx = fi
            # Lockout (top) = most-extended standing frame across the rep.
            lockout_idx = _find_lockout(sag, start, end, ceiling)
            liftoff_idx = bot_idx   # RDL concentric starts at the bottom
        else:
            # Conventional: setup = lowest hip (largest image-y) before the peak.
            setup_idx = start; setup_y = float('-inf')
            for fi in range(start, peak + 1):
                v = hip_y[fi] if fi < len(hip_y) else None
                if v is not None and v > setup_y:
                    setup_y = v; setup_idx = fi
            # Robust top + liftoff — "bar lifted from rest → topmost point."
            lockout_idx = _find_lockout(sag, setup_idx, end, ceiling)
            liftoff_idx = _find_liftoff(sag, setup_idx, lockout_idx)
            bot_idx = setup_idx
        out.append({
            'idx': ri + 1,
            'start': start, 'end': end,
            'setup': setup_idx, 'bottom': bot_idx,
            'liftoff': liftoff_idx, 'lockout': lockout_idx,
        })
    return out


# ─────────────────────────────────────────────────────────────────────
# Per-rep metric computation (the heart of the spec)
# ─────────────────────────────────────────────────────────────────────

def _safe_window_max(arr, lo, hi, default=0.0):
    vals = [arr[i] for i in range(max(0, lo), min(len(arr), hi + 1)) if arr[i] is not None]
    return max(vals) if vals else default


def _safe_window_min(arr, lo, hi, default=0.0):
    vals = [arr[i] for i in range(max(0, lo), min(len(arr), hi + 1)) if arr[i] is not None]
    return min(vals) if vals else default


def _safe_at(arr, idx, default=0.0):
    if 0 <= idx < len(arr) and arr[idx] is not None:
        return arr[idx]
    return default


def _compute_rep_metrics(rep, sag, front, post, obl, variant, athlete_height_cm):
    """Compute all 32 spec metric raw values for ONE rep. Returns a dict."""
    start, end = rep['start'], rep['end']
    setup_idx = rep['setup']
    lockout_idx = rep['lockout']
    bot_idx = rep['bottom']
    liftoff_idx = rep.get('liftoff', setup_idx)   # bar-off-floor frame
    fps = sag['fps']
    px_per_cm = sag['px_per_cm']

    mv = {}

    # ── §3.1 Torso angle at start (above horizontal) ──
    # Conventional: at setup_idx. RDL: at bot_idx (bottom of eccentric).
    eval_frame = bot_idx if variant == 'romanian' else setup_idx
    mv['torso_start_deg'] = _safe_at(sag['torso_angle'], eval_frame, 90.0)
    # Spec: 0 = horizontal, 90 = upright. Torso ANGLE ABOVE HORIZONTAL.

    # ── §3.2 Torso angle at lockout (deviation from vertical) ──
    torso_lock = _safe_at(sag['torso_angle'], lockout_idx, 90.0)
    lockout_forward = max(0.0, 90.0 - torso_lock)   # forward lean degrees
    lockout_back = max(0.0, torso_lock - 90.0)       # backward lean degrees
    mv['lockout_forward_lean'] = lockout_forward
    mv['lockout_back_lean'] = lockout_back

    # ── §3.3 Bar path horizontal drift (% of lifter height) ──
    # Use blended bar_x. Lifter height proxy: pixel distance from foot to nose
    # at standing/lockout frame. Falls back to torso × 2.5.
    # Reference = MEDIAN bar_x around liftoff (a single setup frame — often
    # frame 0, before MediaPipe tracking stabilises — was a 45 px outlier),
    # and the window is liftoff→lockout: after lockout the bar is dropped
    # and the wrist-blended signal follows the empty hands (that alone
    # produced a 21.7% "drift" on a vertical pull).
    bar_x = sag['bar_x']
    h_px = _estimate_lifter_height_px(sag, lockout_idx, athlete_height_cm)
    ref_win = [bar_x[fi] for fi in range(liftoff_idx,
                                         min(liftoff_idx + 5, len(bar_x)))
               if bar_x[fi] is not None]
    ref_bar_x = sorted(ref_win)[len(ref_win) // 2] if ref_win else None
    drift_max_px = 0.0
    if ref_bar_x is not None:
        for fi in range(liftoff_idx, min(lockout_idx + 1, len(bar_x))):
            v = bar_x[fi]
            if v is not None:
                drift_max_px = max(drift_max_px, abs(v - ref_bar_x))
    mv['bar_drift_pct'] = (drift_max_px / max(1e-6, h_px)) * 100.0

    # ── §3.4 Bar-to-shin distance at start (conventional only) ──
    if variant == 'conventional' and px_per_cm > 0:
        ankle_x_s = _safe_at(sag['ankle_x'], setup_idx, None)
        bar_x_s = bar_x[setup_idx] if setup_idx < len(bar_x) else None
        if ankle_x_s and bar_x_s is not None:
            mv['bar_to_shin_cm'] = abs(bar_x_s - ankle_x_s) / px_per_cm
        else:
            mv['bar_to_shin_cm'] = 3.0  # default to Very Good band centre
    else:
        mv['bar_to_shin_cm'] = None

    # ── §3.5 Bar-to-thigh proximity (max gap during pull) ──
    # Gap = horizontal distance from the bar to the LEG PROFILE AT THE
    # BAR'S HEIGHT (ankle→knee segment below the knee, knee→hip above).
    # Comparing against the thigh midpoint X measured hip-hinge geometry,
    # not bar proximity — at setup the thigh centre is legitimately ~25 cm
    # behind a bar that is touching the shins.
    if px_per_cm > 0:
        bar_y = sag.get('bar_y') or [None] * len(bar_x)

        def _leg_gap_cm(fi):
            bx = bar_x[fi]
            by = bar_y[fi] if fi < len(bar_y) else None
            hx, hy = sag['hip_x'][fi], sag['hip_y'][fi]
            kx, ky = sag['knee_x'][fi], sag['knee_y'][fi]
            ax, ay = sag['ankle_x'][fi], sag['ankle_y'][fi]
            if bx is None or hx is None or kx is None or ax is None:
                return None
            if by is not None and ky is not None and ay is not None and hy is not None:
                # Interpolate the leg profile x at the bar's height
                if by >= ky:      # bar below knee → shin segment
                    y0, x0, y1, x1 = ay, ax, ky, kx
                else:             # bar above knee → thigh segment
                    y0, x0, y1, x1 = ky, kx, hy, hx
                t = 0.0 if abs(y1 - y0) < 1e-6 else (by - y0) / (y1 - y0)
                t = min(1.0, max(0.0, t))
                leg_x = x0 + t * (x1 - x0)
            else:
                leg_x = 0.5 * (hx + kx)
            return abs(bx - leg_x) / px_per_cm

        # PARALLAX correction: the plate face sits ~40 cm nearer the camera
        # than the lifter's sagittal plane, so even a bar dragging up the
        # thighs shows a constant apparent offset (≈7 cm in the sample).
        # The offset at lockout — where the bar is ON the thighs — IS that
        # parallax; subtract it. Measured over the knee→lockout phase (the
        # "thigh proximity" the spec names); below the knee the offset also
        # varies with bar height, making it unusable.
        knee_pass_fi = None
        knee_margin_px = (px_per_cm * 5.0) if px_per_cm > 0 else 20.0
        for fi in range(liftoff_idx, min(lockout_idx + 1, len(bar_x))):
            by = bar_y[fi] if fi < len(bar_y) else None
            ky = sag['knee_y'][fi] if fi < len(sag['knee_y']) else None
            # Require the bar clearly above the knee (5 cm margin) — right
            # at the crossing the parallax is still height-dependent.
            if by is not None and ky is not None and by <= ky - knee_margin_px:
                knee_pass_fi = fi
                break
        if knee_pass_fi is None:
            knee_pass_fi = liftoff_idx
        ref_gaps = sorted(g for g in
                          (_leg_gap_cm(fi) for fi in
                           range(max(knee_pass_fi, lockout_idx - 5), lockout_idx + 1))
                          if g is not None)
        parallax_cm = ref_gaps[len(ref_gaps) // 2] if ref_gaps else 0.0
        max_gap_cm = 0.0
        for fi in range(knee_pass_fi, min(lockout_idx + 1, len(bar_x))):
            g = _leg_gap_cm(fi)
            if g is not None:
                max_gap_cm = max(max_gap_cm, max(0.0, g - parallax_cm))
        mv['bar_thigh_gap_cm'] = max_gap_cm
    else:
        mv['bar_thigh_gap_cm'] = 2.0

    # ── §3.6 Hip-shoulder timing R (conventional only, floor→knee phase) ──
    # Measured from LIFTOFF to the frame where the bar reaches knee height.
    # Short fixed windows (100–200 ms) sample either pre-pull stillness
    # (noise ratios like 1.92) or the torso's rotational dynamics right at
    # the break (shoulders momentarily outpace hips → 0.27); the floor-to-
    # knee phase is what "hips shooting up early" is actually about.
    if variant == 'conventional':
        bar_y_arr = sag.get('bar_y') or []
        knee_pass = None
        for fi in range(liftoff_idx, min(lockout_idx + 1, len(bar_y_arr))):
            by = bar_y_arr[fi]
            ky = sag['knee_y'][fi] if fi < len(sag['knee_y']) else None
            if by is not None and ky is not None and by <= ky:
                knee_pass = fi
                break
        b = knee_pass if knee_pass is not None else \
            min(liftoff_idx + max(2, int(fps * 0.4)), len(sag['hip_y']) - 1)
        a = liftoff_idx
        d_hip = _safe_at(sag['hip_y'], a) - _safe_at(sag['hip_y'], b)
        d_sh = _safe_at(sag['shoulder_y'], a) - _safe_at(sag['shoulder_y'], b)
        # Require real movement before computing a ratio (≥ 1% of height)
        if abs(d_sh) > max(2.0, 0.01 * h_px):
            mv['hip_shoulder_R'] = abs(d_hip / d_sh)
        else:
            mv['hip_shoulder_R'] = 1.0
    else:
        mv['hip_shoulder_R'] = None

    # ── §3.7 Knee flexion at start (conventional) ──
    mv['knee_start_deg'] = _safe_at(sag['knee_angle'], setup_idx, 122.0)
    # ── §3.8 Knee flexion at bottom of RDL ──
    if variant == 'romanian':
        kn_at_bottom = _safe_at(sag['knee_angle'], bot_idx, 165.0)
        mv['rdl_knee_flex_deg'] = max(0.0, 180.0 - kn_at_bottom)
    else:
        mv['rdl_knee_flex_deg'] = None

    # ── §3.9 Shin angle from vertical at start (conventional) ──
    mv['shin_angle_deg'] = _safe_at(sag['shin_angle_vertical'], setup_idx, 10.0)

    # ── §3.10 Lumbar flexion deviation ──
    # DYNAMIC spine rounding: increase of the 4-point spine curvature over
    # its setup baseline during the pull. The old shoulder-hip-knee proxy
    # changed 10–16° on a rigid spine purely because the knees extend
    # faster than the hips early in every pull — it measured joint
    # sequencing, not lumbar flexion.
    ref_win = [sag['spine_curv'][fi] for fi in
               range(setup_idx, min(setup_idx + 5, len(sag['spine_curv'])))
               if sag['spine_curv'][fi] is not None]
    ref_curv = sorted(ref_win)[len(ref_win) // 2] if ref_win else 0.0
    worst_delta = 0.0
    for fi in range(liftoff_idx, min(lockout_idx + 1, len(sag['spine_curv']))):
        v = sag['spine_curv'][fi]
        if v is not None:
            worst_delta = max(worst_delta, v - ref_curv)
    mv['lumbar_flex_dev'] = max(0.0, worst_delta)

    # ── §3.11 Thoracic spine position (kyphosis proxy) ──
    # Use the spine 4-pt curvature peak (higher = more bent).
    curv_max = 0.0
    for fi in range(setup_idx, min(lockout_idx + 1, len(sag['spine_curv']))):
        v = sag['spine_curv'][fi]
        if v is not None:
            curv_max = max(curv_max, v)
    mv['thoracic_curv_deg'] = curv_max

    # ── §3.12 Neck / head position (cervical, worst deviation during rep) ──
    # Deviation is measured against the athlete's own NEUTRAL head carriage
    # (the value at lockout, standing tall). The raw ear-shoulder angle has
    # a constant anatomical offset (~20° with the ear forward of the
    # shoulder) that made a neutral head read as a 62° fault.
    neutral_win = [sag['cervical_angle'][fi] for fi in
                   range(max(0, lockout_idx - 2),
                         min(lockout_idx + 3, len(sag['cervical_angle'])))
                   if sag['cervical_angle'][fi] is not None]
    neutral_cerv = sorted(neutral_win)[len(neutral_win) // 2] if neutral_win else 0.0
    cervical_worst = 0.0
    for fi in range(liftoff_idx, min(lockout_idx + 1, len(sag['cervical_angle']))):
        v = sag['cervical_angle'][fi]
        if v is not None:
            cervical_worst = max(cervical_worst, abs(v - neutral_cerv))
    mv['cervical_dev_deg'] = cervical_worst

    # ── §3.13 Hip extension at lockout ──
    mv['hip_lockout_deg'] = _safe_at(sag['hip_angle'], lockout_idx, 178.0)

    # ── §3.14 Knee extension at lockout ──
    mv['knee_lockout_deg'] = _safe_at(sag['knee_angle'], lockout_idx, 178.0)

    # ── §3.15 Heel contact (max sustained heel lift in ms) ──
    # Floor reference = 85th percentile of heel Y (its planted position).
    # The heel is only trustworthy when the plate is NOT in front of it:
    # while the bar is below knee height the plate occludes the foot and
    # MediaPipe drags the "heel" upward with it (an 11 cm excursion during
    # the pull of the sample video — physically impossible). So the check
    # runs where the bar is above the knee, plus an artifact cap: a real
    # heel lift is ≤ ~6 cm; anything larger is landmark failure, not form.
    heel_y_arr = sag['heel_y']
    bar_y_arr2 = sag.get('bar_y') or []
    valid_heels = sorted(v for v in heel_y_arr if v is not None)
    floor_y = valid_heels[int(len(valid_heels) * 0.85)] if valid_heels else 0.0
    lift_threshold_px = max(2.0, (px_per_cm * 1.5) if px_per_cm > 0 else 4.0)
    artifact_cap_px = (px_per_cm * 6.0) if px_per_cm > 0 else 40.0
    lift_run = 0
    longest_run = 0
    for fi in range(liftoff_idx, min(lockout_idx + 1, len(heel_y_arr))):
        v = heel_y_arr[fi]
        by = bar_y_arr2[fi] if fi < len(bar_y_arr2) else None
        ky = sag['knee_y'][fi] if fi < len(sag['knee_y']) else None
        occluded = (by is not None and ky is not None and by > ky)
        if occluded or v is None:
            lift_run = 0
            continue
        lift_px = floor_y - v
        if lift_threshold_px < lift_px <= artifact_cap_px:
            lift_run += 1
            longest_run = max(longest_run, lift_run)
        else:
            lift_run = 0
    mv['heel_lift_ms'] = (longest_run / fps) * 1000.0 if fps > 0 else 0.0

    # ── §3.16 RDL ROM (lowest bar height vs top) ──
    if variant == 'romanian':
        wy = sag['wrist_y']
        top_y = _safe_at(wy, setup_idx, 0.0)
        bot_y = _safe_at(wy, bot_idx, 0.0)
        # Larger image-y = lower bar. Spec wants mid-shin descent.
        rom_px = max(0.0, bot_y - top_y)
        mv['rdl_rom_pct'] = (rom_px / max(1e-6, h_px)) * 100.0
    else:
        mv['rdl_rom_pct'] = None

    # ── §4 Frontal-view metrics ──
    # Continuous "worst-case" metrics (bar tilt, FPPA, hip shift, pull sym) are
    # tracked over the frontal view's OWN pull window [bottom → lockout] so that
    # pre/post-lift frames and the degenerate deep-bent setup don't pollute
    # them. Setup-stable metrics (stance, foot, grip) use a robust median.
    if front:
        f_bot = front.get('bottom_idx')
        f_lk = front.get('lockout_idx')
        # Frontal-view frame indices don't align 1:1 with sagittal; use median.
        sw_vals = [v for v in front['stance_widths'] if v is not None]
        bi_vals = [v for v in front['biacromial'] if v is not None]
        sw = sorted(sw_vals)[len(sw_vals) // 2] if sw_vals else 0.0
        bi = sorted(bi_vals)[len(bi_vals) // 2] if bi_vals else 1.0
        mv['stance_pct_biacromial'] = (sw / bi * 100.0) if bi > 0 else 95.0
        # Foot/toe angle (average left/right, then asymmetry). None when the
        # camera projection made it unmeasurable for every frame.
        fl = [v for v in front['foot_angle_l'] if v is not None]
        fr = [v for v in front['foot_angle_r'] if v is not None]
        if fl or fr:
            avg_l = (sum(fl) / len(fl)) if fl else 12.0
            avg_r = (sum(fr) / len(fr)) if fr else 12.0
            mv['foot_angle_deg'] = (avg_l + avg_r) / 2.0
            mv['foot_angle_asym_deg'] = abs(avg_l - avg_r)
        else:
            mv['foot_angle_deg'] = None
            mv['foot_angle_asym_deg'] = None
        # Grip width (cm if px_per_cm available, else ratio to biacromial)
        gw_vals = [v for v in front['grip_widths_cm'] if v is not None]
        if gw_vals and px_per_cm > 0:
            mv['grip_width_cm'] = (sum(gw_vals) / len(gw_vals)) / px_per_cm
        else:
            # Ratio: 1.0 ≈ at biacromial; spec wants slightly outside thighs
            mv['grip_width_cm'] = 55.0  # default centre
        # Pull window bounds (fall back to whole clip if not resolvable).
        w_lo = f_bot if f_bot is not None else 0
        w_hi = f_lk if f_lk is not None else len(front['bar_tilt_deg']) - 1
        # Bar tilt (worst within the pull)
        mv['bar_tilt_deg'] = _window_max(front['bar_tilt_deg'], w_lo, w_hi) or 0.0
        # Lateral hip shift (% of stance width) — range within the pull window
        hx_win = [front['hip_centre_x'][i]
                  for i in range(max(0, min(w_lo, w_hi)),
                                 min(len(front['hip_centre_x']), max(w_lo, w_hi) + 1))
                  if front['hip_centre_x'][i] is not None]
        if hx_win and sw > 0:
            mv['lateral_hip_shift_pct'] = (max(hx_win) - min(hx_win)) / sw * 100.0
        else:
            mv['lateral_hip_shift_pct'] = 0.0
        # FPPA (worst across both knees, within the pull)
        worst_l = _window_max(front['knee_fppa_l'], w_lo, w_hi) or 0.0
        worst_r = _window_max(front['knee_fppa_r'], w_lo, w_hi) or 0.0
        mv['knee_fppa_max'] = max(worst_l, worst_r)
        # Pull symmetry: timing diff between L/R shoulder reaching peak
        ply, pry = front['pull_left_y'], front['pull_right_y']
        if ply and pry:
            l_peak_fi = _arg_min([v if v is not None else float('inf') for v in ply])
            r_peak_fi = _arg_min([v if v is not None else float('inf') for v in pry])
            fps_f = front.get('fps', fps)
            mv['pull_asym_ms'] = abs(l_peak_fi - r_peak_fi) / fps_f * 1000.0 if fps_f > 0 else 0.0
        else:
            mv['pull_asym_ms'] = 0.0
        # Angular pull-symmetry: max L/R shoulder-y diff within the pull window
        diff_max = 0.0
        for i in range(max(0, min(w_lo, w_hi)), min(len(ply), max(w_lo, w_hi) + 1)):
            if i < len(pry) and ply[i] is not None and pry[i] is not None:
                diff_max = max(diff_max, abs(ply[i] - pry[i]))
        if bi > 0:
            mv['pull_asym_deg'] = math.degrees(math.atan2(diff_max, bi))
        else:
            mv['pull_asym_deg'] = 0.0
    else:
        mv.update({
            'stance_pct_biacromial': 95.0, 'foot_angle_deg': 12.0,
            'foot_angle_asym_deg': 0.0, 'grip_width_cm': 55.0,
            'bar_tilt_deg': 0.0, 'lateral_hip_shift_pct': 0.0,
            'knee_fppa_max': 0.0, 'pull_asym_ms': 0.0, 'pull_asym_deg': 0.0,
        })

    # ── §5 Posterior-view metrics ──
    # Measured AT the posterior view's own lockout (standing) frame, not as a
    # max across the whole clip. During the deep-bent setup the torso is near
    # horizontal, which collapses the spinal-deviation denominator (torso
    # length) and produces absurd values (e.g. 760%). Sampling at lockout —
    # the extreme standing position — is both correct and what the spec's
    # alignment/symmetry metrics intend.
    if post:
        plk = post.get('lockout_idx')
        sld = _window_median(post['spinal_lat_dev_pct'], plk)
        mv['spinal_lat_dev_pct'] = sld if sld is not None else 2.5
        st = _window_median(post['shoulder_tilt_deg'], plk)
        mv['shoulder_tilt_deg'] = st if st is not None else 2.0
        ht = _window_median(post['hip_tilt_deg'], plk)
        mv['hip_tilt_deg'] = ht if ht is not None else 2.0
    else:
        mv['spinal_lat_dev_pct'] = 2.5
        mv['shoulder_tilt_deg'] = 2.0
        mv['hip_tilt_deg'] = 2.0

    # ── §6 Tempo / control / velocity ──
    # Concentric is measured from LIFTOFF (bar leaves the floor) to lockout —
    # spec §6.2 "floor to lockout" — not from the static setup hold.
    mv['concentric_sec'] = max(0.0, (lockout_idx - liftoff_idx) / fps) if fps > 0 else 2.0
    mv['eccentric_sec'] = max(0.0, (end - lockout_idx) / fps) if fps > 0 else 2.0
    # Setup time = first detected stationary stretch before setup_idx (cap 30 s).
    # When the clip starts essentially AT the setup (trimmed demo video),
    # there is nothing to measure — record None so it isn't scored as a
    # rushed 0.5 s setup.
    if start <= 2 and (setup_idx - start) / max(fps, 1e-6) < 1.0:
        mv['setup_sec'] = None
    else:
        mv['setup_sec'] = max(0.5, (setup_idx - start) / fps) if fps > 0 else 3.0
    # Lockout hold = post-peak stationary stretch (look at hip_y stillness)
    hold_run = 0
    hip_y = sag['hip_y']
    for fi in range(lockout_idx, min(end + 1, len(hip_y))):
        if hip_y[fi] is not None and abs(hip_y[fi] - hip_y[lockout_idx]) < 6.0:
            hold_run += 1
        else:
            break
    mv['lockout_hold_sec'] = hold_run / fps if fps > 0 else 0.4
    # MCV (bar speed) over the true concentric window (liftoff → lockout).
    mv['mcv_mps'] = mean_concentric_velocity(
        sag['centres'], liftoff_idx, lockout_idx, fps, px_per_cm
    ) if px_per_cm > 0 else 0.4

    return mv


def _arg_min(arr):
    m, mi = float('inf'), 0
    for i, v in enumerate(arr):
        if v < m:
            m, mi = v, i
    return mi


def _estimate_lifter_height_px(sag, frame_idx, athlete_height_cm):
    """Estimate lifter pixel height. Prefer foot-to-nose at the given frame
    (lockout/standing). Fallback: torso × 2.5."""
    frames = sag['frames']
    w, h = sag['w'], sag['h']
    if 0 <= frame_idx < len(frames):
        lm = frames[frame_idx]['landmarks']
        if lm is not None:
            nose = get_landmark_px(lm, LM['NOSE'], w, h)
            ankle = get_landmark_px(lm, LM['LEFT_ANKLE'], w, h) or \
                    get_landmark_px(lm, LM['RIGHT_ANKLE'], w, h)
            if nose and ankle:
                return abs(ankle[1] - nose[1])
    # Fallback: torso × 2.5
    hp = sag['hip_y'][frame_idx] if frame_idx < len(sag['hip_y']) else None
    sh = sag['shoulder_y'][frame_idx] if frame_idx < len(sag['shoulder_y']) else None
    if hp is not None and sh is not None:
        return abs(hp - sh) * 2.5
    return float(sag['h']) * 0.7


# ─────────────────────────────────────────────────────────────────────
# Sub-scoring per metric (spec §3-§6 tier bands)
# ─────────────────────────────────────────────────────────────────────

def _score_all(mv, variant):
    """Map raw metric values → per-metric sub-scores (0..100). Returns dict
    keyed by the internal metric slug used in the weight tables."""
    s = {}

    # — Safety —
    # Lumbar flexion (deviation in degrees; lower = better)
    s['lumbar_flex'] = score_one_sided(mv['lumbar_flex_dev'], 3, 7, 12, 20, higher_is_better=False)
    # Thoracic kyphosis (curvature deg; lower = better; vg<=5, good<=10, yellow<=20, bad<=30)
    s['thoracic'] = score_one_sided(mv['thoracic_curv_deg'], 5, 10, 20, 30, higher_is_better=False)
    # Hip extension at lockout — tent around 178°, tolerances per spec §3.13
    s['hip_lockout'] = score_two_sided(mv['hip_lockout_deg'], 178.0, (4, 8, 13, 23))
    # Spinal lateral deviation (%) — lower=better; vg<2, good<4, yellow<7, bad<11
    s['spinal_lat_dev'] = score_one_sided(mv['spinal_lat_dev_pct'], 2, 4, 7, 11, higher_is_better=False)
    # Knee valgus (FPPA deg)
    s['knee_valgus'] = score_one_sided(mv['knee_fppa_max'], 5, 10, 15, 22, higher_is_better=False)
    # Hip-shoulder timing R (conventional only)
    if variant == 'conventional':
        R = mv.get('hip_shoulder_R') or 1.0
        s['hip_shoulder_timing'] = score_two_sided(R, 1.0, (0.1, 0.3, 0.6, 1.2))
    # Bar drift (% of lifter height)
    s['bar_drift'] = score_one_sided(mv['bar_drift_pct'], 2, 4, 6, 9, higher_is_better=False)
    # Heel contact — fraction of rep on floor; convert lift_ms back
    # We score the max sustained heel lift in ms: vg<=0, good<=200, yellow<=500, bad>500
    s['heel_contact'] = score_one_sided(mv['heel_lift_ms'], 50, 200, 500, 1000, higher_is_better=False)
    if variant == 'romanian':
        s['lateral_hip_shift'] = score_one_sided(mv['lateral_hip_shift_pct'], 3, 6, 10, 15, higher_is_better=False)

    # — Technique —
    # Torso angle at start (conv) or at bottom (RDL)
    if variant == 'conventional':
        # Spec: vg 20-35°. tent at 27.5° ± 7.5, 12.5, 17.5, 27.5
        s['torso_start'] = score_two_sided(mv['torso_start_deg'], 27.5, (7.5, 12.5, 17.5, 27.5))
        s['knee_start'] = score_two_sided(mv['knee_start_deg'], 122.5, (7.5, 12.5, 17.5, 27.5))
        s['shin_angle'] = score_two_sided(mv['shin_angle_deg'], 10.0, (5, 10, 18, 25))
        s['knee_lockout'] = score_two_sided(mv['knee_lockout_deg'], 178.5, (3.5, 8.5, 13.5, 23.5))
    else:
        # RDL: vg 5-25° above horizontal — tent at 15° ± 10, 15, 25, 35
        s['torso_bottom'] = score_two_sided(mv['torso_start_deg'], 15.0, (10, 15, 25, 35))
        # Constant knee bend — tent at 20° flexion ± 5, 10, 17.5, 27.5
        s['knee_constant'] = score_two_sided(mv['rdl_knee_flex_deg'], 20.0, (5, 10, 17.5, 27.5))
        s['rdl_rom'] = score_one_sided(mv['rdl_rom_pct'], 35, 30, 20, 10, higher_is_better=True)
    # Bar-to-thigh proximity (gap cm; lower=better)
    s['bar_thigh_prox'] = score_one_sided(mv['bar_thigh_gap_cm'], 1, 4, 8, 12, higher_is_better=False)
    # Bar path drift (same as safety but scored at tighter band for technique)
    s['bar_path'] = score_one_sided(mv['bar_drift_pct'], 2, 4, 6, 9, higher_is_better=False)
    # Neck/head: cervical_dev_deg (lower=better)
    s['neck_head'] = score_one_sided(mv['cervical_dev_deg'], 5, 10, 20, 35, higher_is_better=False)
    # Stance width % biacromial — tent at 95% ± 15, 25, 45, 75
    s['stance_width'] = score_two_sided(mv['stance_pct_biacromial'], 95.0, (15, 25, 45, 75))
    # Foot angle — tent at 11° ± 4, 11, 19, 29 (None = unmeasurable)
    s['foot_angle'] = (score_two_sided(mv['foot_angle_deg'], 11.0, (4, 11, 19, 29))
                       if mv.get('foot_angle_deg') is not None else None)
    # Grip width — accept anything reasonable; tent at 55 cm ± 8, 15, 22, 35
    s['grip_width'] = score_two_sided(mv['grip_width_cm'], 55.0, (8, 15, 22, 35))
    # Pull symmetry (deg)
    s['pull_symmetry'] = score_one_sided(mv['pull_asym_deg'], 2, 5, 10, 18, higher_is_better=False)
    # Bar tilt (deg)
    s['bar_tilt'] = score_one_sided(mv['bar_tilt_deg'], 2, 4, 7, 12, higher_is_better=False)

    # — Performance —
    # Concentric tempo (conv: vg 1.0-2.5s) → tent at 1.75 ± 0.75, 1.75, 3.25, 6.25
    if variant == 'conventional':
        s['concentric_tempo'] = score_two_sided(mv['concentric_sec'], 1.75, (0.75, 1.75, 3.25, 6.25))
        # Eccentric tempo: vg 1.5-3.0
        s['eccentric_tempo'] = score_two_sided(mv['eccentric_sec'], 2.25, (0.75, 1.75, 3.25, 5.0))
    else:
        # RDL concentric 1-2s ideal
        s['concentric_tempo'] = score_two_sided(mv['concentric_sec'], 1.5, (0.5, 1.25, 2.5, 4.5))
        # RDL eccentric 2-4s ideal (the defining quality)
        s['eccentric_tempo'] = score_two_sided(mv['eccentric_sec'], 3.0, (1.0, 1.75, 3.0, 5.0))
    # Setup time — unmeasurable (None) when the clip starts at the pull
    s['setup_time'] = (score_two_sided(mv['setup_sec'], 3.5, (1.5, 2.5, 5.5, 14.0))
                       if mv.get('setup_sec') is not None else None)
    # Lockout hold (s)
    s['lockout_hold'] = score_one_sided(mv['lockout_hold_sec'], 0.5, 0.3, 0.15, 0.0, higher_is_better=True)
    # Consistency (CV%) — caller fills this in once we have per-rep values
    s['consistency'] = 80.0  # placeholder; overwritten in aggregation

    return s


def _category_scores(sub_scores, variant):
    """Apply weights → category sub-scores S_safety, S_technique, S_performance."""
    def _weighted(group):
        weights = {
            'safety': SAFETY_W[variant],
            'technique': TECH_W[variant],
            'performance': PERF_W[variant],
        }[group]
        total_w = sum(weights.values())
        if total_w <= 0:
            return 50.0
        acc = 0.0
        used_w = 0.0
        for key, w in weights.items():
            v = sub_scores.get(key)
            if v is None:
                continue
            acc += w * float(v)
            used_w += w
        return acc / used_w if used_w > 0 else 50.0

    return {
        'safety': _weighted('safety'),
        'technique': _weighted('technique'),
        'performance': _weighted('performance'),
    }


def _geometric_composite(cat):
    """Spec §7.3 geometric mean: S_safety^0.50 · S_tech^0.35 · S_perf^0.15."""
    s = max(1e-3, cat['safety'])
    t = max(1e-3, cat['technique'])
    p = max(1e-3, cat['performance'])
    return (s ** CATEGORY_WEIGHTS['safety']) * \
           (t ** CATEGORY_WEIGHTS['technique']) * \
           (p ** CATEGORY_WEIGHTS['performance'])


# ─────────────────────────────────────────────────────────────────────
# Corrective cues — plain-language coaching for the two lowest sub-scores.
# Spec §11.4: "always surface the reason behind the grade".
# ─────────────────────────────────────────────────────────────────────

CUE_TEMPLATES = {
    'lumbar_flex': (
        "Lumbar flexion proxy",
        "Reset before pulling: chest up, brace harder, draw the slack out of "
        "the bar. Drop 10% load for one session and re-pattern with a neutral spine."),
    'thoracic': (
        "Thoracic spine position",
        "Pull your shoulders back and \"bend the bar around your hips\" to "
        "wake up the lats; that locks the thoracic out."),
    'hip_lockout': (
        "Hip extension at lockout",
        "Squeeze the glutes hard at the top — stop the moment ribs are stacked "
        "over the pelvis; don't lean back."),
    'spinal_lat_dev': (
        "Spinal lateral deviation",
        "Set up with weight evenly on both feet. If one side keeps lagging, "
        "check grip width and foot symmetry on the warm-up sets."),
    'knee_valgus': (
        "Knee valgus (FPPA)",
        "Drive your knees out over your 2nd-3rd toe on the way up. Add hip "
        "abduction work (lateral band walks) to your warm-up."),
    'hip_shoulder_timing': (
        "Hip-shoulder timing (\"stripper\")",
        "Sit back into the start; lats engaged; \"leg-press the floor away\" "
        "rather than hinging early. Consider lowering hips ~5 cm in setup."),
    'bar_drift': (
        "Bar path drift",
        "Engage your lats — think \"protect your armpits\" — to keep the bar "
        "tracking against your body. Bar should drag the shins/thighs."),
    'heel_contact': (
        "Heel contact",
        "Spread the floor with your feet and weight your heels. If shoes have "
        "compressible soles, switch to flat-soled lifters."),
    'lateral_hip_shift': (
        "Lateral hip shift (RDL)",
        "Setup with feet square. If one hip keeps drifting, single-leg RDL "
        "work for 2-3 weeks to address the imbalance."),
    'torso_start': (
        "Torso angle at start",
        "Bar over mid-foot; hips slightly higher than the knees. Avoid "
        "squatting the deadlift (too vertical) or stiff-legging it (too flat)."),
    'torso_bottom': (
        "Torso angle at bottom (RDL)",
        "Hinge until hamstrings tell you to stop — don't chase floor depth. "
        "Spine stays neutral; that's the rep end, not a lower target."),
    'knee_start': (
        "Knee flexion at start",
        "Sit hips slightly higher; knees ~120-125° (Escamilla 2000 averaged 124°)."),
    'knee_constant': (
        "Constant knee bend (RDL)",
        "Set knees to ~15-20° flexion at the top and HOLD that angle. Knees "
        "don't extend or further flex during the RDL."),
    'shin_angle': (
        "Shin angle",
        "Shins ~10-12° forward of vertical at the start (Escamilla 2000). "
        "Knees over the bar but not past it."),
    'knee_lockout': (
        "Knee extension at lockout",
        "Lock the knees fully at the top — \"long legs\". Soft-knee finishes "
        "cost points and look unfinished."),
    'rdl_rom': (
        "Range of motion (RDL)",
        "Aim for the bar to descend to mid-shin / just below the knee. If "
        "hamstrings shut you down higher, add daily hamstring stretching."),
    'bar_thigh_prox': (
        "Bar-to-thigh proximity",
        "Drag the bar up the legs. If the bar orbits forward, your lats are "
        "off — fix that on the next rep."),
    'bar_path': (
        "Bar path",
        "Bar travels in a vertical line over mid-foot. Drift means the lats "
        "let go; reset and retry lighter."),
    'neck_head': (
        "Neck / head",
        "Eyes on a spot 3-5 m ahead. No chin tuck, no stargazing — the neck "
        "follows the torso line."),
    'stance_width': (
        "Stance width",
        "Hip-width (or just narrower) — about 80-110% of your biacromial "
        "(shoulder) width."),
    'foot_angle': (
        "Foot / toe angle",
        "Toes ~7-15° out, symmetric L/R. Pigeon-toed or extreme flare both "
        "cost you stability."),
    'grip_width': (
        "Grip width",
        "Hands just outside your thighs, arms hanging vertically. If your "
        "hands collide with your knees, widen by 1 cm at a time."),
    'pull_symmetry': (
        "Symmetry of pull",
        "If one side rises faster, check grip evenness and foot pressure. "
        "Film a few reps from the front to verify."),
    'bar_tilt': (
        "Bar tilt",
        "Re-grip until the bar feels balanced. Visible tilt for >300 ms is a "
        "fault — reset, don't grind through it."),
    'concentric_tempo': (
        "Concentric tempo",
        "Working pulls should take 1-3 s. Faster than 1 s usually means "
        "leaving lockout short; slower than 3 s means grinding."),
    'eccentric_tempo': (
        "Eccentric tempo",
        "Conventional: control to the floor in 1.5-3 s. RDL: 2-4 s down, "
        "loaded the whole way — this is the lift's defining quality."),
    'setup_time': (
        "Setup time / pre-pull tension",
        "Take 2-5 s of deliberate setup. Pull the slack out, brace, then go. "
        "Rushed setups cause everything else to break down."),
    'lockout_hold': (
        "Lockout hold",
        "Hold the lockout 0.3-0.5 s. \"Pause and own it\" before descent."),
    'consistency': (
        "Rep-to-rep consistency",
        "CV >8% across reps means form is drifting through the set. Drop "
        "intensity 10% and rebuild the groove."),
}


def _coaching_for(slug, sub_score):
    name, body = CUE_TEMPLATES.get(slug, (slug, "Work on this metric."))
    return {'metric': name, 'sub_score': round(float(sub_score), 1), 'cue': body}


# ─────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────

def analyse(files, plate_size_kg=None, weight_max=None, reps_max=None,
            target_reps=None, variant='conventional', athlete_height_cm=None):
    """Analyze a deadlift across four camera views.

    Required files key: `sagittal` (back-compat: `side`).
    Recommended:        `frontal`, `posterior`, `oblique`.
    """
    variant = (variant or 'conventional').lower()
    if variant in ('rdl', 'romanian-rdl'):
        variant = 'romanian'
    if variant not in ('conventional', 'romanian'):
        variant = 'conventional'

    # Resolve file paths (back-compat aliases preserved)
    sag_path = (files or {}).get('sagittal') or (files or {}).get('side')
    front_path = (files or {}).get('frontal') or (files or {}).get('front')
    post_path = (files or {}).get('posterior') or (files or {}).get('rear')
    obl_path = (files or {}).get('oblique')
    if not sag_path and files:
        # Last resort: take the first file
        sag_path = list(files.values())[0]
    if not sag_path:
        return _fallback('No sagittal video uploaded.')

    # Process each view
    try:
        sag = _process_sagittal(sag_path, plate_size_kg, variant)
    except Exception as e:
        return _fallback(f'Sagittal pose extraction failed: {e}')
    front = _process_frontal(front_path) if front_path else None
    post = _process_posterior(post_path) if post_path else None
    obl = _process_oblique(obl_path) if obl_path else None

    fps = sag['fps']
    conf = confidence_score(sag['frames'])

    # Detect reps
    reps = _detect_reps_for_variant(sag, variant, target_reps)
    if not reps:
        return _fallback('No reps detected on the sagittal video.')

    # Per-rep metric values and sub-scores
    per_rep = []
    for rep in reps:
        mv = _compute_rep_metrics(rep, sag, front, post, obl, variant,
                                  athlete_height_cm)
        subs = _score_all(mv, variant)
        per_rep.append({
            'rep_num': rep['idx'],
            'setup_frame': rep['setup'],
            'liftoff_frame': rep.get('liftoff', rep['setup']),
            'lockout_frame': rep['lockout'],
            'bottom_frame': rep['bottom'],
            'metric_values': mv,
            'sub_scores': subs,
        })

    # Consistency: CV% across reps for headline numbers
    cv_pct = _consistency_cv(per_rep)
    consistency_score = score_one_sided(cv_pct, 5, 8, 12, 18, higher_is_better=False)
    for r in per_rep:
        r['sub_scores']['consistency'] = consistency_score

    # Category + composite per rep
    for r in per_rep:
        r['categories'] = _category_scores(r['sub_scores'], variant)
        r['composite'] = _geometric_composite(r['categories'])

    # Hard-fail overrides (per rep), pick worst cap across the set
    set_overrides = []
    for spec in _override_specs():
        if spec['key'] == 'lumbar_progressive':
            # Set-level: regression slope of lumbar_flex_dev across reps > 2°/rep
            lfd = [r['metric_values']['lumbar_flex_dev'] for r in per_rep]
            slope = _slope(lfd) if len(lfd) >= 2 else 0.0
            triggered = slope > 2.0 and max(lfd) > 7
            set_overrides.append({
                'condition': spec['condition'], 'cap': spec['cap'],
                'triggered': bool(triggered),
                'triggering_metric': 'Lumbar flexion (per-rep trend)',
                'triggering_value': f"+{slope:.1f}°/rep" if triggered else None,
            })
            continue
        # Per-rep evaluation; trigger if ANY rep trips it
        worst_val_str = None
        worst_rep = None
        triggered = False
        for r in per_rep:
            t, vs = spec['eval'](r['metric_values'])
            if t:
                triggered = True
                # Keep the most-egregious rep for display
                if worst_val_str is None:
                    worst_val_str = vs; worst_rep = r['rep_num']
        set_overrides.append({
            'condition': spec['condition'], 'cap': spec['cap'],
            'triggered': bool(triggered),
            'triggering_metric': spec['metric'],
            'triggering_value': (f"rep {worst_rep}: {worst_val_str}" if triggered else None),
        })

    triggered_caps = [o['cap'] for o in set_overrides if o['triggered']]
    active_cap = min(triggered_caps) if triggered_caps else None

    # Apply cap to each rep composite
    for r in per_rep:
        if active_cap is not None:
            r['composite'] = min(r['composite'], active_cap)

    # Set aggregation (spec §7.5)
    composites = [r['composite'] for r in per_rep]
    set_mean = _mean(composites)
    set_worst = min(composites)
    last3 = composites[-3:] if len(composites) >= 3 else composites
    set_last3 = _mean(last3)
    deteriorating = [r['rep_num'] for r in per_rep
                     if r['composite'] < (set_mean - 15)]

    # Category means across reps
    cat_means = {}
    for k in ('safety', 'technique', 'performance'):
        cat_means[k] = _mean(r['categories'][k] for r in per_rep)

    # Two lowest mean sub-scores (across reps), filtered to applicable slugs
    sub_mean = {}
    all_keys = set()
    for r in per_rep:
        all_keys.update(r['sub_scores'].keys())
    for k in all_keys:
        vals = [r['sub_scores'].get(k) for r in per_rep if r['sub_scores'].get(k) is not None]
        if vals:
            sub_mean[k] = _mean(vals)
    lowest = sorted(sub_mean.items(), key=lambda kv: kv[1])[:2]
    lowest_cues = [_coaching_for(k, v) for k, v in lowest]

    # Grade
    headline = round(set_mean)
    grade, label = grade_from_composite(set_mean)
    status = status_from_grade(grade)

    # ── Build flat per-metric list for the legacy "metrics" array ──
    metrics_list = _build_legacy_metrics(per_rep, variant, sub_mean, sag['bar_med_q'])

    # ── Coaching (top actions): override-triggered first, then top fixes ──
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
        coaching.append("Clean pull. Maintain neutral spine and bar-over-midfoot at the next session.")
    if deteriorating:
        coaching.append(
            f"Rep{'s' if len(deteriorating) > 1 else ''} {', '.join(str(n) for n in deteriorating)} "
            f"deteriorated >15 pts below the set mean — fatigue or form drift; consider lowering "
            f"intensity next set.")

    # Optional 1RM estimates
    if weight_max and reps_max:
        try:
            est = estimate_1rm(weight_max, reps_max)
            metrics_list.append(build_metric('Estimated 1RM (Epley)', f"{est['epley']} kg",
                                             est['epley'], '—', max(est['epley']*1.2, 100), 'GOOD'))
            metrics_list.append(build_metric('Estimated 1RM (Brzycki)', f"{est['brzycki']} kg",
                                             est['brzycki'], '—', max(est['brzycki']*1.2, 100), 'GOOD'))
        except Exception:
            pass

    # Annotated frames — one best-rep skeleton PER camera, each showing only
    # the metrics that camera can measure (spec §1.3). Sagittal (all reps) is
    # the hero; frontal / posterior / oblique add one best-rep diagram each.
    annotated = _render_frames(sag_path, sag, per_rep, status, headline, variant)
    try:
        annotated += _render_camera_frames(
            {'frontal': front_path, 'posterior': post_path, 'oblique': obl_path},
            {'frontal': front, 'posterior': post, 'oblique': obl},
            per_rep, status, headline, variant,
        )
    except Exception as e:
        print(f"[deadlift] per-camera frame rendering skipped: {e}")

    # Stats banner
    n_reps_total = target_reps or len(per_rep)
    valid_reps = sum(1 for r in per_rep if r['composite'] >= 40)
    stats = {
        'validReps': f'{valid_reps}/{n_reps_total}',
        'confidence': f'{conf}%',
        'sides': sag['side'],
        'cameraView': 'Sagittal + Frontal + Posterior + Oblique',
        'variant': variant,
        'composite': f'{headline} ({grade})',
        'load': f'{weight_max} kg' if weight_max else '—',
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
            {'name': 'Safety',      'weight': 0.50, 'score': round(cat_means['safety'], 1)},
            {'name': 'Technique',   'weight': 0.35, 'score': round(cat_means['technique'], 1)},
            {'name': 'Performance', 'weight': 0.15, 'score': round(cat_means['performance'], 1)},
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
        'variant': variant,
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
    result['muscle_activation'] = infer_deadlift(
        variant=variant,
        hip_knee_ratio=1.0 if variant != 'conventional' else _hip_knee_ratio(per_rep),
    )
    result['meta'] = {
        'camera_view': 'sagittal+frontal+posterior+oblique',
        'camera_view_confidence': round(min(1.0, conf / 100.0), 2),
        'camera_view_warning': None,
        'bar_track_quality_median': round(sag['bar_med_q'], 2),
        'analyzer_version': 'deadlift-2026-05-19-spec',
    }
    return result


def _flatten_per_rep_for_ui(rep):
    """Flatten a per_rep entry into a single-level dict of numbers for the
    frontend per-rep accordion."""
    mv = rep['metric_values']
    subs = rep['sub_scores']
    cats = rep['categories']
    out = {
        'composite': round(rep['composite'], 1),
        'safety_score': round(cats['safety'], 1),
        'technique_score': round(cats['technique'], 1),
        'performance_score': round(cats['performance'], 1),
    }
    # Numeric-only keys from metric_values (skip None)
    for k, v in mv.items():
        if isinstance(v, (int, float)):
            out[k] = round(v, 2)
    for k, v in subs.items():
        if isinstance(v, (int, float)):
            out[f'sub_{k}'] = round(v, 1)
    return out


def _hip_knee_ratio(per_rep):
    """Compute hip:knee extension velocity ratio across the set (for muscle inference)."""
    # Simple proxy: hip travel / knee travel across first half of concentric
    return 1.0  # neutral — muscle inference handles None gracefully


def _consistency_cv(per_rep):
    """Average CV% across the key spec metrics (torso start, hip lockout, bar drift)."""
    keys = ('torso_start_deg', 'hip_lockout_deg', 'bar_drift_pct')
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


def _slope(values):
    n = len(values)
    if n < 2:
        return 0.0
    xm = (n - 1) / 2
    ym = sum(values) / n
    num = sum((i - xm) * (values[i] - ym) for i in range(n))
    den = sum((i - xm) ** 2 for i in range(n))
    return num / den if den > 1e-9 else 0.0


# ─────────────────────────────────────────────────────────────────────
# Legacy metrics list (per-metric chips for the existing "Technical" grid)
# ─────────────────────────────────────────────────────────────────────

def _legacy_status(sub_score):
    """5-tier per-metric status (matches frontend MetricStatus)."""
    if sub_score >= 90:
        return 'GOOD'
    if sub_score >= 75:
        return 'GOOD'
    if sub_score >= 60:
        return 'NEEDS IMPROVEMENT'
    return 'RESTRICTED'


def _build_legacy_metrics(per_rep, variant, sub_mean, bar_q):
    """Build the flat metric list for the existing technical grid."""
    n_reps = len(per_rep)
    out = []
    mv = {k: _mean(r['metric_values'][k] for r in per_rep
                   if isinstance(r['metric_values'].get(k), (int, float)))
          for k in per_rep[0]['metric_values']
          if isinstance(per_rep[0]['metric_values'].get(k), (int, float))}

    def m(name, raw, value_fmt, target, max_val, slug):
        sub = sub_mean.get(slug, 60.0)
        cls = _legacy_status(sub)
        return build_metric(name, value_fmt, raw, target, max_val, cls,
                            n_reps=n_reps, confidence=min(1.0, bar_q + 0.4))

    # Safety
    out.append(m('Lumbar flexion proxy (worst)', max(r['metric_values']['lumbar_flex_dev'] for r in per_rep),
                 f"{max(r['metric_values']['lumbar_flex_dev'] for r in per_rep):.1f}°",
                 '≤7° (trained norm)', 30, 'lumbar_flex'))
    out.append(m('Thoracic curvature (max)', mv.get('thoracic_curv_deg', 0),
                 f"{mv.get('thoracic_curv_deg', 0):.1f}°", '<10°', 40, 'thoracic'))
    out.append(m('Hip extension at lockout', mv.get('hip_lockout_deg', 178),
                 f"{mv.get('hip_lockout_deg', 178):.1f}°", '175–182°', 200, 'hip_lockout'))
    out.append(m('Spinal lateral deviation', mv.get('spinal_lat_dev_pct', 2),
                 f"{mv.get('spinal_lat_dev_pct', 2):.1f}%", '<2%', 15, 'spinal_lat_dev'))
    out.append(m('Knee valgus (FPPA worst)', mv.get('knee_fppa_max', 0),
                 f"{mv.get('knee_fppa_max', 0):.1f}°", '<5°', 30, 'knee_valgus'))
    if variant == 'conventional':
        out.append(m('Hip-shoulder timing R', mv.get('hip_shoulder_R', 1.0),
                     f"{mv.get('hip_shoulder_R', 1.0):.2f}", '0.9–1.1', 3, 'hip_shoulder_timing'))
    out.append(m('Bar drift (% of height)', mv.get('bar_drift_pct', 0),
                 f"{mv.get('bar_drift_pct', 0):.1f}%", '<2%', 15, 'bar_drift'))
    out.append(m('Heel lift (max sustained)', mv.get('heel_lift_ms', 0),
                 f"{mv.get('heel_lift_ms', 0):.0f} ms", '<50 ms', 1500, 'heel_contact'))
    if variant == 'romanian':
        out.append(m('Lateral hip shift', mv.get('lateral_hip_shift_pct', 0),
                     f"{mv.get('lateral_hip_shift_pct', 0):.1f}%", '<3%', 20, 'lateral_hip_shift'))

    # Technique
    if variant == 'conventional':
        out.append(m('Torso angle at start', mv.get('torso_start_deg', 27),
                     f"{mv.get('torso_start_deg', 27):.1f}°", '20–35°', 90, 'torso_start'))
        out.append(m('Knee flexion at start', mv.get('knee_start_deg', 122),
                     f"{mv.get('knee_start_deg', 122):.1f}°", '115–130°', 180, 'knee_start'))
        out.append(m('Shin angle (forward)', mv.get('shin_angle_deg', 10),
                     f"{mv.get('shin_angle_deg', 10):.1f}°", '5–15°', 40, 'shin_angle'))
        out.append(m('Knee extension at lockout', mv.get('knee_lockout_deg', 178),
                     f"{mv.get('knee_lockout_deg', 178):.1f}°", '175–182°', 200, 'knee_lockout'))
    else:
        out.append(m('Torso angle at bottom (RDL)', mv.get('torso_start_deg', 15),
                     f"{mv.get('torso_start_deg', 15):.1f}°", '5–25°', 90, 'torso_bottom'))
        out.append(m('Constant knee flexion (RDL)', mv.get('rdl_knee_flex_deg', 20),
                     f"{mv.get('rdl_knee_flex_deg', 20):.1f}°", '15–25°', 60, 'knee_constant'))
        out.append(m('RDL ROM', mv.get('rdl_rom_pct', 30),
                     f"{mv.get('rdl_rom_pct', 30):.1f}%", '≥30% of height', 60, 'rdl_rom'))
    out.append(m('Bar-to-thigh gap (max)', mv.get('bar_thigh_gap_cm', 1),
                 f"{mv.get('bar_thigh_gap_cm', 1):.1f} cm", '<1 cm', 15, 'bar_thigh_prox'))
    out.append(m('Bar path drift', mv.get('bar_drift_pct', 0),
                 f"{mv.get('bar_drift_pct', 0):.1f}%", '<2%', 15, 'bar_path'))
    out.append(m('Neck / head deviation', mv.get('cervical_dev_deg', 0),
                 f"{mv.get('cervical_dev_deg', 0):.1f}°", '≤5°', 60, 'neck_head'))
    out.append(m('Stance width (% biacromial)', mv.get('stance_pct_biacromial', 95),
                 f"{mv.get('stance_pct_biacromial', 95):.0f}%", '80–110%', 200, 'stance_width'))
    if mv.get('foot_angle_deg') is not None:
        out.append(m('Foot / toe angle', mv['foot_angle_deg'],
                     f"{mv['foot_angle_deg']:.1f}°", '7–15°', 45, 'foot_angle'))
    out.append(m('Bar tilt', mv.get('bar_tilt_deg', 0),
                 f"{mv.get('bar_tilt_deg', 0):.1f}°", '<2°', 15, 'bar_tilt'))
    out.append(m('Pull symmetry (angular)', mv.get('pull_asym_deg', 0),
                 f"{mv.get('pull_asym_deg', 0):.1f}°", '<2°', 25, 'pull_symmetry'))

    # Performance
    out.append(m('Concentric tempo', mv.get('concentric_sec', 2),
                 f"{mv.get('concentric_sec', 2):.2f} s",
                 '1.0–2.5 s' if variant == 'conventional' else '1.0–2.0 s',
                 10, 'concentric_tempo'))
    out.append(m('Eccentric tempo', mv.get('eccentric_sec', 2),
                 f"{mv.get('eccentric_sec', 2):.2f} s",
                 '1.5–3.0 s' if variant == 'conventional' else '2–4 s',
                 10, 'eccentric_tempo'))
    if mv.get('setup_sec') is not None:
        out.append(m('Setup time', mv['setup_sec'],
                     f"{mv['setup_sec']:.2f} s", '2–5 s', 30, 'setup_time'))
    out.append(m('Lockout hold', mv.get('lockout_hold_sec', 0.4),
                 f"{mv.get('lockout_hold_sec', 0.4):.2f} s", '≥0.5 s', 3, 'lockout_hold'))
    out.append(m('Mean concentric velocity', mv.get('mcv_mps', 0.4),
                 f"{mv.get('mcv_mps', 0.4):.2f} m/s",
                 '≥0.5 m/s @ 75% 1RM', 1.5, 'concentric_tempo'))

    return out


# ─────────────────────────────────────────────────────────────────────
# Annotated frame rendering (sagittal view only — one frame per rep at lockout)
# ─────────────────────────────────────────────────────────────────────

def _render_frames(video_path, sag, per_rep, status, score, variant):
    out = []
    frames = sag['frames']; w = sag['w']; h = sag['h']; idx = sag['idx']
    if not per_rep:
        fb = render_sample_frame(video_path, frames, w, h, 'Deadlift',
                                 'No reps detected — check sagittal framing.',
                                 connections=DEADLIFT_CONNECTIONS)
        if fb:
            out.append({'label': 'Sample Frame', 'image_base64': fb,
                        'rep_num': 0, 'side': 'center', 'is_best': False,
                        'metrics_shown': ['No reps detected']})
        return out

    best_idx = max(range(len(per_rep)), key=lambda i: per_rep[i]['composite'])
    for ri, r in enumerate(per_rep):
        try:
            pk = r['lockout_frame']
            if pk >= len(frames):
                continue
            lm = frames[pk]['landmarks']
            if lm is None:
                continue
            frame = extract_frame_at(video_path, pk)
            if frame is None:
                continue

            ear = _lm_to_px(lm, idx['ear'], w, h)
            sh  = _lm_to_px(lm, idx['shoulder'], w, h)
            hp  = _lm_to_px(lm, idx['hip'], w, h)
            kn  = _lm_to_px(lm, idx['knee'], w, h)
            an  = _lm_to_px(lm, idx['ankle'], w, h)
            smid = midpoint_px(lm, LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER'], w, h)
            hmid = midpoint_px(lm, LM['LEFT_HIP'], LM['RIGHT_HIP'], w, h)

            draw_skeleton(frame, lm, w, h, connections=DEADLIFT_CONNECTIONS)
            if an:
                draw_reference_line(frame, x=an[0], color=COL_CYAN,
                                    label='Mid-foot (bar reference)')

            mv = r['metric_values']
            lumbar_status = ('good' if mv['lumbar_flex_dev'] < 7
                              else ('warn' if mv['lumbar_flex_dev'] < 12 else 'bad'))
            if ear and smid and hmid:
                draw_angle_arc(frame, smid, ear, hmid,
                               180.0 - mv['lumbar_flex_dev'],
                               label=f"Lumbar Δ {mv['lumbar_flex_dev']:.1f}°",
                               radius=52, status=lumbar_status)
            if sh and hp and kn:
                hip_status = 'good' if 175 <= mv['hip_lockout_deg'] <= 182 else 'warn'
                draw_angle_arc(frame, hp, sh, kn, mv['hip_lockout_deg'],
                               label=f"Hip {mv['hip_lockout_deg']:.0f}°",
                               radius=44, status=hip_status)
            if hp and kn and an:
                knee_status = 'good' if 175 <= mv['knee_lockout_deg'] <= 182 else 'warn'
                draw_angle_arc(frame, kn, hp, an, mv['knee_lockout_deg'],
                               label=f"Knee {mv['knee_lockout_deg']:.0f}°",
                               radius=40, status=knee_status)
            if hp and mv.get('hip_shoulder_R') is not None:
                ratio_status = 'good' if 0.9 <= mv['hip_shoulder_R'] <= 1.3 else 'bad'
                draw_callout(frame, hp,
                             f"Hip:Sh R {mv['hip_shoulder_R']:.2f}",
                             status=ratio_status, offset=(140, -20))

            draw_title_strip(frame, f"Deadlift ({variant})", r['rep_num'],
                             len(per_rep), status=status, score=score)
            draw_phase_label(frame, 'Lockout' if variant == 'conventional' else 'Top')

            overlay = [
                {'label': 'Composite',    'value': f"{r['composite']:.0f}/100",
                 'status': 'good' if r['composite'] >= 75 else ('warn' if r['composite'] >= 60 else 'bad')},
                {'label': 'Safety',       'value': f"{r['categories']['safety']:.0f}",
                 'status': 'good' if r['categories']['safety'] >= 75 else 'warn'},
                {'label': 'Technique',    'value': f"{r['categories']['technique']:.0f}",
                 'status': 'good' if r['categories']['technique'] >= 75 else 'warn'},
                {'label': 'Performance',  'value': f"{r['categories']['performance']:.0f}",
                 'status': 'good' if r['categories']['performance'] >= 75 else 'warn'},
                {'label': 'Lumbar Δ',     'value': f"{mv['lumbar_flex_dev']:.1f}°",
                 'status': lumbar_status},
                {'label': 'Bar drift',    'value': f"{mv['bar_drift_pct']:.1f}%",
                 'status': 'good' if mv['bar_drift_pct'] < 4 else 'bad'},
                {'label': 'Torso start',  'value': f"{mv.get('torso_start_deg', 24):.0f}°",
                 'status': 'good'},
                {'label': 'Shin angle',   'value': f"{mv.get('shin_angle_deg', 12):.0f}°",
                 'status': 'good'},
                {'label': 'Concentric',   'value': f"{mv['concentric_sec']:.2f} s",
                 'status': 'good'},
                {'label': 'MCV',          'value': f"{mv['mcv_mps']:.2f} m/s",
                 'status': 'good' if mv['mcv_mps'] >= 0.5 else 'warn'},
            ]
            # Sagittal frame shows SAGITTAL metrics only — frontal (bar tilt,
            # knee FPPA) and posterior (spinal deviation) metrics move to their
            # own per-camera diagrams below (spec §1.3).
            draw_metric_overlay(frame, overlay, position='top-right',
                                title=f"REP {r['rep_num']} · {variant.upper()} · SAGITTAL")
            draw_legend(frame, position='bottom-left')

            img_b64 = frame_to_base64(frame)
            is_best = (ri == best_idx)
            out.append({
                'label': f"Sagittal · Rep {r['rep_num']}" + (" (Best)" if is_best else ""),
                'image_base64': img_b64,
                'rep_num': r['rep_num'], 'side': 'sagittal', 'is_best': is_best,
                'metrics_shown': [
                    f"Composite: {r['composite']:.0f}/100",
                    f"Safety: {r['categories']['safety']:.0f}",
                    f"Lumbar Δ: {mv['lumbar_flex_dev']:.1f}°",
                    f"Bar drift: {mv['bar_drift_pct']:.1f}%",
                ],
            })
        except Exception as e:
            print(f"[deadlift.render] rep {r.get('rep_num')} failed: {e}")
            continue

    if not out:
        fb = render_sample_frame(video_path, frames, w, h, 'Deadlift',
                                 'Reps detected but frames could not be rendered.',
                                 connections=DEADLIFT_CONNECTIONS)
        if fb:
            out.append({'label': 'Sample Frame', 'image_base64': fb,
                        'rep_num': 0, 'side': 'center', 'is_best': False,
                        'metrics_shown': ['Frame extraction failed']})
    return out


# ─────────────────────────────────────────────────────────────────────
# Per-camera annotated frames (spec §1.3 — each view scores its own metrics)
#
# The deadlift is one set filmed from up to four angles. Each angle measures
# a DIFFERENT family of metrics well (sagittal = torso/hip/knee/bar-path;
# frontal = stance/valgus/bar-tilt/hip-shift; posterior = spinal deviation +
# symmetry; oblique = sagittal cross-check). Rather than crowd every metric
# onto the sagittal frame, we render ONE best-rep skeleton per available
# camera, each annotated only with the metrics that camera can actually see.
# ─────────────────────────────────────────────────────────────────────

def _view_lockout_idx(view):
    """Frame index of the lockout (standing extreme) in an auxiliary view.

    Uses the body-extension signal (hip + knee angle), NOT hip height — a
    bent-over deadlifter's hips ride high, so hip-height would wrongly select
    the setup. Prefers the value precomputed in _process_frontal/_posterior;
    recomputes from landmarks otherwise (e.g. the oblique clone)."""
    lk = view.get('lockout_idx')
    if lk is not None:
        return lk
    _h, _bottom, lockout = _view_standing_and_lockout(
        view['frames'], view['w'], view['h'])
    return lockout


def _render_view_frame(video_path, view, side, title, phase_label,
                       overlay, status, score, rep_num, total, draw_extra=None):
    """Shared aux-view renderer: skeleton + view-specific overlays at the
    lockout frame. Returns one frame dict (best rep) or None."""
    if not view or not video_path:
        return None
    try:
        frames = view['frames']; w = view['w']; h = view['h']
        li = _view_lockout_idx(view)
        if li is None or li >= len(frames):
            return None
        lm = frames[li].get('landmarks')
        if lm is None:
            return None
        frame = extract_frame_at(video_path, li)
        if frame is None:
            return None
        draw_skeleton(frame, lm, w, h, connections=DEADLIFT_CONNECTIONS)
        if draw_extra:
            draw_extra(frame, lm, w, h)
        draw_title_strip(frame, title, rep_num, total, status=status, score=score)
        draw_phase_label(frame, phase_label)
        draw_metric_overlay(frame, overlay, position='top-right',
                            title=f"{side.upper()} · {phase_label.upper()}")
        draw_legend(frame, position='bottom-left')
        return {
            'label': f"{side.title()} · {phase_label}",
            'image_base64': frame_to_base64(frame),
            'rep_num': rep_num, 'side': side, 'is_best': True,
            'metrics_shown': [f"{o['label']}: {o['value']}" for o in overlay[:4]],
        }
    except Exception as e:
        print(f"[deadlift.render.{side}] failed: {e}")
        return None


def _band_status(val, good_hi, warn_hi):
    """Lower-is-better tri-state helper for overlay chips."""
    if val is None:
        return 'warn'
    if val < good_hi:
        return 'good'
    if val < warn_hi:
        return 'warn'
    return 'bad'


def _render_frontal_frame(video_path, front, mv, status, score, rep_num, total):
    """Frontal view — stance, foot angle, knee valgus/FPPA, bar tilt, lateral
    hip shift, grip width, pull symmetry (spec §4)."""
    if not front:
        return None

    def _extra(frame, lm, w, h):
        lan = get_landmark_px(lm, LM['LEFT_ANKLE'], w, h)
        ran = get_landmark_px(lm, LM['RIGHT_ANKLE'], w, h)
        if lan:
            draw_reference_line(frame, x=lan[0], color=COL_CYAN, label='L mid-foot')
        if ran:
            draw_reference_line(frame, x=ran[0], color=COL_CYAN, label='R mid-foot')
        fppa = mv.get('knee_fppa_max', 0.0) or 0.0
        vst = _band_status(fppa, 10, 15)
        lkn = get_landmark_px(lm, LM['LEFT_KNEE'], w, h)
        rkn = get_landmark_px(lm, LM['RIGHT_KNEE'], w, h)
        if lkn:
            draw_valgus_callout(frame, lkn, fppa, 'left', status=vst)
        if rkn:
            draw_valgus_callout(frame, rkn, fppa, 'right', status=vst)

    stance = mv.get('stance_pct_biacromial', 95.0) or 95.0
    overlay = [
        {'label': 'Stance width', 'value': f"{stance:.0f}%",
         'status': 'good' if 80 <= stance <= 110 else 'warn'},
        {'label': 'Foot angle',  'value': f"{mv.get('foot_angle_deg', 12):.0f}°",
         'status': 'good'},
        {'label': 'Knee FPPA',   'value': f"{mv.get('knee_fppa_max', 0):.1f}°",
         'status': _band_status(mv.get('knee_fppa_max', 0), 10, 22)},
        {'label': 'Bar tilt',    'value': f"{mv.get('bar_tilt_deg', 0):.1f}°",
         'status': _band_status(mv.get('bar_tilt_deg', 0), 4, 7)},
        {'label': 'Hip shift',   'value': f"{mv.get('lateral_hip_shift_pct', 0):.1f}%",
         'status': _band_status(mv.get('lateral_hip_shift_pct', 0), 6, 10)},
        {'label': 'Grip width',  'value': f"{mv.get('grip_width_cm', 55):.0f}cm",
         'status': 'good'},
        {'label': 'Pull asym',   'value': f"{mv.get('pull_asym_deg', 0):.1f}°",
         'status': _band_status(mv.get('pull_asym_deg', 0), 5, 18)},
    ]
    return _render_view_frame(video_path, front, 'frontal', 'Deadlift — Frontal',
                              'Lockout', overlay, status, score, rep_num, total, _extra)


def _render_posterior_frame(video_path, post, mv, status, score, rep_num, total):
    """Posterior view — spinal lateral deviation, shoulder/hip symmetry, bar
    tilt cross-check (spec §5)."""
    if not post:
        return None

    def _extra(frame, lm, w, h):
        hmid = midpoint_px(lm, LM['LEFT_HIP'], LM['RIGHT_HIP'], w, h)
        if hmid:
            draw_reference_line(frame, x=hmid[0], color=COL_CYAN, label='Spine plumb-line')

    overlay = [
        {'label': 'Spinal lat dev', 'value': f"{mv.get('spinal_lat_dev_pct', 2.5):.1f}%",
         'status': _band_status(mv.get('spinal_lat_dev_pct', 2.5), 4, 7)},
        {'label': 'Shoulder sym',   'value': f"{mv.get('shoulder_tilt_deg', 2):.1f}°",
         'status': _band_status(mv.get('shoulder_tilt_deg', 2), 4, 7)},
        {'label': 'Hip sym',        'value': f"{mv.get('hip_tilt_deg', 2):.1f}°",
         'status': _band_status(mv.get('hip_tilt_deg', 2), 4, 7)},
        {'label': 'Bar tilt (x-chk)', 'value': f"{mv.get('bar_tilt_deg', 0):.1f}°",
         'status': _band_status(mv.get('bar_tilt_deg', 0), 4, 7)},
    ]
    return _render_view_frame(video_path, post, 'posterior', 'Deadlift — Posterior',
                              'Lockout', overlay, status, score, rep_num, total, _extra)


def _render_oblique_frame(video_path, obl, mv, status, score, rep_num, total):
    """Oblique (45°) view — sagittal cross-check: torso / hip / knee at lockout,
    bar drift (spec §1.1 row 4)."""
    if not obl:
        return None
    idx = obl.get('idx')

    def _extra(frame, lm, w, h):
        if not idx:
            return
        sh = _lm_to_px(lm, idx['shoulder'], w, h)
        hp = _lm_to_px(lm, idx['hip'], w, h)
        kn = _lm_to_px(lm, idx['knee'], w, h)
        an = _lm_to_px(lm, idx['ankle'], w, h)
        if sh and hp and kn:
            draw_angle_arc(frame, hp, sh, kn, mv.get('hip_lockout_deg', 178),
                           label=f"Hip {mv.get('hip_lockout_deg', 178):.0f}°",
                           radius=44, status='good')
        if hp and kn and an:
            draw_angle_arc(frame, kn, hp, an, mv.get('knee_lockout_deg', 178),
                           label=f"Knee {mv.get('knee_lockout_deg', 178):.0f}°",
                           radius=40, status='good')

    overlay = [
        {'label': 'Torso start',  'value': f"{mv.get('torso_start_deg', 24):.0f}°",
         'status': 'good'},
        {'label': 'Hip lockout',  'value': f"{mv.get('hip_lockout_deg', 178):.0f}°",
         'status': 'good' if 175 <= mv.get('hip_lockout_deg', 178) <= 186 else 'warn'},
        {'label': 'Knee lockout', 'value': f"{mv.get('knee_lockout_deg', 178):.0f}°",
         'status': 'good' if 170 <= mv.get('knee_lockout_deg', 178) <= 182 else 'warn'},
        {'label': 'Bar drift',    'value': f"{mv.get('bar_drift_pct', 0):.1f}%",
         'status': _band_status(mv.get('bar_drift_pct', 0), 4, 9)},
    ]
    return _render_view_frame(video_path, obl, 'oblique', 'Deadlift — Oblique',
                              'Cross-check', overlay, status, score, rep_num, total, _extra)


def _render_camera_frames(paths, views, per_rep, status, score, variant):
    """Best-rep skeleton per available camera. `paths` and `views` are dicts
    keyed 'frontal'/'posterior'/'oblique'."""
    out = []
    if not per_rep:
        return out
    best = max(per_rep, key=lambda r: r['composite'])
    mv = best['metric_values']
    total = len(per_rep)
    rn = best['rep_num']
    renderers = [
        (_render_frontal_frame,   paths.get('frontal'),   views.get('frontal')),
        (_render_posterior_frame, paths.get('posterior'), views.get('posterior')),
        (_render_oblique_frame,   paths.get('oblique'),   views.get('oblique')),
    ]
    for fn, path, view in renderers:
        if not (path and view):
            continue
        f = fn(path, view, mv, status, score, rn, total)
        if f:
            out.append(f)
    return out


def _fallback(msg):
    return build_result(
        'NEEDS IMPROVEMENT', 50,
        f'Analysis could not complete: {msg}',
        {'validReps': '0/0', 'confidence': '0%', 'sides': 'n/a',
         'cameraView': 'UNKNOWN'},
        [], [], [msg],
    )
