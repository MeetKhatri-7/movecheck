"""CV2 Frame Annotator — Draws skeleton overlays, angles, and metrics on video frames.

Produces richly annotated analysis images that show the user **every** metric
the analyzer measured, drawn directly on the body. Each rep's annotated
frame should be self-contained: someone seeing it for the first time should
understand exactly what was measured, what passed, and what failed.

Drawing primitives (top of file):
    • draw_skeleton            — full pose skeleton
    • draw_angle_arc           — arc with auto-coloured PASS/FAIL label
    • draw_distance_line       — dashed measurement line
    • draw_reference_line      — vertical/horizontal dashed reference axis
    • draw_callout             — leader-line + boxed value bubble pointing AT a body part
    • draw_phase_label         — large "BOTTOM POSITION" / "LOCKOUT" caption near the body
    • draw_title_strip         — top banner with exercise name + rep + score
    • draw_metric_overlay      — right-side scorecard with PASS/FAIL chips
    • draw_status_badge        — score + status pill
    • draw_rep_label           — small rep counter
    • draw_legend              — colour key explaining what colours mean

Helpers:
    • frame_to_base64          — encode for JSON delivery
    • extract_frame_at         — pull a single frame from a video
    • generate_annotated_frame — backward-compat shortcut for the older analyzers
"""
import cv2
import numpy as np
import math
import base64

# ── Color palette (BGR for OpenCV) ──────────────────────────────
COL_SKELETON     = (100, 220, 80)
COL_SKELETON_DOT = (140, 255, 120)
COL_GOOD         = (176, 229, 0)        # #00e5b0 teal-green
COL_BAD          = (102, 68, 255)       # #ff4466 red
COL_WARN         = (11, 158, 245)       # #f59e0b amber
COL_ANGLE        = (11, 158, 245)
COL_DISTANCE     = (245, 158, 11)
COL_WHITE        = (255, 255, 255)
COL_OVERLAY_BG   = (15, 8, 6)
COL_PURPLE       = (247, 85, 168)
COL_CYAN         = (230, 200, 50)

# Status → color helper
def _status_color(status):
    if status == 'good':    return COL_GOOD
    if status == 'bad':     return COL_BAD
    if status == 'warn':    return COL_WARN
    if status == 'critical':return COL_BAD
    return COL_ANGLE

# ── Skeleton connections (MediaPipe Pose) ────────────────────────
POSE_CONNECTIONS = [
    (11, 12),
    (11, 13), (13, 15),
    (12, 14), (14, 16),
    (11, 23), (12, 24),
    (23, 24),
    (23, 25), (25, 27),
    (24, 26), (26, 28),
    (27, 29), (27, 31),
    (28, 30), (28, 32),
]
KEY_JOINTS = {11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28}


def _lm_to_px(landmarks, idx, w, h):
    if landmarks is None or idx >= len(landmarks):
        return None
    lm = landmarks[idx]
    if lm[3] < 0.2:
        return None
    return (int(lm[0] * w), int(lm[1] * h))


# ═══════════════════════════════════════════════════════════════════
# 1. Skeleton
# ═══════════════════════════════════════════════════════════════════

def draw_skeleton(frame, landmarks, w, h, connections=None, color=None, thickness=3):
    """Draw full skeleton with joints + connections."""
    if landmarks is None:
        return frame
    conns = connections or POSE_CONNECTIONS
    col   = color or COL_SKELETON
    for (a, b) in conns:
        pa = _lm_to_px(landmarks, a, w, h)
        pb = _lm_to_px(landmarks, b, w, h)
        if pa and pb:
            cv2.line(frame, pa, pb, col, thickness, cv2.LINE_AA)
    for i in range(min(33, len(landmarks))):
        pt = _lm_to_px(landmarks, i, w, h)
        if pt:
            r = 7 if i in KEY_JOINTS else 3
            cv2.circle(frame, pt, r, COL_SKELETON_DOT, -1, cv2.LINE_AA)
            cv2.circle(frame, pt, r, col, 1, cv2.LINE_AA)
    return frame


# ═══════════════════════════════════════════════════════════════════
# 2. Angle arc — now status-aware
# ═══════════════════════════════════════════════════════════════════

