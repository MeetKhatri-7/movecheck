"""Back Squat analyzer — full rewrite (v3) implementing the spec doc
`barbell_squat_assessment_system.md`.

  • 18 biomechanical metrics across sagittal / frontal views (rear is folded
    into the front view fallback per spec §11 — we don't ask for a third cam).
  • 5-tier per-metric scoring (very_good / good / yellow_flag / bad / very_bad)
    with linear interpolation within each tier band (spec §7.1).
  • Style-specific thresholds — 'low-bar' uses the doc's "Normal Squat"
    thresholds, 'high-bar' uses the "Deep Squat" thresholds.
  • Category-weighted composite (Safety 40 / Technique 40 / Performance 20)
    plus hard-fail safety overrides (spec §7.2, §7.4).
  • Per-set aggregation = mean of rep composites (spec §7.5).
  • UX extras preserved: per_rep dump, fatigue series, muscle activation,
    plate-based px-per-cm calibration, annotated frames.

Public entry point: ``analyse(files, **kwargs)`` — keeps the existing
signature so neither the router nor the Node backend need changes.
"""
from __future__ import annotations

import math
import traceback

from utils.landmarks import (
    LM, extract_all_landmarks, get_lm, midpoint_px,
    landmark_quality, window_landmark_quality,
)
from utils.angles import (
    angle_3pt, angle_to_vertical, signed_angle_from_vertical,
    distance_px,
)
from utils.rep_detection import detect_reps_minima, moving_average
from utils.scoring import (
    build_result, build_metric, build_bilateral,
    aggregate_per_rep,
)
from utils.frame_annotator import (
    draw_skeleton, draw_angle_arc, draw_distance_line,
    draw_reference_line, draw_callout, draw_phase_label,
    draw_top_phase_banner, draw_top_right_rep_pill,
    draw_info_panel, draw_confidence_pill,
    draw_fault_timing_strip, draw_hip_height_trace,
    draw_valgus_callout,
    extract_frame_at, frame_to_base64, render_sample_frame,
    COL_CYAN,
)
from utils.bar_tracker import track_bar_path, bar_path_horizontal_drift_cm
from utils.muscle_inference import infer_squat


ANALYZER_VERSION = 'back-squat-2026-05-18-v3'


# ════════════════════════════════════════════════════════════════════
#  SECTION A — Threshold tables (doc §3 to §6)
# ════════════════════════════════════════════════════════════════════
#
# Encoding:
#   'mode':            'one_sided' or 'tent'.
#   'higher_is_better' (one_sided only): True if larger raw = better.
#   'tiers' (one_sided): list of (raw_boundary, sub_score) anchors. The
#                        anchors are ordered from BEST raw → WORST raw.
#                        Sub-scores between anchors are linearly interpolated.
#   'ideal' (tent):     ideal raw value (peak of the tent → 100).
#   'tiers' (tent):     list of (half_width, sub_score) anchors. Half-width is
#                        the |raw − ideal| at which the corresponding sub-score
#                        applies. Anchors ordered narrow → wide.

# Doc §7.1 band edges:
#   very_good 90–100   |   good 75–89   |   yellow 60–74
#   bad 40–59          |   very_bad 0–39

_TIER_VERY_GOOD = 100
_TIER_GOOD = 90       # very_good ↔ good
_TIER_YELLOW = 75     # good ↔ yellow
_TIER_BAD = 60        # yellow ↔ bad
_TIER_VERY_BAD = 40   # bad ↔ very_bad
_TIER_FLOOR = 0


# 3.1 — Squat depth (hip vs knee, cm; negative = below knee = better)
DEPTH_SPEC = {
    'low-bar': {
        'mode': 'one_sided', 'higher_is_better': False,
        'tiers': [
            (-5.0, _TIER_VERY_GOOD),
            (-2.0, _TIER_GOOD),     # very_good → good
            ( 0.0, _TIER_YELLOW),   # parallel — good ceiling
            ( 2.0, _TIER_BAD),
            ( 5.0, _TIER_VERY_BAD),
            (10.0, _TIER_FLOOR),
        ],
    },
    'high-bar': {
        'mode': 'one_sided', 'higher_is_better': False,
        # ATG target: hamstring on calf is deeper than doc's "Good: -15 to
        # -10cm" range, so -15cm is the VG/Good boundary (doc §3.1).
        'tiers': [
            (-15.0, _TIER_VERY_GOOD),
            (-10.0, _TIER_GOOD),
            ( -5.0, _TIER_YELLOW),
            (  0.0, _TIER_BAD),
            (  5.0, _TIER_VERY_BAD),
            (15.0,  _TIER_FLOOR),
        ],
    },
}

# 3.2 — Torso angle (deg from vertical). Tent — too upright or too horizontal both bad.
TORSO_SPEC = {
    'low-bar': {
        'mode': 'tent', 'ideal': 37.5,    # mid of 30–45 (doc)
        'tiers': [(7.5, _TIER_GOOD), (12.5, _TIER_YELLOW),
                  (22.5, _TIER_BAD), (32.5, _TIER_VERY_BAD), (45.0, _TIER_FLOOR)],
    },
    'high-bar': {
        'mode': 'tent', 'ideal': 10.0,
        'tiers': [(10.0, _TIER_GOOD), (20.0, _TIER_YELLOW),
                  (30.0, _TIER_BAD), (40.0, _TIER_VERY_BAD), (50.0, _TIER_FLOOR)],
    },
}

# 3.3 — Bar path drift (cm). Lower = better.
BAR_PATH_SPEC = {
    'mode': 'one_sided', 'higher_is_better': False,
    'tiers': [(0.0, _TIER_VERY_GOOD), (2.0, _TIER_GOOD),
              (4.0, _TIER_YELLOW), (7.0, _TIER_BAD),
              (10.0, _TIER_VERY_BAD), (20.0, _TIER_FLOOR)],
}

# 3.4 — Hip-bar horizontal alignment (cm). Lower = better.
HIP_BAR_ALIGN_SPEC = {
    'mode': 'one_sided', 'higher_is_better': False,
    'tiers': [(0.0, _TIER_VERY_GOOD), (5.0, _TIER_GOOD),
              (10.0, _TIER_YELLOW), (15.0, _TIER_BAD),
              (20.0, _TIER_VERY_BAD), (40.0, _TIER_FLOOR)],
}

# 3.5 — Butt wink (deg of additional pelvic tilt at bottom). Lower = better.
# Same point-type VG treatment as knee valgus (doc §3.5: VG is the single
# point 0°) — see VALGUS_SPEC comment.
BUTT_WINK_SPEC = {
    'mode': 'one_sided', 'higher_is_better': False,
    'tiers': [(0.0, _TIER_VERY_GOOD), (5.0, _TIER_YELLOW),
              (10.0, _TIER_BAD), (20.0, _TIER_VERY_BAD), (30.0, _TIER_FLOOR)],
}

# 3.6 — Heel contact (seconds of heel-lift across the rep). Lower = better.
HEEL_LIFT_TIME_SPEC = {
    'mode': 'one_sided', 'higher_is_better': False,
    'tiers': [(0.0, _TIER_VERY_GOOD), (0.05, _TIER_GOOD),
              (0.5, _TIER_YELLOW), (1.0, _TIER_BAD),
              (2.0, _TIER_VERY_BAD), (3.0, _TIER_FLOOR)],
}

# 3.7 — Shin / ankle dorsiflexion (deg). Tent — too little or too much both bad.
SHIN_SPEC = {
    'low-bar': {
        'mode': 'tent', 'ideal': 20.0,
        'tiers': [(5.0, _TIER_GOOD), (10.0, _TIER_YELLOW),
                  (15.0, _TIER_BAD), (25.0, _TIER_VERY_BAD), (40.0, _TIER_FLOOR)],
    },
    'high-bar': {
        'mode': 'tent', 'ideal': 35.0,
        'tiers': [(5.0, _TIER_GOOD), (10.0, _TIER_YELLOW),
                  (15.0, _TIER_BAD), (20.0, _TIER_VERY_BAD), (40.0, _TIER_FLOOR)],
    },
}

# 3.8 — Knee flexion (deg, hip-knee-ankle). Tent — varies by style.
KNEE_FLEX_SPEC = {
    # Lower internal knee angle = deeper flexion. Map raw to "% of ideal flexion."
    'low-bar': {
        'mode': 'tent', 'ideal': 90.0,
        'tiers': [(5.0, _TIER_GOOD), (10.0, _TIER_YELLOW),
                  (20.0, _TIER_BAD), (35.0, _TIER_VERY_BAD), (60.0, _TIER_FLOOR)],
    },
    'high-bar': {
        'mode': 'tent', 'ideal': 40.0,
        'tiers': [(5.0, _TIER_GOOD), (15.0, _TIER_YELLOW),
                  (25.0, _TIER_BAD), (40.0, _TIER_VERY_BAD), (60.0, _TIER_FLOOR)],
    },
}

# 4.1 — Knee valgus (deg of inward collapse). Lower = better.
# Doc §4.1 + the worked §7.1 example: Very Good is the single point 0° (not
# a range), so the anchors run straight VG(100) → Good/Yellow(75) →
# Yellow/Bad(60) → Bad/V.Bad(40) → floor(0) — no intermediate VG/Good (90)
# anchor, matching the doc's explicit 0→100 / 5→75 / 10→60 / 20→40 table.
VALGUS_SPEC = {
    'mode': 'one_sided', 'higher_is_better': False,
    'tiers': [(0.0, _TIER_VERY_GOOD), (5.0, _TIER_YELLOW),
              (10.0, _TIER_BAD), (20.0, _TIER_VERY_BAD), (30.0, _TIER_FLOOR)],
}

# 4.2 — Stance width (ratio of ankle-distance / shoulder-distance). Tent.
STANCE_SPEC = {
    'low-bar': {
        'mode': 'tent', 'ideal': 1.35,
        'tiers': [(0.15, _TIER_GOOD), (0.25, _TIER_YELLOW),
                  (0.40, _TIER_BAD), (0.60, _TIER_VERY_BAD), (1.0, _TIER_FLOOR)],
    },
    'high-bar': {
        'mode': 'tent', 'ideal': 1.10,
        'tiers': [(0.10, _TIER_GOOD), (0.20, _TIER_YELLOW),
                  (0.35, _TIER_BAD), (0.55, _TIER_VERY_BAD), (1.0, _TIER_FLOOR)],
    },
}

# 4.3 — Foot / toe-out angle (deg). Tent around 22° (mid of 15-30).
TOE_OUT_SPEC = {
    'mode': 'tent', 'ideal': 22.0,
    'tiers': [(7.5, _TIER_GOOD), (12.5, _TIER_YELLOW),
              (22.5, _TIER_BAD), (32.5, _TIER_VERY_BAD), (50.0, _TIER_FLOOR)],
}

# 4.4 — Lateral hip shift (cm from feet midline). Lower = better.
LAT_HIP_SHIFT_SPEC = {
    'mode': 'one_sided', 'higher_is_better': False,
    'tiers': [(0.0, _TIER_VERY_GOOD), (1.0, _TIER_GOOD),
              (2.0, _TIER_YELLOW), (4.0, _TIER_BAD),
              (7.0, _TIER_VERY_BAD), (15.0, _TIER_FLOOR)],
}

# 4.5 — Bar tilt (deg). Lower = better.
BAR_TILT_SPEC = {
    'mode': 'one_sided', 'higher_is_better': False,
    'tiers': [(0.0, _TIER_VERY_GOOD), (1.0, _TIER_GOOD),
              (3.0, _TIER_YELLOW), (5.0, _TIER_BAD),
              (10.0, _TIER_VERY_BAD), (20.0, _TIER_FLOOR)],
}

# 5.1 — Spinal lateral deviation (deg). Lower = better.
SPINAL_ALIGN_SPEC = {
    'mode': 'one_sided', 'higher_is_better': False,
    'tiers': [(0.0, _TIER_VERY_GOOD), (2.0, _TIER_GOOD),
              (4.0, _TIER_YELLOW), (7.0, _TIER_BAD),
              (12.0, _TIER_VERY_BAD), (20.0, _TIER_FLOOR)],
}

# 5.2 — Shoulder height symmetry (cm). Lower = better.
SHOULDER_SYM_SPEC = {
    'mode': 'one_sided', 'higher_is_better': False,
    'tiers': [(0.0, _TIER_VERY_GOOD), (1.0, _TIER_GOOD),
              (2.0, _TIER_YELLOW), (4.0, _TIER_BAD),
              (6.0, _TIER_VERY_BAD), (8.0, _TIER_FLOOR)],
}

