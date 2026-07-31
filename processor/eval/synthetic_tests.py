"""Synthetic landmark tests for the no-sample-video analyzers
(bench press, pull-up, overhead press).

Builds parametric 33-landmark skeletons performing N clean reps (and faulty
variants), feeds them through the real analyse() entry points by
monkeypatching extract_all_landmarks, and asserts:
  1. exact rep detection,
  2. sane scores for clean form,
  3. metrics that MOVE THE RIGHT WAY for a planted fault.

Run: venv/bin/python eval/synthetic_tests.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils.landmarks as lm_mod

FPS = 30.0
W, H = 1280, 720

# MediaPipe indices
NOSE = 0
L_EAR, R_EAR = 7, 8
L_SH, R_SH = 11, 12
L_EL, R_EL = 13, 14
L_WR, R_WR = 15, 16
L_HIP, R_HIP = 23, 24
L_KN, R_KN = 25, 26
L_AN, R_AN = 27, 28
L_HE, R_HE = 29, 30
L_FI, R_FI = 31, 32


def _frame_from_points(pts, vis=0.95):
    """pts: dict idx -> (x, y) normalized. Returns a 33-tuple landmark list."""
    out = []
    for i in range(33):
        if i in pts:
            x, y = pts[i]
            out.append((x, y, 0.0, vis))
        else:
            # Park unspecified landmarks near the hip so they exist but do
            # not draw attention (visibility low).
            hx, hy = pts.get(L_HIP, (0.5, 0.6))
            out.append((hx, hy, 0.0, 0.1))
    return out


def _series(builder, n_frames):
    frames = []
    for i in range(n_frames):
        t = i / FPS
        pts = builder(t)
        frames.append({'frame_idx': i, 'time_sec': t,
                       'landmarks': _frame_from_points(pts)})
    return {'frames': frames, 'raw_frames': frames, 'fps': FPS,
            'total_frames': n_frames, 'width': W, 'height': H}


def _cycle(t, period, lo, hi, rest=0.35):
    """Smooth rep cycle: rest at `lo`, excursion to `hi`, back. rest = idle
    fraction at the start of each period."""
    ph = (t % period) / period
    if ph < rest:
        return lo
    x = (ph - rest) / (1.0 - rest)          # 0..1 across the movement
    return lo + (hi - lo) * 0.5 * (1 - math.cos(2 * math.pi * x))


# ─────────────────────────────────────────────────────────────
# Skeleton builders (side view, athlete faces +x)
# ─────────────────────────────────────────────────────────────

def ohp_builder(n_reps=3, lockout_deficit=0.0):
    """Standing OHP: bar from rack position to overhead. lockout_deficit
    (0..1) stops the press short of full lockout."""
    period = 4.0

    def b(t):
        rack_y = 0.28
        top_y = 0.12 + 0.18 * lockout_deficit
        wr_y = _cycle(t, period, rack_y, top_y)
        f = (rack_y - wr_y) / max(1e-6, rack_y - top_y)
        wr_x = 0.60 - 0.08 * f
        # Elbow: horizontal out front at the rack (≈90° elbow angle in this
        # projection), moving inline under the wrist at lockout (≈175°).
        el_x = 0.60 - 0.085 * f
        el_y = 0.36 - 0.12 * f
        return {
            NOSE: (0.53, 0.25), L_EAR: (0.515, 0.26), R_EAR: (0.525, 0.26),
            L_SH: (0.50, 0.35), R_SH: (0.51, 0.35),
            L_EL: (el_x, el_y), R_EL: (el_x + 0.01, el_y),
            L_WR: (wr_x, wr_y), R_WR: (wr_x + 0.01, wr_y),
            L_HIP: (0.50, 0.60), R_HIP: (0.51, 0.60),
            L_KN: (0.50, 0.75), R_KN: (0.51, 0.75),
            L_AN: (0.50, 0.90), R_AN: (0.51, 0.90),
            L_HE: (0.48, 0.915), R_HE: (0.49, 0.915),
            L_FI: (0.545, 0.915), R_FI: (0.555, 0.915),
        }
    return b, int(period * n_reps * FPS)


def pullup_builder(n_reps=5, rom_deficit=0.0):
    """Pull-up: wrists fixed on the bar, body rises. rom_deficit>0 keeps the
    chin below the bar."""
    period = 3.5
    bar_y = 0.15

    def b(t):
        rise = _cycle(t, period, 0.0, 1.0 - rom_deficit)
        sh_y = 0.45 - 0.22 * rise            # hang 0.45 → top 0.23
        nose_y = sh_y - 0.10                 # chin above bar at top
        hip_y = sh_y + 0.25
        kn_y = hip_y + 0.14                  # knees slightly flexed
        an_y = kn_y + 0.13
        return {
            NOSE: (0.52, nose_y), L_EAR: (0.505, nose_y + 0.01), R_EAR: (0.515, nose_y + 0.01),
            L_SH: (0.50, sh_y), R_SH: (0.51, sh_y),
            L_EL: (0.515, (bar_y + sh_y) / 2), R_EL: (0.525, (bar_y + sh_y) / 2),
            L_WR: (0.53, bar_y), R_WR: (0.54, bar_y),
            L_HIP: (0.49, hip_y), R_HIP: (0.50, hip_y),
            L_KN: (0.505, kn_y), R_KN: (0.515, kn_y),
            L_AN: (0.49, an_y), R_AN: (0.50, an_y),
            L_HE: (0.485, an_y + 0.01), R_HE: (0.495, an_y + 0.01),
            L_FI: (0.51, an_y + 0.02), R_FI: (0.52, an_y + 0.02),
        }
    return b, int(period * n_reps * FPS)


def bench_builder(n_reps=3, touch_deficit=0.0):
    """Flat bench (side view, head to the left): bar lockout above chest →
    touch. touch_deficit>0 stops above the chest."""
    period = 4.0

    def b(t):
        # chest plane at y≈0.55; lockout wrist at y≈0.30
        touch_y = 0.53 - 0.12 * touch_deficit
        wr_y = _cycle(t, period, 0.30, touch_y)
        el_y = wr_y + 0.10
        return {
            NOSE: (0.30, 0.52), L_EAR: (0.305, 0.545), R_EAR: (0.315, 0.545),
            L_SH: (0.38, 0.58), R_SH: (0.39, 0.58),
            L_EL: (0.435, el_y), R_EL: (0.445, el_y),
            L_WR: (0.44, wr_y), R_WR: (0.45, wr_y),
            L_HIP: (0.58, 0.60), R_HIP: (0.59, 0.60),
            L_KN: (0.70, 0.68), R_KN: (0.71, 0.68),
            L_AN: (0.72, 0.88), R_AN: (0.73, 0.88),
            L_HE: (0.71, 0.90), R_HE: (0.72, 0.90),
            L_FI: (0.75, 0.90), R_FI: (0.76, 0.90),
        }
    return b, int(period * n_reps * FPS)


# ─────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────

REGISTRY = {}


def fake_extract(video_path, **kwargs):
    if video_path in REGISTRY:
        return REGISTRY[video_path]
    raise ValueError(f"Cannot open video: {video_path}")


def run_case(name, analyzer_fn, files, expect_reps, kwargs=None):
    res = analyzer_fn(files, **(kwargs or {}))
    stats = res.get('stats', {})
    reps = stats.get('validReps', '?')
    print(f"\n── {name}: {res.get('status')} {res.get('score')} reps={reps}")
    interesting = [m for m in res.get('metrics', [])][:14]
    for m in interesting:
        print(f"    {m['name']:34s} {str(m['value']):14s} {m.get('classification') or m.get('status')}")
    ok = str(expect_reps) in str(reps)
    print(f"    rep-check: expected {expect_reps} → {'✅' if ok else f'❌ got {reps}'}")
    return res


def main():
    lm_mod.extract_all_landmarks = fake_extract

    from analyzers.strength import bench_press, pull_up, overhead_press
    import importlib
    for m in (bench_press, pull_up, overhead_press):
        importlib.reload(m)

    # OHP clean + faulty lockout
    b, n = ohp_builder(3)
    REGISTRY['/syn/ohp_clean.mp4'] = _series(b, n)
    b, n = ohp_builder(3, lockout_deficit=0.5)
    REGISTRY['/syn/ohp_partial.mp4'] = _series(b, n)
    clean = run_case('OHP clean (3 reps)', overhead_press.analyse,
                     {'sagittal': '/syn/ohp_clean.mp4'}, 3,
                     {'target_reps_sagittal': 3, 'variant': 'military'})
    partial = run_case('OHP partial lockout', overhead_press.analyse,
                       {'sagittal': '/syn/ohp_partial.mp4'}, 3,
                       {'target_reps_sagittal': 3, 'variant': 'military'})
    print(f"    fault-direction: clean {clean['score']} vs partial {partial['score']} "
          f"→ {'✅ partial scored lower' if partial['score'] < clean['score'] else '❌'}")

    # Pull-up clean + short ROM
    b, n = pullup_builder(5)
    REGISTRY['/syn/pu_clean.mp4'] = _series(b, n)
    b, n = pullup_builder(5, rom_deficit=0.45)
    REGISTRY['/syn/pu_short.mp4'] = _series(b, n)
    clean = run_case('Pull-up clean (5 reps)', pull_up.analyse,
                     {'sagittal': '/syn/pu_clean.mp4'}, 5,
                     {'target_reps_sagittal': 5, 'grip': 'pronated', 'style': 'strict'})
    short = run_case('Pull-up short ROM', pull_up.analyse,
                     {'sagittal': '/syn/pu_short.mp4'}, 5,
                     {'target_reps_sagittal': 5, 'grip': 'pronated', 'style': 'strict'})
    print(f"    fault-direction: clean {clean['score']} vs short {short['score']} "
          f"→ {'✅ short ROM scored lower' if short['score'] < clean['score'] else '❌'}")

    # Bench clean + no chest touch
    b, n = bench_builder(3)
    REGISTRY['/syn/bp_clean.mp4'] = _series(b, n)
    b, n = bench_builder(3, touch_deficit=0.6)
    REGISTRY['/syn/bp_short.mp4'] = _series(b, n)
    clean = run_case('Bench clean (3 reps)', bench_press.analyse,
                     {'sagittal': '/syn/bp_clean.mp4'}, 3,
                     {'target_reps_sagittal': 3, 'variant': 'flat', 'style': 'powerlifting'})
    short = run_case('Bench no-touch', bench_press.analyse,
                     {'sagittal': '/syn/bp_short.mp4'}, 3,
                     {'target_reps_sagittal': 3, 'variant': 'flat', 'style': 'powerlifting'})
    print(f"    fault-direction: clean {clean['score']} vs no-touch {short['score']} "
          f"→ {'✅ no-touch scored lower' if short['score'] < clean['score'] else '❌'}")


if __name__ == '__main__':
    main()
