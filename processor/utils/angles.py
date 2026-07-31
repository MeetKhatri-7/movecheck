"""Angle calculation utilities for joint analysis."""
import math
import numpy as np


def angle_3pt(a, b, c):
    """Calculate the angle at vertex b formed by points a-b-c.
    
    Args:
        a, b, c: tuples of (x, y) coordinates
    Returns:
        Angle in degrees [0, 180]
    """
    if a is None or b is None or c is None:
        return None
    a, b, c = np.array(a), np.array(b), np.array(c)
    ba = a - b
    bc = c - b
    denom = np.linalg.norm(ba) * np.linalg.norm(bc)
    if denom < 1e-8:
        return None
    cosine = np.dot(ba, bc) / denom
    return math.degrees(math.acos(np.clip(cosine, -1.0, 1.0)))


def angle_to_vertical(a, b):
    """Angle of vector a→b relative to vertical (downward Y-axis).
    
    In image coordinates, Y increases downward.
    Returns angle in degrees [0, 180].
    Vertical down = 0°, horizontal = 90°, vertical up = 180°.
    """
    if a is None or b is None:
        return None
    dx = b[0] - a[0]
    dy = b[1] - a[1]  # positive = downward in image
    # vertical reference is (0, 1) in image coords (downward)
    length = math.sqrt(dx*dx + dy*dy)
    if length < 1e-8:
        return None
    cos_angle = dy / length  # dot product with (0,1)
    return math.degrees(math.acos(np.clip(cos_angle, -1.0, 1.0)))


def angle_to_horizontal(a, b):
    """Angle of vector a→b relative to horizontal (rightward X-axis).
    
    Returns signed angle in degrees [-180, 180].
    Right = 0°, down = 90° (image coords).
    """
    if a is None or b is None:
        return None
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return math.degrees(math.atan2(dy, dx))


def signed_angle_from_vertical(a, b):
    """Signed angle of vector a→b from vertical.
    
    Positive = clockwise from vertical (in image coords).
    Returns degrees [-180, 180].
    """
    if a is None or b is None:
        return None
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    # Angle from vertical (0,1) using atan2
    return math.degrees(math.atan2(dx, dy))


def distance_px(a, b):
    """Euclidean distance between two pixel points."""
    if a is None or b is None:
        return None
    return math.sqrt((b[0]-a[0])**2 + (b[1]-a[1])**2)


def horizontal_distance_px(a, b):
    """Horizontal (X-axis) distance between two points."""
    if a is None or b is None:
        return None
    return abs(b[0] - a[0])


def vertical_distance_px(a, b):
    """Vertical (Y-axis) distance between two points."""
    if a is None or b is None:
        return None
    return abs(b[1] - a[1])


def point_to_line_distance(point, line_a, line_b):
    """Perpendicular distance from a point to a line defined by two points.
    
    Returns distance in the same units as input coords.
    """
    if point is None or line_a is None or line_b is None:
        return None
    p = np.array(point)
    a = np.array(line_a)
    b = np.array(line_b)
    ab = b - a
    ap = p - a
    ab_len = np.linalg.norm(ab)
    if ab_len < 1e-8:
        return np.linalg.norm(ap)
    # Cross product magnitude / line length
    # Manual 2D cross product calculation to avoid numpy 2.0+ ValueError on 2D arrays
    cross_prod = ab[0] * ap[1] - ab[1] * ap[0]
    return abs(cross_prod) / ab_len


def estimate_px_per_cm(height_px, assumed_body_height_cm=170):
    """Rough pixel-to-cm conversion assuming full body is visible.

    This is a fallback when no A4 calibration is available.
    Uses frame height as a proportion of assumed body height.
    """
    # Assume the body fills about 75% of the frame height
    body_px = height_px * 0.75
    return body_px / assumed_body_height_cm


# ─────────────────────────────────────────────────────────────────
# Extended geometric helpers (Phase 1.3 — strength analyzer rewrite)
# ─────────────────────────────────────────────────────────────────

def signed_horizontal_offset_cm(point, line_a, line_b, px_per_cm):
    """Signed perpendicular offset of `point` from the line through (a, b).

    Sign convention: positive when `point` is on the right of the directed
    line a→b (using image coords where +x is right). Use for valgus / bar-
    over-midfoot offsets where direction matters.

    Returns None if any input is None or px_per_cm is invalid.
    """
    if point is None or line_a is None or line_b is None or not px_per_cm:
        return None
    ax, ay = float(line_a[0]), float(line_a[1])
    bx, by = float(line_b[0]), float(line_b[1])
    px, py = float(point[0]), float(point[1])
    ab_x, ab_y = bx - ax, by - ay
    ab_len = math.sqrt(ab_x * ab_x + ab_y * ab_y)
    if ab_len < 1e-8:
        return None
    # 2-D cross product (z-component) — sign carries side info
    cross = ab_x * (py - ay) - ab_y * (px - ax)
    offset_px = cross / ab_len
    return offset_px / px_per_cm


