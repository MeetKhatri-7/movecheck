"""Signal filtering primitives used across analyzers.

Centralises landmark / 1-D signal smoothing so every analyzer treats
MediaPipe jitter and bar-tracker noise identically. Three layers:

- OneEuroFilter / smooth_landmarks  : per-coordinate landmark trajectory smoothing
- savgol_series                     : derived 1-D signals (angle traces, bar Y)
- kalman_1d                         : smooth bar-position series for clean velocity

Cheap. Pure CPU. Safe to call every frame.
"""
from __future__ import annotations

import math
from copy import deepcopy
from typing import List, Optional, Sequence

import numpy as np

try:
    from scipy.signal import savgol_filter as _savgol
    _SCIPY_OK = True
except ImportError:  # pragma: no cover
    _SCIPY_OK = False

try:
    from filterpy.kalman import KalmanFilter
    _FILTERPY_OK = True
except ImportError:  # pragma: no cover
    _FILTERPY_OK = False


# ─────────────────────────────────────────────────────────────────
# 1-Euro filter — Casiez et al. 2012
# ─────────────────────────────────────────────────────────────────

def _smoothing_factor(t_e: float, cutoff: float) -> float:
    r = 2 * math.pi * cutoff * t_e
    return r / (r + 1)


class OneEuroFilter:
    """Scalar 1-Euro filter — one instance per (landmark, axis).

    Params:
        min_cutoff: low-pass cutoff at zero velocity. Smaller = smoother but laggy.
        beta:       speed coefficient. Larger = less lag at high speed.
        d_cutoff:   derivative-stage cutoff.
    """

    __slots__ = ("min_cutoff", "beta", "d_cutoff", "_x_prev", "_dx_prev", "_t_prev")

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.007, d_cutoff: float = 1.0):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self._x_prev: Optional[float] = None
        self._dx_prev: float = 0.0
        self._t_prev: Optional[float] = None

    def reset(self) -> None:
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    def __call__(self, t: float, x: float) -> float:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return self._x_prev if self._x_prev is not None else 0.0
        if self._x_prev is None:
            self._x_prev = x
            self._t_prev = t
            return x
        t_e = max(t - (self._t_prev or 0.0), 1e-6)
        dx = (x - self._x_prev) / t_e
        a_d = _smoothing_factor(t_e, self.d_cutoff)
        dx_hat = a_d * dx + (1 - a_d) * self._dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = _smoothing_factor(t_e, cutoff)
        x_hat = a * x + (1 - a) * self._x_prev
        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat


# ─────────────────────────────────────────────────────────────────
# Landmark trajectory smoothing
# ─────────────────────────────────────────────────────────────────

def smooth_landmarks(frames_data: List[dict], fps: float = 30.0,
                     min_cutoff: float = 1.0, beta: float = 0.007) -> List[dict]:
    """Smooth landmark x/y/z trajectories with 1-Euro per coordinate.

    Visibility is left untouched. Frames with missing landmarks pass through.
    The input list is not mutated; a deep copy is returned.
    """
    if not frames_data:
        return frames_data

    # find a sample landmark count
    n_lm = 0
    for f in frames_data:
        if f.get('landmarks'):
            n_lm = len(f['landmarks'])
            break
    if n_lm == 0:
        return deepcopy(frames_data)

    # one filter per (landmark, axis)
    filters = [
        (OneEuroFilter(min_cutoff, beta), OneEuroFilter(min_cutoff, beta),
         OneEuroFilter(min_cutoff, beta))
        for _ in range(n_lm)
    ]

    out: List[dict] = []
    for f in frames_data:
        nf = dict(f)
        lm = f.get('landmarks')
        if lm is None:
            out.append(nf)
            continue
        t = f.get('time_sec', f.get('frame_idx', 0) / max(fps, 1e-6))
        smoothed = []
        for i, p in enumerate(lm):
            x, y, z, vis = p
            fx, fy, fz = filters[i]
            sx = fx(t, x)
            sy = fy(t, y)
            sz = fz(t, z)
            smoothed.append((sx, sy, sz, vis))
        nf['landmarks'] = smoothed
        out.append(nf)
    return out


# ─────────────────────────────────────────────────────────────────
# Derived 1-D signal smoothing (angles, bar Y traces, etc.)
# ─────────────────────────────────────────────────────────────────

