"""Router that maps (assessment_type, slug) → analyzer module.

Replaces the older exercise_id-based dispatch with a registry pattern so
mobility and strength can coexist and new exercises can be added without
touching this file's control flow.
"""
import importlib
import inspect
import os
import sys


# (module_path, function_name) per (assessment_type, slug)
ANALYZERS = {
    'mobility': {
        'knee-to-wall-test':         ('analyzers.mobility.knee_to_wall',         'analyse'),
        'seated-hip-rotation-test':  ('analyzers.mobility.seated_hip_rotation',  'analyse'),
        'thoracic-extension':        ('analyzers.mobility.thoracic_extension',   'analyse'),
        'quadruped-rotation':        ('analyzers.mobility.quadruped_rotation',   'analyse'),
        'shoulder-rotation-90-90':   ('analyzers.mobility.shoulder_rotation',    'analyse'),
        'single-leg-glute-bridge':   ('analyzers.mobility.glute_bridge',         'analyse'),
        'dead-bug':                  ('analyzers.mobility.dead_bug',             'analyse'),
        'hollow-body-hold':          ('analyzers.mobility.hollow_body',          'analyse'),
        'plank-shoulder-tap':        ('analyzers.mobility.plank_shoulder_tap',   'analyse'),
        'prone-y-t-w-raise':         ('analyzers.mobility.ytw_raise',            'analyse'),
    },
    'strength': {
        'back-squat':       ('analyzers.strength.back_squat',      'analyse'),
        'deadlift':         ('analyzers.strength.deadlift',        'analyse'),
        'bench-press':      ('analyzers.strength.bench_press',     'analyse'),
        'pull-up':          ('analyzers.strength.pull_up',         'analyse'),
        'overhead-press':   ('analyzers.strength.overhead_press',  'analyse'),
    },
}

# Back-compat: legacy clients still send exerciseId. Map to mobility slugs.
LEGACY_ID_TO_SLUG = {
    1:  'knee-to-wall-test',
    2:  'seated-hip-rotation-test',
    3:  'thoracic-extension',
    4:  'quadruped-rotation',
    5:  'shoulder-rotation-90-90',
    6:  'single-leg-glute-bridge',
    7:  'dead-bug',
    8:  'hollow-body-hold',
    9:  'plank-shoulder-tap',
    10: 'prone-y-t-w-raise',
}


class UnknownAnalyzerError(ValueError):
    """Raised when (assessment_type, slug) doesn't match a registered analyzer."""


# Source-file mtimes per module, so edits to shared utils are picked up by a
# long-running server. Reloading only the analyzer module is not enough: its
# `from utils.x import y` re-binds from the cached sys.modules entry, so a
# stale utils module would keep serving old code.
_module_mtimes = {}


# Hot-reload is a development convenience: it lets threshold edits take effect
# without restarting Flask, at the cost of a full stat sweep over every loaded
# module on EVERY request. In production the source never changes, so it is
# pure overhead — and reloading a module mid-request is a needless risk.
# Enable locally with HOT_RELOAD=1 (see start.sh / docker-compose).
HOT_RELOAD = os.environ.get('HOT_RELOAD', '0') == '1'


def _reload_stale_support_modules():
    """Reload any utils.* / analyzers.* module whose source file changed."""
    for name in sorted(sys.modules):
        if not (name == 'utils' or name == 'analyzers'
                or name.startswith('utils.') or name.startswith('analyzers.')):
            continue
        mod = sys.modules.get(name)
        src = getattr(mod, '__file__', None)
        if not src or not os.path.exists(src):
            continue
        try:
            mtime = os.path.getmtime(src)
        except OSError:
            continue
        prev = _module_mtimes.get(name)
        _module_mtimes[name] = mtime
        if prev is not None and mtime > prev:
            try:
                importlib.reload(mod)
                print(f"♻️  Reloaded changed module: {name}")
            except Exception as reload_err:
                print(f"⚠️  reload of {name} failed (using cached): {reload_err}")


def route_analysis(assessment_type, slug, files, *, exercise_id=None, params=None):
    """Route to the correct analyzer.

    Args:
        assessment_type: 'mobility' | 'strength'
        slug:            stable slug for the exercise (e.g. 'knee-to-wall-test')
        files:           dict mapping upload keys to file paths
        exercise_id:     legacy fallback if slug is missing (mobility only)
        params:          optional dict of extra analyzer kwargs (e.g.
                         {'tibia_length_cm': 40.0}). Each analyzer receives
                         only the kwargs whose names match its signature, so
                         analyzers that don't know about a param ignore it
                         silently — no need to add **kwargs everywhere.

    Returns:
        Result dict from the analyzer.

    Raises:
        UnknownAnalyzerError: if (assessment_type, slug) is not registered.
        Exception: analyzer failures propagate to the caller so the HTTP
                   layer can return a real error. They must NOT be converted
                   into a fake "score 50" result here — that corrupts session
                   data by persisting a crash as a legitimate assessment.
    """
    # Legacy fallback path
    if not slug and exercise_id is not None:
        slug = LEGACY_ID_TO_SLUG.get(int(exercise_id))
        assessment_type = assessment_type or 'mobility'

    if assessment_type not in ANALYZERS:
        raise UnknownAnalyzerError(f"Unknown assessmentType: {assessment_type}")
    if slug not in ANALYZERS[assessment_type]:
        raise UnknownAnalyzerError(f"Unknown slug for {assessment_type}: {slug}")

    mod_name, fn_name = ANALYZERS[assessment_type][slug]
    print(f"🔬 Routing {assessment_type}/{slug} → {mod_name}.{fn_name}")

    # Pick up edits to shared utils first, then force-refresh the analyzer
    # module itself so its from-imports re-bind against the fresh utils.
    # Skipped entirely in production (see HOT_RELOAD above).
    mod = importlib.import_module(mod_name)
    if HOT_RELOAD:
        _reload_stale_support_modules()
        try:
            mod = importlib.reload(mod)
        except Exception as reload_err:
            print(f"⚠️  module reload failed (using cached): {reload_err}")
    fn = getattr(mod, fn_name)

    # Pass only the kwargs the analyzer actually accepts
    kwargs = {}
    if params:
        sig = inspect.signature(fn)
        kwargs = {k: v for k, v in params.items() if k in sig.parameters}

    result = fn(files, **kwargs)
    print(f"✅ {assessment_type}/{slug} complete — status: {result.get('status')}")
    return result
