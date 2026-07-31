"""End-to-end evaluation harness for strength analyzers.

Usage:
    python eval/run_eval.py --lift deadlift
    python eval/run_eval.py --all

Reads ground-truth annotations from `eval/annotations/<lift>/*.yaml`, runs the
matching analyzer on the referenced video, and reports per-fault precision /
recall / F1 plus the fault-timing MAE. This is the gate that justifies "≥95%"
claims: until macro-F1 ≥ 0.92 holds on a representative set, the analyzer
ships behind a warning.

Annotation YAML schema:
    video_path: ../videos/deadlift_001.mp4   # relative to this YAML file
    lift: deadlift
    variant: conventional
    plate_size_kg: 20
    target_reps: 5
    faults:
        - name: lumbar_flexion         # must match a per_rep metric key
          present: true
          rep: 3
          start_phase_pct: 60          # optional — for timing MAE
    metric_overrides:                   # optional — pass extra kwargs
        athlete_height_cm: 178
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

# Make the processor package importable when running this script directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer_router import route_analysis  # noqa: E402

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install PyYAML")
    sys.exit(1)


ANNOTATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'annotations')


def _load_annotations(lift: str) -> List[dict]:
    pattern = os.path.join(ANNOTATIONS_DIR, lift, '*.yaml')
    paths = sorted(glob.glob(pattern))
    out = []
    for p in paths:
        with open(p, 'r') as f:
            data = yaml.safe_load(f)
        data['_source'] = p
        out.append(data)
    return out


def _extract_predicted_fault(result: dict, fault_name: str) -> dict:
    """Pull predicted fault presence + timing from an analyzer result dict.

    Maps fault_name → metric name patterns. Add cases as new faults are scored.
    """
    metrics = result.get('metrics', [])
    name_lower = fault_name.lower()
    aliases = {
        'lumbar_flexion':       ['lumbar curvature', 'lumbar flexion'],
        'thoracic_extension':   ['thoracic extension', 'lumbar extension'],
        'valgus_left':          ['left knee valgus'],
        'valgus_right':         ['right knee valgus'],
        'butt_wink':            ['pelvic tuck', 'butt wink'],
        'kipping':              ['hip swing', 'kipping'],
        'elbow_flare':          ['elbow flare'],
        'chin_clearance':       ['chin clearance', 'valid reps (chin'],
        'bar_drift':            ['bar drift', 'bar over mid-foot'],
        'push_press':           ['strict press', 'leg drive'],
    }
    needles = [n.lower() for n in aliases.get(name_lower, [name_lower])]
    for m in metrics:
        mn = (m.get('name') or '').lower()
        if any(n in mn for n in needles):
            present = (m.get('status') == 'bad')
            ft = m.get('fault_timing') or {}
            return {
                'present': present,
                'rep': ft.get('rep'),
                'start_phase_pct': ft.get('start_phase_pct'),
                'metric_name': m.get('name'),
                'confidence': m.get('confidence'),
            }
    return {'present': False, 'rep': None, 'start_phase_pct': None,
            'metric_name': None, 'confidence': None}


def _f1(precision: float, recall: float) -> float:
    if precision + recall < 1e-9:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def evaluate_lift(lift: str, verbose: bool = True) -> dict:
    annotations = _load_annotations(lift)
    if not annotations:
        print(f"[eval] No annotations found for {lift} in {ANNOTATIONS_DIR}/{lift}/")
        return {}

    # confusion table per fault
    table: Dict[str, Dict[str, int]] = defaultdict(lambda: {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0})
    timing_errors: Dict[str, List[float]] = defaultdict(list)

    for ann in annotations:
        video_rel = ann.get('video_path', '')
        video_abs = os.path.normpath(os.path.join(os.path.dirname(ann['_source']), video_rel))
        if not os.path.exists(video_abs):
            print(f"  ⚠️ skipping {ann['_source']}: video not found at {video_abs}")
            continue

        # Build the kwargs the router will pass through
        params = {
            'plate_size_kg':     ann.get('plate_size_kg'),
            'target_reps':       ann.get('target_reps'),
            'variant':           ann.get('variant'),
            'load_kg':           ann.get('load_kg'),
            'weight_max':        ann.get('weight_max'),
            'reps_max':          ann.get('reps_max'),
            'athlete_height_cm': ann.get('athlete_height_cm'),
            'grip':              ann.get('grip'),
        }
        params.update(ann.get('metric_overrides') or {})
        params = {k: v for k, v in params.items() if v is not None}

        files = {'side': video_abs}
        if ann.get('front_video'):
            files['front'] = os.path.normpath(os.path.join(os.path.dirname(ann['_source']),
                                                            ann['front_video']))
        try:
            result = route_analysis('strength', lift, files, exercise_id=None, params=params)
        except Exception as e:
            print(f"  ❌ {os.path.basename(ann['_source'])}: analyzer error: {e}")
            continue

        for f in ann.get('faults', []):
            name = f['name']
            gt_present = bool(f['present'])
            pred = _extract_predicted_fault(result, name)
            pred_present = bool(pred['present'])
            cell = table[name]
            if gt_present and pred_present:
                cell['tp'] += 1
                if pred['start_phase_pct'] is not None and f.get('start_phase_pct') is not None:
                    timing_errors[name].append(abs(pred['start_phase_pct'] - f['start_phase_pct']))
            elif gt_present:
                cell['fn'] += 1
            elif pred_present:
                cell['fp'] += 1
            else:
                cell['tn'] += 1

        if verbose:
            print(f"  ✓ {os.path.basename(ann['_source'])}: score={result.get('score')} "
                   f"status={result.get('status')}")

    # report
    print(f"\n{'─'*72}\nLift: {lift}\n{'─'*72}")
    print(f"{'Fault':<24} {'TP':>4} {'FP':>4} {'FN':>4} {'TN':>4}  {'Prec':>6} {'Rec':>6} {'F1':>6}  {'MAE':>6}")
    f1s = []
    for fault, cell in sorted(table.items()):
        tp, fp, fn, tn = cell['tp'], cell['fp'], cell['fn'], cell['tn']
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec  = tp / (tp + fn) if (tp + fn) else 0.0
        f1   = _f1(prec, rec)
        f1s.append(f1)
        errs = timing_errors[fault]
        mae  = (sum(errs) / len(errs)) if errs else None
        mae_str = f"{mae:.1f}%" if mae is not None else " —"
        print(f"{fault:<24} {tp:>4} {fp:>4} {fn:>4} {tn:>4}  {prec:>6.2f} {rec:>6.2f} {f1:>6.2f}  {mae_str:>6}")

    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0
    print(f"\nMacro-F1: {macro_f1:.3f}    (gate: ≥ 0.92 for merge)")
    return {'lift': lift, 'table': dict(table), 'macro_f1': macro_f1,
            'timing_mae': {k: (sum(v) / len(v)) if v else None for k, v in timing_errors.items()}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lift', choices=['deadlift', 'back-squat', 'bench-press',
                                            'overhead-press', 'pull-up'])
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--json', action='store_true', help='emit machine-readable JSON summary')
    args = parser.parse_args()

    if args.all:
        results = [evaluate_lift(l, verbose=not args.json) for l in
                   ('deadlift', 'back-squat', 'bench-press', 'overhead-press', 'pull-up')]
    elif args.lift:
        results = [evaluate_lift(args.lift, verbose=not args.json)]
    else:
        parser.error('Pass --lift <slug> or --all')

    if args.json:
        print(json.dumps(results, indent=2, default=str))


if __name__ == '__main__':
    main()
