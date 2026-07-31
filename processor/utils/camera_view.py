"""Camera-view classifier for strength videos.

Gates every strength analyzer: if the wrong view is uploaded, we fail clean
with a clear message instead of producing silently-bad metrics.

The classifier uses purely geometric heuristics over the middle 50% of a
recording (skips warm-up reps and setup motion). Three measurements vote:

  1. shoulder-spread / torso-length ratio
     - front view: shoulder-shoulder distance ≈ 0.5–1.0 × torso length
     - side  view: shoulder-shoulder distance ≈ 0.1–0.25 × torso length
       (one shoulder is occluded behind the other)

  2. left-vs-right ankle z-depth differential
     - MediaPipe's z-channel is noisy but the side view has consistently large
       |L − R| z difference; front view has near-zero.

  3. landmark-visibility asymmetry
     - side view: one side ~0.9, the other ~0.4 (occluded limbs)
     - front view: both sides roughly symmetric (~0.7+ each)

Each measurement contributes a vote with weight 1; the winning class needs at
least 2 of 3 votes, otherwise we return `unknown` and the caller decides
whether to soft-warn or hard-reject.
"""
from __future__ import annotations

from typing import List, Dict, Optional, Tuple
import math

from .landmarks import LM


# ─────────────────────────────────────────────────────────────────
# Configuration: per-lift accepted views
# ─────────────────────────────────────────────────────────────────

# 'side' = sagittal (90° to athlete)
# 'front' = frontal (head-on or directly behind)
# 'three_quarter' = ~45° (rejected by all strength lifts)

ACCEPTED_VIEWS_BY_LIFT: Dict[str, Dict[str, set]] = {
    'back-squat': {
        'side':  {'side'},
        'front': {'front'},
    },
    'deadlift':       {'side': {'side'}},
    'bench-press':    {'side': {'side'}, 'front': {'front'}},  # front optional
    'overhead-press': {'side': {'side'}, 'front': {'front'}},  # front optional
    'pull-up':        {'front': {'front'}, 'side': {'side'}},  # side optional
}


# ─────────────────────────────────────────────────────────────────
# Classification
# ─────────────────────────────────────────────────────────────────

