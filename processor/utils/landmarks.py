"""Full-frame landmark extraction using MediaPipe Pose."""
import cv2
import numpy as np

# Default visibility threshold for the new accessors. The legacy 0.3 default is
# preserved on `get_landmark_px` / `get_landmark_norm` to avoid breaking older
# analyzer code; new analyzers use `get_lm` with the stricter 0.5 default.
MIN_VIS = 0.5

# Frames larger than this (long side, px) are downscaled before pose
# inference. MediaPipe's pose model consumes a small fixed-size input and
# returns NORMALIZED coordinates, so feeding it 4K frames only slows the
# pipeline (cvtColor + tensor prep on 8MP images) without accuracy benefit.
# Reported width/height stay the ORIGINAL video dimensions — normalized
# coords are resolution-independent, so all px math downstream is unchanged.
MAX_INFERENCE_DIM = 1920

# MediaPipe 0.10+ uses a new tasks-based API
MP_AVAILABLE = False
MP_LEGACY = False
mp = None
mp_pose = None
PoseLandmarker = None
PoseLandmarkerOptions = None
mp_tasks_base = None
mp_vision = None

try:
    import mediapipe as _mp
    mp = _mp
    
    # Try legacy solutions API first (mediapipe < 0.10.14)
    try:
        mp_pose = mp.solutions.pose
        MP_LEGACY = True
        MP_AVAILABLE = True
    except AttributeError:
        pass
    
    # Try new tasks-based API (mediapipe >= 0.10.14)
    if not MP_LEGACY:
        try:
            from mediapipe.tasks.python.vision import PoseLandmarker as _PL
            from mediapipe.tasks.python.vision import PoseLandmarkerOptions as _PLO
            from mediapipe.tasks.python import vision as _vision
            from mediapipe.tasks import python as _mp_tasks
            PoseLandmarker = _PL
            PoseLandmarkerOptions = _PLO
            mp_vision = _vision
            mp_tasks_base = _mp_tasks
            MP_AVAILABLE = True
        except ImportError as e:
            print(f"⚠️  MediaPipe tasks API not available: {e}")
            
except ImportError as e:
    print(f"⚠️  MediaPipe not installed: {e}")

# MediaPipe landmark indices
LM = {
    'NOSE': 0,
    'LEFT_EAR': 7, 'RIGHT_EAR': 8,
    'MOUTH_LEFT': 9, 'MOUTH_RIGHT': 10,
    'LEFT_SHOULDER': 11, 'RIGHT_SHOULDER': 12,
    'LEFT_ELBOW': 13, 'RIGHT_ELBOW': 14,
    'LEFT_WRIST': 15, 'RIGHT_WRIST': 16,
    'LEFT_PINKY': 17, 'RIGHT_PINKY': 18,
    'LEFT_INDEX': 19, 'RIGHT_INDEX': 20,
    'LEFT_THUMB': 21, 'RIGHT_THUMB': 22,
    'LEFT_HIP': 23, 'RIGHT_HIP': 24,
    'LEFT_KNEE': 25, 'RIGHT_KNEE': 26,
    'LEFT_ANKLE': 27, 'RIGHT_ANKLE': 28,
    'LEFT_HEEL': 29, 'RIGHT_HEEL': 30,
    'LEFT_FOOT_INDEX': 31, 'RIGHT_FOOT_INDEX': 32,
}


