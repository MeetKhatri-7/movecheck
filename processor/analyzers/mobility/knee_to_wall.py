"""Exercise 1 — Knee-to-Wall Test (Ankle Dorsiflexion).

Camera: Side view, 90° to athlete, hip height, 1.5–2 m
         (optional) Front view, hip height — required for knee valgus
Landmarks: ANKLE(27/28), KNEE(25/26), HIP(23/24), FOOT_INDEX(31/32), HEEL(29/30)

Pipeline upgrades (2026-05-12):

  1. CALIBRATION — Tibia length (cm) is the known constant.
     `px_per_cm = (knee→ankle pixel distance) / tibia_length_cm`
     This is a zero-setup calibration; no A4 paper / no ruler required.
     Falls back to estimate_px_per_cm(h) only if tibia_length_cm is missing.

  2. HEEL LIFT — Binary pixel-intensity check at the baseline heel
     position. If the pixels there brighten (background visible because
     the heel has rolled off the floor), it counts as a lift even if
     the landmark Y has barely moved. Pairs with a tightened geometric
     threshold of 0.5 cm (1.5 cm was too lenient for pro-sport screening).

  3. KNEE VALGUS — Requires a front-view video. From side view the
     medial caving collapses into the camera's depth axis and is
     invisible, so we no longer attempt to report valgus from the
     side-only file. If `front` is supplied, we compute
     frontal_plane_valgus_deg = 180 − angle_3pt(hip, knee, ankle).

Inputs:
   - left          (required)  Left side view, 3 reps
   - right         (required)  Right side view, 3 reps
   - front         (optional)  Front view, 1 rep each side
   - tibiaLengthCm (optional)  User's tibia length in cm
"""
import math
import cv2
import numpy as np
from utils.landmarks import (
    extract_all_landmarks, get_landmark_px, LM, confidence_score
)
from utils.angles import (
    angle_3pt, angle_to_vertical, estimate_px_per_cm
)
from utils.rep_detection import detect_reps
from utils.scoring import (
    classify, build_metric, build_bilateral, build_result,
    compute_overall_score, overall_status, generate_coaching_notes
)
from utils.frame_annotator import (
    extract_frame_at, frame_to_base64,
    draw_skeleton, draw_angle_arc, draw_distance_line, draw_reference_line,
    draw_callout, draw_phase_label, draw_title_strip, draw_metric_overlay,
    draw_legend, draw_rep_label, _lm_to_px,
    COL_GOOD, COL_BAD, COL_DISTANCE,
)

# Green skeleton for clinical look (BGR)
COL_GREEN        = (100, 220, 80)
COL_GREEN_BRIGHT = (120, 255, 100)
COL_CYAN         = (230, 200, 50)

LEG_CONNECTIONS = [
    (23, 25), (25, 27), (27, 29), (27, 31),
    (24, 26), (26, 28), (28, 30), (28, 32),
    (23, 24), (11, 23), (12, 24), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]

# Spec threshold (AI_Metrics_Specification-Mobility.md): heel lift is a lift
# only above 1.5 cm; 1.5–3 cm = NEEDS IMPROVEMENT; >3 cm = RESTRICTED.
HEEL_LIFT_THRESHOLD_CM = 1.5
HEEL_LIFT_RESTRICTED_CM = 3.0
# Pixel-occupancy ROI ("Ghost-heel" detection): 10×10 patch at the baseline
# heel-floor contact point, MSE between baseline and peak frame. If the
# texture / brightness changes (floor visible through where heel used to be),
# MSE rises sharply. ~100 on a 0-255 grayscale scale picks up ~2 mm of lift.
HEEL_PIXEL_PATCH = 10
HEEL_MSE_THRESHOLD = 100.0
# Pelvis-rotation guard for the seated hip rotation test (used elsewhere).
# Knee-touches-wall via Canny-detected wall edge
WALL_EDGE_CANNY_LOW  = 30
WALL_EDGE_CANNY_HIGH = 90
WALL_EDGE_MIN_LEN_FRAC = 0.30   # min line length as fraction of frame height


# ─────────────────────────────────────────────────────────────
# Calibration — tibia length is the known constant
# ─────────────────────────────────────────────────────────────

def _calibrate_px_per_cm(frames, knee_idx, ankle_idx, w, h, tibia_length_cm):
    """Compute px/cm from the knee→ankle pixel distance in the resting frames.

    Tibia length is the most camera-position-stable rigid body segment
    visible in this test, so it's the cleanest known constant for a
    zero-setup conversion.

    Returns a fallback (estimate_px_per_cm) if calibration is impossible.
    """
    if not tibia_length_cm or tibia_length_cm <= 0:
        return estimate_px_per_cm(h), 'fallback-estimate'

    distances = []
    sample = frames[:max(int(len(frames) * 0.15), 15)]
    for f in sample:
        lm = f['landmarks']
        if lm is None:
            continue
        knee  = get_landmark_px(lm, knee_idx,  w, h)
        ankle = get_landmark_px(lm, ankle_idx, w, h)
        if knee and ankle:
            dist = math.hypot(knee[0] - ankle[0], knee[1] - ankle[1])
            if dist > 30:                          # ignore degenerate detections
                distances.append(dist)

    if len(distances) < 5:
        return estimate_px_per_cm(h), 'fallback-estimate'

    distances.sort()
    median_px = distances[len(distances) // 2]
    return median_px / tibia_length_cm, 'tibia-calibrated'


# ─────────────────────────────────────────────────────────────
# Heel lift — pixel-intensity binary check
# ─────────────────────────────────────────────────────────────

def _extract_patch(frame, center_xy, patch=HEEL_PIXEL_PATCH):
    """Return a `patch × patch` grayscale ROI centred on (x,y).

    Returns None if the patch can't be fully extracted (off frame / shrunk).
    """
    if frame is None or center_xy is None:
        return None
    fh, fw = frame.shape[:2]
    cx, cy = int(center_xy[0]), int(center_xy[1])
    half = patch // 2
    x0, x1 = max(0, cx - half), min(fw, cx + half)
    y0, y1 = max(0, cy - half), min(fh, cy + half)
    if (x1 - x0) < patch or (y1 - y0) < patch:
        return None
    return cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)


