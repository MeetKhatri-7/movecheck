"""DTW-based template matching for strength reps.

Per-lift canonical templates of the primary motion signal (e.g. bar Y for
deadlift/bench/OHP, hip Y for squat, shoulder-to-bar elevation for pull-up).
Each template is the time-normalized, magnitude-normalized average of a small
set of 'ideal' reps.

Use:
    sim = template_similarity(rep_signal, 'deadlift')   # 0..1
    outliers = flag_outlier_reps(rep_signals, 'deadlift')

Templates live in `processor/templates/<lift>.json` as a list of 100 floats
sampled across the rep timeline. When a template is missing, we fall back to
a synthetic cosine-like prototype (down then up, normalized to [0,1]) which
is good enough to flag truly aberrant reps (kipping, mid-rep dump).
"""
from __future__ import annotations

import json
import math
import os
from typing import List, Optional, Sequence

import numpy as np

try:
    from dtaidistance import dtw
    _DTW_OK = True
except ImportError:  # pragma: no cover
    _DTW_OK = False


_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              '..', 'templates')
_TEMPLATE_LEN = 100
_TEMPLATE_CACHE: dict[str, np.ndarray] = {}


def _synthetic_template(kind: str = 'down_up') -> np.ndarray:
    """Fallback prototype: smooth descent → bottom → smooth ascent.

    Values in [0,1], length 100. Represents a clean rep signal where 0 = top
    and 1 = bottom, time-normalized.
    """
    t = np.linspace(0, math.pi, _TEMPLATE_LEN)
    # half-sine peaks at the bottom (t = pi/2 = midway)
    return np.sin(t)


def _load_template(lift_slug: str) -> np.ndarray:
    """Load a per-lift template from disk, or return the synthetic fallback."""
    if lift_slug in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[lift_slug]
    path = os.path.join(_TEMPLATE_DIR, f'{lift_slug.replace("-", "_")}.json')
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            arr = np.array(data, dtype=float)
            if arr.size >= 10:
                _TEMPLATE_CACHE[lift_slug] = _normalize(arr)
                return _TEMPLATE_CACHE[lift_slug]
        except Exception:
            pass
    _TEMPLATE_CACHE[lift_slug] = _synthetic_template()
    return _TEMPLATE_CACHE[lift_slug]


def _normalize(series: Sequence[float]) -> np.ndarray:
    """Resample to TEMPLATE_LEN and rescale to [0,1]."""
    arr = np.array([v for v in series if v is not None], dtype=float)
    if arr.size < 2:
        return np.zeros(_TEMPLATE_LEN)
    # resample
    src_x = np.linspace(0, 1, arr.size)
    tgt_x = np.linspace(0, 1, _TEMPLATE_LEN)
    arr = np.interp(tgt_x, src_x, arr)
    lo, hi = float(arr.min()), float(arr.max())
    if hi - lo < 1e-9:
        return np.zeros(_TEMPLATE_LEN)
    return (arr - lo) / (hi - lo)


def template_similarity(rep_signal: Sequence[float], lift_slug: str) -> float:
    """Similarity of `rep_signal` to the lift's canonical template, in [0,1].

    1.0 = perfect match (identical after normalization).
    0.0 = maximally dissimilar (DTW distance >= 1 after norm).

    When dtaidistance is not installed, falls back to normalized cross-
    correlation, which is correlation under linear time alignment.
    """
    template = _load_template(lift_slug)
    sig = _normalize(rep_signal)
    if sig.size != template.size:
        sig = np.interp(np.linspace(0, 1, _TEMPLATE_LEN),
                        np.linspace(0, 1, sig.size), sig)
    if _DTW_OK:
        try:
            d = dtw.distance_fast(sig.astype(np.double),
                                   template.astype(np.double),
                                   use_pruning=True)
            # normalize by template length so result is comparable across reps.
            d_norm = d / math.sqrt(_TEMPLATE_LEN)
            return max(0.0, min(1.0, 1.0 - d_norm))
        except Exception:
            pass
    # Fallback: NCC
    if sig.std() < 1e-9 or template.std() < 1e-9:
        return 0.0
    corr = float(np.corrcoef(sig, template)[0, 1])
    return max(0.0, min(1.0, (corr + 1.0) / 2.0))


