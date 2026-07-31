"""Barbell-plate tracker for strength analysis.

Two responsibilities:

  1. **Plate detection** — find the circular plate (one or both ends of the
     bar) in a frame via HoughCircles. This gives us:
       • plate centre  → bar position
       • plate radius  → px/cm calibration (we know the real-world diameter)

  2. **Per-frame tracking** — once we have a seed location, run an OpenCV
     KCF tracker on subsequent frames. Falls back to re-detection when
     the tracker loses confidence.

The plate diameter map (kg → diameter mm) is the strength-side analog of
the tibia-length calibration we use for mobility:

  25 kg → 450 mm    20 kg → 450 mm   15 kg → 400 mm
  10 kg → 320 mm     5 kg → 230 mm

Caller passes plate_size_kg and we look up the diameter for the px/cm
conversion.
"""
from __future__ import annotations
import math
import cv2
import numpy as np

# Real-world plate diameters (millimetres). Caller picks the largest plate
# loaded on the bar; that's what HoughCircles will most reliably detect.
PLATE_DIAM_MM = {
    25.0: 450.0,
    20.0: 450.0,
    15.0: 400.0,
    10.0: 320.0,
    5.0:  230.0,
    2.5:  190.0,
    1.25: 160.0,
}

# Default plate size if the user doesn't tell us — assume a competition
# 20 kg plate. Most working sets at intermediate+ level use these.
DEFAULT_PLATE_KG = 20.0


def plate_diameter_cm(plate_size_kg=None):
    """Look up plate diameter in cm. Falls back to the 20 kg plate."""
    if plate_size_kg is None:
        plate_size_kg = DEFAULT_PLATE_KG
    diam_mm = PLATE_DIAM_MM.get(float(plate_size_kg))
    if diam_mm is None:
        # Round to the nearest known plate, otherwise default
        nearest = min(PLATE_DIAM_MM.keys(), key=lambda k: abs(k - float(plate_size_kg)))
        diam_mm = PLATE_DIAM_MM[nearest]
    return diam_mm / 10.0


def detect_plate(frame, expected_radius_px=None, search_roi=None):
    """Detect the most plausible plate centre via HoughCircles.

    Args:
        frame: BGR frame.
        expected_radius_px: rough size hint; if known, narrows the search.
        search_roi: (x, y, w, h) to search within; None = full frame.

    Returns:
        (cx, cy, r) in pixels, or None if no plate found.
    """
    if frame is None:
        return None

    if search_roi is not None:
        x0, y0, w, h = search_roi
        view = frame[y0:y0 + h, x0:x0 + w]
        offset = (x0, y0)
    else:
        view = frame
        offset = (0, 0)

    gray = cv2.cvtColor(view, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)

    # Radius window — narrow if we have an expectation, otherwise 5-25% of view height
    if expected_radius_px is not None:
        r_min = int(max(8, expected_radius_px * 0.7))
        r_max = int(expected_radius_px * 1.3)
    else:
        r_min = max(15, int(view.shape[0] * 0.05))
        r_max = int(view.shape[0] * 0.25)

    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1.2,
        minDist=int(view.shape[0] * 0.20),
        param1=120, param2=35,
        minRadius=r_min, maxRadius=r_max,
    )
    if circles is None:
        return None
    circles = np.round(circles[0]).astype(int)
    # Pick the largest detected circle (the plate is the biggest round thing
    # in a lifting setup; smaller circles are usually plate-pin holes / lights)
    circles = sorted(circles, key=lambda c: c[2], reverse=True)
    cx, cy, r = circles[0]
    return (cx + offset[0], cy + offset[1], r)


def calibrate_px_per_cm(frame, plate_size_kg=None, hint_radius_px=None):
    """Find a plate and convert its measured radius → real-world cm.

    Returns (px_per_cm: float, plate: (cx, cy, r) | None).
    """
    plate_cm = plate_diameter_cm(plate_size_kg)
    p = detect_plate(frame, expected_radius_px=hint_radius_px)
    if p is None:
        return 0.0, None
    cx, cy, r = p
    plate_diameter_px = r * 2.0
    return plate_diameter_px / plate_cm, p