def draw_angle_arc(frame, vertex, p1, p2, angle_deg,
                   color=None, label=None, radius=40, status=None,
                   thickness=3):
    """Draw an angle arc at `vertex` between vectors vertex→p1 and vertex→p2.

    If `status` is provided ('good'|'bad'|'warn'), the arc and label adopt
    the corresponding traffic-light colour and a small ✓ / ✗ glyph is
    appended to the label.
    """
    if vertex is None or p1 is None or p2 is None:
        return frame
    if status is not None:
        col = _status_color(status)
        suffix = ' OK' if status == 'good' else (' X' if status in ('bad', 'critical') else '')
    else:
        col = color or COL_ANGLE
        suffix = ''
    vx, vy = vertex

    ang1 = math.degrees(math.atan2(p1[1] - vy, p1[0] - vx))
    ang2 = math.degrees(math.atan2(p2[1] - vy, p2[0] - vx))
    start_angle = min(ang1, ang2)
    end_angle = max(ang1, ang2)
    if end_angle - start_angle > 180:
        start_angle, end_angle = end_angle, start_angle + 360

    cv2.ellipse(frame, (int(vx), int(vy)), (radius, radius),
                0, start_angle, end_angle, col, thickness, cv2.LINE_AA)

    # Subtle filled wedge for visibility
    overlay = frame.copy()
    pts = [(int(vx), int(vy))]
    for ang in np.linspace(start_angle, end_angle, 22):
        pts.append((int(vx + radius * math.cos(math.radians(ang))),
                    int(vy + radius * math.sin(math.radians(ang)))))
    cv2.fillPoly(overlay, [np.array(pts, dtype=np.int32)], col)
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)

    lbl = (label or f"{angle_deg:.1f}deg") + suffix
    mid_angle = math.radians((start_angle + end_angle) / 2)
    tx = int(vx + (radius + 22) * math.cos(mid_angle))
    ty = int(vy + (radius + 22) * math.sin(mid_angle))
    _draw_pill_label(frame, lbl, (tx, ty), col)
    return frame


# ═══════════════════════════════════════════════════════════════════
# 3. Distance line
# ═══════════════════════════════════════════════════════════════════

def draw_distance_line(frame, p1, p2, label, color=None, status=None, thickness=2):
    """Dashed line between p1 and p2 with a labeled mid-point pill."""
    if p1 is None or p2 is None:
        return frame
    col = _status_color(status) if status is not None else (color or COL_DISTANCE)
    p1i = (int(p1[0]), int(p1[1])); p2i = (int(p2[0]), int(p2[1]))
    _draw_dashed_line(frame, p1i, p2i, col, thickness=thickness, dash_length=10)
    cv2.circle(frame, p1i, 5, col, -1, cv2.LINE_AA)
    cv2.circle(frame, p2i, 5, col, -1, cv2.LINE_AA)
    mx, my = (p1i[0] + p2i[0]) // 2, (p1i[1] + p2i[1]) // 2
    suffix = ''
    if status == 'good': suffix = ' OK'
    elif status in ('bad', 'critical'): suffix = ' X'
    _draw_pill_label(frame, (label or '') + suffix, (mx, my - 14), col)
    return frame


# ═══════════════════════════════════════════════════════════════════
# 4. Reference line — full-frame dashed axis
# ═══════════════════════════════════════════════════════════════════

def draw_reference_line(frame, x=None, y=None, color=None, label=None,
                        thickness=2, dash_length=12, status=None):
    """Draw a full-frame vertical (when x given) or horizontal (when y given) dashed reference line.

    Use cases: bar-over-mid-foot reference, wall edge, floor baseline, plumb line.
    """
    h, w = frame.shape[:2]
    col = _status_color(status) if status is not None else (color or COL_CYAN)
    if x is not None:
        x = int(x)
        _draw_dashed_line(frame, (x, 0), (x, h - 1), col, thickness=thickness, dash_length=dash_length)
        if label:
            _draw_pill_label(frame, label, (x + 8, 28), col)
    elif y is not None:
        y = int(y)
        _draw_dashed_line(frame, (0, y), (w - 1, y), col, thickness=thickness, dash_length=dash_length)
        if label:
            _draw_pill_label(frame, label, (28, y - 8), col)
    return frame


# ═══════════════════════════════════════════════════════════════════
# 5. Callout — leader line + boxed label pointing AT a body point
# ═══════════════════════════════════════════════════════════════════

def draw_callout(frame, anchor, text, status='good', offset=(60, -60), thickness=2):
    """Draw a leader line from `anchor` to an offset position and label it.

    Used to surface metric values *next to* the relevant body part without
    cluttering the joint itself. e.g. heel-lift callout pointing AT the heel.
    """
    if anchor is None:
        return frame
    col = _status_color(status)
    ax, ay = int(anchor[0]), int(anchor[1])
    bx, by = ax + offset[0], ay + offset[1]

    # Anchor dot
    cv2.circle(frame, (ax, ay), 6, col, -1, cv2.LINE_AA)
    cv2.circle(frame, (ax, ay), 6, COL_WHITE, 1, cv2.LINE_AA)

    # Bend the leader-line: a small horizontal segment near the label for readability
    elbow = (bx, ay)
    cv2.line(frame, (ax, ay), elbow, col, thickness, cv2.LINE_AA)
    cv2.line(frame, elbow,    (bx, by), col, thickness, cv2.LINE_AA)

    # Label pill
    _draw_pill_label(frame, text, (bx, by), col, fill=True)
    return frame