# 6.1 — Eccentric tempo (sec). Tent around 2.5 sec.
ECC_TEMPO_SPEC = {
    'mode': 'tent', 'ideal': 2.5,
    'tiers': [(0.5, _TIER_GOOD), (1.0, _TIER_YELLOW),
              (1.5, _TIER_BAD), (2.5, _TIER_VERY_BAD), (4.0, _TIER_FLOOR)],
}

# 6.2 — Concentric tempo (sec). Tent around 1.5 sec.
CON_TEMPO_SPEC = {
    'mode': 'tent', 'ideal': 1.5,
    'tiers': [(0.5, _TIER_GOOD), (1.0, _TIER_YELLOW),
              (1.5, _TIER_BAD), (2.5, _TIER_VERY_BAD), (4.0, _TIER_FLOOR)],
}

# 6.3 — Consistency (coefficient of variation across reps, as %). Lower = better.
CONSISTENCY_SPEC = {
    'mode': 'one_sided', 'higher_is_better': False,
    'tiers': [(0.0, _TIER_VERY_GOOD), (5.0, _TIER_GOOD),
              (10.0, _TIER_YELLOW), (15.0, _TIER_BAD),
              (25.0, _TIER_VERY_BAD), (60.0, _TIER_FLOOR)],
}


# ════════════════════════════════════════════════════════════════════
#  SECTION B — Sub-score interpolation (doc §7.1)
# ════════════════════════════════════════════════════════════════════

def sub_score_one_sided(raw, spec):
    """Linearly interpolate raw → sub-score using one-sided tier anchors."""
    if raw is None:
        return None
    tiers = spec['tiers']
    higher_is_better = spec.get('higher_is_better', True)
    # Walk anchor pairs; clamp to [0, 100]
    if higher_is_better:
        # raw above first anchor → max score
        if raw >= tiers[0][0]:
            return tiers[0][1]
        # raw below last anchor → floor
        if raw <= tiers[-1][0]:
            return tiers[-1][1]
        for i in range(len(tiers) - 1):
            hi_raw, hi_score = tiers[i]
            lo_raw, lo_score = tiers[i + 1]
            if lo_raw <= raw <= hi_raw:
                t = (raw - lo_raw) / max(1e-9, hi_raw - lo_raw)
                return lo_score + t * (hi_score - lo_score)
        return tiers[-1][1]
    else:
        # lower is better — anchors ordered from BEST raw (smallest) → WORST (largest)
        if raw <= tiers[0][0]:
            return tiers[0][1]
        if raw >= tiers[-1][0]:
            return tiers[-1][1]
        for i in range(len(tiers) - 1):
            lo_raw, lo_score = tiers[i]
            hi_raw, hi_score = tiers[i + 1]
            if lo_raw <= raw <= hi_raw:
                t = (raw - lo_raw) / max(1e-9, hi_raw - lo_raw)
                return lo_score + t * (hi_score - lo_score)
        return tiers[-1][1]


def sub_score_tent(raw, spec):
    """Two-sided tent function. Score peaks at `ideal`, falls off either side.

    `spec['tiers']` holds (half_width, sub_score) anchors for the boundaries
    *after* the ideal — i.e. the VG/Good, Good/Yellow, Yellow/Bad and
    Bad/V.Bad edges (doc §7.1 band edges: 90 / 75 / 60 / 40), plus a final
    floor anchor (0). The ideal itself is an implicit (0, 100) anchor so the
    very-good band also interpolates linearly from the peak down to its own
    edge — matching how the one-sided formula (and the doc's own worked
    knee-valgus example in §7.1) linearly interpolates *within* every band,
    not just between them.
    """
    if raw is None:
        return None
    ideal = spec['ideal']
    delta = abs(raw - ideal)
    anchors = [(0.0, 100.0)] + list(spec['tiers'])
    if delta <= anchors[0][0]:
        return anchors[0][1]
    if delta >= anchors[-1][0]:
        return anchors[-1][1]
    for i in range(len(anchors) - 1):
        lo_hw, lo_score = anchors[i]
        hi_hw, hi_score = anchors[i + 1]
        if lo_hw <= delta <= hi_hw:
            t = (delta - lo_hw) / max(1e-9, hi_hw - lo_hw)
            return lo_score + t * (hi_score - lo_score)
    return anchors[-1][1]


def compute_sub_score(raw, spec):
    """Dispatcher that handles either spec mode."""
    if raw is None or spec is None:
        return None
    if spec.get('mode') == 'tent':
        s = sub_score_tent(raw, spec)
    else:
        s = sub_score_one_sided(raw, spec)
    if s is None:
        return None
    return max(0.0, min(100.0, float(s)))


def tier_from_subscore(s):
    """Bucket a 0-100 sub-score into one of the 5 tier labels."""
    if s is None:
        return 'bad'
    if s >= _TIER_GOOD:    return 'very_good'
    if s >= _TIER_YELLOW:  return 'good'
    if s >= _TIER_BAD:     return 'yellow_flag'
    if s >= _TIER_VERY_BAD:return 'bad'
    return 'very_bad'


# ════════════════════════════════════════════════════════════════════
#  SECTION C — Category weights (doc §7.2)
# ════════════════════════════════════════════════════════════════════

WEIGHTS = {
    'safety':      {'knee_valgus': 15, 'butt_wink': 15,
                    'heel_contact': 5,  'spinal_align': 5},
    'technique':   {'depth': 15,        'torso_angle': 10,
                    'bar_path': 10,     'lat_hip_shift': 5},
    'performance': {'bar_tilt': 3,      'ecc_tempo': 4,
                    'con_tempo': 4,     'consistency': 9},
}

# Metrics tracked & displayed but not in the composite (informational).
INFORMATIONAL_METRICS = (
    'hip_bar_align', 'shin_angle', 'knee_flexion',
    'stance_width', 'toe_out', 'shoulder_sym',
)


# ════════════════════════════════════════════════════════════════════
#  SECTION D — Composite + safety hard-fail overrides (doc §7.3, §7.4)
# ════════════════════════════════════════════════════════════════════

def compute_composite(sub_scores):
    """Apply category weights + hard-fail overrides.

    Args:
        sub_scores: dict[metric_slug] → 0-100 (may contain None).
    Returns:
        (composite_int, list_of_override_notes)
    """
    total = 0.0
    total_weight = 0
    for cat, weights in WEIGHTS.items():
        for m, w in weights.items():
            s = sub_scores.get(m)
            if s is None:
                continue
            total += w * s
            total_weight += w
    composite = total / max(1, total_weight)

    notes = []
    safety_subs = [sub_scores.get(m) for m in WEIGHTS['safety']
                   if sub_scores.get(m) is not None]
    crit = sum(1 for s in safety_subs if s < _TIER_VERY_BAD)
    if crit >= 2:
        composite = min(composite, 40.0)
        notes.append('Two or more safety metrics critical — capped at 40 (doc §7.4).')
    elif crit >= 1:
        composite = min(composite, 55.0)
        notes.append('A safety metric flagged critical — capped at 55 (doc §7.4).')

    # Specific overrides (doc §7.4: butt wink / valgus >20° → cap at 50).
    # With the corrected VALGUS_SPEC/BUTT_WINK_SPEC anchors, raw==20° maps
    # to sub_score==40 exactly, so "< 40" fires precisely for raw > 20°.
    wink = sub_scores.get('butt_wink')
    if wink is not None and wink < _TIER_VERY_BAD:
        composite = min(composite, 50.0)
        notes.append('Excessive lumbar flexion under load — capped at 50.')
    valgus = sub_scores.get('knee_valgus')
    if valgus is not None and valgus < _TIER_VERY_BAD:
        composite = min(composite, 50.0)
        notes.append('Sustained knee valgus — capped at 50.')

    return int(round(composite)), notes


# ════════════════════════════════════════════════════════════════════
#  SECTION D.1 — composite_score UI payload (doc §7–§8, §11.4)
# ════════════════════════════════════════════════════════════════════
#
# The frontend's `CompositeBreakdown` component (ResultPage.tsx) only
# renders when `ExerciseResult.composite_score` is present — this is the
# doc's Safety/Technique/Performance category bars, grade letter, hard-fail
# override banner, and "two lowest sub-scores" corrective cues (§11.4).
# Everything below packages the composite math already computed above
# into that shape; it doesn't change any scoring.

CATEGORY_WEIGHTS = {'Safety': 0.40, 'Technique': 0.40, 'Performance': 0.20}

CUE_TEXT = {
    'knee_valgus':   'Track knees over toes — add band walks / glute-med activation before your next session.',
    'butt_wink':     'Stop the descent before the pelvis tucks under; likely a hip or ankle mobility limit.',
    'heel_contact':  'Drive through mid-foot/heel throughout — check ankle mobility or a slight heel lift.',
    'spinal_align':  'Brace harder and check for uneven loading (grip, stance, or bar re-rack).',
    'depth':         'Work on hitting full depth — mobility drills or a lighter warm-up ramp.',
    'torso_angle':   'Adjust bar position / stance so torso lean matches your squat style.',
    'bar_path':      'Keep the bar stacked over mid-foot — brace before the descent starts.',
    'lat_hip_shift': 'Check for a strength or mobility asymmetry between sides.',
    'bar_tilt':      'Level the bar before unracking; check for uneven plate loading.',
    'ecc_tempo':     'Control the descent — avoid dropping into the hole.',
    'con_tempo':     'Drive up with consistent bar speed; avoid grinding stalls.',
    'consistency':   'Standardize depth and tempo rep-to-rep — fatigue may be creeping in.',
}


def grade_from_composite(score):
    """Doc §8 grade + label mapping."""
    if score >= _TIER_GOOD:    return 'A', 'Very Good'
    if score >= _TIER_YELLOW:  return 'B', 'Good'
    if score >= _TIER_BAD:     return 'C', 'Yellow Flag'
    if score >= _TIER_VERY_BAD:return 'D', 'Bad'
    return 'E', 'Very Bad'


def _category_score(sub_scores, cat_key):
    """Weighted mean of one category's metrics, renormalised over the
    metrics actually available (doc §7.2)."""
    weights = WEIGHTS[cat_key]
    total, wsum = 0.0, 0
    for m, w in weights.items():
        s = sub_scores.get(m)
        if s is None:
            continue
        total += w * s
        wsum += w
    return (total / wsum) if wsum else None


def _evaluate_overrides(sub_scores, raw_lookup, variant):
    """Doc §7.4 hard-fail safety overrides, evaluated at the set level and
    returned as structured `SafetyOverride` records (vs. compute_composite's
    plain-text notes, used for the per-rep composite)."""
    safety_subs = {m: sub_scores.get(m) for m in WEIGHTS['safety']
                   if sub_scores.get(m) is not None}
    crit_keys = [k for k, v in safety_subs.items() if v < _TIER_VERY_BAD]
    worst_key = min(crit_keys, key=lambda k: safety_subs[k]) if crit_keys else None

    overrides = [
        {
            'condition': 'Any Safety metric scores <40 (Bad/Very Bad)',
            'cap': 55,
            'triggered': len(crit_keys) >= 1,
            'triggering_metric': _metric_label(variant, worst_key) if worst_key else None,
            'triggering_value': f"{round(safety_subs[worst_key])}/100" if worst_key else None,
        },
        {
            'condition': 'Two or more Safety metrics score <40',
            'cap': 40,
            'triggered': len(crit_keys) >= 2,
            'triggering_metric': ', '.join(_metric_label(variant, k) for k in crit_keys) if len(crit_keys) >= 2 else None,
            'triggering_value': None,
        },
    ]

    wink = sub_scores.get('butt_wink')
    wink_hit = wink is not None and wink < _TIER_VERY_BAD
    wink_raw = raw_lookup.get('butt_wink')
    overrides.append({
        'condition': 'Butt wink / posterior pelvic tilt >20° under load',
        'cap': 50,
        'triggered': wink_hit,
        'triggering_metric': _metric_label(variant, 'butt_wink') if wink_hit else None,
        'triggering_value': f"{wink_raw:.1f}°" if (wink_hit and wink_raw is not None) else None,
    })

    valgus = sub_scores.get('knee_valgus')
    valgus_hit = valgus is not None and valgus < _TIER_VERY_BAD
    valgus_raw = raw_lookup.get('knee_valgus')
    overrides.append({
        'condition': 'Sustained knee valgus >20°',
        'cap': 50,
        'triggered': valgus_hit,
        'triggering_metric': _metric_label(variant, 'knee_valgus') if valgus_hit else None,
        'triggering_value': f"{valgus_raw:.1f}°" if (valgus_hit and valgus_raw is not None) else None,
    })

    return overrides