def savgol_series(series: Sequence[Optional[float]], fps: float = 30.0,
                  window_sec: float = 0.25, poly: int = 3) -> List[Optional[float]]:
    """Savitzky-Golay smoothing for a 1-D series with possible Nones.

    Interpolates Nones linearly for the filter, but preserves them in the output
    so downstream code keeps its missing-data signalling.
    """
    arr = list(series)
    n = len(arr)
    if n < 5:
        return arr

    nones = [v is None for v in arr]
    if all(nones):
        return arr
    vals = np.array([0.0 if v is None else float(v) for v in arr], dtype=float)
    # linear-interpolate gaps so SG has no NaN propagation
    idx = np.arange(n)
    known = ~np.array(nones)
    if known.sum() >= 2:
        vals[~known] = np.interp(idx[~known], idx[known], vals[known])

    window = max(5, int(round(window_sec * fps)))
    if window % 2 == 0:
        window += 1
    window = min(window, n if n % 2 == 1 else n - 1)
    if window < poly + 2:
        # too short for SG — fall back to moving average
        return _moving_average(arr, max(3, window))

    if _SCIPY_OK:
        smoothed = _savgol(vals, window, poly, mode="interp")
    else:
        smoothed = _moving_average_np(vals, window)

    return [None if nones[i] else float(smoothed[i]) for i in range(n)]


def _moving_average(series: Sequence[Optional[float]], window: int) -> List[Optional[float]]:
    n = len(series)
    out: List[Optional[float]] = []
    half = window // 2
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        sub = [v for v in series[lo:hi] if v is not None]
        out.append(sum(sub) / len(sub) if sub else None)
    return out


def _moving_average_np(arr: np.ndarray, window: int) -> np.ndarray:
    kernel = np.ones(window) / window
    return np.convolve(arr, kernel, mode="same")


# ─────────────────────────────────────────────────────────────────
# Kalman 1-D — for bar Y / smooth velocity
# ─────────────────────────────────────────────────────────────────

def kalman_1d(series: Sequence[Optional[float]], fps: float = 30.0,
              q: float = 1e-3, r: float = 1e-2) -> List[Optional[float]]:
    """Constant-velocity Kalman smoother for a 1-D position signal.

    State: [position, velocity]. Returns the filtered position with Nones
    forward-predicted from the model.
    """
    n = len(series)
    if n == 0:
        return []
    if not _FILTERPY_OK:
        return savgol_series(series, fps=fps, window_sec=0.3, poly=2)

    dt = 1.0 / max(fps, 1e-6)
    kf = KalmanFilter(dim_x=2, dim_z=1)
    kf.F = np.array([[1.0, dt], [0.0, 1.0]])
    kf.H = np.array([[1.0, 0.0]])
    kf.P *= 100.0
    kf.R = np.array([[r]])
    kf.Q = q * np.array([[dt**4 / 4, dt**3 / 2], [dt**3 / 2, dt**2]])

    # initialise on first observation
    first = next((v for v in series if v is not None), None)
    if first is None:
        return list(series)
    kf.x = np.array([float(first), 0.0])

    out: List[Optional[float]] = []
    for v in series:
        kf.predict()
        if v is not None:
            kf.update(np.array([float(v)]))
        out.append(float(kf.x[0]))
    return out


def kalman_velocity(series: Sequence[Optional[float]], fps: float = 30.0,
                    q: float = 1e-3, r: float = 1e-2) -> List[float]:
    """Velocity series from the same Kalman model as `kalman_1d`. Units = pos / sec."""
    n = len(series)
    if n == 0:
        return []
    if not _FILTERPY_OK:
        # fall back to centred difference on Savgol-smoothed position
        smoothed = savgol_series(series, fps=fps, window_sec=0.25, poly=3)
        return _central_diff(smoothed, fps)

    dt = 1.0 / max(fps, 1e-6)
    kf = KalmanFilter(dim_x=2, dim_z=1)
    kf.F = np.array([[1.0, dt], [0.0, 1.0]])
    kf.H = np.array([[1.0, 0.0]])
    kf.P *= 100.0
    kf.R = np.array([[r]])
    kf.Q = q * np.array([[dt**4 / 4, dt**3 / 2], [dt**3 / 2, dt**2]])

    first = next((v for v in series if v is not None), None)
    if first is None:
        return [0.0] * n
    kf.x = np.array([float(first), 0.0])

    vel: List[float] = []
    for v in series:
        kf.predict()
        if v is not None:
            kf.update(np.array([float(v)]))
        vel.append(float(kf.x[1] * fps) / fps)  # already per-second from state
    return vel


def _central_diff(series: Sequence[Optional[float]], fps: float) -> List[float]:
    n = len(series)
    out = [0.0] * n
    dt = 1.0 / max(fps, 1e-6)
    vals = [v if v is not None else 0.0 for v in series]
    for i in range(1, n - 1):
        out[i] = (vals[i + 1] - vals[i - 1]) / (2 * dt)
    if n >= 2:
        out[0] = (vals[1] - vals[0]) / dt
        out[-1] = (vals[-1] - vals[-2]) / dt
    return out
