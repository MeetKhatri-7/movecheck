# Strength Analyzer Evaluation Set

Each lift's accuracy gate is **macro-F1 ≥ 0.92** with **per-fault F1 ≥ 0.85**, measured against hand-annotated videos in this directory.

## Annotation format

One YAML file per video, in `eval/annotations/<lift-slug>/`.

```yaml
video_path: ../videos/deadlift_001.mp4
lift: deadlift
variant: conventional
plate_size_kg: 20
target_reps: 5
faults:
  - name: lumbar_flexion          # see _extract_predicted_fault aliases
    present: true                 # ground-truth from a qualified coach
    rep: 3                        # which rep the fault appears on
    start_phase_pct: 60           # optional — where in the pull (0=setup, 100=lockout)
  - name: bar_drift
    present: false
```

## Running the eval

```
python eval/run_eval.py --lift deadlift
python eval/run_eval.py --all
python eval/run_eval.py --all --json > eval_results.json
```

## Target counts

| Lift | Videos needed | Faults per video |
|---|---|---|
| Deadlift       | 30 | 3–5  |
| Back Squat     | 30 | 4–6  |
| Bench Press    | 30 | 3–5  |
| Overhead Press | 30 | 3–5  |
| Pull-Up        | 30 | 3–5  |

Mix: ~50% clean reps, ~30% one fault present, ~20% multiple faults. Two-rater agreement (~85–90%) is the practical ceiling.