def track_bar_path(video_path, plate_size_kg=None, sample_every=1, max_frames=None):
    """Track the bar through the whole video.

    Strategy:
        1. Find plate in frame 0 (HoughCircles).
        2. Initialise a KCF tracker on that bounding box.
        3. Step through the video; every N frames re-verify with HoughCircles
           inside the tracker's neighbourhood and snap back if drift > radius.
        4. Returns lists of (cx, cy) per frame and the calibration.

    Returns dict with:
      'centres':    list[ (x, y) | None ] aligned to frame index
      'quality':    list[ float in [0,1] ] aligned to frame index
                    1.0  = Hough re-verified within 1 radius of the tracker
                    0.5  = KCF tracker only (no recent verification)
                    0.0  = no detection / inherited from previous frame
      'px_per_cm':  float (0.0 if calibration failed)
      'frame_count': int
      'fps':        float
      'median_quality': float in [0,1] — bar-tracking confidence summary
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {'centres': [], 'px_per_cm': 0.0, 'frame_count': 0, 'fps': 30.0}
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if max_frames is not None:
        total = min(total, max_frames)

    ok, frame = cap.read()
    if not ok or frame is None:
        cap.release()
        return {'centres': [], 'px_per_cm': 0.0, 'frame_count': 0, 'fps': fps}

    px_per_cm, plate = calibrate_px_per_cm(frame, plate_size_kg)
    centres = [None] * total
    quality = [0.0] * total

    if plate is None:
        # No plate detected on frame 0 — bail and return calibration-only zeros
        cap.release()
        return {'centres': centres, 'quality': quality, 'px_per_cm': px_per_cm,
                'frame_count': total, 'fps': fps, 'median_quality': 0.0}

    cx, cy, r = plate
    centres[0] = (float(cx), float(cy))
    quality[0] = 1.0  # frame-0 Hough detection counts as verified
    bbox = (int(cx - r), int(cy - r), int(2 * r), int(2 * r))

    tracker = None
    try:
        tracker = cv2.TrackerKCF_create()
        tracker.init(frame, bbox)
    except Exception:
        tracker = None

    redetect_every = max(int(fps), 15)
    idx = 1
    while True:
        ok, frame = cap.read()
        if not ok or frame is None or idx >= total:
            break
        if idx % sample_every != 0:
            idx += 1
            continue

        # 1. Try the tracker
        new_centre = None
        q = 0.0
        if tracker is not None:
            ok_t, box = tracker.update(frame)
            if ok_t:
                x, y, ww, hh = box
                new_centre = (x + ww / 2.0, y + hh / 2.0)
                q = 0.5  # tracker-only confidence

        # 2. Every N frames, re-verify with HoughCircles near the last centre
        if idx % redetect_every == 0 and centres[idx - 1] is not None:
            lcx, lcy = centres[idx - 1]
            roi_size = int(r * 4)
            roi = (max(0, int(lcx - roi_size / 2)),
                   max(0, int(lcy - roi_size / 2)),
                   roi_size, roi_size)
            detect = detect_plate(frame, expected_radius_px=r, search_roi=roi)
            if detect is not None:
                dcx, dcy, dr = detect
                # If the tracker and detector disagree by more than the radius,
                # trust the detector and re-seed the tracker
                if new_centre is None or math.hypot(new_centre[0] - dcx, new_centre[1] - dcy) > r:
                    new_centre = (float(dcx), float(dcy))
                    try:
                        tracker = cv2.TrackerKCF_create()
                        tracker.init(frame, (int(dcx - dr), int(dcy - dr), int(2 * dr), int(2 * dr)))
                        r = dr
                    except Exception:
                        tracker = None
                q = 1.0  # verified by Hough
            elif new_centre is not None:
                # tracker still running but Hough couldn't confirm — derate
                q = 0.35

        if new_centre is not None:
            centres[idx] = new_centre
            quality[idx] = q
        else:
            # Drift fallback — inherit previous centre at zero confidence
            centres[idx] = centres[idx - 1]
            quality[idx] = 0.0
        idx += 1

    cap.release()

    valid_q = [v for v in quality if v > 0]
    median_q = 0.0
    if valid_q:
        valid_q.sort()
        median_q = valid_q[len(valid_q) // 2]

    return {
        'centres':         centres,
        'quality':         quality,
        'px_per_cm':       px_per_cm,
        'frame_count':     total,
        'fps':             fps,
        'median_quality':  median_q,
    }


def mean_concentric_velocity(centres, start_idx, end_idx, fps, px_per_cm):
    """Mean concentric velocity in m/s over the bar's ascent.

    centres: list[(x, y) | None], indexed by frame.
    start_idx, end_idx: concentric phase bounds (e.g. trough → peak of bar Y).
    """
    if px_per_cm <= 0 or end_idx <= start_idx:
        return 0.0
    pts = [c for c in centres[start_idx:end_idx + 1] if c is not None]
    if len(pts) < 2:
        return 0.0
    # Sum Euclidean path length, then divide by elapsed seconds
    path_px = 0.0
    for a, b in zip(pts[:-1], pts[1:]):
        path_px += math.hypot(b[0] - a[0], b[1] - a[1])
    path_m = (path_px / px_per_cm) / 100.0
    duration_s = (end_idx - start_idx) / fps
    if duration_s <= 0:
        return 0.0
    return path_m / duration_s


def bar_path_rms_x(centres, start_idx, end_idx):
    """RMS X-deviation of the bar from its mean X position over a phase.

    Returns RMS in pixels. Divide by px_per_cm in the caller for cm units.
    """
    xs = [c[0] for c in centres[start_idx:end_idx + 1] if c is not None]
    if len(xs) < 3:
        return 0.0
    mean_x = sum(xs) / len(xs)
    return math.sqrt(sum((x - mean_x) ** 2 for x in xs) / len(xs))


def bar_velocity_series(centres, fps, px_per_cm, axis='y'):
    """Kalman-smoothed bar velocity series in m/s.

    Args:
        centres:    list[ (x, y) | None ] from track_bar_path.
        fps:        video framerate.
        px_per_cm:  calibration (must be > 0 for meaningful units).
        axis:       'y' (default, vertical for squat/dl/ohp/bench) or 'x'.

    Returns list[float] aligned to frame index. Sign convention:
        axis='y': +ve = bar moving UP in the world (i.e. -dy in image coords).
        axis='x': +ve = bar moving right in image coords.

    When px_per_cm is 0 or invalid, returns m/s computed from a fallback
    px-per-cm of 1 (i.e. units become pixels/sec); callers should check
    px_per_cm separately.
    """
    n = len(centres)
    if n == 0:
        return []
    # extract the chosen axis with Nones
    raw = []
    for c in centres:
        if c is None:
            raw.append(None)
        else:
            raw.append(c[1] if axis == 'y' else c[0])

    # Kalman smooth the position, then central-difference for velocity
    from .signal_filters import kalman_1d  # local import to avoid cycle
    smoothed = kalman_1d(raw, fps=fps, q=1e-3, r=1e-2)

    px_to_m = (1.0 / (px_per_cm * 100.0)) if px_per_cm > 0 else 1.0
    dt = 1.0 / max(fps, 1e-6)
    vel = [0.0] * n
    for i in range(n):
        if i == 0 or i == n - 1:
            continue
        v_px = (smoothed[i + 1] - smoothed[i - 1]) / (2 * dt)
        v_m = v_px * px_to_m
        # Flip sign on Y so +ve = up (world) for caller convenience
        if axis == 'y':
            v_m = -v_m
        vel[i] = v_m
    if n >= 2:
        vel[0] = vel[1]
        vel[-1] = vel[-2]
    return vel


def bar_path_horizontal_drift_cm(centres, start_idx, end_idx, px_per_cm,
                                  baseline_x=None):
    """Horizontal drift summary for a phase.

    Returns dict:
        max_drift_cm:        peak |x - baseline| across the phase
        drift_at_top_cm:     final - initial X position (signed)
        rms_drift_cm:        RMS deviation from baseline

    `baseline_x` defaults to the first valid centre's x. RMS uses the mean if
    baseline_x is None (legacy behaviour).
    """
    if px_per_cm <= 0:
        return {'max_drift_cm': 0.0, 'drift_at_top_cm': 0.0, 'rms_drift_cm': 0.0}
    pts = [(i, c) for i, c in enumerate(centres[start_idx:end_idx + 1]) if c is not None]
    if len(pts) < 2:
        return {'max_drift_cm': 0.0, 'drift_at_top_cm': 0.0, 'rms_drift_cm': 0.0}
    xs = [c[0] for _, c in pts]
    base = baseline_x if baseline_x is not None else xs[0]
    deltas = [x - base for x in xs]
    max_drift = max(abs(d) for d in deltas)
    drift_top = xs[-1] - xs[0]
    mean_x = sum(xs) / len(xs)
    rms = math.sqrt(sum((x - mean_x) ** 2 for x in xs) / len(xs))
    return {
        'max_drift_cm':    round(max_drift / px_per_cm, 2),
        'drift_at_top_cm': round(drift_top / px_per_cm, 2),
        'rms_drift_cm':    round(rms / px_per_cm, 2),
    }


# ─────────────────────────────────────────────────────────────
# 1RM estimators (used by every strength analyzer)
# ─────────────────────────────────────────────────────────────

def estimate_1rm(load_kg, reps):
    """Both Epley and Brzycki 1RM estimates."""
    if not load_kg or load_kg <= 0 or not reps or reps <= 0:
        return {'epley': 0.0, 'brzycki': 0.0}
    epley = load_kg * (1.0 + reps / 30.0)
    brzycki = load_kg * 36.0 / (37.0 - reps) if reps < 37 else load_kg
    return {'epley': round(epley, 1), 'brzycki': round(brzycki, 1)}