def classify_camera_view(frames_data: List[dict], w: int, h: int,
                          middle_window: float = 0.5) -> Dict:
    """Classify a video's camera view from its landmarks.

    Args:
        frames_data: list of {frame_idx, landmarks, ...} from extract_all_landmarks.
        w, h: frame dimensions.
        middle_window: fraction of the recording to sample. 0.5 = middle 50%.

    Returns:
        {'view': 'side'|'front'|'three_quarter'|'unknown',
         'confidence': float in [0,1],
         'reasoning': str  (human-readable summary)}
    """
    if not frames_data:
        return {'view': 'unknown', 'confidence': 0.0,
                'reasoning': 'no frames'}

    n = len(frames_data)
    lo = int(n * (0.5 - middle_window / 2))
    hi = int(n * (0.5 + middle_window / 2))
    sample = [f for f in frames_data[lo:hi] if f.get('landmarks') is not None]
    if len(sample) < 5:
        return {'view': 'unknown', 'confidence': 0.0,
                'reasoning': f'only {len(sample)} valid frames in middle window'}

    spread_ratios: List[float] = []
    ankle_z_diffs: List[float] = []
    vis_asyms: List[float] = []

    for f in sample:
        lm = f['landmarks']
        l_sh, r_sh = lm[LM['LEFT_SHOULDER']], lm[LM['RIGHT_SHOULDER']]
        l_hip, r_hip = lm[LM['LEFT_HIP']], lm[LM['RIGHT_HIP']]
        l_ank, r_ank = lm[LM['LEFT_ANKLE']], lm[LM['RIGHT_ANKLE']]

        # 1. shoulder spread / torso length (normalized; sign-independent)
        sh_dx = (r_sh[0] - l_sh[0]) * w
        sh_dy = (r_sh[1] - l_sh[1]) * h
        sh_spread = math.hypot(sh_dx, sh_dy)
        mid_sh = ((l_sh[0] + r_sh[0]) / 2 * w, (l_sh[1] + r_sh[1]) / 2 * h)
        mid_hip = ((l_hip[0] + r_hip[0]) / 2 * w, (l_hip[1] + r_hip[1]) / 2 * h)
        torso = math.hypot(mid_hip[0] - mid_sh[0], mid_hip[1] - mid_sh[1])
        if torso > 1e-3:
            spread_ratios.append(sh_spread / torso)

        # 2. ankle z differential — only meaningful when both visible
        if l_ank[3] > 0.4 and r_ank[3] > 0.4:
            ankle_z_diffs.append(abs(l_ank[2] - r_ank[2]))

        # 3. visibility asymmetry — magnitude of (l_vis - r_vis) averaged
        #    over symmetric pairs (shoulder, hip, knee, ankle)
        v_l = sum(lm[LM[f'LEFT_{p}']][3] for p in ('SHOULDER', 'HIP', 'KNEE', 'ANKLE')) / 4
        v_r = sum(lm[LM[f'RIGHT_{p}']][3] for p in ('SHOULDER', 'HIP', 'KNEE', 'ANKLE')) / 4
        vis_asyms.append(abs(v_l - v_r))

    if not spread_ratios:
        return {'view': 'unknown', 'confidence': 0.0,
                'reasoning': 'no valid torso measurements'}

    def _median(xs: List[float]) -> float:
        if not xs:
            return 0.0
        xs = sorted(xs)
        return xs[len(xs) // 2]

    med_spread = _median(spread_ratios)
    med_z = _median(ankle_z_diffs)
    med_vis = _median(vis_asyms)

    # ─── Voting ─────────────────────────────────────────────────
    votes = {'side': 0, 'front': 0}
    margins = []

    # 1. spread ratio: front ≥ 0.45, side ≤ 0.30 (gap is ambiguous)
    if med_spread <= 0.30:
        votes['side'] += 1
        margins.append(('spread', 'side', 0.30 - med_spread))
    elif med_spread >= 0.45:
        votes['front'] += 1
        margins.append(('spread', 'front', med_spread - 0.45))

    # 2. ankle z diff: side ≥ 0.20 (MediaPipe z-units), front ≤ 0.05
    if med_z >= 0.20:
        votes['side'] += 1
        margins.append(('z_diff', 'side', min(1.0, med_z)))
    elif med_z <= 0.05:
        votes['front'] += 1
        margins.append(('z_diff', 'front', 0.05 - med_z))

    # 3. visibility asymmetry: side ≥ 0.18, front ≤ 0.07
    if med_vis >= 0.18:
        votes['side'] += 1
        margins.append(('vis_asym', 'side', min(1.0, med_vis)))
    elif med_vis <= 0.07:
        votes['front'] += 1
        margins.append(('vis_asym', 'front', 0.07 - med_vis))

    total_votes = votes['side'] + votes['front']
    if total_votes == 0:
        return {
            'view': 'three_quarter',
            'confidence': 0.4,
            'reasoning': (f'all measurements in ambiguous band: '
                          f'spread={med_spread:.2f}, z_diff={med_z:.2f}, '
                          f'vis_asym={med_vis:.2f} — likely a ~45° angle'),
            'measurements': {'spread_ratio': round(med_spread, 3),
                              'ankle_z_diff': round(med_z, 3),
                              'vis_asym': round(med_vis, 3)},
        }

    winner = 'side' if votes['side'] > votes['front'] else 'front'
    if votes['side'] == votes['front']:
        return {
            'view': 'three_quarter',
            'confidence': 0.45,
            'reasoning': f'split vote (side={votes["side"]}, front={votes["front"]})',
            'measurements': {'spread_ratio': round(med_spread, 3),
                              'ankle_z_diff': round(med_z, 3),
                              'vis_asym': round(med_vis, 3)},
        }

    # Confidence: votes for winner / total votes possible (3), scaled by margin
    vote_strength = votes[winner] / 3.0
    margin_strength = min(1.0, sum(m[2] for m in margins if m[1] == winner) / max(1, votes[winner]))
    confidence = round(0.5 + 0.5 * (vote_strength * 0.5 + margin_strength * 0.5), 2)
    confidence = max(0.0, min(1.0, confidence))

    reason_lines = [f"{m[0]}→{m[1]}" for m in margins]
    return {
        'view': winner,
        'confidence': confidence,
        'reasoning': (f'{votes[winner]}/3 votes for {winner}: ' + ', '.join(reason_lines) +
                      f' (spread={med_spread:.2f}, z_diff={med_z:.2f}, '
                      f'vis_asym={med_vis:.2f})'),
        'measurements': {'spread_ratio': round(med_spread, 3),
                          'ankle_z_diff': round(med_z, 3),
                          'vis_asym': round(med_vis, 3)},
    }


def validate_for_lift(view: str, expected_role: str, lift_slug: str) -> Tuple[bool, str]:
    """Check if a classified view is acceptable for a given lift + role.

    Args:
        view: classifier output ('side', 'front', 'three_quarter', 'unknown').
        expected_role: 'side' or 'front' — what the analyzer needs.
        lift_slug: exercise slug.

    Returns:
        (ok, reason). When `ok` is False, `reason` explains why for the UI.
    """
    config = ACCEPTED_VIEWS_BY_LIFT.get(lift_slug, {})
    accepted = config.get(expected_role, {expected_role})
    if view in accepted:
        return True, f'{view} view accepted for {lift_slug} ({expected_role})'
    if view == 'unknown':
        return False, (f'Camera view could not be classified. '
                       f'{lift_slug} expects a {expected_role} view — '
                       f're-record with the camera placed as shown in the guide.')
    if view == 'three_quarter':
        return False, (f'Camera appears to be at ~45° (three-quarter). '
                       f'{lift_slug} requires a clean {expected_role} view '
                       f'(90° to the athlete for side, head-on for front).')
    return False, (f'Detected a {view} view but {lift_slug} expects a '
                   f'{expected_role} view. Re-record from the correct angle.')


def assign_video_roles(classifications: Dict[str, Dict],
                       lift_slug: str) -> Dict[str, str]:
    """Map upload labels → roles by view classification, ignoring upload order.

    Args:
        classifications: {upload_label: classify_camera_view(...) result}
        lift_slug: exercise slug.

    Returns:
        {upload_label: assigned_role}. Role is the matching expected role
        for the lift, or 'unknown' when no match. Useful when the user
        uploads two files and we don't trust their naming.
    """
    config = ACCEPTED_VIEWS_BY_LIFT.get(lift_slug, {})
    out: Dict[str, str] = {}
    used_roles: set = set()
    # First pass: high-confidence matches
    ordered = sorted(classifications.items(),
                     key=lambda kv: -kv[1].get('confidence', 0))
    for label, c in ordered:
        v = c.get('view', 'unknown')
        for role, accepted in config.items():
            if v in accepted and role not in used_roles:
                out[label] = role
                used_roles.add(role)
                break
        else:
            out[label] = 'unknown'
    return out