def _pixel_heel_lift(video_path, baseline_frame_idx, peak_frame_idx, heel_baseline_px):
    """Pixel-occupancy ROI ("Ghost Heel") detection.

    Compares a 10×10 ROI at the *baseline heel-floor contact point* between
    the resting frame and the peak frame. Uses **mean squared error** on
    grayscale pixels, which catches texture changes (floor tile / shadow
    line visible) that a simple brightness Δ would miss.

      • Heel still on floor at peak → both patches contain heel/shoe → low MSE
      • Heel lifted at peak         → background visible at the baseline
                                       location → high MSE

    Returns (lifted: bool, mse: float).
    """
    if heel_baseline_px is None:
        return False, 0.0
    base = extract_frame_at(video_path, baseline_frame_idx)
    peak = extract_frame_at(video_path, peak_frame_idx)
    b_roi = _extract_patch(base, heel_baseline_px)
    p_roi = _extract_patch(peak, heel_baseline_px)
    if b_roi is None or p_roi is None:
        return False, 0.0
    mse = float(np.mean((p_roi.astype(np.float32) - b_roi.astype(np.float32)) ** 2))
    return mse >= HEEL_MSE_THRESHOLD, mse


def _detect_wall_edge_x(video_path, w, h, toe_x):
    """Automated wall mapping — find the vertical line of a wall/doorframe.

    Runs Canny on the first 5 frames, then HoughLinesP for near-vertical
    segments. Picks the line CLOSEST to the toe (in the direction the knee
    travels) — that's the wall/doorframe the athlete is driving toward.

    Returns the wall X-coordinate in pixels, or None if no plausible
    vertical edge is detectable.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    candidates = []
    for _ in range(5):
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        # Edge detection must run at moderate resolution: on soft 4K phone
        # footage the wall edge's gradient is spread across many pixels, so
        # full-res Canny at these thresholds finds NOTHING (verified on the
        # sample corpus — 0 lines at 4K, clean doorframe lines at 1/4 res).
        fh = frame.shape[0]
        det_scale = min(1.0, 960.0 / fh)
        det = cv2.resize(frame, None, fx=det_scale, fy=det_scale,
                         interpolation=cv2.INTER_AREA) if det_scale < 1.0 else frame
        gray = cv2.cvtColor(det, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, WALL_EDGE_CANNY_LOW, WALL_EDGE_CANNY_HIGH)
        min_len = int(det.shape[0] * WALL_EDGE_MIN_LEN_FRAC)
        lines = cv2.HoughLinesP(
            edges, rho=1, theta=np.pi / 180,
            threshold=60, minLineLength=min_len, maxLineGap=12,
        )
        if lines is None:
            continue
        for line in np.asarray(lines).reshape(-1, 4):
            x1, y1, x2, y2 = line
            dx, dy = (x2 - x1), (y2 - y1)
            if dx == 0:
                ang = 90.0
            else:
                ang = abs(math.degrees(math.atan2(dy, dx)))
            # Near-vertical: 80..100° from horizontal
            if 80 <= ang <= 100:
                candidates.append(((x1 + x2) / 2.0) / det_scale)
    cap.release()
    if not candidates:
        return None
    return candidates


def _pick_wall_x(candidates, peak_knee_x, travel_sign, px_per_cm):
    """Choose the wall line the knee is actually driving toward.

    The wall must lie in the direction of knee travel, at (or just behind —
    touch overlap) the knee's furthest point. Lines behind the athlete or
    far past the knee's reach are furniture/door edges, not the target.
    """
    if not candidates:
        return None
    allowance_px = 10.0 * px_per_cm if px_per_cm and px_per_cm > 0 else 100.0
    reach_px     = 12.0 * px_per_cm if px_per_cm and px_per_cm > 0 else 120.0
    plausible = []
    for x in candidates:
        delta = (x - peak_knee_x) * travel_sign   # + = in front of knee's furthest point
        # A real touch target sits within reach of the deepest lunge. A line
        # >12 cm past the knee's furthest point is a door/furniture edge —
        # reporting a "gap" to it would be misleading, so it's rejected and
        # the wall metric is omitted for the video instead.
        if -allowance_px <= delta <= reach_px:
            plausible.append((abs(delta), x))
    if not plausible:
        return None
    plausible.sort()
    return plausible[0][1]


# ─────────────────────────────────────────────────────────────
# Front view — knee valgus
# ─────────────────────────────────────────────────────────────

def _analyse_front_view(video_path, tibia_length_cm=None):
    """From a front-view video, compute peak knee valgus + arch collapse.

    VALGUS (frontal-plane knee tracking):
      valgus_deg = 180 − angle_3pt(hip, knee, ankle), 90th-percentile.

    ARCH COLLAPSE (the "Cheat Checker"):
      Athletes with stiff ankles cheat by pronating — the ankle drifts
      medially relative to the 1st-metatarsal (FOOT_INDEX) while the knee
      moves forward. We track the per-leg `ankle.x − toe.x` offset:
        • baseline = median over first 0.5 s
        • collapse_px = baseline_offset − peak_offset, signed so that
          a positive value means the ankle moved *toward* the body midline
          relative to the toe — i.e., the arch fell.
      Reported in cm if tibia calibration is available, else px.

    Returns dict with valgus + arch values or None on failure.
    """
    if not video_path:
        return None
    try:
        data = extract_all_landmarks(video_path)
    except Exception as e:
        print(f"[knee_to_wall.front] failed: {e}")
        return None

    frames = data['frames']
    w, h   = data['width'], data['height']
    fps    = data['fps']
    if not frames:
        return None

    # Calibrate using LEFT tibia (left leg is most likely visible in the front shot)
    px_per_cm_l, _ = _calibrate_px_per_cm(
        frames, LM['LEFT_KNEE'],  LM['LEFT_ANKLE'],  w, h, tibia_length_cm
    )
    px_per_cm_r, _ = _calibrate_px_per_cm(
        frames, LM['RIGHT_KNEE'], LM['RIGHT_ANKLE'], w, h, tibia_length_cm
    )

    def _signed_valgus(hip, knee, ankle):
        if not (hip and knee and ankle):
            return None
        ang = angle_3pt(hip, knee, ankle)
        if ang is None:
            return None
        return max(0.0, 180.0 - ang)

    # Per-frame offsets (ankle.x − toe.x) for arch tracking
    l_offsets, r_offsets = [], []
    l_peaks_val, r_peaks_val = [], []
    for f in frames:
        lm = f['landmarks']
        if lm is None:
            l_offsets.append(None); r_offsets.append(None); continue

        l_hip   = get_landmark_px(lm, LM['LEFT_HIP'],        w, h)
        l_knee  = get_landmark_px(lm, LM['LEFT_KNEE'],       w, h)
        l_ankle = get_landmark_px(lm, LM['LEFT_ANKLE'],      w, h)
        l_toe   = get_landmark_px(lm, LM['LEFT_FOOT_INDEX'], w, h)
        r_hip   = get_landmark_px(lm, LM['RIGHT_HIP'],       w, h)
        r_knee  = get_landmark_px(lm, LM['RIGHT_KNEE'],      w, h)
        r_ankle = get_landmark_px(lm, LM['RIGHT_ANKLE'],     w, h)
        r_toe   = get_landmark_px(lm, LM['RIGHT_FOOT_INDEX'],w, h)

        lv = _signed_valgus(l_hip, l_knee, l_ankle)
        rv = _signed_valgus(r_hip, r_knee, r_ankle)
        if lv is not None: l_peaks_val.append(lv)
        if rv is not None: r_peaks_val.append(rv)

        l_offsets.append(l_ankle[0] - l_toe[0] if (l_ankle and l_toe) else None)
        r_offsets.append(r_ankle[0] - r_toe[0] if (r_ankle and r_toe) else None)

    if not l_peaks_val and not r_peaks_val:
        return None

    # 90th-percentile worst-case valgus
    def _p90(arr):
        if not arr: return 0.0
        arr = sorted(arr)
        return arr[int(len(arr) * 0.90)]

    # ── Arch collapse ──
    # Baseline = median of first 0.5 s of offsets (foot is still + flat)
    baseline_n = max(int(fps * 0.5), 10)

    def _arch_collapse_cm(offsets, side, px_per_cm):
        baseline = [o for o in offsets[:baseline_n] if o is not None]
        if not baseline:
            return 0.0
        base = sorted(baseline)[len(baseline) // 2]
        # Worst medial drift: ankle pulls toward body midline relative to toe.
        # Side-aware sign: for LEFT leg, midline is to the RIGHT (+x) of the
        # foot, so medial drift = current_offset > baseline (ankle moves +x
        # relative to toe). For RIGHT leg it's the opposite.
        worst = 0.0
        for o in offsets[baseline_n:]:
            if o is None: continue
            if side == 'left':
                drift = o - base                 # positive = medial
            else:
                drift = base - o
            if drift > worst:
                worst = drift
        return (worst / px_per_cm) if px_per_cm > 0 else 0.0

    l_arch_cm = _arch_collapse_cm(l_offsets, 'left',  px_per_cm_l)
    r_arch_cm = _arch_collapse_cm(r_offsets, 'right', px_per_cm_r)

    return {
        'left_valgus':  round(_p90(l_peaks_val), 1),
        'right_valgus': round(_p90(r_peaks_val), 1),
        'left_arch_collapse_cm':  round(l_arch_cm, 2),
        'right_arch_collapse_cm': round(r_arch_cm, 2),
        'valid':        bool(l_peaks_val or r_peaks_val),
    }


# ─────────────────────────────────────────────────────────────
# Per-side analysis
# ─────────────────────────────────────────────────────────────

def _analyse_side(video_path, side_label, tibia_length_cm):
    """Analyse one side video for knee-to-wall."""
    data = extract_all_landmarks(video_path)
    frames = data['frames']
    fps = data['fps']
    w, h = data['width'], data['height']
    conf = confidence_score(frames)

    knee_idx  = LM['LEFT_KNEE']        if side_label == 'left' else LM['RIGHT_KNEE']
    ankle_idx = LM['LEFT_ANKLE']       if side_label == 'left' else LM['RIGHT_ANKLE']
    hip_idx   = LM['LEFT_HIP']         if side_label == 'left' else LM['RIGHT_HIP']
    heel_idx  = LM['LEFT_HEEL']        if side_label == 'left' else LM['RIGHT_HEEL']
    toe_idx   = LM['LEFT_FOOT_INDEX']  if side_label == 'left' else LM['RIGHT_FOOT_INDEX']

    # ── Upgrade 1: tibia-length calibration (Pixels Per CM = L_px / X_cm) ──
    px_per_cm, cal_mode = _calibrate_px_per_cm(
        frames, knee_idx, ankle_idx, w, h, tibia_length_cm
    )

    # ── Upgrade 4: automated wall detection via Canny ──
    # Collect vertical-line candidates now; the actual wall is picked after
    # rep detection, when we know where the knee travels (see _pick_wall_x).
    wall_candidates = _detect_wall_edge_x(video_path, w, h, 0)

    # ── Build the movement signal: shin lean from vertical ──
    # Weight-bearing dorsiflexion in the knee-to-wall test IS the tibia's
    # forward inclination: with the foot planted, every degree the shin leans
    # toward the wall is a degree of ankle dorsiflexion. This is far more
    # robust than 90−angle3pt(knee,ankle,toe), whose value depends on the
    # foot-index landmark's position along the foot and therefore reported
    # single-digit "dorsiflexion" on textbook 35° reps.
    shin_lean = []       # degrees from vertical, 0 = upright shin
    ankle_angles = []    # knee-ankle-toe joint angle (secondary metric)
    knee_xs = []         # knee X per frame — used for wall-target selection
    for f in frames:
        lm = f['landmarks']
        if lm is None:
            shin_lean.append(0.0)
            ankle_angles.append(None)
            knee_xs.append(None)
            continue
        knee  = get_landmark_px(lm, knee_idx,  w, h)
        ankle = get_landmark_px(lm, ankle_idx, w, h)
        toe   = get_landmark_px(lm, toe_idx,   w, h)
        av = angle_to_vertical(ankle, knee) if ankle and knee else None
        # ankle→knee points up: 180° = vertical shin, so lean = 180 − angle.
        shin_lean.append(max(0.0, 180.0 - av) if av is not None else 0.0)
        ankle_angles.append(angle_3pt(knee, ankle, toe))
        knee_xs.append(knee[0] if knee else None)

    reps = detect_reps(shin_lean, expected_reps=3, fps=fps, min_hold_sec=0.3)

    # Pick the wall line from the knee's travel: direction = rest → deepest
    # lean, target = furthest knee X reached across all reps.
    wall_x = None
    if wall_candidates:
        lean_order = sorted(range(len(shin_lean)), key=lambda i: shin_lean[i])
        rest_xs = [knee_xs[i] for i in lean_order[:max(10, len(lean_order)//5)]
                   if knee_xs[i] is not None]
        deep_xs = [knee_xs[i] for i in lean_order[-max(10, len(lean_order)//10):]
                   if knee_xs[i] is not None]
        if rest_xs and deep_xs:
            rest_x = sorted(rest_xs)[len(rest_xs)//2]
            deep_x = sorted(deep_xs)[len(deep_xs)//2]
            sign = 1.0 if deep_x >= rest_x else -1.0
            peak_knee_x = max(deep_xs) if sign > 0 else min(deep_xs)
            wall_x = _pick_wall_x(wall_candidates, peak_knee_x, sign, px_per_cm)

    # ── Per-rep analysis — all metrics at the TRUE extreme frame ──
    rep_results = []
    for rep in reps:
        seg_start = rep['start_frame']
        seg_end   = min(rep['end_frame'] + 1, len(frames))

        # True extreme = frame with max shin lean inside the rep window
        # (detect_reps peaks on the smoothed signal, which lags the extreme).
        peak = max(range(seg_start, seg_end), key=lambda i: shin_lean[i])
        lm = frames[peak]['landmarks'] if peak < len(frames) else None
        if lm is None:
            rep_results.append(None)
            continue

        knee  = get_landmark_px(lm, knee_idx,  w, h)
        ankle = get_landmark_px(lm, ankle_idx, w, h)
        toe   = get_landmark_px(lm, toe_idx,   w, h)

        dorsiflexion_deg = shin_lean[peak]
        ankle_angle = round(ankle_angles[peak], 1) if ankle_angles[peak] is not None else 90.0

        # Knee forward travel — horizontal knee-past-toe at the true extreme
        knee_past_toe_px = abs(knee[0] - toe[0]) if (knee and toe) else 0
        knee_travel_cm = knee_past_toe_px / px_per_cm if px_per_cm > 0 else 0

        # Knee-touches-wall pass/fail (only meaningful if a wall edge was found)
        knee_at_wall = None
        wall_gap_cm  = None
        if wall_x is not None and knee and toe:
            gap_px = (wall_x - knee[0]) if wall_x > toe[0] else (knee[0] - wall_x)
            wall_gap_cm = (gap_px / px_per_cm) if px_per_cm > 0 else gap_px
            # The KNEE landmark is the joint centre, ~5 cm behind the patella
            # surface — when the kneecap touches the wall the landmark still
            # reads a ~5 cm gap. Allow that radius plus 1 cm of tolerance.
            knee_at_wall = wall_gap_cm <= 6.0

        # ── Heel lift — per-rep baseline, loaded-window measurement ──
        # Baseline: heel Y while the shin is still upright at the START of
        # THIS rep (lean < 40% of the rep's own max). A global first-frames
        # baseline breaks when the athlete steps/repositions between reps —
        # it reported >9 cm phantom lifts on clean reps.
        # Lift is only meaningful while the ankle is loaded (lean ≥ 70% of
        # rep max): stepping out of the lunge afterwards is not a heel lift.
        rep_max_lean = shin_lean[peak]
        base_ys, base_frame_idx, base_heel_px = [], None, None
        for fi in range(seg_start, seg_end):
            if shin_lean[fi] > rep_max_lean * 0.4:
                continue
            flm = frames[fi]['landmarks']
            if flm is None:
                continue
            h_pt = get_landmark_px(flm, heel_idx, w, h)
            if h_pt:
                base_ys.append(h_pt[1])
                if base_frame_idx is None:
                    base_frame_idx, base_heel_px = fi, h_pt
        heel_baseline_y = None
        if base_ys:
            base_ys.sort()
            heel_baseline_y = base_ys[len(base_ys) // 2]

        max_heel_lift = 0.0
        for fi in range(seg_start, seg_end):
            if shin_lean[fi] < rep_max_lean * 0.7:
                continue
            flm = frames[fi]['landmarks']
            if flm is None:
                continue
            h_pt = get_landmark_px(flm, heel_idx, w, h)
            if h_pt and heel_baseline_y is not None:
                lift_px = heel_baseline_y - h_pt[1]      # image: up = smaller Y
                if lift_px > 0:
                    cm = lift_px / px_per_cm if px_per_cm > 0 else 0
                    if cm > max_heel_lift:
                        max_heel_lift = cm

        # Pixel-intensity confirmation, against THIS rep's own baseline frame
        pixel_lift, pixel_delta = _pixel_heel_lift(
            video_path, base_frame_idx if base_frame_idx is not None else seg_start,
            peak, base_heel_px
        )
        # Geometric measurement decides; pixel evidence only corroborates a
        # borderline geometric lift (within 0.5 cm of threshold), it can no
        # longer flag a lift on its own — patch MSE fires on any foot shift.
        heel_lifted = (max_heel_lift > HEEL_LIFT_THRESHOLD_CM) or \
                      (pixel_lift and max_heel_lift > HEEL_LIFT_THRESHOLD_CM - 0.5)

        # End-range hold: time spent at ≥90% of this rep's max lean
        hold_frames = sum(
            1 for fi in range(seg_start, seg_end)
            if shin_lean[fi] >= rep_max_lean * 0.9
        )
        hold_sec = hold_frames / fps if fps > 0 else 0

        rep_results.append({
            'peak_frame':       peak,
            'ankle_angle':      ankle_angle,
            'dorsiflexion_deg': round(dorsiflexion_deg, 1),
            'tibia_angle':      round(dorsiflexion_deg, 1),   # same physical quantity
            'knee_travel_cm':   round(knee_travel_cm, 1),
            'heel_lift_cm':     round(max_heel_lift, 1),
            'heel_mse':         round(pixel_delta, 1),
            'heel_lifted':      heel_lifted,
            'hold_sec':         round(hold_sec, 1),
            'wall_gap_cm':      round(wall_gap_cm, 1) if wall_gap_cm is not None else None,
            'knee_at_wall':     knee_at_wall,
            'heel_baseline_y':  heel_baseline_y,
        })

    valid = [r for r in rep_results if r is not None]
    valid_count = len(valid)
    total_count = len(reps) if reps else 3

    if not valid:
        return {
            'side': side_label, 'valid_reps': 0, 'total_reps': total_count,
            'best_dorsiflexion': 0, 'best_ankle_angle': 90, 'best_tibia': 0,
            'avg_knee_travel': 0, 'max_heel_lift': 0, 'any_heel_lifted': False,
            'best_hold': 0, 'confidence': conf, 'per_rep': [], 'annotated_frames': [],
            'px_per_cm': px_per_cm, 'calibration_mode': cal_mode,
        }

    best_dorsi  = max(r['dorsiflexion_deg'] for r in valid)
    best_ankle  = min(r['ankle_angle']      for r in valid)
    avg_travel  = sum(r['knee_travel_cm']   for r in valid) / len(valid)
    max_heel    = max(r['heel_lift_cm']     for r in valid)
    any_lifted  = any(r['heel_lifted']      for r in valid)
    best_hold   = max(r['hold_sec']         for r in valid)
    best_tibia  = max(r['tibia_angle']      for r in valid)

    # ── Annotated frames — every metric visualised on the body ──
    annotated = []
    best_rep_idx = max(range(len(valid)), key=lambda i: valid[i]['dorsiflexion_deg'])
    for i, rep in enumerate(valid):
        is_best = (i == best_rep_idx)
        pk = rep['peak_frame']
        lm = frames[pk]['landmarks'] if pk < len(frames) else None
        if lm is None:
            continue
        frame = extract_frame_at(video_path, pk)
        if frame is None:
            continue

        # ── 1. Skeleton ──
        draw_skeleton(frame, lm, w, h, connections=LEG_CONNECTIONS,
                      color=COL_GREEN, thickness=3)

        knee_px  = _lm_to_px(lm, knee_idx,  w, h)
        ankle_px = _lm_to_px(lm, ankle_idx, w, h)
        toe_px   = _lm_to_px(lm, toe_idx,   w, h)
        heel_px  = _lm_to_px(lm, heel_idx,  w, h)

        # ── 2. Reference lines: wall edge + this rep's heel-baseline floor ──
        if wall_x is not None:
            wall_status = 'good' if rep.get('knee_at_wall') else 'bad'
            tag = 'WALL TOUCH' if rep.get('knee_at_wall') else f"GAP {rep.get('wall_gap_cm')}cm"
            draw_reference_line(frame, x=wall_x, status=wall_status, label=tag)
        rep_heel_base_y = rep.get('heel_baseline_y')
        if rep_heel_base_y is not None:
            draw_reference_line(frame, y=rep_heel_base_y, color=COL_CYAN,
                                label='Floor baseline')

        # ── 3. Angle arcs (status-coloured) ──
        if knee_px and ankle_px and toe_px:
            dorsi_status = 'good' if rep['dorsiflexion_deg'] >= 35 else \
                           ('warn' if rep['dorsiflexion_deg'] >= 20 else 'bad')
            draw_angle_arc(frame, ankle_px, knee_px, toe_px,
                           rep['ankle_angle'],
                           label=f"Dorsi {rep['dorsiflexion_deg']}°",
                           radius=52, status=dorsi_status)
        if ankle_px and knee_px:
            vert_pt = (ankle_px[0], ankle_px[1] - 120)
            tibia_status = 'good' if rep['tibia_angle'] >= 35 else \
                           ('warn' if rep['tibia_angle'] >= 20 else 'bad')
            draw_angle_arc(frame, ankle_px, knee_px, vert_pt,
                           rep['tibia_angle'],
                           label=f"Shin lean {rep['tibia_angle']}°",
                           radius=40, status=tibia_status)

        # ── 4. Knee travel distance ──
        if knee_px and toe_px:
            travel_status = 'good' if rep['knee_travel_cm'] >= 10 else \
                            ('warn' if rep['knee_travel_cm'] >= 5 else 'bad')
            draw_distance_line(frame, (toe_px[0], toe_px[1]),
                               (knee_px[0], toe_px[1]),
                               f"Knee Travel {rep['knee_travel_cm']}cm",
                               status=travel_status)

        # ── 5. Heel callout (with MSE detail when pixel-confirmed) ──
        if heel_px:
            if rep['heel_lifted']:
                lift_lbl = f"HEEL LIFT {rep['heel_lift_cm']}cm  (MSE {rep['heel_mse']})"
                draw_callout(frame, heel_px, lift_lbl, status='bad', offset=(80, 50))
                if rep_heel_base_y is not None:
                    draw_distance_line(frame, heel_px,
                                       (heel_px[0], int(rep_heel_base_y)),
                                       '', status='bad')
            else:
                draw_callout(frame, heel_px, 'Heel Contact ✓',
                             status='good', offset=(80, 50))

        # ── 6. End-range hold callout near the knee ──
        if knee_px:
            hold_status = 'good' if rep['hold_sec'] >= 0.5 else 'warn'
            draw_callout(frame, knee_px, f"End-Range Hold {rep['hold_sec']}s",
                         status=hold_status, offset=(-160, -50))

        # ── 7. Title + phase + metric card + legend ──
        # (overall score/status are computed in analyse() — title strip handles None)
        draw_title_strip(frame, 'Knee-to-Wall', i + 1, len(valid), side=side_label)
        draw_phase_label(frame, 'Peak Dorsiflexion')

        overlay_metrics = [
            {'label': 'Ankle Dorsiflexion', 'value': f"{rep['dorsiflexion_deg']}°",
             'status': 'good' if rep['dorsiflexion_deg'] >= 35 else 'bad'},
            {'label': 'Shin–Foot Angle',    'value': f"{rep['ankle_angle']}°",
             'status': 'good'},
            {'label': 'Shin Lean (vert.)',  'value': f"{rep['tibia_angle']}°",
             'status': 'good' if rep['tibia_angle'] >= 35 else 'bad'},
            {'label': 'Knee Travel',        'value': f"{rep['knee_travel_cm']} cm",
             'status': 'good' if rep['knee_travel_cm'] >= 10 else 'bad'},
            {'label': 'Heel Lift',          'value': f"{rep['heel_lift_cm']} cm",
             'status': 'bad' if rep['heel_lifted'] else 'good'},
            {'label': 'Heel MSE (pixel)',   'value': f"{rep['heel_mse']}",
             'status': 'bad' if rep['heel_lifted'] else 'good'},
            {'label': 'End-Range Hold',     'value': f"{rep['hold_sec']} s",
             'status': 'good' if rep['hold_sec'] >= 0.5 else 'bad'},
        ]
        if wall_x is not None and rep.get('wall_gap_cm') is not None:
            overlay_metrics.append({'label': 'Wall Gap',
                                    'value': f"{rep['wall_gap_cm']} cm",
                                    'status': 'good' if rep.get('knee_at_wall') else 'bad'})
        draw_metric_overlay(frame, overlay_metrics, position='top-right',
                            title=f"REP {i+1} METRICS")
        draw_legend(frame, position='bottom-left')

        img_b64 = frame_to_base64(frame)
        tag = " (Best)" if is_best else ""
        annotated.append({
            'label': f"{side_label.title()} — Rep {i+1}{tag}",
            'image_base64': img_b64,
            'rep_num': i + 1,
            'side': side_label,
            'is_best': is_best,
            'metrics_shown': [
                f"Dorsiflex: {rep['dorsiflexion_deg']}°",
                f"Travel: {rep['knee_travel_cm']}cm",
                f"Heel: {'LIFT' if rep['heel_lifted'] else 'OK'}",
                f"Hold: {rep['hold_sec']}s",
            ],
        })

    wall_touches = sum(1 for r in valid if r.get('knee_at_wall'))
    return {
        'side': side_label, 'valid_reps': valid_count, 'total_reps': total_count,
        'best_dorsiflexion': round(best_dorsi, 1),
        'best_ankle_angle':  round(best_ankle, 1),
        'best_tibia':        round(best_tibia, 1),
        'avg_knee_travel':   round(avg_travel, 1),
        'max_heel_lift':     round(max_heel,   1),
        'any_heel_lifted':   any_lifted,
        'best_hold':         round(best_hold,  1),
        'wall_detected':     wall_x is not None,
        'wall_touches':      wall_touches,
        'confidence':        conf,
        'per_rep':           valid,
        'annotated_frames':  annotated,
        'px_per_cm':         round(px_per_cm, 3),
        'calibration_mode':  cal_mode,
    }


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def analyse(files, tibia_length_cm=None):
    """Main entry point for Knee-to-Wall analysis.

    Args:
        files: dict mapping upload keys → file paths.
               Required: 'left', 'right'.
               Optional: 'front' (front-view video for knee valgus).
        tibia_length_cm: user's tibia length in cm, used for px/cm
                         calibration. If None or invalid, falls back to
                         the frame-height-based estimate.
    """
    left  = _analyse_side(files.get('left', ''),  'left',  tibia_length_cm)
    right = _analyse_side(files.get('right', ''), 'right', tibia_length_cm)

    # Optional front-view: valgus + arch collapse
    front = _analyse_front_view(files.get('front'), tibia_length_cm=tibia_length_cm)

    total_valid = left['valid_reps'] + right['valid_reps']
    total_reps  = left['total_reps'] + right['total_reps']
    avg_conf    = (left['confidence'] + right['confidence']) // 2

    metrics = []

    # Ankle dorsiflexion (primary)
    metrics.append(build_metric('Left Ankle Dorsiflexion',  f"{left['best_dorsiflexion']}°",
                                left['best_dorsiflexion'],  '≥35°', 60,
                                classify(left['best_dorsiflexion'],  35, 20, higher_is_better=True)))
    metrics.append(build_metric('Right Ankle Dorsiflexion', f"{right['best_dorsiflexion']}°",
                                right['best_dorsiflexion'], '≥35°', 60,
                                classify(right['best_dorsiflexion'], 35, 20, higher_is_better=True)))

    # Knee travel
    metrics.append(build_metric('Left Knee Travel',  f"{left['avg_knee_travel']} cm",
                                left['avg_knee_travel'],  '≥10 cm', 25,
                                classify(left['avg_knee_travel'],  10, 5, higher_is_better=True)))
    metrics.append(build_metric('Right Knee Travel', f"{right['avg_knee_travel']} cm",
                                right['avg_knee_travel'], '≥10 cm', 25,
                                classify(right['avg_knee_travel'], 10, 5, higher_is_better=True)))

    # Ankle joint angle (knee-ankle-toe at peak — smaller = deeper dorsiflexion)
    metrics.append(build_metric('Left Ankle Joint Angle',  f"{left['best_ankle_angle']}°",
                                left['best_ankle_angle'],  '≤80°', 130,
                                classify(left['best_ankle_angle'],  80, 90, higher_is_better=False)))
    metrics.append(build_metric('Right Ankle Joint Angle', f"{right['best_ankle_angle']}°",
                                right['best_ankle_angle'], '≤80°', 130,
                                classify(right['best_ankle_angle'], 80, 90, higher_is_better=False)))

    # ── Heel lift — spec thresholds: <1.5 cm GOOD, 1.5–3 NEEDS, >3 RESTRICTED ──
    metrics.append(build_metric('Left Heel Lift',  f"{left['max_heel_lift']} cm",
                                left['max_heel_lift'],  f"<{HEEL_LIFT_THRESHOLD_CM} cm", 5,
                                classify(left['max_heel_lift'], HEEL_LIFT_THRESHOLD_CM,
                                         HEEL_LIFT_RESTRICTED_CM, higher_is_better=False)))
    metrics.append(build_metric('Right Heel Lift', f"{right['max_heel_lift']} cm",
                                right['max_heel_lift'], f"<{HEEL_LIFT_THRESHOLD_CM} cm", 5,
                                classify(right['max_heel_lift'], HEEL_LIFT_THRESHOLD_CM,
                                         HEEL_LIFT_RESTRICTED_CM, higher_is_better=False)))

    # End-range hold
    metrics.append(build_metric('Left End Range Hold',  f"{left['best_hold']} s",
                                left['best_hold'],  '≥0.5s', 3,
                                classify(left['best_hold'],  0.5, 0.3, higher_is_better=True)))
    metrics.append(build_metric('Right End Range Hold', f"{right['best_hold']} s",
                                right['best_hold'], '≥0.5s', 3,
                                classify(right['best_hold'], 0.5, 0.3, higher_is_better=True)))

    # ── Wall-touch (Canny-detected wall edge) ──
    if left['wall_detected']:
        metrics.append(build_metric('Left Wall Touches',  f"{left['wall_touches']}/{left['valid_reps']}",
                                    left['wall_touches'],  '≥1', max(left['valid_reps'], 1),
                                    'GOOD' if left['wall_touches'] >= 1 else 'RESTRICTED'))
    if right['wall_detected']:
        metrics.append(build_metric('Right Wall Touches', f"{right['wall_touches']}/{right['valid_reps']}",
                                    right['wall_touches'], '≥1', max(right['valid_reps'], 1),
                                    'GOOD' if right['wall_touches'] >= 1 else 'RESTRICTED'))

    # ── Front-view metrics: valgus + arch collapse ──
    if front:
        metrics.append(build_metric('Left Knee Valgus',  f"{front['left_valgus']}°",
                                    front['left_valgus'],  '<5°', 25,
                                    classify(front['left_valgus'],  5, 10, higher_is_better=False)))
        metrics.append(build_metric('Right Knee Valgus', f"{front['right_valgus']}°",
                                    front['right_valgus'], '<5°', 25,
                                    classify(front['right_valgus'], 5, 10, higher_is_better=False)))
        # Arch collapse (Cheat Checker) — >0.5 cm medial drift = false positive
        metrics.append(build_metric('Left Arch Collapse',  f"{front['left_arch_collapse_cm']} cm",
                                    front['left_arch_collapse_cm'],  '<0.5 cm', 3,
                                    classify(front['left_arch_collapse_cm'],  0.5, 1.0, higher_is_better=False)))
        metrics.append(build_metric('Right Arch Collapse', f"{front['right_arch_collapse_cm']} cm",
                                    front['right_arch_collapse_cm'], '<0.5 cm', 3,
                                    classify(front['right_arch_collapse_cm'], 0.5, 1.0, higher_is_better=False)))

    bilateral = [
        build_bilateral('Ankle Dorsiflexion',
                        left['best_dorsiflexion'], right['best_dorsiflexion'], '°', 60),
        build_bilateral('Knee Travel',
                        left['avg_knee_travel'], right['avg_knee_travel'], 'cm', 25),
    ]
    if front:
        bilateral.append(build_bilateral('Knee Valgus',
                                         front['left_valgus'], front['right_valgus'], '°', 25))

    score    = compute_overall_score(metrics)
    status   = overall_status(score)
    coaching = generate_coaching_notes(metrics, bilateral, 'Knee-to-Wall Test')

    # Asymmetry callouts
    dorsi_asym = abs(left['best_dorsiflexion'] - right['best_dorsiflexion'])
    if dorsi_asym > 5:
        worse = 'left' if left['best_dorsiflexion'] < right['best_dorsiflexion'] else 'right'
        coaching.insert(0, f"Ankle dorsiflexion asymmetry of {round(dorsi_asym, 1)}° — prioritise the {worse} side.")

    travel_asym = abs(left['avg_knee_travel'] - right['avg_knee_travel'])
    if travel_asym > 2:
        worse = 'left' if left['avg_knee_travel'] < right['avg_knee_travel'] else 'right'
        coaching.insert(0, f"Knee travel asymmetry of {round(travel_asym, 1)} cm — prioritise the {worse} side.")

    # Heel-lift coaching (pixel-confirmed lifts deserve a louder callout)
    if left['any_heel_lifted'] or right['any_heel_lifted']:
        coaching.insert(0,
            "Heel rolled off the floor during the test — repeat with the heel "
            "weighted; pixel-intensity check detected background between heel and floor.")

    # Calibration note
    if left['calibration_mode'] == 'fallback-estimate' and right['calibration_mode'] == 'fallback-estimate':
        coaching.append(
            "Calibration used a height-based estimate — provide your tibia "
            "length (cm) in profile for ±0.3 cm accurate measurements.")

    # Arch-collapse callout — "false positive" cheat
    if front:
        worst_arch = max(front['left_arch_collapse_cm'], front['right_arch_collapse_cm'])
        if worst_arch > 0.5:
            side = 'left' if front['left_arch_collapse_cm'] >= front['right_arch_collapse_cm'] else 'right'
            coaching.insert(0,
                f"FALSE POSITIVE: ARCH COLLAPSE on {side} ({worst_arch} cm medial drift). "
                f"Knee travel was achieved by pronating the foot, not by true ankle "
                f"dorsiflexion. Repeat with a flat arch — mobility is about stability "
                f"under load, not just distance.")

    # Wall-detection diagnostic
    if not (left['wall_detected'] or right['wall_detected']):
        coaching.append(
            "No vertical wall edge detected — film with a clear wall or doorframe "
            "in frame so the AI can auto-map the touch target.")

    if not front:
        coaching.append(
            "Add a front-view video to measure knee valgus and arch collapse. "
            "Side view alone cannot detect medial knee caving or pronation cheats.")

    summary = f"Analysed {total_valid}/{total_reps} valid reps across both sides."
    if status == 'RESTRICTED':
        summary += " Significant ankle mobility restriction detected."
    elif status == 'NEEDS IMPROVEMENT':
        summary += " Moderate ankle mobility — room for improvement."
    else:
        summary += " Good ankle dorsiflexion range."

    stats = {
        'validReps':  f'{total_valid}/{total_reps}',
        'confidence': f'{avg_conf}%',
        'sides':      'left, right' + (', front' if front else ''),
        'cameraView': 'OK',
        'calibration': left['calibration_mode'],
    }

    annotated_frames = left.get('annotated_frames', []) + right.get('annotated_frames', [])
    per_rep = []
    for r in left.get('per_rep', []):
        per_rep.append({'rep': len(per_rep)+1, 'side': 'left',  'metrics': r})
    for r in right.get('per_rep', []):
        per_rep.append({'rep': len(per_rep)+1, 'side': 'right', 'metrics': r})

    result = build_result(status, score, summary, stats, metrics, bilateral, coaching)
    result['annotated_frames'] = annotated_frames
    result['per_rep'] = per_rep
    return result