def extract_all_landmarks(video_path, smooth=True, smooth_min_cutoff=1.0,
                          smooth_beta=0.007):
    """Extract pose landmarks from every frame of a video.

    Args:
        video_path: path to a video file.
        smooth: when True (default), the returned `frames` list has 1-Euro
                filtered landmark x/y/z trajectories. The raw frames are still
                available under `raw_frames` for debugging / reproducibility.
        smooth_min_cutoff, smooth_beta: 1-Euro filter params (see signal_filters).

    Returns:
        dict with keys:
            frames: list of dicts {frame_idx, time_sec, landmarks}
                    landmarks is a list of 33 tuples (x, y, z, visibility)
                    x,y are normalized [0,1], z is depth estimate
            raw_frames: same shape as `frames` but pre-smoothing (when smooth=True)
            fps: float
            total_frames: int
            width: int (frame width in pixels)
            height: int (frame height in pixels)
    """
    if not MP_AVAILABLE:
        raise RuntimeError("MediaPipe is not installed. Cannot extract landmarks.")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    frames_data = []
    frame_idx = 0

    # Downscale factor for pose inference on very large frames (see
    # MAX_INFERENCE_DIM). Landmarks come back normalized, so this does not
    # change any downstream coordinate math.
    infer_scale = 1.0
    long_side = max(width, height)
    if long_side > MAX_INFERENCE_DIM and long_side > 0:
        infer_scale = MAX_INFERENCE_DIM / long_side

    def _prep(frame):
        if infer_scale < 1.0:
            frame = cv2.resize(frame, None, fx=infer_scale, fy=infer_scale,
                               interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    if MP_LEGACY:
        # Legacy mp.solutions.pose API
        with mp_pose.Pose(
            static_image_mode=False,
            model_complexity=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) as pose:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                rgb = _prep(frame)
                results = pose.process(rgb)

                if results.pose_landmarks:
                    lm = results.pose_landmarks.landmark
                    landmarks = [(l.x, l.y, l.z, l.visibility) for l in lm]
                else:
                    landmarks = None

                frames_data.append({
                    'frame_idx': frame_idx,
                    'time_sec': frame_idx / fps,
                    'landmarks': landmarks,
                })
                frame_idx += 1
    else:
        # New tasks-based API (MediaPipe 0.10.14+)
        import os
        import urllib.request
        
        # Download model if not present
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pose_landmarker_heavy.task')
        if not os.path.exists(model_path):
            print("📥 Downloading MediaPipe Pose Landmarker model...")
            url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"
            urllib.request.urlretrieve(url, model_path)
            print("✅ Model downloaded")
        
        base_options = mp_tasks_base.BaseOptions(model_asset_path=model_path)
        options = PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        
        with PoseLandmarker.create_from_options(options) as landmarker:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                rgb = _prep(frame)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                timestamp_ms = int(frame_idx * 1000 / fps)
                
                result = landmarker.detect_for_video(mp_image, timestamp_ms)
                
                if result.pose_landmarks and len(result.pose_landmarks) > 0:
                    lm = result.pose_landmarks[0]
                    landmarks = [(l.x, l.y, l.z, l.visibility) for l in lm]
                else:
                    landmarks = None
                
                frames_data.append({
                    'frame_idx': frame_idx,
                    'time_sec': frame_idx / fps,
                    'landmarks': landmarks,
                })
                frame_idx += 1

    cap.release()

    raw_frames = frames_data
    out_frames = frames_data
    if smooth:
        try:
            from .signal_filters import smooth_landmarks as _smooth
            out_frames = _smooth(frames_data, fps=fps,
                                 min_cutoff=smooth_min_cutoff, beta=smooth_beta)
        except Exception as e:
            # never let smoothing break extraction
            print(f"⚠️  Landmark smoothing skipped: {e}")
            out_frames = frames_data

    return {
        'frames': out_frames,
        'raw_frames': raw_frames,
        'fps': fps,
        'total_frames': total_frames,
        'width': width,
        'height': height,
    }


def get_landmark_px(landmarks, idx, width, height):
    """Get a landmark's pixel coordinates.
    
    Returns (x_px, y_px) or None if landmark is missing.
    """
    if landmarks is None or idx >= len(landmarks):
        return None
    lm = landmarks[idx]
    if lm[3] < 0.3:  # low visibility threshold
        return None
    return (lm[0] * width, lm[1] * height)


def get_landmark_norm(landmarks, idx):
    """Get normalized (x, y) of a landmark. Returns None if missing."""
    if landmarks is None or idx >= len(landmarks):
        return None
    lm = landmarks[idx]
    if lm[3] < 0.3:
        return None
    return (lm[0], lm[1])


def midpoint_px(landmarks, idx1, idx2, width, height):
    """Get midpoint of two landmarks in pixel coords."""
    p1 = get_landmark_px(landmarks, idx1, width, height)
    p2 = get_landmark_px(landmarks, idx2, width, height)
    if p1 is None or p2 is None:
        return None
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)


def midpoint_norm(landmarks, idx1, idx2):
    """Get midpoint of two landmarks in normalized coords."""
    p1 = get_landmark_norm(landmarks, idx1)
    p2 = get_landmark_norm(landmarks, idx2)
    if p1 is None or p2 is None:
        return None
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)


def confidence_score(frames_data):
    """Calculate overall landmark detection confidence (0-100)."""
    detected = sum(1 for f in frames_data if f['landmarks'] is not None)
    total = len(frames_data)
    if total == 0:
        return 0
    return round((detected / total) * 100)


def get_lm(landmarks, idx, width, height, min_vis=MIN_VIS):
    """Strict landmark accessor that returns (x_px, y_px, visibility).

    Used by the new analyzer code that needs per-metric confidence.
    Returns None if the landmark is missing or below `min_vis`.
    """
    if landmarks is None or idx >= len(landmarks):
        return None
    lm = landmarks[idx]
    if lm[3] < min_vis:
        return None
    return (lm[0] * width, lm[1] * height, lm[3])


def landmark_quality(landmarks, idxs):
    """Mean visibility across an iterable of landmark indices.

    Used as the per-metric input-quality signal that feeds into confidence
    scoring. Returns a float in [0,1], or 0.0 when landmarks are missing.
    """
    if landmarks is None:
        return 0.0
    vis = []
    for i in idxs:
        if i < len(landmarks):
            vis.append(float(landmarks[i][3]))
    if not vis:
        return 0.0
    return sum(vis) / len(vis)


def window_landmark_quality(frames_data, idxs, start=None, end=None):
    """Mean landmark_quality across a frame window. Skips missing frames."""
    if not frames_data:
        return 0.0
    start = 0 if start is None else max(0, start)
    end = len(frames_data) if end is None else min(len(frames_data), end)
    vals = []
    for f in frames_data[start:end]:
        lm = f.get('landmarks')
        if lm is None:
            continue
        q = landmark_quality(lm, idxs)
        if q > 0:
            vals.append(q)
    if not vals:
        return 0.0
    return sum(vals) / len(vals)
