"""Shared muscle-activation inference from kinematic measurements.

Maps joint angles, bar paths, grip widths, and movement patterns to
estimated per-muscle activation percentages.  Based on EMG-to-kinematic
correlations published in the AI_Metrics_Specification-Strength.md spec.

IMPORTANT CAVEAT: These are kinematic proxies, NOT direct EMG readings.
The frontend labels them "Estimated from kinematics · Not EMG".
"""

# ─── Canonical muscle slugs ─────────────────────────────────────────────
# These MUST match the frontend SVG path IDs in muscle-paths.ts.

ALL_MUSCLES = [
    'quadriceps', 'hamstrings', 'glutes', 'adductors', 'calves',
    'erector_spinae', 'core', 'pectorals', 'anterior_deltoid',
    'lateral_deltoid', 'posterior_deltoid', 'triceps', 'biceps',
    'lats', 'rhomboids', 'traps', 'forearms', 'hip_flexors',
]

MUSCLE_NAMES = {
    'quadriceps':       'Quadriceps',
    'hamstrings':       'Hamstrings',
    'glutes':           'Gluteus Maximus',
    'adductors':        'Adductors',
    'calves':           'Calves',
    'erector_spinae':   'Erector Spinae',
    'core':             'Core / Abdominals',
    'pectorals':        'Pectoralis Major',
    'anterior_deltoid': 'Anterior Deltoid',
    'lateral_deltoid':  'Lateral Deltoid',
    'posterior_deltoid': 'Posterior Deltoid',
    'triceps':          'Triceps Brachii',
    'biceps':           'Biceps Brachii',
    'lats':             'Latissimus Dorsi',
    'rhomboids':        'Rhomboids',
    'traps':            'Trapezius',
    'forearms':         'Forearms',
    'hip_flexors':      'Hip Flexors',
}


def _entry(slug, pct, primary=True, side='both'):
    """Build a single muscle activation dict."""
    return {
        'slug':       slug,
        'name':       MUSCLE_NAMES.get(slug, slug),
        'percentage': max(0, min(100, int(round(pct)))),
        'side':       side,
        'isPrimary':  primary,
    }


# ─── Per-exercise inference functions ────────────────────────────────────

def infer_squat(tta_deg=0.0, variant='back-squat', heel_lift_cm=0.0,
                butt_wink_deg=0.0, **_kw):
    """Back Squat / Bodyweight Squat muscle activation.

    Primary driver: TTA (Trunk-Tibia Angle).
      TTA > +10°  → hip-dominant  → glute/hamstring emphasis
      TTA < -10°  → knee-dominant → quad emphasis
      balanced    → roughly equal quad/glute
    """
    if tta_deg > 10:
        # Hip-dominant (low-bar / good-morning pattern)
        dominance = 'Hip-Dominant (Glute/Hamstring Bias)'
        quads, glutes, hams = 45, 85, 75
    elif tta_deg < -10:
        # Knee-dominant (high-bar / front-squat pattern)
        dominance = 'Quad-Dominant (Knee Bias)'
        quads, glutes, hams = 90, 50, 30
    else:
        dominance = 'Balanced (Neutral)'
        quads, glutes, hams = 70, 65, 50

    # Variant tweaks
    if variant in ('front-squat', 'goblet'):
        quads = min(95, quads + 10)
        glutes = max(20, glutes - 10)
        dominance = 'Quad-Dominant (Front-Squat Pattern)'

    # Ankle mobility indicator
    calves = 30 + int(min(20, heel_lift_cm * 8))

    muscles = [
        _entry('quadriceps',     quads),
        _entry('glutes',         glutes),
        _entry('hamstrings',     hams),
        _entry('adductors',      40),
        _entry('erector_spinae', 55 if tta_deg > 5 else 35, primary=False),
        _entry('core',           45, primary=False),
        _entry('calves',         calves, primary=False),
        _entry('hip_flexors',    25, primary=False),
    ]
    return {
        'exercise':  'Back Squat',
        'dominance': dominance,
        'muscles':   muscles,
    }


def infer_deadlift(variant='conventional', hip_knee_ratio=1.0,
                   tta_deg=0.0, **_kw):
    """Deadlift muscle activation.

    Variant-based inference:
      Conventional → glute/ham/erector dominant
      Trap-bar     → more quad involvement
      Sumo         → adductor + balanced
      RDL          → hamstring focus
    """
    if variant == 'sumo':
        dominance = 'Balanced (Sumo — Adductor Emphasis)'
        muscles = [
            _entry('glutes',         65),
            _entry('adductors',      75),
            _entry('quadriceps',     55),
            _entry('hamstrings',     50),
            _entry('erector_spinae', 55),
            _entry('lats',           35, primary=False),
            _entry('traps',          30, primary=False),
            _entry('core',           40, primary=False),
            _entry('forearms',       35, primary=False),
        ]
    elif variant == 'trap-bar':
        dominance = 'Quad-Biased (Trap-Bar)'
        muscles = [
            _entry('quadriceps',     60),
            _entry('glutes',         70),
            _entry('hamstrings',     45),
            _entry('erector_spinae', 45),
            _entry('traps',          40, primary=False),
            _entry('lats',           30, primary=False),
            _entry('core',           40, primary=False),
            _entry('forearms',       35, primary=False),
        ]
    elif variant in ('rdl', 'romanian'):
        dominance = 'Hamstring-Dominant (RDL Pattern)'
        muscles = [
            _entry('hamstrings',     85),
            _entry('glutes',         75),
            _entry('erector_spinae', 65),
            _entry('lats',           25, primary=False),
            _entry('core',           35, primary=False),
            _entry('forearms',       30, primary=False),
            _entry('quadriceps',     20, primary=False),
        ]
    else:
        # Conventional (default)
        dominance = 'Hip-Dominant (Conventional)'
        # Adjust by hip:knee velocity ratio
        glute_pct = 85 if hip_knee_ratio > 1.0 else 70
        ham_pct   = 80 if hip_knee_ratio > 1.0 else 60
        quad_pct  = 35 if hip_knee_ratio > 1.0 else 50
        muscles = [
            _entry('glutes',         glute_pct),
            _entry('hamstrings',     ham_pct),
            _entry('erector_spinae', 75),
            _entry('quadriceps',     quad_pct),
            _entry('lats',           40, primary=False),
            _entry('traps',          35, primary=False),
            _entry('core',           45, primary=False),
            _entry('forearms',       40, primary=False),
        ]

    return {
        'exercise':  'Deadlift',
        'dominance': dominance,
        'muscles':   muscles,
    }


