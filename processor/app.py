"""MobilityAI Python CV Processor — Flask server for video analysis."""
import os
import sys
import json
import math
import tempfile
import traceback
import shutil
# pyrefly: ignore [missing-import]
from flask import Flask, request, jsonify
from flask_cors import CORS


def _sanitize_for_json(obj):
    """Recursively convert numpy/non-JSON types to native Python types.

    Analyzers frequently produce numpy.bool_, numpy.float32, etc. from
    OpenCV / MediaPipe comparisons. Flask's default JSON provider rejects
    those, causing 500s like
        TypeError: Object of type bool is not JSON serializable
    even though the field IS a boolean — it just isn't Python's bool.
    This runs once at the response boundary so every analyzer is safe.
    """
    try:
        import numpy as np
    except ImportError:
        np = None
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, (bytes, bytearray)):
        # base64 payloads should already be str; raw bytes are not JSON
        try: return obj.decode('utf-8')
        except Exception: return None
    if np is not None:
        if isinstance(obj, np.bool_):       return bool(obj)
        if isinstance(obj, np.integer):     return int(obj)
        if isinstance(obj, np.floating):
            v = float(obj)
            # NaN / inf aren't JSON-valid either
            if math.isnan(v) or math.isinf(v): return None
            return v
        if isinstance(obj, np.ndarray):     return _sanitize_for_json(obj.tolist())
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj

app = Flask(__name__)
CORS(app)

# Add processor root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to import CV libraries
try:
    import cv2
    import numpy as np
    import mediapipe as mp
    CV_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  CV libraries not fully available: {e}")
    CV_AVAILABLE = False

from analyzer_router import route_analysis, UnknownAnalyzerError