_COMPOSITE_SLUGS = (set(WEIGHTS['safety']) | set(WEIGHTS['technique'])
                     | set(WEIGHTS['performance']))


def _build_composite_score(set_score, set_subs, rep_composites, raw_lookup, variant):
    """Assemble the `CompositeScore` payload (frontend/src/data/types.ts)."""
    grade, label = grade_from_composite(set_score)

    categories = []
    for name, key in (('Safety', 'safety'), ('Technique', 'technique'), ('Performance', 'performance')):
        score = _category_score(set_subs, key)
        categories.append({
            'name': name,
            'weight': CATEGORY_WEIGHTS[name],
            'score': round(score, 1) if score is not None else 0.0,
        })

    overrides = _evaluate_overrides(set_subs, raw_lookup, variant)
    triggered_caps = [o['cap'] for o in overrides if o['triggered']]
    active_cap = min(triggered_caps) if triggered_caps else None

    ranked = sorted(
        ((k, v) for k, v in set_subs.items() if v is not None and k in _COMPOSITE_SLUGS),
        key=lambda kv: kv[1],
    )
    lowest_sub_scores = [
        {'metric': _metric_label(variant, k), 'sub_score': round(float(v), 1),
         'cue': CUE_TEXT.get(k, 'Focus on this metric next session.')}
        for k, v in ranked[:2]
    ]

    if rep_composites:
        mean_c = sum(rep_composites) / len(rep_composites)
        worst_c = min(rep_composites)
        last3 = rep_composites[-3:] if len(rep_composites) >= 3 else rep_composites
        last3_mean = sum(last3) / len(last3)
        deteriorating = [i + 1 for i, c in enumerate(rep_composites) if c < mean_c - 15]
    else:
        mean_c = worst_c = last3_mean = float(set_score)
        deteriorating = []

    return {
        'composite': set_score,
        'grade': grade,
        'label': label,
        'composite_method': 'arithmetic',
        'categories': categories,
        'overrides': overrides,
        'active_cap': active_cap,
        'lowest_sub_scores': lowest_sub_scores,
        'aggregation': {
            'mean': round(mean_c, 1),
            'worst': round(worst_c, 1),
            'last_three': round(last3_mean, 1),
            'deteriorating_rep_nums': deteriorating,
        },
        'variant': variant,
    }


# ════════════════════════════════════════════════════════════════════
#  SECTION E — Per-frame extractors (doc §12.5)
# ════════════════════════════════════════════════════════════════════

SQUAT_CONNECTIONS = [
    (11, 12),                       # shoulders
    (11, 23), (12, 24), (23, 24),   # torso + pelvis
    (23, 25), (25, 27), (27, 29), (27, 31),
    (24, 26), (26, 28), (28, 30), (28, 32),
]


def _pick_side(frames, w, h):
    """Choose the dominant visible side for sagittal analysis (doc §12.3 pt 2)."""
    left_vis = window_landmark_quality(
        frames, [LM['LEFT_HIP'], LM['LEFT_KNEE'], LM['LEFT_ANKLE'],
                 LM['LEFT_SHOULDER'], LM['LEFT_HEEL'], LM['LEFT_FOOT_INDEX']])
    right_vis = window_landmark_quality(
        frames, [LM['RIGHT_HIP'], LM['RIGHT_KNEE'], LM['RIGHT_ANKLE'],
                 LM['RIGHT_SHOULDER'], LM['RIGHT_HEEL'], LM['RIGHT_FOOT_INDEX']])
    return 'LEFT' if left_vis >= right_vis else 'RIGHT'