def pelvic_tilt_deg(l_hip, r_hip, l_shoulder, r_shoulder):
    """Anterior/posterior pelvic tilt proxy (frontal plane).

    Uses the angle between the hip-to-hip axis and the shoulder-to-shoulder
    axis. A truly neutral pelvis has these lines parallel; pelvic tilt rotates
    the hip line vs the shoulder line. Returns an unsigned angle in degrees.

    This is a 2-D proxy — it cannot distinguish true anterior tilt from a hip
    drop, but it is sensitive to butt-wink in the squat (the pelvis rotates
    under the spine, the hip line rotates relative to the torso line).
    """
    if l_hip is None or r_hip is None or l_shoulder is None or r_shoulder is None:
        return None
    hip_vec = (r_hip[0] - l_hip[0], r_hip[1] - l_hip[1])
    sh_vec = (r_shoulder[0] - l_shoulder[0], r_shoulder[1] - l_shoulder[1])
    a1 = math.degrees(math.atan2(hip_vec[1], hip_vec[0]))
    a2 = math.degrees(math.atan2(sh_vec[1], sh_vec[0]))
    diff = abs(a1 - a2) % 360
    if diff > 180:
        diff = 360 - diff
    return diff


def multipoint_spine_curvature(ear, shoulder, hip, mid_back=None):
    """4-point spine curvature deviation from a straight line, in degrees.

    `mid_back` may be supplied explicitly (e.g. T8 estimated from another
    landmark) or defaults to `0.6*shoulder + 0.4*hip` — the empirical
    rule-of-thumb for mid-thoracic position in lifting biomechanics.

    Returns the deviation of the mid-back point from the ear→hip line,
    expressed as an angle. Positive = the mid-back bows AWAY from the
    spine's neutral axis. This catches lumbar rounding in the deadlift
    much better than the existing 3-point EAR→SHOULDER→HIP angle, which
    is dominated by torso orientation rather than curvature.
    """
    if ear is None or shoulder is None or hip is None:
        return None
    if mid_back is None:
        mid_back = (0.6 * shoulder[0] + 0.4 * hip[0],
                    0.6 * shoulder[1] + 0.4 * hip[1])

    # angle at mid_back formed by mid_back→ear and mid_back→hip; deviation
    # from 180° (perfectly straight) is the curvature reading.
    interior = angle_3pt(ear, mid_back, hip)
    if interior is None:
        return None
    return abs(180.0 - interior)


def body_segment_lengths(frames_data, w, h, sample_every=3):
    """Median pixel lengths of the major body segments across a window.

    Returns dict with keys: tibia_px, femur_px, torso_px, upper_arm_px,
    forearm_px. Used to (a) normalize displacement thresholds to body size,
    and (b) feed the camera-view classifier.

    Skips frames with missing required landmarks. Returns None values when
    no frames in the window have the required landmarks visible.
    """
    from .landmarks import get_lm, LM  # local import to avoid cycles

    lengths = {
        'tibia_px':     [],
        'femur_px':     [],
        'torso_px':     [],
        'upper_arm_px': [],
        'forearm_px':   [],
    }

    for i, f in enumerate(frames_data):
        if i % sample_every:
            continue
        lm = f.get('landmarks')
        if lm is None:
            continue

        for side in ('LEFT', 'RIGHT'):
            ank = get_lm(lm, LM[f'{side}_ANKLE'], w, h)
            knee = get_lm(lm, LM[f'{side}_KNEE'], w, h)
            hip = get_lm(lm, LM[f'{side}_HIP'], w, h)
            sh = get_lm(lm, LM[f'{side}_SHOULDER'], w, h)
            el = get_lm(lm, LM[f'{side}_ELBOW'], w, h)
            wr = get_lm(lm, LM[f'{side}_WRIST'], w, h)
            if ank and knee:
                lengths['tibia_px'].append(distance_px(ank[:2], knee[:2]))
            if knee and hip:
                lengths['femur_px'].append(distance_px(knee[:2], hip[:2]))
            if hip and sh:
                lengths['torso_px'].append(distance_px(hip[:2], sh[:2]))
            if sh and el:
                lengths['upper_arm_px'].append(distance_px(sh[:2], el[:2]))
            if el and wr:
                lengths['forearm_px'].append(distance_px(el[:2], wr[:2]))

    def _med(vs):
        vs = [v for v in vs if v is not None and v > 0]
        if not vs:
            return None
        vs.sort()
        return vs[len(vs) // 2]

    return {k: _med(v) for k, v in lengths.items()}


def angle_to_vertical_signed(a, b):
    """Signed angle of vector a→b from vertical (downward Y axis).

    Image coords: +y is down. Returns degrees in [-180, 180].
    Positive = the vector points to the right of vertical.
    Useful for trunk-lean direction (forward vs backward).
    """
    if a is None or b is None:
        return None
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return math.degrees(math.atan2(dx, dy))
