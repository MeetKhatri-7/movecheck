"""Scoring and result formatting utilities."""


def classify(value, good_thresh, needs_thresh, higher_is_better=True):
    """Classify a metric value into GOOD / NEEDS IMPROVEMENT / RESTRICTED.
    
    Args:
        value: the measured value
        good_thresh: threshold for GOOD
        needs_thresh: threshold for NEEDS IMPROVEMENT (boundary with RESTRICTED)
        higher_is_better: True if higher values are better (e.g., ROM angles)
                         False if lower values are better (e.g., heel lift)
    """
    if value is None:
        return 'RESTRICTED'
    if higher_is_better:
        if value >= good_thresh:
            return 'GOOD'
        elif value >= needs_thresh:
            return 'NEEDS IMPROVEMENT'
        else:
            return 'RESTRICTED'
    else:
        if value <= good_thresh:
            return 'GOOD'
        elif value <= needs_thresh:
            return 'NEEDS IMPROVEMENT'
        else:
            return 'RESTRICTED'


def classify_range(value, good_min, good_max, needs_min, needs_max):
    """Classify a range-target metric (e.g., ER 80-95°).

    For ROM / rotation metrics, exceeding good_max is still GOOD —
    more range of motion is always better mobility.
    GOOD:              value >= good_min  (includes everything above the target)
    NEEDS IMPROVEMENT: needs_min <= value < good_min
    RESTRICTED:        value < needs_min
    """
    if value is None:
        return 'RESTRICTED'
    if value >= good_min:
        return 'GOOD'
    if value >= needs_min:
        return 'NEEDS IMPROVEMENT'
    return 'RESTRICTED'


def classify_band(value, good_min, good_max, needs_min, needs_max):
    """Classify a FORM/position metric where the target is a closed band.

    Unlike classify_range (ROM semantics: more is always better), exceeding
    good_max here is a formation error — e.g. a 'T' raise swept 40° past
    perpendicular is not a better T.
    GOOD:              good_min <= value <= good_max
    NEEDS IMPROVEMENT: within [needs_min, needs_max] but outside the good band
    RESTRICTED:        outside [needs_min, needs_max]
    """
    if value is None:
        return 'RESTRICTED'
    if good_min <= value <= good_max:
        return 'GOOD'
    if needs_min <= value <= needs_max:
        return 'NEEDS IMPROVEMENT'
    return 'RESTRICTED'


def metric_status(classification):
    """Convert classification to simple good/bad for frontend."""
    return 'good' if classification == 'GOOD' else 'bad'


_TIER_SCORE = {
    'GOOD': 100,
    'NEEDS IMPROVEMENT': 60,
    'RESTRICTED': 25,
}


def compute_overall_score(metrics):
    """Compute 0-100 composite score from individual metric classifications.

    GOOD = 100 points, NEEDS IMPROVEMENT = 60, RESTRICTED = 25.
    Metrics built via build_metric() carry the tri-state `classification`;
    hand-rolled metric dicts that only have the binary 'good'/'bad' `status`
    fall back to the legacy two-state mapping (100 / 35).

    If a metric has a `confidence` key in [0,1], its contribution is weighted
    by that confidence so low-confidence metrics drag less. A floor of 0.3 is
    applied to avoid completely zero-weighting noisy metrics — the user still
    sees a result, the score just trends toward neutral.
    """
    if not metrics:
        return 50
    weights = []
    scores = []
    for m in metrics:
        base = _TIER_SCORE.get(m.get('classification'))
        if base is None:
            base = 100 if m.get('status') == 'good' else 35
        conf = m.get('confidence')
        w = 1.0 if conf is None else max(0.3, min(1.0, float(conf)))
        scores.append(base * w)
        weights.append(w)
    if not weights:
        return 50
    return round(sum(scores) / sum(weights))


def overall_status(score):
    """Convert composite score to overall status."""
    if score >= 80:
        return 'GOOD'
    elif score >= 55:
        return 'NEEDS IMPROVEMENT'
    else:
        return 'RESTRICTED'