def _baseline_index(hip_y_signal):
    """Find the standing-reference frame (first local max of hip_y_signal,
    i.e. earliest top of rep)."""
    if not hip_y_signal:
        return 0
    smoothed = moving_average(hip_y_signal, max(5, len(hip_y_signal) // 30))
    # In image coords, smaller y = higher position. Standing = min(y).
    min_idx = 0
    min_val = float('inf')
    for i, v in enumerate(smoothed):
        if v is None:
            continue
        if v < min_val:
            min_val = v
            min_idx = i
        # bail once we've descended substantially (>10% of range) from the
        # initial standing posture, so we lock onto the *first* standing top
        if min_val < float('inf') and v > min_val + 0.1 * abs(min_val):
            break
    return min_idx


def _compute_side_frame(lm, w, h, side_key, px_per_cm):
    """Per-frame measurements from the sagittal (side) view.

    Returns dict of measurements + per-metric landmark quality. Missing
    landmarks yield None for the dependent measurement.
    """
    hip   = get_lm(lm, LM[f'{side_key}_HIP'],    w, h)
    knee  = get_lm(lm, LM[f'{side_key}_KNEE'],   w, h)
    ankle = get_lm(lm, LM[f'{side_key}_ANKLE'],  w, h)
    heel  = get_lm(lm, LM[f'{side_key}_HEEL'],   w, h)
    toe   = get_lm(lm, LM[f'{side_key}_FOOT_INDEX'], w, h)
    shldr = get_lm(lm, LM[f'{side_key}_SHOULDER'], w, h)

    def _xy(p): return None if p is None else (p[0], p[1])

    out = {
        'hip_y':       hip[1]   if hip   else None,
        'knee_y':      knee[1]  if knee  else None,
        'ankle_y':     ankle[1] if ankle else None,
        'heel_y':      heel[1]  if heel  else None,
        'toe_y':       toe[1]   if toe   else None,
        'shoulder_y':  shldr[1] if shldr else None,
        'shoulder_x':  shldr[0] if shldr else None,
        'hip_x':       hip[0]   if hip   else None,

        # cm-scale measurements (None when calibration missing or landmarks gone)
        'depth_cm':            None,
        'heel_lift_cm':        None,
        'hip_bar_x_offset_cm': None,

        # angles (deg)
        'torso_deg':       None,
        'shin_deg':        None,
        'knee_flex_deg':   None,
        'pelvic_line_deg': None,

        # quality of the joints feeding this frame's measurements
        'q_hipknee':   landmark_quality(lm, [LM[f'{side_key}_HIP'], LM[f'{side_key}_KNEE']]),
        'q_legchain':  landmark_quality(lm, [LM[f'{side_key}_HIP'], LM[f'{side_key}_KNEE'], LM[f'{side_key}_ANKLE']]),
        'q_torso':     landmark_quality(lm, [LM[f'{side_key}_HIP'], LM[f'{side_key}_SHOULDER']]),
        'q_foot':      landmark_quality(lm, [LM[f'{side_key}_HEEL'], LM[f'{side_key}_FOOT_INDEX']]),
    }

    if hip and knee and px_per_cm:
        # Doc §12.5 metric 1: negative = hip below knee = good.
        # Image coords: hip BELOW knee ⇒ hip_y > knee_y, so the spec's
        # negative-is-deep convention needs (knee_y − hip_y). The previous
        # (hip_y − knee_y) inverted the sign, and min() over the window then
        # picked the STANDING frame (hip far above knee) as "depth" — every
        # squat measured −30 cm+ 'very good' regardless of actual depth.
        out['depth_cm'] = (knee[1] - hip[1]) / px_per_cm

    if heel and toe and px_per_cm:
        # Doc §12.5 metric 6: heel_y < toe_y (heel higher in frame, smaller y) → heel lifted
        out['heel_lift_cm'] = (toe[1] - heel[1]) / px_per_cm

    if shldr and ankle and px_per_cm:
        # Doc §12.5 metric 4 intent: bar balance over the midfoot. The bar
        # rides at shoulder level, so |shoulder_x − ankle_x| measures how
        # far the load drifts off the base of support. (Measuring against
        # the HIP just re-measured torso lean — 16 cm for any correctly
        # inclined torso, an automatic fail.)
        out['hip_bar_x_offset_cm'] = abs(shldr[0] - ankle[0]) / px_per_cm

    if shldr and hip:
        # Doc §12.5 metric 2: forward LEAN of the torso from vertical.
        # angle_to_vertical measures from the DOWNWARD vertical, and the
        # hip→shoulder vector points UP, so an upright torso reads ~180°
        # and the lean is (180 − value) — the raw value reported 154° for
        # a 26° lean.
        atv = angle_to_vertical(_xy(hip), _xy(shldr))
        out['torso_deg'] = (180.0 - atv) if atv is not None else None
        out['pelvic_line_deg'] = out['torso_deg']

    if knee and ankle:
        # Doc §12.5 metric 7: forward shin inclination from vertical
        # (same convention correction as the torso).
        atv = angle_to_vertical(_xy(ankle), _xy(knee))
        out['shin_deg'] = (180.0 - atv) if atv is not None else None

    if hip and knee and ankle:
        # Doc §12.5 metric 8: knee angle (3-point).
        out['knee_flex_deg'] = angle_3pt(_xy(hip), _xy(knee), _xy(ankle))

    return out


def _compute_front_frame(lm, w, h, px_per_cm):
    """Per-frame measurements from the frontal (front) view."""
    l_hip = get_lm(lm, LM['LEFT_HIP'],   w, h)
    r_hip = get_lm(lm, LM['RIGHT_HIP'],  w, h)
    l_kn  = get_lm(lm, LM['LEFT_KNEE'],  w, h)
    r_kn  = get_lm(lm, LM['RIGHT_KNEE'], w, h)
    l_an  = get_lm(lm, LM['LEFT_ANKLE'], w, h)
    r_an  = get_lm(lm, LM['RIGHT_ANKLE'],w, h)
    l_he  = get_lm(lm, LM['LEFT_HEEL'],  w, h)
    r_he  = get_lm(lm, LM['RIGHT_HEEL'], w, h)
    l_fi  = get_lm(lm, LM['LEFT_FOOT_INDEX'],  w, h)
    r_fi  = get_lm(lm, LM['RIGHT_FOOT_INDEX'], w, h)
    l_sh  = get_lm(lm, LM['LEFT_SHOULDER'],  w, h)
    r_sh  = get_lm(lm, LM['RIGHT_SHOULDER'], w, h)

    def _xy(p): return None if p is None else (p[0], p[1])

    out = {
        'hip_y':              None,
        'l_valgus_deg':       None,
        'r_valgus_deg':       None,
        'l_knee_flex_deg':    None,
        'r_knee_flex_deg':    None,
        'lat_hip_shift_cm':   None,
        'bar_tilt_deg':       None,
        'spinal_lateral_deg': None,
        'shoulder_diff_cm':   None,
        'l_toe_out_deg':      None,
        'r_toe_out_deg':      None,
        'stance_ratio':       None,
        'knee_dist_px':       None,
        'ankle_dist_px':      None,
        'shoulder_dist_px':   None,
        'q_legs':       landmark_quality(lm, [LM['LEFT_KNEE'], LM['RIGHT_KNEE'],
                                              LM['LEFT_ANKLE'], LM['RIGHT_ANKLE'],
                                              LM['LEFT_HIP'], LM['RIGHT_HIP']]),
        'q_shoulders':  landmark_quality(lm, [LM['LEFT_SHOULDER'], LM['RIGHT_SHOULDER']]),
        'q_feet':       landmark_quality(lm, [LM['LEFT_HEEL'], LM['RIGHT_HEEL'],
                                              LM['LEFT_FOOT_INDEX'], LM['RIGHT_FOOT_INDEX']]),
    }

    if l_hip and r_hip:
        out['hip_y'] = (l_hip[1] + r_hip[1]) / 2.0
        hip_cx = (l_hip[0] + r_hip[0]) / 2.0
        # Doc §12.5 metric 12 — lateral hip shift vs feet midline.
        if l_an and r_an and px_per_cm:
            feet_cx = (l_an[0] + r_an[0]) / 2.0
            out['lat_hip_shift_cm'] = abs(hip_cx - feet_cx) / px_per_cm

    # Knee valgus per-leg — doc §12.5 metric 9 primary method
    # (MEDIAL deviation of knee from the hip→ankle line, as an angle).
    mid_hip_x = (l_hip[0] + r_hip[0]) / 2.0 if (l_hip and r_hip) else None
    if l_hip and l_kn and l_an:
        out['l_valgus_deg'] = _valgus_angle(l_hip, l_kn, l_an, mid_hip_x)
        out['l_knee_flex_deg'] = angle_3pt(_xy(l_hip), _xy(l_kn), _xy(l_an))
    if r_hip and r_kn and r_an:
        out['r_valgus_deg'] = _valgus_angle(r_hip, r_kn, r_an, mid_hip_x)
        out['r_knee_flex_deg'] = angle_3pt(_xy(r_hip), _xy(r_kn), _xy(r_an))

    # Doc §12.5 metric 10 — stance width.
    if l_an and r_an:
        out['ankle_dist_px'] = abs(l_an[0] - r_an[0])
    if l_kn and r_kn:
        out['knee_dist_px'] = abs(l_kn[0] - r_kn[0])
    if l_sh and r_sh:
        out['shoulder_dist_px'] = abs(l_sh[0] - r_sh[0])
        # Doc §12.5 metric 13 — bar tilt (shoulder-line angle).
        out['bar_tilt_deg'] = abs(math.degrees(
            math.atan2(r_sh[1] - l_sh[1], r_sh[0] - l_sh[0])))
        # Doc §12.5 metric 15 — shoulder height symmetry.
        if px_per_cm:
            out['shoulder_diff_cm'] = abs(l_sh[1] - r_sh[1]) / px_per_cm
        # Doc §12.5 metric 14 — spine lateral deviation (fallback from front).
        # hip→shoulder points UP: signed_angle_from_vertical reads ~±180 for
        # a perfectly straight spine, so the lateral lean is 180 − |angle|
        # (the raw value reported 179.9° for an upright torso).
        if l_hip and r_hip:
            sh_mid = ((l_sh[0] + r_sh[0]) / 2.0, (l_sh[1] + r_sh[1]) / 2.0)
            hp_mid = ((l_hip[0] + r_hip[0]) / 2.0, (l_hip[1] + r_hip[1]) / 2.0)
            out['spinal_lateral_deg'] = 180.0 - abs(signed_angle_from_vertical(hp_mid, sh_mid))

    if out['ankle_dist_px'] and out['shoulder_dist_px']:
        out['stance_ratio'] = out['ankle_dist_px'] / max(1e-6, out['shoulder_dist_px'])

    # Doc §12.5 metric 11 — toe-out angle. Approximate from front projection.
    if l_he and l_fi:
        out['l_toe_out_deg'] = _toe_out_from_xy(l_he, l_fi)
    if r_he and r_fi:
        out['r_toe_out_deg'] = _toe_out_from_xy(r_he, r_fi)

    return out


def _valgus_angle(hip, knee, ankle, mid_hip_x=None):
    """Frontal-plane valgus angle — MEDIAL deviation only.

    Builds the expected knee X via linear interpolation between hip and ankle
    (at knee_y height), then converts the X deviation into degrees relative
    to the femur length (doc §12.5 metric 9 primary method).

    Valgus is the knee collapsing TOWARD the body midline. The old abs()
    counted varus / knees-out (good form) as "valgus" too, which flagged
    25° on a clean demo squat. With `mid_hip_x` the deviation is signed and
    only the medial component is returned; without it, falls back to |dev|.
    """
    if hip is None or knee is None or ankle is None:
        return None
    hx, hy = hip[0], hip[1]
    kx, ky = knee[0], knee[1]
    ax, ay = ankle[0], ankle[1]
    span = ay - hy
    if abs(span) < 1e-6:
        return 0.0
    t = (ky - hy) / span
    expected_x = hx + t * (ax - hx)
    deviation_px = kx - expected_x       # +ve = knee to the right of the line
    leg_segment = max(1.0, math.hypot(kx - hx, ky - hy))
    if mid_hip_x is not None:
        medial_sign = 1.0 if (mid_hip_x - ax) >= 0 else -1.0
        medial_px = deviation_px * medial_sign   # +ve = toward midline
        return max(0.0, math.degrees(math.atan2(medial_px, leg_segment)))
    return abs(math.degrees(math.atan2(deviation_px, leg_segment)))


def _toe_out_from_xy(heel, foot_index):
    """Toe-out angle from 2D heel→foot vector vs the +x (forward) axis."""
    if heel is None or foot_index is None:
        return None
    dx = foot_index[0] - heel[0]
    dy = foot_index[1] - heel[1]
    # MediaPipe ground-plane projection in front view: most of the foot
    # vector lies along the depth axis we can't see, so the visible X
    # component is the toe-out signal. Use atan2(|x|, |y|) as a proxy.
    # A camera at knee height foreshortens the depth (y) component to
    # almost nothing, which inflates any real toe-out toward 90° (a clean
    # 20° stance read 55°). When the visible x-extent dominates the
    # y-extent the projection carries no usable angle — unmeasurable.
    if abs(dx) > abs(dy):
        return None
    return abs(math.degrees(math.atan2(abs(dx), max(1e-3, abs(dy)))))


# ════════════════════════════════════════════════════════════════════
#  SECTION F — Per-rep aggregation
# ════════════════════════════════════════════════════════════════════

def _ecc_con_tempo(hip_y_window, fps):
    """Return (eccentric_sec, concentric_sec) from a per-rep hip_y window."""
    vals = [v for v in hip_y_window if v is not None]
    if len(vals) < 4:
        return None, None
    # bottom = max hip_y (lowest position in image coords)
    bot_idx = max(range(len(hip_y_window)),
                  key=lambda i: hip_y_window[i] if hip_y_window[i] is not None else -1)
    ecc = bot_idx / fps
    con = max(0.0, (len(hip_y_window) - bot_idx) / fps)
    return ecc, con


def _cv_pct(values):
    """Coefficient of variation (%) — used for the consistency metric."""
    vs = [v for v in values if v is not None]
    if len(vs) < 2:
        return None
    mean = sum(vs) / len(vs)
    if abs(mean) < 1e-6:
        return None
    var = sum((v - mean) ** 2 for v in vs) / len(vs)
    return math.sqrt(var) / abs(mean) * 100.0


def _aggregate_side_rep(per_frame, rep, fps, baseline):
    """Build a rep dict of metric raw values from the side per-frame series.

    `per_frame` is a list of dicts (length = total frames).
    `rep`       is the {start_frame, end_frame, peak_frame, peak_value} from rep_detection.
    `baseline`  is a dict of standing-reference values.
    """
    start, end = rep['start_frame'], rep['end_frame']
    window = per_frame[start:end + 1]

    # Bottom frame within window — min hip_y in image coords is the highest position;
    # max hip_y is the deepest. We use detect_reps_minima on hip_y above so peak_frame
    # already corresponds to the deepest frame.
    bot_idx_local = max(range(len(window)),
                        key=lambda i: window[i].get('hip_y') or -1)
    bot = window[bot_idx_local]

    # Depth — best (most negative) across the window.
    depth_values = [f['depth_cm'] for f in window if f['depth_cm'] is not None]
    depth_cm = min(depth_values) if depth_values else None

    # Torso, butt wink, hip-bar, knee flex, shin — value at the bottom frame.
    torso_deg = bot.get('torso_deg')
    knee_flex_deg = bot.get('knee_flex_deg')
    shin_deg = bot.get('shin_deg')
    hip_bar_cm = bot.get('hip_bar_x_offset_cm')

    # Butt wink = the EXTRA torso-line rotation that appears in the last
    # part of the descent (the pelvis tucking under at the very bottom).
    # Comparing bottom vs STANDING measures the entire intentional forward
    # lean (~25–35°) and flagged every deep squat. Instead: compare the
    # torso angle at the bottom against the torso angle when the hip first
    # reached 85% of this rep's depth — extra rotation in that final 15%
    # of descent is the wink signature.
    butt_wink_deg = None
    hip_ys = [f.get('hip_y') for f in window]
    valid_hips = [(i, y) for i, y in enumerate(hip_ys) if y is not None]
    bw_bot = bot.get('torso_deg')
    if bw_bot is not None and len(valid_hips) > 3:
        top_y = min(y for _, y in valid_hips)
        bot_y = hip_ys[bot_idx_local] if hip_ys[bot_idx_local] is not None else max(y for _, y in valid_hips)
        threshold_y = top_y + 0.85 * (bot_y - top_y)
        ref_angle = None
        for i, y in valid_hips:
            if i >= bot_idx_local:
                break
            if y >= threshold_y and window[i].get('torso_deg') is not None:
                ref_angle = window[i]['torso_deg']
                break
        if ref_angle is not None:
            butt_wink_deg = max(0.0, bw_bot - ref_angle)

    # Heel lift — duration in seconds where heel_lift_cm > 1.0 cm above the
    # standing baseline. Only trustworthy when the foot landmarks are
    # actually SEEN: in a sagittal barbell video the plate occludes the
    # feet, MediaPipe hallucinates them, and phantom 'lifts' covered 70% of
    # the rep. Gate on foot-landmark quality.
    q_foot_window = [f.get('q_foot', 0.0) for f in window]
    avg_q_foot = sum(q_foot_window) / max(1, len(q_foot_window))
    heel_vals = sorted(f['heel_lift_cm'] for f in window
                       if f.get('heel_lift_cm') is not None)
    if avg_q_foot < 0.5 or len(heel_vals) < 5:
        heel_lift_sec = None      # unmeasurable — excluded from scoring
    else:
        # Baseline = the foot's NATURAL heel-toe landmark offset. The
        # standing-frame baseline is often None (plate occludes the feet
        # early in the clip) and `or 0.0` then counted the natural ~2 cm
        # offset as a permanent lift (3.5 s of phantom heel-lift per rep).
        # The median across the rep is that natural offset — the heel is
        # planted most of the time.
        base_heel = baseline.get('heel_lift_cm')
        if base_heel is None:
            base_heel = heel_vals[len(heel_vals) // 2]
        heel_lift_frames = sum(
            1 for f in window
            if f.get('heel_lift_cm') is not None and (f['heel_lift_cm'] - base_heel) > 1.0
        )
        heel_lift_sec = heel_lift_frames / max(1.0, fps)

    # Tempo — eccentric and concentric times.
    hip_y_series = [f.get('hip_y') for f in window]
    ecc_sec, con_sec = _ecc_con_tempo(hip_y_series, fps)

    return {
        'depth_cm':         depth_cm,
        'torso_deg':        torso_deg,
        'butt_wink_deg':    butt_wink_deg,
        'heel_lift_sec':    heel_lift_sec,
        'shin_deg':         shin_deg,
        'knee_flex_deg':    knee_flex_deg,
        'hip_bar_cm':       hip_bar_cm,
        'ecc_sec':          ecc_sec,
        'con_sec':          con_sec,
        'bot_frame':        start + bot_idx_local,
        'q_legchain':       bot.get('q_legchain', 0.0),
        'q_torso':          bot.get('q_torso', 0.0),
        'q_foot':           bot.get('q_foot', 0.0),
    }


def _aggregate_front_rep(per_frame, rep, baseline):
    start, end = rep['start_frame'], rep['end_frame']
    window = per_frame[start:end + 1]
    bot_idx_local = max(range(len(window)),
                        key=lambda i: window[i].get('hip_y') or -1)
    bot = window[bot_idx_local]

    def _max_abs(key):
        vals = [abs(f[key]) for f in window if f.get(key) is not None]
        return max(vals) if vals else None

    # Worst-frame valgus + worst-frame hip shift + worst-frame bar tilt (doc §11.2).
    # Valgus is baseline-subtracted: a standing FPPA offset (anatomy or
    # slight camera yaw) is not dynamic knee collapse.
    l_valgus = _max_abs('l_valgus_deg')
    r_valgus = _max_abs('r_valgus_deg')
    if l_valgus is not None and baseline.get('l_valgus_deg') is not None:
        l_valgus = max(0.0, l_valgus - baseline['l_valgus_deg'])
    if r_valgus is not None and baseline.get('r_valgus_deg') is not None:
        r_valgus = max(0.0, r_valgus - baseline['r_valgus_deg'])
    lat_shift = _max_abs('lat_hip_shift_cm')
    bar_tilt = _max_abs('bar_tilt_deg')

    # Baseline-subtract bar tilt and lat shift (so a naturally tilted athlete
    # doesn't get penalized).
    if bar_tilt is not None and baseline.get('bar_tilt_deg') is not None:
        bar_tilt = max(0.0, bar_tilt - baseline['bar_tilt_deg'])
    if lat_shift is not None and baseline.get('lat_hip_shift_cm') is not None:
        lat_shift = max(0.0, lat_shift - baseline['lat_hip_shift_cm'])

    spinal = _max_abs('spinal_lateral_deg')
    shoulder_diff = _max_abs('shoulder_diff_cm')

    # Stance + toe-out are setup measurements — take baseline values.
    stance = baseline.get('stance_ratio')
    l_toe = baseline.get('l_toe_out_deg')
    r_toe = baseline.get('r_toe_out_deg')

    return {
        'l_valgus_deg':       l_valgus,
        'r_valgus_deg':       r_valgus,
        'l_knee_flex_deg':    bot.get('l_knee_flex_deg'),
        'r_knee_flex_deg':    bot.get('r_knee_flex_deg'),
        'lat_hip_shift_cm':   lat_shift,
        'bar_tilt_deg':       bar_tilt,
        'spinal_lateral_deg': spinal,
        'shoulder_diff_cm':   shoulder_diff,
        'l_toe_out_deg':      l_toe,
        'r_toe_out_deg':      r_toe,
        'stance_ratio':       stance,
        'bot_frame':          start + bot_idx_local,
        'q_legs':             bot.get('q_legs', 0.0),
        'q_shoulders':        bot.get('q_shoulders', 0.0),
        'q_feet':             bot.get('q_feet', 0.0),
    }


# ════════════════════════════════════════════════════════════════════
#  SECTION I (orchestrator) — Side + Front analysis pipelines
# ════════════════════════════════════════════════════════════════════

def _analyse_side(video_path, plate_size_kg, target_reps, variant):
    out = {
        'video_path': video_path,
        'available':  False,
        'reps':       [],
        'per_frame':  [],
        'frames':     [],
        'baseline':   {},
        'fps':        30.0,
        'w': 0, 'h': 0,
        'side_key':   'LEFT',
        'px_per_cm':  0.0,
        'plate_quality': 0.0,
        'reason_unavailable': None,
        'bar_centres': None,
    }
    if not video_path:
        out['reason_unavailable'] = 'No side video provided'
        return out

    try:
        result = extract_all_landmarks(video_path)
    except Exception as e:
        out['reason_unavailable'] = f'Landmark extraction failed: {e}'
        return out

    frames = result['frames']
    fps = result['fps']
    w, h = result['width'], result['height']

    out.update({'frames': frames, 'fps': fps, 'w': w, 'h': h})

    # Calibration via plate detection — fallback px_per_cm = 0 means cm-units
    # disabled (we still report pixel-relative metrics).
    bar_track = {}
    for attempt in (1, 2):
        try:
            bar_track = track_bar_path(video_path, plate_size_kg=plate_size_kg)
            break
        except Exception as e:
            print(f"[back_squat] side bar tracking failed (attempt {attempt}): {e}")
    px_per_cm = bar_track.get('px_per_cm') or 0.0
    out['px_per_cm'] = px_per_cm
    out['plate_quality'] = bar_track.get('median_quality', 0.0)
    out['bar_centres'] = bar_track.get('centres')

    side_key = _pick_side(frames, w, h)
    out['side_key'] = side_key

    per_frame = []
    for f in frames:
        lm = f.get('landmarks')
        if lm is None:
            per_frame.append({'hip_y': None, 'knee_y': None, 'ankle_y': None,
                              'heel_y': None, 'toe_y': None, 'shoulder_y': None,
                              'shoulder_x': None, 'hip_x': None,
                              'depth_cm': None, 'heel_lift_cm': None,
                              'hip_bar_x_offset_cm': None,
                              'torso_deg': None, 'shin_deg': None,
                              'knee_flex_deg': None, 'pelvic_line_deg': None,
                              'q_hipknee': 0.0, 'q_legchain': 0.0,
                              'q_torso': 0.0, 'q_foot': 0.0})
            continue
        per_frame.append(_compute_side_frame(lm, w, h, side_key, px_per_cm))
    out['per_frame'] = per_frame

    # Baseline (standing reference) — first top of the hip_y trace.
    hip_y_signal = [f.get('hip_y') for f in per_frame]
    base_idx = _baseline_index(hip_y_signal)
    out['baseline'] = {k: per_frame[base_idx].get(k) for k in
                       ('torso_deg', 'pelvic_line_deg', 'heel_lift_cm')}

    # Rep detection — bottoms of hip_y signal (image coords: bottom = max).
    expected = max(1, target_reps or 3)
    hip_for_detection = [v if v is not None else hip_y_signal[max(0, i - 1)]
                         for i, v in enumerate(hip_y_signal)]
    reps_raw = detect_reps_minima(  # signal: invert sign so peaks → valleys
        [-v if v is not None else 0.0 for v in hip_for_detection],
        expected_reps=expected, fps=fps)
    # Flip back peak_value to original hip_y scale and re-key consistently
    for r in reps_raw:
        r['peak_value'] = -r['peak_value']

    # Filter degenerate reps (length too small)
    min_len = max(int(fps * 0.5), 6)
    reps_raw = [r for r in reps_raw if (r['end_frame'] - r['start_frame']) >= min_len]

    out['reps'] = reps_raw
    out['available'] = True
    return out


def _analyse_front(video_path, target_reps):
    out = {
        'video_path': video_path,
        'available':  False,
        'reps':       [],
        'per_frame':  [],
        'frames':     [],
        'baseline':   {},
        'fps':        30.0,
        'w': 0, 'h': 0,
        'px_per_cm':  0.0,
        'reason_unavailable': None,
    }
    if not video_path:
        out['reason_unavailable'] = 'No front video provided'
        return out
    try:
        result = extract_all_landmarks(video_path)
    except Exception as e:
        out['reason_unavailable'] = f'Landmark extraction failed: {e}'
        return out

    frames = result['frames']
    fps = result['fps']
    w, h = result['width'], result['height']

    # px_per_cm via shoulder-width body-segment fallback. Plate detection from
    # the front view is unreliable (plates seen edge-on), so we approximate
    # using the front-cam shoulder distance as a ~38 cm proxy for adults.
    px_per_cm = 0.0
    try:
        from utils.angles import body_segment_lengths
        segs = body_segment_lengths(frames, w, h)
        if segs.get('torso_px'):
            # Adult torso (hip→shoulder) ≈ 50 cm.
            px_per_cm = segs['torso_px'] / 50.0
    except Exception as e:
        print(f"[back_squat] front segment fallback failed: {e}")

    out.update({'frames': frames, 'fps': fps, 'w': w, 'h': h, 'px_per_cm': px_per_cm})

    per_frame = []
    for f in frames:
        lm = f.get('landmarks')
        if lm is None:
            per_frame.append({'hip_y': None, 'l_valgus_deg': None, 'r_valgus_deg': None,
                              'l_knee_flex_deg': None, 'r_knee_flex_deg': None,
                              'lat_hip_shift_cm': None, 'bar_tilt_deg': None,
                              'spinal_lateral_deg': None, 'shoulder_diff_cm': None,
                              'l_toe_out_deg': None, 'r_toe_out_deg': None,
                              'stance_ratio': None,
                              'knee_dist_px': None, 'ankle_dist_px': None,
                              'shoulder_dist_px': None,
                              'q_legs': 0.0, 'q_shoulders': 0.0, 'q_feet': 0.0})
            continue
        per_frame.append(_compute_front_frame(lm, w, h, px_per_cm))
    out['per_frame'] = per_frame

    hip_y_signal = [f.get('hip_y') for f in per_frame]
    base_idx = _baseline_index(hip_y_signal)
    out['baseline'] = {k: per_frame[base_idx].get(k) for k in
                       ('bar_tilt_deg', 'lat_hip_shift_cm', 'stance_ratio',
                        'l_toe_out_deg', 'r_toe_out_deg',
                        'l_valgus_deg', 'r_valgus_deg')}

    expected = max(1, target_reps or 3)
    hip_for_detection = [v if v is not None else hip_y_signal[max(0, i - 1)]
                         for i, v in enumerate(hip_y_signal)]
    reps_raw = detect_reps_minima(
        [-v if v is not None else 0.0 for v in hip_for_detection],
        expected_reps=expected, fps=fps)
    for r in reps_raw:
        r['peak_value'] = -r['peak_value']
    min_len = max(int(fps * 0.5), 6)
    reps_raw = [r for r in reps_raw if (r['end_frame'] - r['start_frame']) >= min_len]

    out['reps'] = reps_raw
    out['available'] = True
    return out


# ════════════════════════════════════════════════════════════════════
#  SECTION I — analyse() main orchestrator
# ════════════════════════════════════════════════════════════════════

def analyse(files, plate_size_kg=None, weight_max=None, reps_max=None,
            target_reps=None, target_reps_side=None, target_reps_front=None,
            variant='high-bar'):
    """Back squat analyzer entry point — see module docstring."""
    try:
        return _analyse_dual_cam(
            files,
            plate_size_kg=plate_size_kg,
            weight_max=weight_max,
            reps_max=reps_max,
            target_reps_side=target_reps_side or target_reps,
            target_reps_front=target_reps_front or target_reps,
            variant=variant,
        )
    except Exception as e:
        traceback.print_exc()
        return _fallback(str(e))


def _analyse_dual_cam(files, plate_size_kg, weight_max, reps_max,
                      target_reps_side, target_reps_front, variant):
    # Normalise the variant against the spec doc's threshold tables.
    if variant not in ('low-bar', 'high-bar'):
        # Map legacy values to high-bar (doc's "Deep Squat" default).
        variant = 'high-bar'

    side_path = (files or {}).get('side')
    front_path = (files or {}).get('front')

    side = _analyse_side(side_path, plate_size_kg, target_reps_side, variant)
    front = _analyse_front(front_path, target_reps_front)

    if not side['available'] and not front['available']:
        return _fallback('Both videos failed to process — see logs.')

    # ── 1. Per-rep aggregation ────────────────────────────────────
    side_reps = []
    for i, r in enumerate(side['reps'], start=1):
        rep = _aggregate_side_rep(side['per_frame'], r, side['fps'], side['baseline'])
        rep['rep_num'] = i
        rep['peak_frame'] = r['peak_frame']
        rep['start_frame'] = r['start_frame']
        rep['end_frame'] = r['end_frame']
        # Bar path from plate tracker (cm) — falls back to shoulder-x range.
        rep['bar_path_cm'] = _rep_bar_path_cm(side, r['start_frame'], r['end_frame'])
        side_reps.append(rep)

    front_reps = []
    for i, r in enumerate(front['reps'], start=1):
        rep = _aggregate_front_rep(front['per_frame'], r, front['baseline'])
        rep['rep_num'] = i
        rep['peak_frame'] = r['peak_frame']
        rep['start_frame'] = r['start_frame']
        rep['end_frame'] = r['end_frame']
        front_reps.append(rep)

    n_reps = max(len(side_reps), len(front_reps))

    # ── 2. Sub-score per rep ──────────────────────────────────────
    per_rep_subs = []
    for i in range(n_reps):
        s_rep = side_reps[i] if i < len(side_reps) else None
        f_rep = front_reps[i] if i < len(front_reps) else None
        per_rep_subs.append(_score_rep(s_rep, f_rep, variant))

    # ── 3. Set composite (mean of rep composites) ─────────────────
    rep_composites = []
    rep_override_notes = set()
    for subs in per_rep_subs:
        comp, notes = compute_composite(subs)
        rep_composites.append(comp)
        for n in notes:
            rep_override_notes.add(n)

    if rep_composites:
        set_score = int(round(sum(rep_composites) / len(rep_composites)))
    else:
        set_score = 0

    # ── 4. Aggregate per-set sub-scores (mean) for the headline metrics ──
    set_subs = _mean_dict(per_rep_subs)

    # Consistency (CV across reps) — doc §6.3.
    set_subs['consistency'] = _consistency_subscore(side_reps, front_reps)

    # Recompute composite with consistency factored in.
    set_score_with_consistency, _ = compute_composite(set_subs)
    set_score = set_score_with_consistency or set_score

    set_status = _status_from_score(set_score)

    # ── 5. Build metric list ──────────────────────────────────────
    metrics, raw_lookup = _build_metric_list(per_rep_subs, side_reps, front_reps,
                                             side, front, variant, n_reps)

    # ── 6. Bilateral (front-cam) ──────────────────────────────────
    bilateral = _build_bilateral(front_reps)

    # ── 7. Coaching notes ─────────────────────────────────────────
    coaching = _coaching(set_subs, list(rep_override_notes), variant,
                          set_score, n_reps)

    # ── 8. Stats strip ────────────────────────────────────────────
    confidence_pct = round(_overall_confidence(side, front) * 100)
    stats = {
        'validReps':   f"{n_reps}/{max(target_reps_side or 3, target_reps_front or 3, n_reps)}",
        'confidence':  f"{confidence_pct}%",
        'sides':       _sides_label(side, front),
        'cameraView':  'OK' if confidence_pct >= 60 else 'WARNING',
        'style':       _style_label(variant),
        'sideReps':    f"{len(side_reps)}/{target_reps_side or 3}",
        'frontReps':   f"{len(front_reps)}/{target_reps_front or 3}",
        'calibration': 'plate' if (side.get('plate_quality') or 0) > 0.4 else 'segment-fallback',
        'load':        f"{weight_max} kg" if weight_max else 'bodyweight',
    }

    summary = _summary(set_subs, set_score, variant)

    # ── 9. Annotated frames ───────────────────────────────────────
    annotated = []
    try:
        if side['available']:
            annotated += _render_side_frames(side, side_reps, per_rep_subs,
                                             rep_composites, set_status, variant)
    except Exception as e:
        traceback.print_exc()
        print(f"[back_squat] side rendering failed: {e}")
    try:
        if front['available']:
            annotated += _render_front_frames(front, front_reps, per_rep_subs,
                                              rep_composites, set_status)
    except Exception as e:
        traceback.print_exc()
        print(f"[back_squat] front rendering failed: {e}")

    # ── 10. Fatigue series (UX extra) ─────────────────────────────
    fatigue_metrics = {}
    try:
        if side_reps:
            keys = ['depth_cm', 'torso_deg', 'butt_wink_deg',
                    'ecc_sec', 'con_sec', 'bar_path_cm']
            fatigue_metrics['side'] = aggregate_per_rep(side_reps, keys=keys)
        if front_reps:
            keys = ['l_valgus_deg', 'r_valgus_deg', 'lat_hip_shift_cm', 'bar_tilt_deg']
            fatigue_metrics['front'] = aggregate_per_rep(front_reps, keys=keys)
    except Exception as e:
        print(f"[back_squat] fatigue step skipped: {e}")

    # ── 11. Result ────────────────────────────────────────────────
    result = build_result(set_status, set_score, summary, stats,
                          metrics, bilateral, coaching)
    result['annotated_frames'] = annotated
    result['per_rep'] = _build_per_rep_dump(side_reps, front_reps, per_rep_subs, rep_composites)
    result['fatigue'] = fatigue_metrics
    result['composite_score'] = _build_composite_score(
        set_score, set_subs, rep_composites, raw_lookup, variant)
    result['meta'] = {
        'analyzer_version': ANALYZER_VERSION,
        'style': variant,
        'camera_view_side': 'side' if side['available'] else None,
        'camera_view_front': 'front' if front['available'] else None,
        'bar_track_quality_median': round(side.get('plate_quality', 0.0), 2),
    }

    # Muscle activation (UX extra) — feeds the body diagram.
    try:
        avg_torso = set_subs.get('_avg_torso_deg')
        # TTA proxy: positive = hip-dominant (low-bar), negative = quad (high-bar).
        tta = (avg_torso or 0) - (45 if variant == 'low-bar' else 20)
        max_heel = _max_raw(side_reps, 'heel_lift_sec') or 0.0
        max_wink = _max_raw(side_reps, 'butt_wink_deg') or 0.0
        result['muscle_activation'] = infer_squat(
            tta_deg=tta, variant=variant,
            heel_lift_cm=max_heel * 5.0, butt_wink_deg=max_wink,
        )
    except Exception as e:
        print(f"[back_squat] muscle inference skipped: {e}")
    return result


# ════════════════════════════════════════════════════════════════════
#  Per-rep scoring helper
# ════════════════════════════════════════════════════════════════════

def _score_rep(s_rep, f_rep, variant):
    """Convert one rep's raw values into a sub-score dict."""
    subs = {}

    if s_rep:
        subs['depth']         = compute_sub_score(s_rep['depth_cm'], DEPTH_SPEC[variant])
        subs['torso_angle']   = compute_sub_score(s_rep['torso_deg'], TORSO_SPEC[variant])
        subs['butt_wink']     = compute_sub_score(s_rep['butt_wink_deg'], BUTT_WINK_SPEC)
        subs['heel_contact']  = compute_sub_score(s_rep['heel_lift_sec'], HEEL_LIFT_TIME_SPEC)
        subs['shin_angle']    = compute_sub_score(s_rep['shin_deg'], SHIN_SPEC[variant])
        subs['knee_flexion']  = compute_sub_score(s_rep['knee_flex_deg'], KNEE_FLEX_SPEC[variant])
        subs['hip_bar_align'] = compute_sub_score(s_rep['hip_bar_cm'], HIP_BAR_ALIGN_SPEC)
        subs['bar_path']      = compute_sub_score(s_rep.get('bar_path_cm'), BAR_PATH_SPEC)
        subs['ecc_tempo']     = compute_sub_score(s_rep.get('ecc_sec'), ECC_TEMPO_SPEC)
        subs['con_tempo']     = compute_sub_score(s_rep.get('con_sec'), CON_TEMPO_SPEC)

    if f_rep:
        # Knee valgus — worst leg dominates the safety score.
        valgus_raw = max(
            f_rep.get('l_valgus_deg') or 0,
            f_rep.get('r_valgus_deg') or 0,
        )
        subs['knee_valgus']   = compute_sub_score(valgus_raw, VALGUS_SPEC)
        subs['stance_width']  = compute_sub_score(f_rep.get('stance_ratio'), STANCE_SPEC[variant])
        toe_vals = [v for v in (f_rep.get('l_toe_out_deg'),
                                f_rep.get('r_toe_out_deg')) if v is not None]
        # None = unmeasurable projection — skip the metric, don't score 0°
        subs['toe_out']       = compute_sub_score(max(toe_vals) if toe_vals else None,
                                                  TOE_OUT_SPEC)
        subs['lat_hip_shift'] = compute_sub_score(f_rep.get('lat_hip_shift_cm'), LAT_HIP_SHIFT_SPEC)
        subs['bar_tilt']      = compute_sub_score(f_rep.get('bar_tilt_deg'), BAR_TILT_SPEC)
        subs['spinal_align']  = compute_sub_score(f_rep.get('spinal_lateral_deg'), SPINAL_ALIGN_SPEC)
        subs['shoulder_sym']  = compute_sub_score(f_rep.get('shoulder_diff_cm'), SHOULDER_SYM_SPEC)

    return subs


def _consistency_subscore(side_reps, front_reps):
    """CV across key per-rep metrics → consistency sub-score (doc §6.3)."""
    series = []
    for k in ('depth_cm', 'torso_deg', 'ecc_sec', 'con_sec'):
        vals = [r.get(k) for r in side_reps]
        cv = _cv_pct(vals)
        if cv is not None:
            series.append(cv)
    for k in ('l_valgus_deg', 'r_valgus_deg'):
        vals = [r.get(k) for r in front_reps]
        cv = _cv_pct(vals)
        if cv is not None:
            series.append(cv)
    if not series:
        return None
    mean_cv = sum(series) / len(series)
    return compute_sub_score(mean_cv, CONSISTENCY_SPEC)


# ════════════════════════════════════════════════════════════════════
#  Metric-list assembly (doc-driven Safety/Form/Performance ordering)
# ════════════════════════════════════════════════════════════════════

def _metric_label(variant, slug):
    """Display name for the frontend. Naming chosen so the ResultPage
    `classifyMetric` regex maps it into the right Safety/Form/Performance
    bucket."""
    return {
        # ── Safety ─────────────────────────────────────────────
        'knee_valgus':    'Knee Valgus (frontal collapse)',
        'butt_wink':      'Butt Wink (lumbar tuck)',
        'heel_contact':   'Heel Lift Duration',
        'spinal_align':   'Spinal Alignment (lateral lean)',
        # ── Technique / Form ───────────────────────────────────
        'depth':          'Squat Depth (hip vs knee)',
        'torso_angle':    'Torso Angle (forward lean)',
        'bar_path':       'Bar Path Drift',
        'lat_hip_shift':  'Lateral Hip Asymmetry',
        # ── Performance ────────────────────────────────────────
        'bar_tilt':       'Bar Tilt',
        'ecc_tempo':      'Eccentric Tempo',
        'con_tempo':      'Concentric Tempo',
        'consistency':    'Rep-to-Rep Consistency (Tempo & ROM)',
        # ── Informational ──────────────────────────────────────
        'hip_bar_align':  'Hip–Bar Alignment',
        'shin_angle':     'Shin Angle (dorsiflexion)',
        'knee_flexion':   'Knee Flexion at Bottom',
        'stance_width':   'Stance Width Ratio',
        'toe_out':        'Foot/Toe-Out Angle',
        'shoulder_sym':   'Shoulder Height Symmetry',
    }.get(slug, slug)


def _metric_target(variant, slug):
    return {
        'knee_valgus':    '≤ 5°',
        'butt_wink':      '≤ 5°',
        'heel_contact':   '≤ 0.05 s',
        'spinal_align':   '≤ 2°',
        'depth':          '≤ 0 cm (parallel)' if variant == 'low-bar' else '≤ −10 cm (deep)',
        'torso_angle':    '30°–45° (low-bar)' if variant == 'low-bar' else '0°–20° (high-bar)',
        'bar_path':       '< 2 cm',
        'lat_hip_shift':  '< 1 cm',
        'bar_tilt':       '< 1°',
        'ecc_tempo':      '2–3 s',
        'con_tempo':      '1–2 s',
        'consistency':    '< 5% CV',
        'hip_bar_align':  '< 5 cm',
        'shin_angle':     '15°–25° (low-bar)' if variant == 'low-bar' else '30°–40° (high-bar)',
        'knee_flexion':   '85°–95° (low-bar)' if variant == 'low-bar' else '30°–45° (high-bar)',
        'stance_width':   '1.2–1.5×' if variant == 'low-bar' else '1.0–1.2×',
        'toe_out':        '15°–30°',
        'shoulder_sym':   '< 1 cm',
    }.get(slug, '')


def _metric_max(slug):
    return {
        'knee_valgus': 30, 'butt_wink': 30, 'heel_contact': 3.0,
        'spinal_align': 15, 'depth': 15, 'torso_angle': 90, 'bar_path': 15,
        'lat_hip_shift': 10, 'bar_tilt': 20, 'ecc_tempo': 5, 'con_tempo': 5,
        'consistency': 60, 'hip_bar_align': 30, 'shin_angle': 60,
        'knee_flexion': 130, 'stance_width': 2.5, 'toe_out': 50, 'shoulder_sym': 8,
    }.get(slug, 10)


def _value_str(slug, raw):
    if raw is None:
        return '—'
    if slug in ('depth', 'lat_hip_shift', 'shoulder_sym', 'hip_bar_align', 'bar_path'):
        return f"{raw:+.1f} cm" if slug == 'depth' else f"{raw:.1f} cm"
    if slug in ('heel_contact', 'ecc_tempo', 'con_tempo'):
        return f"{raw:.2f} s"
    if slug == 'consistency':
        return f"{raw:.1f}% CV"
    if slug == 'stance_width':
        return f"{raw:.2f}×"
    if slug in ('knee_valgus', 'butt_wink', 'torso_angle', 'shin_angle',
                'knee_flexion', 'bar_tilt', 'spinal_align', 'toe_out'):
        return f"{raw:.1f}°"
    return f"{raw:.1f}"


def _avg_raw(reps, key):
    vals = [r[key] for r in reps if r.get(key) is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _max_raw(reps, key):
    vals = [abs(r[key]) for r in reps if r.get(key) is not None]
    if not vals:
        return None
    return max(vals)


def _min_raw(reps, key):
    vals = [r[key] for r in reps if r.get(key) is not None]
    if not vals:
        return None
    return min(vals)


def _build_metric_list(per_rep_subs, side_reps, front_reps, side, front, variant, n_reps):
    """Build the flat metric list for the result payload.

    Each metric is a dict whose `status` is now the 5-tier label
    (`very_good` / `good` / `yellow_flag` / `bad` / `very_bad`) — the frontend
    Metric.status union has been extended to accept it.
    """
    metrics = []
    raw_lookup = {}  # slug → raw value used by coaching summary

    set_subs = _mean_dict(per_rep_subs)
    set_subs['consistency'] = _consistency_subscore(side_reps, front_reps)

    # Per-slug raw aggregator (worst-rep for safety, mean for form/performance)
    SAFETY_KEYS = ('knee_valgus', 'butt_wink', 'heel_contact', 'spinal_align',
                   'lat_hip_shift', 'bar_path', 'bar_tilt')

    def _raw_for(slug):
        if slug == 'depth':
            return _min_raw(side_reps, 'depth_cm')
        if slug == 'torso_angle':
            return _avg_raw(side_reps, 'torso_deg')
        if slug == 'butt_wink':
            return _max_raw(side_reps, 'butt_wink_deg')
        if slug == 'heel_contact':
            return _max_raw(side_reps, 'heel_lift_sec')
        if slug == 'shin_angle':
            return _avg_raw(side_reps, 'shin_deg')
        if slug == 'knee_flexion':
            return _min_raw(side_reps, 'knee_flex_deg')
        if slug == 'hip_bar_align':
            return _max_raw(side_reps, 'hip_bar_cm')
        if slug == 'bar_path':
            return _max_raw(side_reps, 'bar_path_cm')
        if slug == 'ecc_tempo':
            return _avg_raw(side_reps, 'ecc_sec')
        if slug == 'con_tempo':
            return _avg_raw(side_reps, 'con_sec')
        if slug == 'knee_valgus':
            l = _max_raw(front_reps, 'l_valgus_deg') or 0
            r = _max_raw(front_reps, 'r_valgus_deg') or 0
            return max(l, r)
        if slug == 'stance_width':
            return _avg_raw(front_reps, 'stance_ratio')
        if slug == 'toe_out':
            l = _avg_raw(front_reps, 'l_toe_out_deg') or 0
            r = _avg_raw(front_reps, 'r_toe_out_deg') or 0
            return max(l, r)
        if slug == 'lat_hip_shift':
            return _max_raw(front_reps, 'lat_hip_shift_cm')
        if slug == 'bar_tilt':
            return _max_raw(front_reps, 'bar_tilt_deg')
        if slug == 'spinal_align':
            return _max_raw(front_reps, 'spinal_lateral_deg')
        if slug == 'shoulder_sym':
            return _max_raw(front_reps, 'shoulder_diff_cm')
        if slug == 'consistency':
            # consistency raw = mean CV value; recompute here for display.
            cvs = []
            for k in ('depth_cm', 'torso_deg', 'ecc_sec', 'con_sec'):
                v = _cv_pct([r.get(k) for r in side_reps])
                if v is not None:
                    cvs.append(v)
            return sum(cvs) / len(cvs) if cvs else None
        return None

    # Order matters — drives ResultPage's section ordering after the
    # frontend regex bucketing (Safety → Form → Performance → Informational).
    ORDERED_SLUGS = (
        # safety
        'knee_valgus', 'butt_wink', 'heel_contact', 'spinal_align',
        # technique
        'depth', 'torso_angle', 'bar_path', 'lat_hip_shift',
        # performance
        'bar_tilt', 'ecc_tempo', 'con_tempo', 'consistency',
        # informational
        'hip_bar_align', 'shin_angle', 'knee_flexion', 'stance_width',
        'toe_out', 'shoulder_sym',
    )

    for slug in ORDERED_SLUGS:
        sub = set_subs.get(slug)
        if sub is None:
            continue
        raw = _raw_for(slug)
        raw_lookup[slug] = raw

        tier = tier_from_subscore(sub)
        # Map the 5-tier label onto the tri-state classification that the
        # scoring/UI pipeline understands (previously left at a hardcoded
        # 'GOOD' placeholder for every metric).
        tri = {'very_good': 'GOOD', 'good': 'GOOD',
               'yellow_flag': 'NEEDS IMPROVEMENT'}.get(tier, 'RESTRICTED')

        confidence = _metric_confidence(slug, side, front)
        m = build_metric(
            name=_metric_label(variant, slug),
            value_str=_value_str(slug, raw),
            raw=raw if raw is not None else 0.0,
            target=_metric_target(variant, slug),
            max_val=_metric_max(slug),
            classification=tri,
            confidence=confidence,
            n_reps=n_reps,
        )
        # Replace the legacy good/bad with the new 5-tier label and surface
        # the sub-score for the histogram + per-metric drill-downs.
        m['status'] = tier
        m['sub_score'] = round(float(sub), 1)
        metrics.append(m)

    # Stash an internal avg for muscle inference downstream
    set_subs['_avg_torso_deg'] = _avg_raw(side_reps, 'torso_deg')

    return metrics, raw_lookup


def _metric_confidence(slug, side, front):
    """Per-metric confidence in [0, 1]."""
    s_q = lambda key: window_landmark_quality(
        side['frames'],
        [LM[f"{side['side_key']}_{j}"] for j in key]) if side['available'] else 0.0
    f_q = lambda key: window_landmark_quality(
        front['frames'], [LM[j] for j in key]) if front['available'] else 0.0

    table = {
        'depth':         s_q(('HIP', 'KNEE')),
        'torso_angle':   s_q(('HIP', 'SHOULDER')),
        'butt_wink':     0.5 * s_q(('HIP', 'SHOULDER')),  # doc §11.4 — low confidence
        'heel_contact':  s_q(('HEEL', 'FOOT_INDEX')),
        'shin_angle':    s_q(('KNEE', 'ANKLE')),
        'knee_flexion':  s_q(('HIP', 'KNEE', 'ANKLE')),
        'hip_bar_align': s_q(('HIP', 'SHOULDER')),
        'bar_path':      (side.get('plate_quality') or 0.0) if side.get('px_per_cm') else 0.5 * s_q(('SHOULDER',)),
        'ecc_tempo':     s_q(('HIP',)),
        'con_tempo':     s_q(('HIP',)),
        'knee_valgus':   f_q(('LEFT_HIP', 'LEFT_KNEE', 'LEFT_ANKLE',
                              'RIGHT_HIP', 'RIGHT_KNEE', 'RIGHT_ANKLE')),
        'stance_width':  f_q(('LEFT_ANKLE', 'RIGHT_ANKLE', 'LEFT_SHOULDER', 'RIGHT_SHOULDER')),
        'toe_out':       0.5 * f_q(('LEFT_HEEL', 'LEFT_FOOT_INDEX',
                                    'RIGHT_HEEL', 'RIGHT_FOOT_INDEX')),
        'lat_hip_shift': f_q(('LEFT_HIP', 'RIGHT_HIP', 'LEFT_ANKLE', 'RIGHT_ANKLE')),
        'bar_tilt':      f_q(('LEFT_SHOULDER', 'RIGHT_SHOULDER')),
        'spinal_align':  0.6 * f_q(('LEFT_SHOULDER', 'RIGHT_SHOULDER', 'LEFT_HIP', 'RIGHT_HIP')),
        'shoulder_sym':  f_q(('LEFT_SHOULDER', 'RIGHT_SHOULDER')),
        'consistency':   0.9 if (side['available'] and front['available']) else 0.6,
    }
    return float(max(0.0, min(1.0, table.get(slug, 0.5))))


def _build_bilateral(front_reps):
    out = []
    if not front_reps:
        return out
    l_valgus = _avg_raw(front_reps, 'l_valgus_deg')
    r_valgus = _avg_raw(front_reps, 'r_valgus_deg')
    if l_valgus is not None and r_valgus is not None:
        out.append(build_bilateral('Knee Valgus (peak)', round(l_valgus, 1),
                                   round(r_valgus, 1), '°', 25))
    l_knee = _avg_raw(front_reps, 'l_knee_flex_deg')
    r_knee = _avg_raw(front_reps, 'r_knee_flex_deg')
    if l_knee is not None and r_knee is not None:
        out.append(build_bilateral('Knee Flexion at Bottom', round(l_knee, 1),
                                   round(r_knee, 1), '°', 130))
    return out


def _build_per_rep_dump(side_reps, front_reps, per_rep_subs, rep_composites):
    out = []
    for i, r in enumerate(side_reps):
        sub = per_rep_subs[i] if i < len(per_rep_subs) else {}
        out.append({
            'rep': r['rep_num'], 'side': 'side',
            'metrics': {
                **{k: r.get(k) for k in (
                    'depth_cm', 'torso_deg', 'butt_wink_deg', 'heel_lift_sec',
                    'shin_deg', 'knee_flex_deg', 'hip_bar_cm', 'bar_path_cm',
                    'ecc_sec', 'con_sec')},
                'sub_scores': {k: (round(v, 1) if v is not None else None)
                               for k, v in sub.items() if not k.startswith('_')},
                'composite': rep_composites[i] if i < len(rep_composites) else None,
            },
        })
    for i, r in enumerate(front_reps):
        sub = per_rep_subs[i] if i < len(per_rep_subs) else {}
        out.append({
            'rep': r['rep_num'], 'side': 'front',
            'metrics': {
                **{k: r.get(k) for k in (
                    'l_valgus_deg', 'r_valgus_deg', 'l_knee_flex_deg',
                    'r_knee_flex_deg', 'lat_hip_shift_cm', 'bar_tilt_deg',
                    'spinal_lateral_deg', 'shoulder_diff_cm', 'stance_ratio',
                    'l_toe_out_deg', 'r_toe_out_deg')},
                'sub_scores': {k: (round(v, 1) if v is not None else None)
                               for k, v in sub.items() if not k.startswith('_')},
                'composite': rep_composites[i] if i < len(rep_composites) else None,
            },
        })
    return out


# ════════════════════════════════════════════════════════════════════
#  Helpers used across the orchestrator
# ════════════════════════════════════════════════════════════════════

def _mean_dict(list_of_dicts):
    """Mean of each key across dicts (None values skipped)."""
    out = {}
    if not list_of_dicts:
        return out
    keys = set()
    for d in list_of_dicts:
        keys.update(d.keys())
    for k in keys:
        vals = [d[k] for d in list_of_dicts if d.get(k) is not None]
        if not vals:
            continue
        out[k] = sum(vals) / len(vals)
    return out


def _rep_bar_path_cm(side, start, end):
    """Best available bar-path drift in cm for a rep.

    Prefers the plate centres from track_bar_path; falls back to the
    shoulder-x range from per-frame data (doc §12.5 metric 3 fallback).
    """
    centres = side.get('bar_centres')
    px_per_cm = side.get('px_per_cm') or 0.0
    if centres and px_per_cm > 0:
        drift = bar_path_horizontal_drift_cm(centres, start, end, px_per_cm)
        return drift.get('max_drift_cm')
    # Fallback — shoulder x range / px_per_cm (or pixels if calibration absent)
    xs = [side['per_frame'][i].get('shoulder_x')
          for i in range(start, min(end + 1, len(side['per_frame'])))]
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    span_px = max(xs) - min(xs)
    if px_per_cm > 0:
        return span_px / px_per_cm
    # No calibration → no honest cm value. The old ÷30 "crude conversion"
    # emitted values like 152 cm and torpedoed the composite whenever plate
    # tracking transiently failed.
    return None


def _overall_confidence(side, front):
    qs = []
    if side['available']:
        qs.append(window_landmark_quality(
            side['frames'],
            [LM[f"{side['side_key']}_HIP"], LM[f"{side['side_key']}_KNEE"],
             LM[f"{side['side_key']}_ANKLE"], LM[f"{side['side_key']}_SHOULDER"]]))
    if front['available']:
        qs.append(window_landmark_quality(
            front['frames'],
            [LM['LEFT_HIP'], LM['RIGHT_HIP'], LM['LEFT_KNEE'], LM['RIGHT_KNEE']]))
    if not qs:
        return 0.0
    return sum(qs) / len(qs)


def _sides_label(side, front):
    if side['available'] and front['available']:
        return 'side + front'
    if side['available']:
        return 'side only'
    if front['available']:
        return 'front only'
    return 'no cams'


def _style_label(variant):
    return 'High bar' if variant == 'high-bar' else 'Low bar'


def _status_from_score(score):
    if score >= 75:
        return 'GOOD'
    if score >= 55:
        return 'NEEDS IMPROVEMENT'
    return 'RESTRICTED'


def _summary(set_subs, set_score, variant):
    style = _style_label(variant)
    band = _band_label(set_score)
    return f"{style} squat — {band}. Composite {set_score}/100 (doc §7-style 5-tier scoring)."


def _band_label(score):
    if score >= 90: return 'pristine, A grade'
    if score >= 75: return 'solid, B grade'
    if score >= 60: return 'workable, C grade — fixable'
    if score >= 40: return 'risky, D grade — slow down'
    return 'critical, E grade — re-set'


def _coaching(set_subs, override_notes, variant, set_score, n_reps):
    """Surface the two lowest sub-scores plus any safety overrides (doc §11.4)."""
    # Ignore the synthetic '_avg_torso_deg' key
    ranked = [(k, v) for k, v in set_subs.items()
              if v is not None and not k.startswith('_')
              and k in (set(WEIGHTS['safety']) | set(WEIGHTS['technique']) |
                        set(WEIGHTS['performance']))]
    ranked.sort(key=lambda kv: kv[1])
    weak = ranked[:2]

    notes = [
        f"{_style_label(variant)} squat composite: {set_score}/100 across {n_reps} rep(s)."
    ]
    if weak:
        slug, sub = weak[0]
        notes.append(
            f"⚠️ Lowest sub-score: {_metric_label(variant, slug)} ({round(sub)}/100). "
            f"Focus your next session here — see the per-metric histogram for the gap.")
    if len(weak) >= 2:
        slug, sub = weak[1]
        notes.append(
            f"Next priority: {_metric_label(variant, slug)} ({round(sub)}/100).")

    for n in override_notes:
        notes.append(f"🚩 {n}")
    if set_score >= 85 and not override_notes:
        notes.append("Strong work — keep your routine and progress load gradually.")
    return notes


# ════════════════════════════════════════════════════════════════════
#  Annotated frames — SIDE
# ════════════════════════════════════════════════════════════════════

def _safe_xy(p):
    return (int(p[0]), int(p[1])) if p else None


def _render_side_frames(side, side_reps, per_rep_subs, rep_composites,
                        set_status, variant):
    out = []
    frames, w, h = side['frames'], side['w'], side['h']
    video_path = side['video_path']
    side_key = side['side_key']

    if not side_reps:
        fb = render_sample_frame(video_path, frames, w, h, 'Back Squat (Side)',
                                 'No reps detected on side camera — check framing.',
                                 connections=SQUAT_CONNECTIONS)
        if fb:
            out.append({'label': 'Side — Sample Frame', 'image_base64': fb,
                        'rep_num': 0, 'side': 'side', 'is_best': False,
                        'metrics_shown': ['No reps detected']})
        return out

    best_idx = max(range(len(rep_composites)), key=lambda i: rep_composites[i] if i < len(rep_composites) else -1)

    for i, r in enumerate(side_reps):
        bot_frame = r.get('bot_frame', r['peak_frame'])
        if bot_frame >= len(frames):
            continue
        lm = frames[bot_frame].get('landmarks')
        if lm is None:
            continue
        frame = extract_frame_at(video_path, bot_frame)
        if frame is None:
            continue

        # Landmark pixel positions for drawing
        hp  = _safe_xy(get_lm(lm, LM[f'{side_key}_HIP'],    w, h))
        kn  = _safe_xy(get_lm(lm, LM[f'{side_key}_KNEE'],   w, h))
        an  = _safe_xy(get_lm(lm, LM[f'{side_key}_ANKLE'],  w, h))
        sh  = _safe_xy(get_lm(lm, LM[f'{side_key}_SHOULDER'], w, h))
        hl  = _safe_xy(get_lm(lm, LM[f'{side_key}_HEEL'],   w, h))

        draw_skeleton(frame, lm, w, h, connections=SQUAT_CONNECTIONS)

        if an:
            draw_reference_line(frame, x=an[0], color=COL_CYAN,
                                label='Mid-foot (bar plumb-line)')
        if kn:
            draw_reference_line(frame, y=kn[1], color=COL_CYAN,
                                label='Knee line — depth target')

        sub = per_rep_subs[i] if i < len(per_rep_subs) else {}
        composite = rep_composites[i] if i < len(rep_composites) else 0

        # Angle arcs
        if hp and kn and an and r.get('knee_flex_deg') is not None:
            tier = tier_from_subscore(sub.get('knee_flexion'))
            draw_angle_arc(frame, kn, hp, an, r['knee_flex_deg'],
                           label=f"Knee {r['knee_flex_deg']:.0f}°",
                           radius=52, status=_tier_to_status(tier))
        if sh and hp and r.get('torso_deg') is not None:
            v = (hp[0], hp[1] - 130)
            tier = tier_from_subscore(sub.get('torso_angle'))
            draw_angle_arc(frame, hp, sh, v, r['torso_deg'],
                           label=f"Trunk {r['torso_deg']:.0f}°",
                           radius=38, status=_tier_to_status(tier))
        if an and kn and r.get('shin_deg') is not None:
            v = (an[0], an[1] - 120)
            tier = tier_from_subscore(sub.get('shin_angle'))
            draw_angle_arc(frame, an, kn, v, r['shin_deg'],
                           label=f"Shin {r['shin_deg']:.0f}°",
                           radius=34, status=_tier_to_status(tier))

        # Depth line
        if hp and kn and r.get('depth_cm') is not None:
            depth_pt = (hp[0], kn[1])
            tier = tier_from_subscore(sub.get('depth'))
            draw_distance_line(frame, hp, depth_pt,
                               f"Depth {r['depth_cm']:+.1f} cm",
                               status=_tier_to_status(tier))

        # Heel-lift callout if any time was logged
        if hl and r.get('heel_lift_sec', 0) > 0.05:
            tier = tier_from_subscore(sub.get('heel_contact'))
            draw_callout(frame, hl, f"Heel lift {r['heel_lift_sec']:.2f}s",
                         status=_tier_to_status(tier))

        # Top banner + rep pill
        draw_top_phase_banner(frame, 'DEEPEST POINT',
                              sublabel=f'{_style_label(variant)} · Rep {r["rep_num"]}')
        draw_top_right_rep_pill(frame, r['rep_num'], len(side_reps),
                                status=_tier_to_status(tier_from_subscore(composite)))

        # Sub-score info panel
        panel_rows = []
        for slug in ('depth', 'torso_angle', 'butt_wink',
                     'heel_contact', 'shin_angle', 'bar_path'):
            s = sub.get(slug)
            if s is None:
                continue
            panel_rows.append({
                'label': _metric_label(variant, slug).split('(')[0].strip(),
                'value': f"{round(s)}/100",
                'status': _tier_to_status(tier_from_subscore(s)),
            })
        if panel_rows:
            draw_info_panel(frame, f"Side · {composite}/100", panel_rows,
                            position='left', width=360, top=70)

        # Hip-height trace
        hip_y_window = [side['per_frame'][k].get('hip_y') if k < len(side['per_frame']) else None
                        for k in range(r['start_frame'], min(r['end_frame'] + 1, len(side['per_frame'])))]
        draw_hip_height_trace(frame, hip_y_window,
                              peak_frame=bot_frame - r['start_frame'],
                              rep_num=r['rep_num'], total=len(side_reps))

        # Confidence pill — visible top-right
        draw_confidence_pill(frame, _overall_confidence(side, {'available': False}),
                             anchor=(w - 220, 80), label=None)

        is_best = (i == best_idx)
        out.append({
            'label': f"Side · Rep {r['rep_num']}/{len(side_reps)}"
                     + (' (Best)' if is_best else ''),
            'image_base64': frame_to_base64(frame),
            'rep_num': r['rep_num'], 'side': 'side', 'is_best': is_best,
            'metrics_shown': ['Depth', 'Torso', 'Knee Flex', 'Bar Path'],
        })

    return out


# ════════════════════════════════════════════════════════════════════
#  Annotated frames — FRONT
# ════════════════════════════════════════════════════════════════════

def _render_front_frames(front, front_reps, per_rep_subs, rep_composites, set_status):
    out = []
    frames, w, h = front['frames'], front['w'], front['h']
    video_path = front['video_path']

    if not front_reps:
        fb = render_sample_frame(video_path, frames, w, h, 'Back Squat (Front)',
                                 'No reps detected on front camera — check framing.',
                                 connections=SQUAT_CONNECTIONS)
        if fb:
            out.append({'label': 'Front — Sample Frame', 'image_base64': fb,
                        'rep_num': 0, 'side': 'front', 'is_best': False,
                        'metrics_shown': ['No reps detected']})
        return out

    best_idx = max(range(len(rep_composites)), key=lambda i: rep_composites[i] if i < len(rep_composites) else -1)

    for i, r in enumerate(front_reps):
        bot_frame = r.get('bot_frame', r['peak_frame'])
        if bot_frame >= len(frames):
            continue
        lm = frames[bot_frame].get('landmarks')
        if lm is None:
            continue
        frame = extract_frame_at(video_path, bot_frame)
        if frame is None:
            continue

        l_kn = _safe_xy(get_lm(lm, LM['LEFT_KNEE'],  w, h))
        r_kn = _safe_xy(get_lm(lm, LM['RIGHT_KNEE'], w, h))
        l_an = _safe_xy(get_lm(lm, LM['LEFT_ANKLE'], w, h))
        r_an = _safe_xy(get_lm(lm, LM['RIGHT_ANKLE'],w, h))

        draw_skeleton(frame, lm, w, h, connections=SQUAT_CONNECTIONS)

        # Mid-foot plumb lines
        if l_an:
            draw_reference_line(frame, x=l_an[0], color=COL_CYAN, label='L mid-foot')
        if r_an:
            draw_reference_line(frame, x=r_an[0], color=COL_CYAN, label='R mid-foot')

        sub = per_rep_subs[i] if i < len(per_rep_subs) else {}

        # Valgus callouts per leg (doc-recommended visualisation, §11.4)
        if l_kn and r.get('l_valgus_deg') is not None:
            tier = tier_from_subscore(sub.get('knee_valgus'))
            draw_valgus_callout(frame, l_kn, r['l_valgus_deg'], 'left',
                                status=_tier_to_status(tier))
        if r_kn and r.get('r_valgus_deg') is not None:
            tier = tier_from_subscore(sub.get('knee_valgus'))
            draw_valgus_callout(frame, r_kn, r['r_valgus_deg'], 'right',
                                status=_tier_to_status(tier))

        # Bar tilt callout (shoulder line)
        if r.get('bar_tilt_deg') is not None and r['bar_tilt_deg'] > 0:
            tier = tier_from_subscore(sub.get('bar_tilt'))
            draw_phase_label(frame, f"BAR TILT {r['bar_tilt_deg']:.1f}°",
                             anchor=None)

        # Sub-score info panel
        panel_rows = []
        for slug in ('knee_valgus', 'lat_hip_shift', 'bar_tilt',
                     'spinal_align', 'stance_width'):
            s = sub.get(slug)
            if s is None:
                continue
            panel_rows.append({
                'label': _metric_label('high-bar', slug).split('(')[0].strip(),
                'value': f"{round(s)}/100",
                'status': _tier_to_status(tier_from_subscore(s)),
            })
        if panel_rows:
            composite = rep_composites[i] if i < len(rep_composites) else 0
            draw_info_panel(frame, f"Front · {composite}/100", panel_rows,
                            position='right', width=360, top=70)

        draw_top_phase_banner(frame, 'FRONT VIEW — DEEPEST POINT',
                              sublabel=f'Rep {r["rep_num"]}')
        composite = rep_composites[i] if i < len(rep_composites) else 0
        draw_top_right_rep_pill(frame, r['rep_num'], len(front_reps),
                                status=_tier_to_status(tier_from_subscore(composite)))

        # Fault timing strip — surface frames where valgus exceeded threshold
        events = []
        if r.get('l_valgus_deg') is not None and r['l_valgus_deg'] > 10:
            events.append({'name': 'L Valgus',
                           'start_phase_pct': 50,
                           'status': 'bad'})
        if r.get('r_valgus_deg') is not None and r['r_valgus_deg'] > 10:
            events.append({'name': 'R Valgus',
                           'start_phase_pct': 60,
                           'status': 'bad'})
        if events:
            draw_fault_timing_strip(frame, r['rep_num'], len(front_reps), events)

        is_best = (i == best_idx)
        out.append({
            'label': f"Front · Rep {r['rep_num']}/{len(front_reps)}"
                     + (' (Best)' if is_best else ''),
            'image_base64': frame_to_base64(frame),
            'rep_num': r['rep_num'], 'side': 'front', 'is_best': is_best,
            'metrics_shown': ['Valgus', 'Hip Shift', 'Bar Tilt'],
        })

    return out


def _tier_to_status(tier):
    """Map our 5-tier label to the 3-color statuses the frame_annotator helpers understand."""
    if tier in ('very_good', 'good'):
        return 'good'
    if tier == 'yellow_flag':
        return 'warn'
    return 'bad'


# ════════════════════════════════════════════════════════════════════
#  Fallback for hard failure paths
# ════════════════════════════════════════════════════════════════════

def _fallback(msg):
    return {
        'status': 'RESTRICTED',
        'score': 0,
        'summary': f'Analysis failed: {msg}',
        'stats': {
            'validReps':   '0/0',
            'confidence':  '0%',
            'sides':       'error',
            'cameraView':  'ERROR',
            'style':       '—',
        },
        'metrics': [],
        'bilateral': [],
        'coaching': [
            f'Analyzer error: {msg}',
            'Verify both videos uploaded and that the camera angles match the setup spec.',
            'Check the Python/Node logs for the full traceback.',
        ],
        'annotated_frames': [],
        'per_rep': [],
        'meta': {'analyzer_version': ANALYZER_VERSION, '_isError': True},
    }
