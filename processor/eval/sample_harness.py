"""Sample-video harness with landmark caching.

Extracting MediaPipe landmarks from a 4K video takes minutes; analyzer logic
takes milliseconds. This harness extracts landmarks ONCE per video into a
pickle cache, then serves `extract_all_landmarks` from the cache so analyzers
can be re-run instantly while iterating on their logic.

Usage:
    # one-time (slow) cache build for one video:
    python eval/sample_harness.py extract "<video path>"

    # run an analyzer against cached landmarks:
    python eval/sample_harness.py run mobility knee-to-wall-test \
        left="<left video>" right="<right video>"

The cache key includes the file's size and mtime, so re-recorded videos
re-extract automatically. Cache lives in eval/cache/.
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time

PROCESSOR_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROCESSOR_ROOT)

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

import utils.landmarks as _lm_mod

_real_extract = _lm_mod.extract_all_landmarks


def _cache_path(video_path):
    st = os.stat(video_path)
    base = os.path.basename(video_path).replace(' ', '_')
    return os.path.join(CACHE_DIR, f'{base}.{st.st_size}.{int(st.st_mtime)}.pkl')


def extract_cached(video_path, **kwargs):
    """Drop-in replacement for extract_all_landmarks with a pickle cache.

    Smoothing params are applied AFTER the cache: the cache stores raw
    frames, so smoothing changes don't invalidate it.
    """
    cp = _cache_path(video_path)
    if os.path.exists(cp):
        with open(cp, 'rb') as f:
            data = pickle.load(f)
    else:
        t0 = time.time()
        print(f'⏳ extracting {os.path.basename(video_path)} ...', flush=True)
        # Ask the real extractor for raw (unsmoothed) frames; cache those.
        data = _real_extract(video_path, smooth=False)
        with open(cp, 'wb') as f:
            pickle.dump({
                'raw_frames': data['raw_frames'],
                'fps': data['fps'],
                'total_frames': data['total_frames'],
                'width': data['width'],
                'height': data['height'],
            }, f)
        print(f'✅ extracted {os.path.basename(video_path)} in {time.time()-t0:.0f}s', flush=True)
        with open(cp, 'rb') as f:
            data = pickle.load(f)

    raw_frames = data['raw_frames']
    fps = data['fps']
    out_frames = raw_frames
    if kwargs.get('smooth', True):
        try:
            from utils.signal_filters import smooth_landmarks as _smooth
            out_frames = _smooth(
                raw_frames, fps=fps,
                min_cutoff=kwargs.get('smooth_min_cutoff', 1.0),
                beta=kwargs.get('smooth_beta', 0.007),
            )
        except Exception as e:
            print(f'⚠️  smoothing skipped: {e}')
            out_frames = raw_frames
    return {
        'frames': out_frames,
        'raw_frames': raw_frames,
        'fps': fps,
        'total_frames': data['total_frames'],
        'width': data['width'],
        'height': data['height'],
    }


def install():
    """Patch extract_all_landmarks with the cached version (idempotent)."""
    _lm_mod.extract_all_landmarks = extract_cached


def run_analyzer(assessment_type, slug, files, params=None):
    """Run an analyzer through the real router with the cache installed."""
    install()
    from analyzer_router import route_analysis
    t0 = time.time()
    result = route_analysis(assessment_type, slug, files, params=params or {})
    print(f'⏱  analyzer logic took {time.time()-t0:.1f}s (post-extraction)')
    return result


def summarize(result, max_metrics=99):
    out = {
        'status': result.get('status'),
        'score': result.get('score'),
        'summary': result.get('summary'),
        'stats': result.get('stats'),
        'metrics': [
            {k: m.get(k) for k in ('name', 'value', 'target', 'status', 'classification')}
            for m in result.get('metrics', [])[:max_metrics]
        ],
        'bilateral': result.get('bilateral'),
        'coaching': result.get('coaching'),
        'n_annotated_frames': len(result.get('annotated_frames', []) or []),
        'per_rep': result.get('per_rep'),
    }
    return out


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'extract':
        install()
        for vp in sys.argv[2:]:
            extract_cached(vp)
    elif cmd == 'run':
        atype, slug = sys.argv[2], sys.argv[3]
        files = {}
        params = {}
        for kv in sys.argv[4:]:
            k, v = kv.split('=', 1)
            if k.startswith('p:'):
                params[k[2:]] = float(v) if v.replace('.', '', 1).isdigit() else v
            else:
                files[k] = v
        res = run_analyzer(atype, slug, files, params)
        print(json.dumps(summarize(res), indent=2, default=str))
    else:
        print('unknown command', cmd)
