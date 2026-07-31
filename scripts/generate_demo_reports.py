#!/usr/bin/env python
"""Pre-generate real analyzer output for the public demo mode.

Runs the actual production analyzers against the local sample videos and
writes each result to `demo/sample-reports/<type>__<slug>.json`. Those JSON
files are committed and served as static assets, so a visitor can open a
genuine, fully-rendered report (annotated frames included) instantly —
without uploading anything and without waking the CV container.

Usage:
    processor/venv/bin/python scripts/generate_demo_reports.py            # all
    processor/venv/bin/python scripts/generate_demo_reports.py knee-to-wall-test
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSOR = os.path.join(ROOT, 'processor')
sys.path.insert(0, PROCESSOR)

MOB_DIR = os.path.join(ROOT, 'Sample Videos for Mobility Assessment')
STR_DIR = os.path.join(ROOT, 'Sample Videos for Strength Assessment')
# Written straight into the frontend's static assets so both Vercel and the
# container serve them with no extra copy step. These files ARE committed.
OUT_DIR = os.path.join(ROOT, 'frontend', 'public', 'demo')


def m(name: str) -> str:
    return os.path.join(MOB_DIR, name)


def s(name: str) -> str:
    return os.path.join(STR_DIR, name)


# (assessment_type, slug, {upload_key: video_path}, analyzer_params)
JOBS = [
    # ── Mobility ────────────────────────────────────────────────────
    ('mobility', 'knee-to-wall-test', {
        'left':  m('1-knee-to-wall-left.mp4'),
        'right': m('1-knee-to-wall-right.mp4'),
    }, {'tibia_length_cm': 40.0}),

    ('mobility', 'seated-hip-rotation-test', {
        'left':  m('2-seated-hip-rotation-left.mp4'),
        'right': m('2-seated-hip-rotation-right.mp4'),
    }, {}),

    ('mobility', 'thoracic-extension', {
        'all': m('3-thoracic-extension.mp4'),
    }, {}),

    ('mobility', 'quadruped-rotation', {
        'left':  m('4-quadruped-rotation-left.mp4'),
        'right': m('4-quadruped-rotation-right.mp4'),
    }, {}),

    ('mobility', 'shoulder-rotation-90-90', {
        'left':  m('5-shoulder-rotation-90-90-left.mp4'),
        'right': m('5-shoulder-rotation-90-90-right.mp4'),
    }, {}),

    ('mobility', 'single-leg-glute-bridge', {
        'left':  m('6-single-leg-glute-bridge-left.mp4'),
        'right': m('6-single-leg-glute-bridge-right.mp4'),
    }, {}),

    ('mobility', 'dead-bug', {
        'all': m('7-dead-bug.mp4'),
    }, {}),

    ('mobility', 'hollow-body-hold', {
        'hold': m('8-hollow-body-hold.mp4'),
    }, {}),

    ('mobility', 'plank-shoulder-tap', {
        'all': m('9-plank-shoulder-tap.mp4'),
    }, {}),

    ('mobility', 'prone-y-t-w-raise', {
        'y-overhead': m('10-prone-y-top-raise.mp4'),
        'y-footside': m('10-prone-y-back-raise.mp4'),
        't-overhead': m('10-prone-t-top-raise.mp4'),
        't-footside': m('10-prone-t-back-raise.mp4'),
        'w-overhead': m('10-prone-w-top-raise.mp4'),
        'w-footside': m('10-prone-w-back-raise.mp4'),
    }, {}),

    # ── Strength ────────────────────────────────────────────────────
    ('strength', 'deadlift', {
        'sagittal':  s('Deadlift-Sagittal_View.mp4'),
        'frontal':   s('Deadlift-Frontal_View.mp4'),
        'posterior': s('Deadlft-Posterior_View.mp4'),
        'oblique':   s('Deadlift-Oblique_View.mp4'),
    }, {'plate_size_kg': 20.0, 'variant': 'conventional', 'target_reps': 3,
        'load_kg': 100.0, 'athlete_height_cm': 178.0}),

    ('strength', 'back-squat', {
        'side':  s('Sagittal_view.mp4'),
        'front': s('Frontal_view.mp4'),
    }, {'plate_size_kg': 20.0, 'variant': 'back-squat', 'target_reps': 3,
        'target_reps_side': 3, 'target_reps_front': 3,
        'load_kg': 100.0, 'athlete_height_cm': 178.0}),
]


def human_size(n: int) -> str:
    for unit in ('B', 'KB', 'MB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024.0
    return f'{n:.1f} GB'


def main() -> int:
    only = set(sys.argv[1:])
    os.makedirs(OUT_DIR, exist_ok=True)

    from analyzer_router import route_analysis

    # Reuse the processor's own numpy/NaN sanitiser so the JSON we write is
    # byte-identical in shape to what the live API returns.
    from app import _sanitize_for_json

    jobs = [j for j in JOBS if not only or j[1] in only]
    index = []
    ok_count = 0

    for a_type, slug, files, params in jobs:
        missing = [p for p in files.values() if not os.path.exists(p)]
        if missing:
            print(f'⏭  SKIP {a_type}/{slug} — missing video(s):')
            for p in missing:
                print(f'      {os.path.basename(p)}')
            continue

        print(f'\n▶  {a_type}/{slug}  ({len(files)} video(s))', flush=True)
        t0 = time.time()
        try:
            result = route_analysis(a_type, slug, files, params=params)
            result = _sanitize_for_json(result)
        except Exception as e:
            print(f'✗  FAILED {a_type}/{slug}: {type(e).__name__}: {e}')
            traceback.print_exc()
            continue

        elapsed = time.time() - t0
        out_path = os.path.join(OUT_DIR, f'{a_type}__{slug}.json')
        payload = json.dumps(result, separators=(',', ':'))
        with open(out_path, 'w') as f:
            f.write(payload)

        n_frames = len(result.get('annotated_frames') or [])
        size = len(payload.encode())
        print(f'✓  {a_type}/{slug}  score={result.get("score")} '
              f'status={result.get("status")}  frames={n_frames}  '
              f'{human_size(size)}  {elapsed:.0f}s', flush=True)

        index.append({
            'assessmentType': a_type,
            'slug': slug,
            'score': result.get('score'),
            'status': result.get('status'),
            'summary': result.get('summary'),
            'annotatedFrames': n_frames,
            'file': f'{a_type}__{slug}.json',
            'bytes': size,
        })
        ok_count += 1

    index_path = os.path.join(OUT_DIR, 'index.json')
    with open(index_path, 'w') as f:
        json.dump({'generated': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                   'reports': index}, f, indent=2)

    total = sum(r['bytes'] for r in index)
    print(f'\n══ Generated {ok_count}/{len(jobs)} reports — '
          f'{human_size(total)} total → {OUT_DIR}')
    return 0 if ok_count else 1


if __name__ == '__main__':
    raise SystemExit(main())