def flag_outlier_reps(rep_signals: List[Sequence[float]], lift_slug: str,
                      similarity_floor: float = 0.5) -> List[int]:
    """Indices of reps whose template similarity falls below `similarity_floor`.

    Use to downweight a single mangled rep in aggregation so it doesn't flip a
    whole session classification.
    """
    out: List[int] = []
    for i, sig in enumerate(rep_signals):
        sim = template_similarity(sig, lift_slug)
        if sim < similarity_floor:
            out.append(i)
    return out


def rep_signal_for_lift(rep, frames_data, lift_slug: str,
                         bar_centres: Optional[List] = None) -> List[float]:
    """Pull the canonical motion signal for a rep, given lift + frames.

    Returns the time-series sampled from the rep's frame window. Used as the
    input to `template_similarity` / `flag_outlier_reps`.

    Convention: signal increases as the body moves AWAY from the top of the
    rep (so bottom = max for squat/dl, top = max for pull-up, etc.).
    """
    start = rep.get('start_frame', 0)
    end = rep.get('end_frame', len(frames_data) - 1)
    if start >= end:
        return []

    from .landmarks import LM  # local import

    if lift_slug == 'back-squat':
        # hip-Y (lower → bottom → higher again would be the standard rep
        # cycle; flip to "0=top, 1=bottom"):
        ys = []
        for f in frames_data[start:end + 1]:
            lm = f.get('landmarks')
            if lm is None:
                ys.append(None)
                continue
            l = lm[LM['LEFT_HIP']]; r = lm[LM['RIGHT_HIP']]
            if l[3] > 0.4 and r[3] > 0.4:
                ys.append((l[1] + r[1]) / 2)
            else:
                ys.append(None)
        return ys

    if lift_slug == 'deadlift':
        # Use bar Y (inverted: lockout = top, so 1=bottom)
        if bar_centres is not None:
            ys = [c[1] if c else None for c in bar_centres[start:end + 1]]
            return ys
        ys = []
        for f in frames_data[start:end + 1]:
            lm = f.get('landmarks')
            ys.append((lm[LM['LEFT_HIP']][1] + lm[LM['RIGHT_HIP']][1]) / 2 if lm else None)
        return ys

    if lift_slug == 'bench-press':
        if bar_centres is not None:
            return [c[1] if c else None for c in bar_centres[start:end + 1]]
        ys = []
        for f in frames_data[start:end + 1]:
            lm = f.get('landmarks')
            ys.append(lm[LM['LEFT_WRIST']][1] if lm else None)
        return ys

    if lift_slug == 'overhead-press':
        if bar_centres is not None:
            return [c[1] if c else None for c in bar_centres[start:end + 1]]
        ys = []
        for f in frames_data[start:end + 1]:
            lm = f.get('landmarks')
            ys.append(lm[LM['LEFT_WRIST']][1] if lm else None)
        return ys

    if lift_slug == 'pull-up':
        # shoulder-to-wrist elevation: shoulder rises toward wrist at the top
        ys = []
        for f in frames_data[start:end + 1]:
            lm = f.get('landmarks')
            if lm is None:
                ys.append(None)
                continue
            sh = (lm[LM['LEFT_SHOULDER']][1] + lm[LM['RIGHT_SHOULDER']][1]) / 2
            wr = (lm[LM['LEFT_WRIST']][1]  + lm[LM['RIGHT_WRIST']][1])  / 2
            ys.append(sh - wr)  # large = shoulder far above wrist (top of rep)
        return ys

    return []