@app.route('/process', methods=['POST'])
def process_video():
    """Process uploaded exercise videos through the CV pipeline."""
    try:
        assessment_type = request.form.get('assessmentType')
        slug            = request.form.get('slug')
        exercise_id_raw = request.form.get('exerciseId')
        exercise_id     = int(exercise_id_raw) if exercise_id_raw else None
        files = request.files

        # Per-analyzer parameters forwarded transparently. The router only
        # passes the ones each analyzer's signature actually accepts, so
        # listing them all here is safe.
        params = {}

        def _float(name, key):
            raw = request.form.get(name)
            if raw:
                try: params[key] = float(raw)
                except ValueError: pass

        def _int(name, key):
            raw = request.form.get(name)
            if raw:
                try: params[key] = int(float(raw))
                except ValueError: pass

        def _str(name, key):
            raw = request.form.get(name)
            if raw: params[key] = raw

        # Mobility
        _float('tibiaLengthCm',    'tibia_length_cm')
        # Strength — shared
        _float('plateSizeKg',      'plate_size_kg')
        _float('loadKg',           'load_kg')
        _float('weightMax',        'weight_max')
        _int  ('repsMax',          'reps_max')
        _int  ('targetReps',       'target_reps')
        _str  ('variant',          'variant')
        # Strength — per-exercise
        _float('inclineDeg',       'incline_deg')
        _float('backrestDeg',      'backrest_deg')       # overhead press: 75 / 80 / 85 / 90
        _str  ('stance',           'stance')             # overhead press: military_true | strict
        _str  ('style',            'style')              # bench press, pull-up
        _str  ('paused',           'paused')             # bench press: paused | tng
        _str  ('grip',             'grip')
        _float('athleteHeightCm',  'athlete_height_cm')
        _int  ('targetRepsSide',   'target_reps_side')   # back squat
        _int  ('targetRepsFront',  'target_reps_front')  # back squat
        _int  ('targetRepsSagittal', 'target_reps_sagittal')   # bench press, pull-up
        _int  ('targetRepsOverhead', 'target_reps_overhead')   # bench press
        _int  ('targetRepsHeadEnd',  'target_reps_head_end')   # bench press
        _int  ('targetRepsFrontal',  'target_reps_frontal')    # pull-up
        _int  ('targetRepsPosterior','target_reps_posterior')  # pull-up
        _int  ('targetRepsOblique',  'target_reps_oblique')    # bench press, pull-up

        # Save files temporarily. Filenames are derived from the (unique)
        # upload field key, NOT the browser-supplied original filename — two
        # camera angles exported with the same name (e.g. IMG_0001.MOV) must
        # not overwrite each other in the shared temp dir.
        temp_dir = tempfile.mkdtemp()
        try:
            saved_files = {}

            for key in files:
                f = files[key]
                ext = os.path.splitext(f.filename or '')[1] or '.mp4'
                safe_key = ''.join(c if c.isalnum() or c in '-_' else '_' for c in key)
                filepath = os.path.join(temp_dir, f'{safe_key}{ext}')
                f.save(filepath)
                saved_files[key] = filepath

            print(f"\n📹 Processing {assessment_type}/{slug} (legacy id={exercise_id}) "
                  f"with {len(saved_files)} video(s)")
            for k, v in saved_files.items():
                size_mb = os.path.getsize(v) / (1024 * 1024)
                print(f"   {k}: {os.path.basename(v)} ({size_mb:.1f} MB)")

            # Route to the correct analyzer
            if CV_AVAILABLE and saved_files:
                result = route_analysis(
                    assessment_type, slug, saved_files,
                    exercise_id=exercise_id, params=params,
                )
            else:
                result = {
                    'status': 'NEEDS IMPROVEMENT',
                    'score': 50,
                    'summary': 'CV libraries not available — using mock results.',
                    'stats': {'validReps': '0/0', 'confidence': '0%', 'sides': 'n/a', 'cameraView': 'N/A'},
                    'metrics': [],
                    'bilateral': [],
                    'coaching': ['Install OpenCV and MediaPipe for real video analysis.'],
                }
        finally:
            # Always cleanup temp files — including when f.save() or the
            # analyzer raises, so failed uploads don't orphan directories.
            shutil.rmtree(temp_dir, ignore_errors=True)

        # Sanitize numpy/non-JSON types out of the result before serializing.
        # Any analyzer that produces numpy.bool_/float32/etc. is now safe.
        try:
            safe_result = _sanitize_for_json(result)
        except Exception as san_err:
            traceback.print_exc()
            return jsonify({
                'error':  f'Result sanitization failed: {san_err}',
                'detail': traceback.format_exc().splitlines()[-3:],
                'status': 'error',
            }), 500
        return jsonify(safe_result)

    except UnknownAnalyzerError as e:
        return jsonify({'error': str(e), 'status': 'error'}), 400
    except Exception as e:
        traceback.print_exc()
        # Always include both the short error and a full traceback so the
        # Node side can surface real diagnostics to the user.
        return jsonify({
            'error':  f'{type(e).__name__}: {e}',
            'detail': traceback.format_exc().splitlines()[-3:],
            'status': 'error',
        }), 500


@app.route('/health', methods=['GET'])
def health():
    from analyzer_router import ANALYZERS
    return jsonify({
        'status': 'ok',
        'cv_available': CV_AVAILABLE,
        'exercises': {t: sorted(slugs.keys()) for t, slugs in ANALYZERS.items()},
        # legacy field — old clients expect the mobility integer ids
        'legacy_exercise_ids': list(range(1, 11)),
    })


if __name__ == '__main__':
    # debug=True exposes the Werkzeug interactive debugger (arbitrary code
    # execution on any unhandled exception) — opt in explicitly, never in prod.
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    # Host/port are configurable but default to loopback: only the local Node
    # proxy should ever reach this service. In the single-container deploy both
    # processes share a network namespace, so 127.0.0.1 still works — and the
    # CV service stays unreachable from the public internet.
    host = os.environ.get('PROCESSOR_HOST', '127.0.0.1')
    port = int(os.environ.get('PROCESSOR_PORT', '5001'))
    n_analyzers = sum(len(v) for v in __import__('analyzer_router').ANALYZERS.values())
    print("\n🔬 MobilityAI Python Processor starting...")
    print(f"   CV Available: {CV_AVAILABLE}")
    print(f"   Analyzers: {n_analyzers} exercises loaded")
    print(f"   Debug mode: {debug_mode}")
    print(f"   Listening on http://{host}:{port}\n", flush=True)
    # threaded=True so the health check stays responsive while an analysis
    # is running (the platform's health probe must not time out mid-job).
    app.run(host=host, port=port, debug=debug_mode, threaded=True)