def build_metric(name, value_str, raw, target, max_val, classification,
                 confidence=None, n_reps=None, fault_timing=None):
    """Build a standardized metric dict for the frontend.

    New optional fields (Phase 1):
        confidence:   float in [0,1] — used by compute_overall_score and the
                      UI confidence pill. None means 'not reported'.
        n_reps:       number of reps that contributed to this aggregated metric.
        fault_timing: dict like {'rep': 3, 'start_phase_pct': 65,
                                  'message': 'valgus appeared at 65% of descent'}
                      surfaced as a chip in the result UI.
    """
    out = {
        'name': name,
        'value': value_str,
        'raw': round(raw, 1) if raw is not None else 0,
        'target': target,
        'max': max_val,
        'status': metric_status(classification),
        # Full tri-state kept alongside the binary status so scoring can
        # distinguish "slightly below target" from "severely restricted".
        'classification': classification,
    }
    if confidence is not None:
        out['confidence'] = round(max(0.0, min(1.0, float(confidence))), 2)
        # Tier label for UI: high >= 0.7, medium >= 0.4, low otherwise
        if out['confidence'] >= 0.7:
            out['confidence_tier'] = 'high'
        elif out['confidence'] >= 0.4:
            out['confidence_tier'] = 'medium'
        else:
            out['confidence_tier'] = 'low'
    if n_reps is not None:
        out['n_reps'] = int(n_reps)
    if fault_timing is not None:
        out['fault_timing'] = fault_timing
    return out


def build_bilateral(name, left, right, unit, max_val):
    """Build a bilateral comparison dict."""
    asym = round(abs(left - right), 1)
    return {
        'name': name,
        'left': round(left, 1),
        'right': round(right, 1),
        'unit': unit,
        'max': max_val,
        'asymmetry': asym,
    }


def build_result(status, score, summary, stats, metrics, bilateral, coaching):
    """Build the complete result dict matching frontend expectations."""
    return {
        'status': status,
        'score': score,
        'summary': summary,
        'stats': stats,
        'metrics': metrics,
        'bilateral': bilateral,
        'coaching': coaching,
    }


def aggregate_per_rep(rep_metrics, keys=None):
    """Aggregate per-rep metric values into mean / std / decay slope.

    Args:
        rep_metrics: list of dicts; each dict is the per-rep metric bag.
        keys:        optional iterable of metric names to aggregate. If None,
                     the union of numeric keys across all reps is used.
    Returns:
        dict[name] -> {'mean', 'std', 'decay_slope', 'n', 'values'}
        where `decay_slope` is the linear-regression slope vs rep index — a
        positive slope indicates the metric grows over the set (e.g. valgus
        worsens), useful for fatigue/form-decay reporting.
    """
    if not rep_metrics:
        return {}
    # Discover keys
    if keys is None:
        keys = set()
        for r in rep_metrics:
            for k, v in r.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    keys.add(k)
    out = {}
    for k in keys:
        vals = []
        idxs = []
        for i, r in enumerate(rep_metrics):
            v = r.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals.append(float(v))
                idxs.append(i)
        if not vals:
            continue
        n = len(vals)
        mean = sum(vals) / n
        var = sum((v - mean) ** 2 for v in vals) / n if n > 1 else 0.0
        std = var ** 0.5
        # Linear regression slope: cov(x,y) / var(x)
        slope = 0.0
        if n >= 2:
            x_mean = sum(idxs) / n
            num = sum((idxs[i] - x_mean) * (vals[i] - mean) for i in range(n))
            denom = sum((idxs[i] - x_mean) ** 2 for i in range(n))
            slope = num / denom if denom > 1e-9 else 0.0
        out[k] = {
            'mean': round(mean, 3),
            'std': round(std, 3),
            'decay_slope': round(slope, 4),
            'n': n,
            'values': [round(v, 3) for v in vals],
        }
    return out


def generate_coaching_notes(metrics, bilateral, exercise_name):
    """Auto-generate coaching notes from metric results."""
    notes = []
    
    # Flag bad metrics
    bad = [m for m in metrics if m.get('status') == 'bad']
    if bad:
        names = ', '.join(m['name'] for m in bad[:3])
        notes.append(f"Attention needed on: {names}. These metrics fell below target thresholds.")

    # Flag bilateral asymmetry
    for b in bilateral:
        if b['asymmetry'] > 5:
            notes.append(
                f"{b['name']} asymmetry of {b['asymmetry']}{b['unit']} detected between left and right. "
                f"Prioritise the restricted side in your training."
            )

    if not notes:
        notes.append(f"{exercise_name} performance looks good. Continue maintaining your current mobility routine.")

    return notes
