"""Run every sample-video analyzer against the landmark cache and dump
summaries + annotated frames for review.

Usage: python eval/run_all_samples.py [slug ...]
       (no args = all mobility+strength slugs that have sample videos)
"""
import base64
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sample_harness import install, summarize
install()

M = "/Volumes/KIOXIA 1/Bold and Projects/Moblity 2/Sample Videos for Mobility Assessment"
S = "/Volumes/KIOXIA 1/Bold and Projects/Moblity 2/Sample Videos for Strength Assessment"
OUT = "/private/tmp/claude-501/-Volumes-KIOXIA-1-Bold-and-Projects-Moblity-2/20e6cc62-edcf-4f1e-8191-f96d51504abd/scratchpad/results"
os.makedirs(OUT, exist_ok=True)

RUNS = {
    'knee-to-wall-test': ('mobility', {
        'left':  f'{M}/1-knee-to-wall-left.mp4',
        'right': f'{M}/1-knee-to-wall-right.mp4'}, {}),
    'seated-hip-rotation-test': ('mobility', {
        'left':  f'{M}/2-seated-hip-rotation-left.mp4',
        'right': f'{M}/2-seated-hip-rotation-right.mp4'}, {}),
    'thoracic-extension': ('mobility', {
        'all': f'{M}/3-thoracic-extension.mp4'}, {}),
    'quadruped-rotation': ('mobility', {
        'left':  f'{M}/4-quadruped-rotation-left.mp4',
        'right': f'{M}/4-quadruped-rotation-right.mp4'}, {}),
    'shoulder-rotation-90-90': ('mobility', {
        'left':  f'{M}/5-shoulder-rotation-90-90-left.mp4',
        'right': f'{M}/5-shoulder-rotation-90-90-right.mp4'}, {}),
    'single-leg-glute-bridge': ('mobility', {
        'left':  f'{M}/6-single-leg-glute-bridge-left.mp4',
        'right': f'{M}/6-single-leg-glute-bridge-right.mp4'}, {}),
    'dead-bug': ('mobility', {
        'all': f'{M}/7-dead-bug.mp4'}, {}),
    'hollow-body-hold': ('mobility', {
        'all': f'{M}/8-hollow-body-hold.mp4'}, {}),
    'plank-shoulder-tap': ('mobility', {
        'all': f'{M}/9-plank-shoulder-tap.mp4'}, {}),
    'prone-y-t-w-raise': ('mobility', {
        'y-overhead': f'{M}/10-prone-y-top-raise.mp4',
        'y-footside': f'{M}/10-prone-y-back-raise.mp4',
        't-overhead': f'{M}/10-prone-t-top-raise.mp4',
        't-footside': f'{M}/10-prone-t-back-raise.mp4',
        'w-overhead': f'{M}/10-prone-w-top-raise.mp4',
        'w-footside': f'{M}/10-prone-w-back-raise.mp4'}, {}),
    'back-squat': ('strength', {
        'side':  f'{S}/Sagittal_view.mp4',
        'front': f'{S}/Frontal_view.mp4'},
        {'target_reps_side': 1, 'target_reps_front': 1, 'plate_size_kg': 20.0}),
    'deadlift': ('strength', {
        'sagittal':  f'{S}/Deadlift-Sagittal_View.mp4',
        'frontal':   f'{S}/Deadlift-Frontal_View.mp4',
        'posterior': f'{S}/Deadlft-Posterior_View.mp4',
        'oblique':   f'{S}/Deadlift-Oblique_View.mp4'},
        {'target_reps': 1, 'plate_size_kg': 20.0}),
}


def run_one(slug):
    atype, files, params = RUNS[slug]
    from analyzer_router import route_analysis
    print(f'\n════ {slug} ════', flush=True)
    try:
        res = route_analysis(atype, slug, files, params=params)
    except Exception as e:
        traceback.print_exc()
        with open(os.path.join(OUT, f'{slug}.json'), 'w') as f:
            json.dump({'error': f'{type(e).__name__}: {e}'}, f, indent=2)
        return
    summ = summarize(res)
    with open(os.path.join(OUT, f'{slug}.json'), 'w') as f:
        json.dump(summ, f, indent=2, default=str)
    # save annotated frames as jpgs
    for i, af in enumerate(res.get('annotated_frames', []) or []):
        b64 = af.get('image_base64', '')
        if ',' in b64:
            b64 = b64.split(',', 1)[1]
        if not b64:
            continue
        label = af.get('label', str(i)).replace(' ', '_').replace('/', '-')
        with open(os.path.join(OUT, f'{slug}__{i:02d}_{label}.jpg'), 'wb') as f:
            f.write(base64.b64decode(b64))
    print(f'  -> {summ["status"]} {summ["score"]} reps={summ["stats"].get("validReps")} '
          f'frames={summ["n_annotated_frames"]}', flush=True)


if __name__ == '__main__':
    slugs = sys.argv[1:] or list(RUNS.keys())
    for slug in slugs:
        run_one(slug)
    print('\nDONE', flush=True)