# ═══════════════════════════════════════════════════════════════════
# 6. Phase label — "BOTTOM POSITION" caption
# ═══════════════════════════════════════════════════════════════════

def draw_phase_label(frame, text, anchor=None, color=None):
    """Large caption stamped near `anchor` (defaults to top-centre of frame)."""
    h, w = frame.shape[:2]
    col = color or COL_PURPLE
    text = text.upper()

    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    pad_x, pad_y = 14, 8
    if anchor is None:
        cx = w // 2; cy = 56
    else:
        cx, cy = int(anchor[0]), int(anchor[1])
    x0 = cx - tw // 2 - pad_x; x1 = cx + tw // 2 + pad_x
    y0 = cy - th // 2 - pad_y; y1 = cy + th // 2 + pad_y

    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x1, y1), COL_OVERLAY_BG, -1)
    cv2.addWeighted(overlay, 0.82, frame, 0.18, 0, frame)
    cv2.rectangle(frame, (x0, y0), (x1, y1), col, 2, cv2.LINE_AA)
    cv2.putText(frame, text, (cx - tw // 2, cy + th // 2 - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2, cv2.LINE_AA)
    return frame


# ═══════════════════════════════════════════════════════════════════
# 7. Title strip — top banner with exercise name + rep + score
# ═══════════════════════════════════════════════════════════════════

def draw_title_strip(frame, exercise_name, rep_num, total_reps,
                     status=None, score=None, side=None):
    """Wide top banner: exercise on the left, rep counter centre, score chip on the right."""
    h, w = frame.shape[:2]
    strip_h = 50
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, strip_h), COL_OVERLAY_BG, -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
    cv2.line(frame, (0, strip_h), (w, strip_h), COL_SKELETON, 1, cv2.LINE_AA)

    # Exercise name
    cv2.putText(frame, exercise_name.upper(), (16, 32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, COL_GOOD, 2, cv2.LINE_AA)

    # Rep counter (centre)
    rep_txt = f"REP {rep_num}/{total_reps}"
    if side and side != 'center':
        rep_txt = f"{side.upper()} · " + rep_txt
    (tw, _), _ = cv2.getTextSize(rep_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
    cv2.putText(frame, rep_txt, (w // 2 - tw // 2, 32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COL_PURPLE, 2, cv2.LINE_AA)

    # Status / score chip on the right
    if status is not None and score is not None:
        col = _status_color('good' if status == 'GOOD' else
                            ('bad' if status == 'RESTRICTED' else 'warn'))
        chip = f"{score}  {status}"
        (cw_, _), _ = cv2.getTextSize(chip, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(frame, (w - cw_ - 28, 10), (w - 10, 40), col, 1, cv2.LINE_AA)
        cv2.putText(frame, chip, (w - cw_ - 18, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2, cv2.LINE_AA)
    return frame


# ═══════════════════════════════════════════════════════════════════
# 8. Metric scorecard — PASS / FAIL chips, multi-section friendly
# ═══════════════════════════════════════════════════════════════════

def draw_metric_overlay(frame, metrics, position='top-right', title='METRICS'):
    """Draw a semi-transparent scorecard.

    metrics: list[ {'label': str, 'value': str, 'status': 'good'|'bad'|'warn'|'critical'} ]
    `title` is rendered in the header bar.
    """
    if not metrics:
        return frame
    h, w = frame.shape[:2]

    # Auto-size based on longest label/value
    line_h = 26
    pad = 14
    label_max = max((len(m.get('label', '')) for m in metrics), default=10)
    value_max = max((len(m.get('value', '')) for m in metrics), default=4)
    overlay_w = min(420, max(280, label_max * 9 + value_max * 10 + 80))
    overlay_h = pad * 2 + line_h * len(metrics) + 36

    if 'right' in position:
        x1 = w - overlay_w - 16
    else:
        x1 = 16
    # title strip occupies 50 px at the top; offset so the card sits below it
    title_offset = 56 if 'top' in position else 0
    if 'bottom' in position:
        y1 = h - overlay_h - 16
    else:
        y1 = title_offset

    x2, y2 = x1 + overlay_w, y1 + overlay_h

    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), COL_OVERLAY_BG, -1)
    cv2.addWeighted(overlay, 0.86, frame, 0.14, 0, frame)
    cv2.rectangle(frame, (x1, y1), (x2, y2), COL_SKELETON, 1, cv2.LINE_AA)

    # Header bar
    cv2.rectangle(frame, (x1, y1), (x2, y1 + 32), COL_SKELETON, -1)
    cv2.putText(frame, title, (x1 + 12, y1 + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, COL_OVERLAY_BG, 2, cv2.LINE_AA)
    pass_count = sum(1 for m in metrics if m.get('status') == 'good')
    summary = f"{pass_count}/{len(metrics)}"
    (sw, _), _ = cv2.getTextSize(summary, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
    cv2.putText(frame, summary, (x2 - sw - 12, y1 + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COL_OVERLAY_BG, 2, cv2.LINE_AA)

    for i, m in enumerate(metrics):
        ty = y1 + 32 + pad + i * line_h
        label = m.get('label', '')
        value = m.get('value', '')
        status = m.get('status', 'good')
        col = _status_color(status)
        chip = '✓' if status == 'good' else ('✗' if status in ('bad','critical') else '!')
        cv2.putText(frame, label, (x1 + pad, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.43, (210, 215, 225), 1, cv2.LINE_AA)
        # Right-align the value + chip
        chip_w = 18
        (vw, _), _ = cv2.getTextSize(value, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 2)
        vx = x2 - pad - chip_w - vw - 6
        cv2.putText(frame, value, (vx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, col, 2, cv2.LINE_AA)
        cv2.circle(frame, (x2 - pad - 8, ty - 6), 8, col, -1, cv2.LINE_AA)
        cv2.putText(frame, chip, (x2 - pad - 13, ty - 1),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, COL_OVERLAY_BG, 2, cv2.LINE_AA)
    return frame


# ═══════════════════════════════════════════════════════════════════
# 9. Status badge + 10. Rep label + 11. Legend
# ═══════════════════════════════════════════════════════════════════

def draw_status_badge(frame, status, score, position='top-left'):
    h, w = frame.shape[:2]
    status_colors = {
        'GOOD': COL_GOOD, 'NEEDS IMPROVEMENT': COL_WARN, 'RESTRICTED': COL_BAD,
    }
    col = status_colors.get(status, COL_WARN)
    if 'right' in position: x = w - 200
    else: x = 16
    y = 60 if 'top' in position else h - 60   # leave room for title strip
    badge_w, badge_h = 184, 48
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + badge_w, y + badge_h), COL_OVERLAY_BG, -1)
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)
    cv2.rectangle(frame, (x, y), (x + badge_w, y + badge_h), col, 2, cv2.LINE_AA)
    cv2.putText(frame, str(score), (x + 12, y + 36),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, col, 2, cv2.LINE_AA)
    display_status = status[:14]
    cv2.putText(frame, display_status, (x + 70, y + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, col, 1, cv2.LINE_AA)
    cv2.putText(frame, "/100", (x + 70, y + 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (160, 165, 180), 1, cv2.LINE_AA)
    return frame


def draw_rep_label(frame, rep_num, total_reps, side=None):
    """Small rep counter — only used if the title strip isn't drawn."""
    h, w = frame.shape[:2]
    label = f"Rep {rep_num}/{total_reps}"
    if side and side != 'center':
        label = f"{side.upper()} — {label}"
    (tw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    x = w - 16 - tw - 14; y = 60
    overlay = frame.copy()
    cv2.rectangle(overlay, (x - 8, y - 4), (w - 8, y + 28), COL_OVERLAY_BG, -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
    cv2.putText(frame, label, (x, y + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, COL_PURPLE, 2, cv2.LINE_AA)
    return frame


def draw_legend(frame, items=None, position='bottom-left'):
    """Small colour-key strip explaining what colours / glyphs mean.

    items defaults to the canonical PASS / NEEDS / FAIL / ANGLE / DISTANCE / REF set.
    """
    if items is None:
        items = [
            ('+ PASS',     'good'),
            ('! NEEDS',    'warn'),
            ('X FAIL',     'bad'),
            ('- DIST',     'distance'),
            ('| REF',      'reference'),
        ]
    h, w = frame.shape[:2]
    pad = 10; line_h = 22
    box_w = 200; box_h = pad * 2 + line_h * len(items)
    if 'right' in position: x1 = w - box_w - 16
    else: x1 = 16
    if 'bottom' in position: y1 = h - box_h - 16
    else: y1 = 60
    x2, y2 = x1 + box_w, y1 + box_h
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), COL_OVERLAY_BG, -1)
    cv2.addWeighted(overlay, 0.82, frame, 0.18, 0, frame)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (90, 100, 120), 1, cv2.LINE_AA)
    for i, (text, kind) in enumerate(items):
        cy = y1 + pad + i * line_h + 14
        if kind == 'good':       col = COL_GOOD
        elif kind == 'warn':     col = COL_WARN
        elif kind == 'bad':      col = COL_BAD
        elif kind == 'distance': col = COL_DISTANCE
        elif kind == 'reference':col = COL_CYAN
        else: col = COL_WHITE
        cv2.rectangle(frame, (x1 + pad, cy - 8), (x1 + pad + 14, cy + 4), col, -1)
        cv2.putText(frame, text, (x1 + pad + 22, cy + 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (210, 215, 225), 1, cv2.LINE_AA)
    return frame


# ═══════════════════════════════════════════════════════════════════
# 12. Frame I/O
# ═══════════════════════════════════════════════════════════════════

def extract_frame_at(video_path, frame_idx):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def render_sample_frame(video_path, frames, w, h, exercise_name, message,
                        connections=None):
    """Render a single fallback frame when no usable reps were detected.

    Guarantees the result gallery is never empty: even when rep detection
    fails, the user sees ONE annotated still with a clear message explaining
    what went wrong (instead of a missing gallery section).

    Returns a base64 image string, or None if no valid frame is available.
    """
    sample_idx = None
    for i, f in enumerate(frames):
        if f.get('landmarks') is not None:
            sample_idx = i
            break
    if sample_idx is None:
        return None
    frame = extract_frame_at(video_path, sample_idx)
    if frame is None:
        return None
    lm = frames[sample_idx]['landmarks']
    draw_skeleton(frame, lm, w, h, connections=connections)
    draw_title_strip(frame, exercise_name, 1, 1)
    draw_phase_label(frame, 'No Reps Detected')

    # Bottom-centre notice
    overlay = frame.copy()
    fh, fw = frame.shape[:2]
    cv2.rectangle(overlay, (40, fh - 100), (fw - 40, fh - 30), COL_OVERLAY_BG, -1)
    cv2.addWeighted(overlay, 0.88, frame, 0.12, 0, frame)
    cv2.rectangle(frame, (40, fh - 100), (fw - 40, fh - 30), COL_BAD, 2, cv2.LINE_AA)
    _draw_text_with_shadow(frame, message, (60, fh - 60), 0.6, COL_BAD, 2)
    _draw_text_with_shadow(frame, 'Re-record with the camera angle / framing from the guide.',
                           (60, fh - 40), 0.45, COL_WHITE, 1)
    return frame_to_base64(frame)


def frame_to_base64(frame, max_width=1100):
    h, w = frame.shape[:2]
    if w > max_width:
        scale = max_width / w
        frame = cv2.resize(frame, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
    b64 = base64.b64encode(buffer).decode('utf-8')
    return f"data:image/jpeg;base64,{b64}"


# ═══════════════════════════════════════════════════════════════════
# Backward-compat shortcut for older analyzers
# ═══════════════════════════════════════════════════════════════════

def generate_annotated_frame(video_path, frame_idx, landmarks, w, h,
                              angles=None, distances=None, metrics=None,
                              status=None, score=None,
                              rep_num=None, total_reps=None, side=None,
                              exercise_connections=None):
    """Backward-compatible all-in-one helper used by the older analyzers."""
    frame = extract_frame_at(video_path, frame_idx)
    if frame is None:
        return None
    draw_skeleton(frame, landmarks, w, h, connections=exercise_connections)
    if angles:
        for ang in angles:
            v  = _lm_to_px(landmarks, ang['vertex_idx'], w, h)
            p1 = _lm_to_px(landmarks, ang['p1_idx'], w, h)
            p2 = _lm_to_px(landmarks, ang['p2_idx'], w, h)
            label = ang.get('label', f"{ang['value']:.1f}°")
            draw_angle_arc(frame, v, p1, p2, ang['value'], label=label,
                           color=ang.get('color'), status=ang.get('status'))
    if distances:
        for dist in distances:
            p1 = _lm_to_px(landmarks, dist['p1_idx'], w, h)
            p2 = _lm_to_px(landmarks, dist['p2_idx'], w, h)
            draw_distance_line(frame, p1, p2, dist['label'],
                               color=dist.get('color'), status=dist.get('status'))
    if metrics:
        draw_metric_overlay(frame, metrics)
    if status and score is not None:
        draw_status_badge(frame, status, score)
    if rep_num is not None and total_reps is not None:
        draw_rep_label(frame, rep_num, total_reps, side)
    return frame_to_base64(frame)


# ═══════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════

def _draw_pill_label(frame, text, pos, color, fill=False, scale=0.5, thickness=2):
    """Draw text inside a dark/coloured pill for readability over busy backgrounds."""
    if not text:
        return frame
    (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    px, py = int(pos[0]), int(pos[1])
    pad_x, pad_y = 6, 4
    x0 = px - pad_x; y0 = py - th - pad_y
    x1 = px + tw + pad_x; y1 = py + pad_y
    # Keep on-screen
    h, w = frame.shape[:2]
    if x0 < 0: shift = -x0 + 4; x0 += shift; x1 += shift; px += shift
    if x1 > w: shift = x1 - w + 4; x0 -= shift; x1 -= shift; px -= shift
    if y0 < 0: shift = -y0 + 4; y0 += shift; y1 += shift; py += shift
    if y1 > h: shift = y1 - h + 4; y0 -= shift; y1 -= shift; py -= shift

    overlay = frame.copy()
    if fill:
        cv2.rectangle(overlay, (x0, y0), (x1, y1), color, -1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        text_col = COL_OVERLAY_BG
    else:
        cv2.rectangle(overlay, (x0, y0), (x1, y1), COL_OVERLAY_BG, -1)
        cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, frame)
        cv2.rectangle(frame, (x0, y0), (x1, y1), color, 1, cv2.LINE_AA)
        text_col = color
    cv2.putText(frame, text, (px, py),
                cv2.FONT_HERSHEY_SIMPLEX, scale, text_col, thickness, cv2.LINE_AA)
    return frame


def _draw_text_with_shadow(frame, text, pos, scale, color, thickness):
    x, y = pos
    cv2.putText(frame, text, (x + 1, y + 1),
                cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def _draw_dashed_line(frame, p1, p2, color, thickness=2, dash_length=10):
    dx = p2[0] - p1[0]; dy = p2[1] - p1[1]
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 1:
        return
    dashes = max(int(dist / dash_length), 2)
    for i in range(0, dashes, 2):
        t1 = i / dashes
        t2 = min((i + 1) / dashes, 1.0)
        sp = (int(p1[0] + dx * t1), int(p1[1] + dy * t1))
        ep = (int(p1[0] + dx * t2), int(p1[1] + dy * t2))
        cv2.line(frame, sp, ep, color, thickness, cv2.LINE_AA)


# ═══════════════════════════════════════════════════════════════════
# Squat-style info panels — matches the reference layout
# ═══════════════════════════════════════════════════════════════════

def draw_info_panel(frame, title, rows, position='left', width=380, top=70):
    """Draw a left- or right-side info panel with title + rows of label/value/status.

    Each row is a dict: { 'label': str, 'value': str, 'status': 'good'|'bad'|'warn'|None }.
    A row's status colours both the value AND the trailing PASS/FAIL chip.

    Used by the squat analyzer to render the reference image's left
    'Compensation & Velocity' panel and right 'AI Biomechanical' panel.
    """
    if not rows:
        return frame
    h, w = frame.shape[:2]
    pad = 14
    title_h = 36
    row_h = 44
    panel_h = title_h + row_h * len(rows) + pad

    if position == 'left':
        x0 = pad
    else:
        x0 = w - width - pad
    y0 = top
    x1 = x0 + width
    y1 = min(h - pad, y0 + panel_h)

    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x1, y1), COL_OVERLAY_BG, -1)
    cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, frame)
    cv2.rectangle(frame, (x0, y0), (x1, y1), (60, 80, 110), 1, cv2.LINE_AA)

    # Title
    cv2.putText(frame, title.upper(), (x0 + 12, y0 + 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COL_WHITE, 2, cv2.LINE_AA)
    cv2.line(frame, (x0 + 12, y0 + title_h - 4), (x1 - 12, y0 + title_h - 4),
             (60, 80, 110), 1, cv2.LINE_AA)

    # Rows
    y = y0 + title_h + 10
    for row in rows:
        label  = row.get('label', '')
        value  = row.get('value', '')
        status = row.get('status', None)
        col    = _status_color(status) if status else COL_WHITE

        # Label (wrapped) — small dim
        cv2.putText(frame, label, (x0 + 12, y + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (170, 190, 220), 1, cv2.LINE_AA)
        # Value — bigger, status-coloured
        cv2.putText(frame, value, (x0 + 12, y + 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2, cv2.LINE_AA)

        # Status chip aligned right
        if status:
            chip_txt = 'PASS' if status == 'good' else ('FAIL' if status == 'bad' else 'NEEDS')
            (tw, th), _ = cv2.getTextSize(chip_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cx1 = x1 - 12
            cx0 = cx1 - tw - 14
            cy0 = y + 8
            cy1 = y + 34
            cv2.rectangle(frame, (cx0, cy0), (cx1, cy1), col, 1, cv2.LINE_AA)
            cv2.putText(frame, chip_txt, (cx0 + 7, cy1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2, cv2.LINE_AA)

        y += row_h
    return frame


def draw_top_phase_banner(frame, text, sublabel=None):
    """Centred 'DEEPEST POINT' style banner at the very top of the frame."""
    h, w = frame.shape[:2]
    lines = [text]
    if sublabel:
        lines.append(sublabel)
    # Measure widest
    sizes = [cv2.getTextSize(L, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0] for L in lines]
    tw = max(s[0] for s in sizes) + 28
    th = 26 * len(lines) + 14
    cx = w // 2
    x0 = cx - tw // 2; x1 = cx + tw // 2
    y0 = 16; y1 = y0 + th

    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x1, y1), COL_OVERLAY_BG, -1)
    cv2.addWeighted(overlay, 0.80, frame, 0.20, 0, frame)
    cv2.rectangle(frame, (x0, y0), (x1, y1), COL_PURPLE, 1, cv2.LINE_AA)

    for i, L in enumerate(lines):
        size = sizes[i]
        tx = cx - size[0] // 2
        ty = y0 + 22 + i * 24
        cv2.putText(frame, L, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    COL_PURPLE if i == 0 else COL_WHITE, 2, cv2.LINE_AA)
    return frame


def draw_confidence_pill(frame, conf, anchor=None, label=None):
    """Small pill showing per-metric confidence (high/medium/low).

    `conf` in [0,1]. Defaults to top-right if anchor is None.
    """
    if conf is None:
        return frame
    conf = max(0.0, min(1.0, float(conf)))
    if conf >= 0.7:
        tier = 'HIGH CONF'
        col = COL_GOOD
    elif conf >= 0.4:
        tier = 'MED CONF'
        col = COL_WARN
    else:
        tier = 'LOW CONF'
        col = COL_BAD
    text = label or f"{tier} {int(conf*100)}%"
    h, w = frame.shape[:2]
    pos = anchor or (w - 220, 80)
    _draw_pill_label(frame, text, pos, col, fill=True)
    return frame


def draw_fault_timing_strip(frame, rep_num, total_reps, events,
                            position='bottom-left'):
    """Strip showing when in a rep each fault appeared.

    events: list of dicts:
        {'name': 'Valgus', 'start_phase_pct': 65, 'status': 'bad'}
        start_phase_pct is 0-100 across the rep timeline (0=top, 100=top after
        full rep for cyclical lifts; 0=start, 100=lockout for unilateral).

    Draws a horizontal track per rep with coloured tick marks at each event's
    phase position. Helps surface "valgus appeared at 65% of descent" visually.
    """
    if not events:
        return frame
    h, w = frame.shape[:2]
    box_w = min(380, max(220, len(events) * 50))
    box_h = 60
    pad = 14
    if 'right' in position:
        x0 = w - box_w - pad
    else:
        x0 = pad
    if 'bottom' in position:
        y0 = h - box_h - pad
    else:
        y0 = pad

    x1, y1 = x0 + box_w, y0 + box_h
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x1, y1), COL_OVERLAY_BG, -1)
    cv2.addWeighted(overlay, 0.80, frame, 0.20, 0, frame)
    cv2.rectangle(frame, (x0, y0), (x1, y1), (60, 80, 110), 1, cv2.LINE_AA)

    title = f"FAULT TIMING (Rep {rep_num}/{total_reps})"
    cv2.putText(frame, title, (x0 + 10, y0 + 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, COL_WHITE, 1, cv2.LINE_AA)

    track_y = y0 + 38
    track_x0 = x0 + 10
    track_x1 = x1 - 10
    cv2.line(frame, (track_x0, track_y), (track_x1, track_y),
             (90, 100, 120), 1, cv2.LINE_AA)
    # phase labels
    cv2.putText(frame, "0%", (track_x0 - 2, track_y + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.32, (170, 190, 220), 1, cv2.LINE_AA)
    cv2.putText(frame, "100%", (track_x1 - 24, track_y + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.32, (170, 190, 220), 1, cv2.LINE_AA)

    for ev in events:
        pct = float(ev.get('start_phase_pct', 0))
        pct = max(0.0, min(100.0, pct))
        col = _status_color(ev.get('status', 'warn'))
        ex = int(track_x0 + (pct / 100.0) * (track_x1 - track_x0))
        cv2.line(frame, (ex, track_y - 6), (ex, track_y + 6), col, 2, cv2.LINE_AA)
        cv2.circle(frame, (ex, track_y), 4, col, -1, cv2.LINE_AA)
        nm = ev.get('name', '')[:14]
        (tw, _), _ = cv2.getTextSize(nm, cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1)
        cv2.putText(frame, nm, (ex - tw // 2, track_y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, col, 1, cv2.LINE_AA)
    return frame


def draw_top_right_rep_pill(frame, rep_num, total, status=None):
    """Small 'REP 5/5' pill at top right with status colour."""
    h, w = frame.shape[:2]
    txt = f"REP {rep_num}/{total}"
    col = _status_color(status) if status else COL_PURPLE
    (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
    pad_x, pad_y = 10, 6
    x1 = w - 16
    y0 = 16
    x0 = x1 - tw - pad_x * 2
    y1 = y0 + th + pad_y * 2
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x1, y1), COL_OVERLAY_BG, -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
    cv2.rectangle(frame, (x0, y0), (x1, y1), col, 1, cv2.LINE_AA)
    cv2.putText(frame, txt, (x0 + pad_x, y1 - pad_y - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2, cv2.LINE_AA)
    return frame


def draw_hip_height_trace(frame, signal, peak_frame=None, rep_num=None, total=None,
                          position='bottom-right', width=320, height=110):
    """Bottom-right line graph of the hip-Y trace for the rep window.

    `signal` is a list of float Y-positions (image y, larger = lower in frame).
    The graph plots inverted Y so 'going down' visually descends.
    """
    if not signal or len(signal) < 2:
        return frame
    h, w = frame.shape[:2]
    pad = 14
    if position == 'bottom-right':
        x0 = w - width - pad
        y0 = h - height - pad
    else:
        x0 = pad
        y0 = h - height - pad
    x1 = x0 + width; y1 = y0 + height

    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x1, y1), COL_OVERLAY_BG, -1)
    cv2.addWeighted(overlay, 0.80, frame, 0.20, 0, frame)
    cv2.rectangle(frame, (x0, y0), (x1, y1), (60, 80, 110), 1, cv2.LINE_AA)

    title = f"HIP HEIGHT TRACE"
    if rep_num is not None and total is not None:
        title += f"  (Rep {rep_num}/{total})"
    cv2.putText(frame, title, (x0 + 10, y0 + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, COL_WHITE, 1, cv2.LINE_AA)

    vals = [v for v in signal if v is not None]
    if not vals:
        return frame
    vmin, vmax = min(vals), max(vals)
    if vmax - vmin < 1e-6:
        vmax = vmin + 1
    plot_x0 = x0 + 30; plot_x1 = x1 - 10
    plot_y0 = y0 + 30; plot_y1 = y1 - 16
    n = len(signal)

    # Plot
    last_pt = None
    for i, v in enumerate(signal):
        if v is None: continue
        t = i / max(n - 1, 1)
        # Inverted Y: lower hip (larger v) = lower on graph
        norm = (v - vmin) / (vmax - vmin)
        px = int(plot_x0 + t * (plot_x1 - plot_x0))
        py = int(plot_y0 + norm * (plot_y1 - plot_y0))
        if last_pt is not None:
            cv2.line(frame, last_pt, (px, py), (240, 180, 80), 2, cv2.LINE_AA)
        last_pt = (px, py)

    # Peak marker
    if peak_frame is not None and 0 <= peak_frame < n and signal[peak_frame] is not None:
        t = peak_frame / max(n - 1, 1)
        v = signal[peak_frame]
        norm = (v - vmin) / (vmax - vmin)
        px = int(plot_x0 + t * (plot_x1 - plot_x0))
        py = int(plot_y0 + norm * (plot_y1 - plot_y0))
        cv2.circle(frame, (px, py), 4, COL_PURPLE, -1, cv2.LINE_AA)

    # Axis labels
    cv2.putText(frame, "Time", (plot_x1 - 30, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (170, 190, 220), 1, cv2.LINE_AA)
    cv2.putText(frame, "Hip Y", (x0 + 4, plot_y0 + 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (170, 190, 220), 1, cv2.LINE_AA)
    return frame


def draw_valgus_callout(frame, knee_pt, valgus_deg, side_label, status='good'):
    """Annotate a knee in the front view with a 'VALGUS CAVE: PASS/FAIL' callout.

    Used by the front-view squat analyzer where MediaPipe gives sagittal-plane
    angles. Draws a small colour-coded chip pointing at the knee.
    """
    if knee_pt is None:
        return frame
    label = f"VALGUS: {valgus_deg:.1f}deg"
    detail = f"{side_label.upper()} ({'MINIMAL' if status == 'good' else 'DETECTED'})"
    col = _status_color(status)
    # Offset away from body centre
    h, w = frame.shape[:2]
    ox = -160 if knee_pt[0] < w // 2 else 100
    oy = -10
    box_x = int(knee_pt[0] + ox)
    box_y = int(knee_pt[1] + oy)
    # Leader line
    cv2.line(frame, (int(knee_pt[0]), int(knee_pt[1])), (box_x + 70, box_y + 10),
             col, 1, cv2.LINE_AA)
    cv2.circle(frame, (int(knee_pt[0]), int(knee_pt[1])), 8, col, 2, cv2.LINE_AA)
    _draw_pill_label(frame, label, (box_x + 8, box_y + 8), col)
    _draw_pill_label(frame, detail, (box_x + 8, box_y + 30), col)
    return frame
