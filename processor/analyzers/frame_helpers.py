"""Shared frame annotation helpers for all exercise analyzers."""
from utils.frame_annotator import generate_annotated_frame


# Common connection sets
FULL_BODY = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
    (27, 29), (27, 31), (28, 30), (28, 32),
]

UPPER_BODY = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
]

LOWER_BODY = [
    (23, 25), (25, 27), (27, 29), (27, 31),
    (24, 26), (26, 28), (28, 30), (28, 32),
    (23, 24), (11, 23), (12, 24), (11, 12),
]

CORE_BODY = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
]


def annotate_peak_frame(video_path, peak_frame, landmarks, w, h,
                         metric_list, angle_list=None, distance_list=None,
                         rep_num=None, total_reps=None, side=None,
                         status=None, score=None, connections=None):
    """Convenience wrapper to annotate a single peak frame.
    
    Args:
        metric_list: list of (label, value_str, is_good_bool) tuples
        angle_list: list of (vertex_idx, p1_idx, p2_idx, value, label_str) tuples  
        distance_list: list of (p1_idx, p2_idx, label_str) tuples
    
    Returns:
        base64 image string or None
    """
    metrics = [{'label': m[0], 'value': m[1], 'status': 'good' if m[2] else 'bad'} for m in metric_list]
    
    angles = None
    if angle_list:
        angles = [{'vertex_idx': a[0], 'p1_idx': a[1], 'p2_idx': a[2], 'value': a[3], 'label': a[4]} for a in angle_list]
    
    distances = None
    if distance_list:
        distances = [{'p1_idx': d[0], 'p2_idx': d[1], 'label': d[2]} for d in distance_list]
    
    return generate_annotated_frame(
        video_path, peak_frame, landmarks, w, h,
        angles=angles, distances=distances, metrics=metrics,
        status=status, score=score,
        rep_num=rep_num, total_reps=total_reps, side=side,
        exercise_connections=connections or FULL_BODY,
    )


def build_frame_entry(label, img_b64, rep_num, side, is_best, metrics_shown):
    """Build a standardized annotated frame dict for the result."""
    if img_b64 is None:
        return None
    return {
        'label': label,
        'image_base64': img_b64,
        'rep_num': rep_num,
        'side': side,
        'is_best': is_best,
        'metrics_shown': metrics_shown,
    }