def infer_bench_press(elbow_flare_deg=45.0, variant='flat',
                      grip_ratio=1.5, incline_deg=0.0, **_kw):
    """Bench Press / Push-Up muscle activation.

    Inference from:
      - Elbow flare: wide flare → pec-dominant, tight → tricep-dominant
      - Grip width: wide → pec emphasis, narrow → tricep emphasis
      - Variant: incline → anterior delt, decline → lower pec
    """
    # Base pec/tri split from flare angle
    if elbow_flare_deg >= 60:
        pecs, tris = 90, 40
        dominance = 'Pec-Dominant (Wide Flare)'
    elif elbow_flare_deg <= 35:
        pecs, tris = 50, 85
        dominance = 'Tricep-Dominant (Tight Tuck)'
    else:
        pecs, tris = 75, 60
        dominance = 'Balanced (Pec + Tricep)'

    # Grip width adjustment
    if grip_ratio >= 1.8:
        pecs = min(95, pecs + 10)
        dominance = 'Pec-Dominant (Wide Grip + Flare)'
    elif grip_ratio <= 1.3:
        tris = min(90, tris + 10)
        dominance = 'Tricep-Dominant (Narrow Grip)'

    # Anterior delt for incline
    ant_delt = 35
    if variant == 'incline' or incline_deg > 20:
        ant_delt = 75
        pecs = max(30, pecs - 15)
        dominance = 'Anterior Delt-Dominant (Incline)'

    muscles = [
        _entry('pectorals',       pecs),
        _entry('triceps',         tris),
        _entry('anterior_deltoid', ant_delt),
        _entry('core',            25, primary=False),
        _entry('biceps',          15, primary=False),
        _entry('lats',            20, primary=False),
    ]
    return {
        'exercise':  'Bench Press',
        'dominance': dominance,
        'muscles':   muscles,
    }


def infer_pull_up(grip='pronated', grip_width_ratio=1.5,
                  scapular_initiation=False, hip_swing_cm=0.0, **_kw):
    """Pull-Up / Chin-Up muscle activation.

    Inference from:
      - Grip type: pronated → lat-dominant, supinated → bicep-dominant
      - Grip width: wide → more lat, narrow → more bicep
      - Scapular initiation: strong → lower trap engagement
    """
    if grip in ('supinated', 'chin-up'):
        lats_pct, bi_pct = 70, 80
        dominance = 'Bicep-Dominant (Chin-Up)'
    elif grip == 'neutral':
        lats_pct, bi_pct = 75, 65
        dominance = 'Balanced (Neutral Grip)'
    else:
        # Pronated (default)
        lats_pct, bi_pct = 90, 45
        dominance = 'Lat-Dominant (Pronated)'

    # Wide grip → more lat
    if grip_width_ratio > 1.6:
        lats_pct = min(95, lats_pct + 10)
        bi_pct = max(25, bi_pct - 10)
        dominance = 'Lat-Dominant (Wide Pronated)'

    # Scapular initiation → lower trap / rhomboid
    lower_trap = 55 if scapular_initiation else 30
    rhomboids  = 50 if scapular_initiation else 25

    # Core engagement from swing control
    core_pct = 50 if hip_swing_cm < 5 else 25

    muscles = [
        _entry('lats',              lats_pct),
        _entry('biceps',            bi_pct),
        _entry('rhomboids',         rhomboids),
        _entry('traps',             lower_trap),
        _entry('posterior_deltoid',  40, primary=False),
        _entry('core',              core_pct, primary=False),
        _entry('forearms',          45, primary=False),
    ]
    return {
        'exercise':  'Pull-Up',
        'dominance': dominance,
        'muscles':   muscles,
    }


def infer_overhead_press(trunk_lean_deg=0.0, bar_path_rms_cm=0.0,
                         grip_ratio=1.4, variant='standing', **_kw):
    """Overhead Press muscle activation.

    Inference from:
      - Bar path: vertical = balanced delt, forward drift = anterior delt
      - Trunk lean: excessive lean = anterior delt emphasis
      - Grip width: narrow = tricep emphasis
    """
    ant_delt = 50
    lat_delt = 70
    tris     = 60

    if trunk_lean_deg > 10 or bar_path_rms_cm > 5:
        ant_delt = 85
        lat_delt = 45
        dominance = 'Anterior Delt-Dominant (Forward Lean)'
    elif grip_ratio <= 1.2:
        tris = 85
        dominance = 'Tricep-Dominant (Narrow Grip)'
    else:
        dominance = 'Lateral Delt + Tricep (Balanced)'

    muscles = [
        _entry('lateral_deltoid',  lat_delt),
        _entry('anterior_deltoid', ant_delt),
        _entry('triceps',          tris),
        _entry('traps',            55, primary=False),
        _entry('core',             40, primary=False),
        _entry('erector_spinae',   30, primary=False),
    ]
    return {
        'exercise':  'Overhead Press',
        'dominance': dominance,
        'muscles':   muscles,
    }
