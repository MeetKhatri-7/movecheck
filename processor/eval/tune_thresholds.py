"""Grid-search per-fault thresholds to maximise F1 on a 70/30 split.

This is the last 5–10% of accuracy gain — instead of guessing thresholds,
optimise them against the annotated set. Writes results to
`processor/config/<lift>_variants.json`.

Usage:
    python eval/tune_thresholds.py --lift deadlift --metric lumbar_flexion

Status: scaffold. Concrete tuning loops are added per-metric once we have
real annotation videos to grid against — this file documents the contract.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def tune(lift: str, metric: str, candidate_thresholds: List[Tuple[float, float]]) -> dict:
    """Try each (good_max, ni_max) pair and return the F1-maximising choice.

    This is currently a stub — when annotation data exists, swap in the loop
    that calls run_eval.evaluate_lift with mutated thresholds and records F1.
    """
    print(f"[tune] lift={lift} metric={metric} candidates={len(candidate_thresholds)}")
    print("[tune] No annotation data yet — populate eval/annotations/ first.")
    return {'lift': lift, 'metric': metric, 'best': None}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--lift', required=True)
    p.add_argument('--metric', required=True)
    p.add_argument('--good', type=float, nargs='+', default=[10, 12, 15])
    p.add_argument('--ni', type=float, nargs='+', default=[17, 19, 22])
    args = p.parse_args()
    candidates = [(g, n) for g in args.good for n in args.ni if g < n]
    out = tune(args.lift, args.metric, candidates)
    config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
    os.makedirs(config_dir, exist_ok=True)
    path = os.path.join(config_dir, f'{args.lift.replace("-", "_")}_tuned.json')
    with open(path, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"[tune] result written: {path}")


if __name__ == '__main__':
    main()
