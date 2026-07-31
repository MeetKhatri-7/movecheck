"""Automatic rep detection using angle velocity peaks."""
import math


def _fill_none(signal):
    """Replace None entries with the nearest previous valid value.

    Leading Nones take the first valid value. Returns [] if the signal has
    no valid values at all. Detection functions in this module compare and
    negate raw samples, so a stray None must never reach them — callers
    historically pre-sanitised, but the utility contract is now safe too.
    """
    first = next((v for v in signal if v is not None), None)
    if first is None:
        return []
    out = []
    last = first
    for v in signal:
        if v is None:
            out.append(last)
        else:
            out.append(v)
            last = v
    return out


def detect_reps(signal, expected_reps, fps, min_hold_sec=0.3):
    """Detect repetitions in a time-series signal using peak detection.

    Handles both sharp peaks and plateau-type peaks (e.g. held positions).

    Args:
        signal: list of float values (e.g., angle at each frame)
        expected_reps: int, number of reps expected
        fps: frames per second
        min_hold_sec: minimum time between peaks in seconds

    Returns:
        list of dicts: {peak_frame, start_frame, end_frame, peak_value}
    """
    signal = _fill_none(signal)
    if not signal or len(signal) < 3:
        return []

    min_distance = max(int(fps * min_hold_sec * 2), 5)

    # Smooth with a wider window to handle both sharp peaks and plateaus
    window = max(int(fps * 0.2), 5)
    smoothed = moving_average(signal, window)

    # Find peaks including plateaus:
    # A plateau peak is a region where the signal stays at its local max.
    # We detect rising-edge start and falling-edge end, then use the midpoint.
    peaks = []
    i = 1
    while i < len(smoothed) - 1:
        if smoothed[i] > smoothed[i - 1]:
            # Rising edge — find where it flattens or falls
            plateau_start = i
            j = i + 1
            while j < len(smoothed) and smoothed[j] >= smoothed[j - 1] - 1e-9:
                j += 1
            plateau_end = j - 1
            peak_val = smoothed[plateau_end]
            # Only count if it then falls (not end-of-signal noise)
            if plateau_end < len(smoothed) - 1 and smoothed[plateau_end] > smoothed[plateau_end + 1] - 1e-9:
                peak_idx = (plateau_start + plateau_end) // 2
                peaks.append((peak_idx, peak_val))
            i = j
        else:
            i += 1

    # Filter peaks by minimum distance, keeping higher-value peak when close
    filtered = []
    for idx, val in peaks:
        if not filtered or (idx - filtered[-1][0]) >= min_distance:
            filtered.append((idx, val))
        elif val > filtered[-1][1]:
            filtered[-1] = (idx, val)

    # If too many peaks, keep the top N by value. (The gate matches the
    # trim size — previously counts between N and 2N slipped through
    # untrimmed while counts above 2N were hard-cut to N.)
    if expected_reps and len(filtered) > expected_reps:
        filtered.sort(key=lambda x: x[1], reverse=True)
        filtered = filtered[:expected_reps]
        filtered.sort(key=lambda x: x[0])

    # Build rep segments with start/end frames
    reps = []
    for i, (peak_frame, peak_val) in enumerate(filtered):
        if i == 0:
            start = 0
        else:
            start = (filtered[i - 1][0] + peak_frame) // 2

        if i == len(filtered) - 1:
            end = len(signal) - 1
        else:
            end = (peak_frame + filtered[i + 1][0]) // 2

        reps.append({
            'peak_frame': peak_frame,
            'start_frame': start,
            'end_frame': end,
            'peak_value': peak_val,
        })

    return reps


def detect_reps_minima(signal, expected_reps, fps, min_hold_sec=0.3):
    """Detect reps by finding local minima (for signals where lower = peak movement)."""
    signal = _fill_none(signal)
    inverted = [-v for v in signal]
    reps = detect_reps(inverted, expected_reps, fps, min_hold_sec)
    for r in reps:
        r['peak_value'] = -r['peak_value']
    return reps


def detect_holds(signal, threshold, fps, min_hold_sec=3.0):
    """Detect sustained hold periods where signal stays above a threshold.
    
    Args:
        signal: list of float values
        threshold: minimum value to consider as "in position"
        fps: frames per second
        min_hold_sec: minimum hold duration to count
    
    Returns:
        list of dicts: {start_frame, end_frame, duration_sec, avg_value}
    """
    min_frames = int(fps * min_hold_sec)
    holds = []
    start = None

    for i, val in enumerate(signal):
        # A None sample (landmark dropout) counts as "not in position" so a
        # sparse signal can't crash the >= comparison below.
        if val is not None and val >= threshold:
            if start is None:
                start = i
        else:
            if start is not None and (i - start) >= min_frames:
                segment = signal[start:i]
                holds.append({
                    'start_frame': start,
                    'end_frame': i - 1,
                    'duration_sec': (i - start) / fps,
                    'avg_value': sum(segment) / len(segment),
                })
            start = None

    # Handle hold extending to end of video
    if start is not None and (len(signal) - start) >= min_frames:
        segment = signal[start:]
        holds.append({
            'start_frame': start,
            'end_frame': len(signal) - 1,
            'duration_sec': (len(signal) - start) / fps,
            'avg_value': sum(segment) / len(segment),
        })

    return holds


def detect_taps(wrist_y_signal, fps, expected_taps=20):
    """Detect shoulder taps by finding Y-displacement spikes in wrist position.
    
    A tap is when the wrist lifts significantly from its baseline position.
    """
    wrist_y_signal = _fill_none(wrist_y_signal)
    if not wrist_y_signal or len(wrist_y_signal) < 10:
        return []

    # Baseline = resting (on-floor) wrist position. In image coords Y grows
    # downward, so resting = LARGE Y. Use the 75th percentile — most of the
    # video is spent with the wrist planted, taps are brief low-Y excursions.
    # (Previously this took the 25th percentile, i.e. a near-LIFTED position,
    # which made the lift threshold nearly unreachable and undercounted taps.)
    sorted_y = sorted(wrist_y_signal)
    baseline = sorted_y[(len(sorted_y) * 3) // 4]

    # Threshold for detecting lift
    lift_threshold = abs(baseline) * 0.05  # 5% of baseline height

    # Detect lift events
    in_tap = False
    taps = []
    tap_start = None
    tap_peak_frame = None
    tap_peak_val = float('inf')

    for i, y in enumerate(wrist_y_signal):
        lift = baseline - y  # positive = hand lifted (Y decreases when lifting)
        if lift > lift_threshold:
            if not in_tap:
                in_tap = True
                tap_start = i
                tap_peak_frame = i
                tap_peak_val = y
            elif y < tap_peak_val:
                tap_peak_frame = i
                tap_peak_val = y
        else:
            if in_tap:
                taps.append({
                    'start_frame': tap_start,
                    'peak_frame': tap_peak_frame,
                    'end_frame': i,
                    'duration_sec': (i - tap_start) / fps,
                })
                in_tap = False

    return taps


def moving_average(signal, window):
    """Simple moving average smoothing, ignoring None values.

    Never returns None entries: short signals are returned None-filled, and
    windows with no valid samples inherit the previous smoothed value —
    callers compare these samples directly.
    """
    if window <= 1 or len(signal) <= window:
        return _fill_none(signal) or list(signal)
    result = []
    for i in range(len(signal)):
        start = max(0, i - window // 2)
        end = min(len(signal), i + window // 2 + 1)
        vals = [v for v in signal[start:end] if v is not None]
        if not vals:
            result.append(None)
        else:
            result.append(sum(vals) / len(vals))
    # An all-None window leaves a None hole — fill from neighbours so
    # downstream comparisons never see None.
    return _fill_none(result) or result


# ─────────────────────────────────────────────────────────────
# Phase 2.2 — multi-signal fusion + velocity-based phase segmentation
# ─────────────────────────────────────────────────────────────

def detect_reps_multi(signals, expected_reps, fps, min_hold_sec=0.3,
                      vote_window_sec=0.4):
    """Fuse rep peaks across multiple signals via majority vote.

    Args:
        signals: dict[name -> list[float]]. Each signal is detected
                 independently (use detect_reps_minima by passing pre-inverted
                 series). All series must have the same length.
        expected_reps: target rep count.
        fps: framerate.
        min_hold_sec: passed to detect_reps for each signal.
        vote_window_sec: peaks within this window across signals are merged
                         into the same rep.

    Returns list of Rep dicts. Each has the same fields as detect_reps plus:
        signal_agreement:  float in [0,1] — fraction of signals that voted
                           for this rep within the merge window.
        sources:           list of signal names that contributed.
    """
    if not signals:
        return []
    # Detect peaks in each signal
    per_signal_reps = {}
    for name, sig in signals.items():
        per_signal_reps[name] = detect_reps(sig, expected_reps, fps, min_hold_sec)

    n_signals = len(signals)
    merge_window = max(1, int(vote_window_sec * fps))

    # Collect all (peak_frame, name, peak_value) tuples
    votes = []
    for name, reps in per_signal_reps.items():
        for r in reps:
            votes.append((r['peak_frame'], name, r['peak_value'], r['start_frame'], r['end_frame']))
    if not votes:
        return []
    votes.sort(key=lambda v: v[0])

    # Cluster votes within merge_window
    clusters = []
    cur = [votes[0]]
    for v in votes[1:]:
        if v[0] - cur[-1][0] <= merge_window:
            cur.append(v)
        else:
            clusters.append(cur)
            cur = [v]
    clusters.append(cur)

    # Build reps from clusters
    reps = []
    for cluster in clusters:
        names = {c[1] for c in cluster}
        agreement = len(names) / n_signals
        # use mean peak frame, max(end), min(start) across votes
        pk = int(sum(c[0] for c in cluster) / len(cluster))
        start = min(c[3] for c in cluster)
        end = max(c[4] for c in cluster)
        # peak_value: average across signals (signals are heterogeneous so
        # treat as relative). Carry separate scalar from the FIRST signal as
        # peak_value for back-compat.
        first_name = next(iter(signals.keys()))
        first_val = next((c[2] for c in cluster if c[1] == first_name), cluster[0][2])
        reps.append({
            'peak_frame': pk,
            'start_frame': start,
            'end_frame': end,
            'peak_value': first_val,
            'signal_agreement': round(agreement, 2),
            'sources': sorted(names),
        })

    # If too many reps detected, prefer high-agreement + high peak_value
    if len(reps) > expected_reps and expected_reps > 0:
        reps.sort(key=lambda r: (r['signal_agreement'], abs(r['peak_value'])), reverse=True)
        reps = reps[:expected_reps]
        reps.sort(key=lambda r: r['peak_frame'])
    return reps


def detect_reps_velocity(bar_y, fps, expected_reps, px_per_cm=None,
                         min_hold_sec=0.3, sticking_grace_sec=0.05):
    """Velocity-based rep segmentation from bar Y position.

    Segments each rep into descent / bottom / ascent / top using zero
    crossings of bar velocity. Also reports the **sticking_frame** — the first
    concentric velocity minimum above the bottom (the rep's hardest point).

    Args:
        bar_y: list[float|None] of bar Y in IMAGE coords (+y is down).
               Will be smoothed internally with Kalman.
        fps: framerate.
        expected_reps: target rep count (caps detection).
        px_per_cm: optional, for velocity in m/s reporting (units only).
        min_hold_sec: min time between rep tops.
        sticking_grace_sec: minimum time from bottom before sticking is valid.

    Returns list of Rep dicts:
        {peak_frame (top), bottom_frame, descent_start, ascent_start, end_frame,
         sticking_frame, peak_velocity_mps, mean_concentric_mps,
         peak_value (bar Y at top)}
    """
    from .signal_filters import kalman_1d  # local import to avoid hard dep at module load
    n = len(bar_y)
    if n < 5:
        return []

    smoothed = kalman_1d(bar_y, fps=fps, q=1e-3, r=1e-2)

    # Velocity in image coords (+y is down). Flip sign so +ve = bar going UP.
    dt = 1.0 / max(fps, 1e-6)
    vel = [0.0] * n
    for i in range(1, n - 1):
        vel[i] = -(smoothed[i + 1] - smoothed[i - 1]) / (2 * dt)
    vel[0] = vel[1]
    vel[-1] = vel[-2]

    # Convert to m/s if calibrated
    if px_per_cm and px_per_cm > 0:
        scale = 1.0 / (px_per_cm * 100.0)
        vel_mps = [v * scale for v in vel]
    else:
        vel_mps = list(vel)

    # Zero crossings give phase boundaries
    sign = [1 if v > 0 else (-1 if v < 0 else 0) for v in vel]
    crossings = []  # list of (frame, 'up'|'down')
    for i in range(1, n):
        if sign[i] == 0:
            continue
        if sign[i - 1] <= 0 and sign[i] > 0:
            crossings.append((i, 'up'))
        elif sign[i - 1] >= 0 and sign[i] < 0:
            crossings.append((i, 'down'))

    # Synthesize boundaries for any leading partial rep:
    #   - if the signal starts in descent (first crossing is 'up'), insert a
    #     synthetic 'down' at frame 0.
    #   - if the signal ends in ascent (last crossing is 'up'), the closing
    #     'down' is implicit at n-1 (handled below).
    if crossings and crossings[0][1] == 'up':
        crossings.insert(0, (0, 'down'))

    # A rep = down-start ... up-start ... down-start (or end-of-signal)
    reps = []
    min_gap = max(int(fps * min_hold_sec), 3)
    i = 0
    while i < len(crossings):
        # find a 'down' (descent start)
        while i < len(crossings) and crossings[i][1] != 'down':
            i += 1
        if i >= len(crossings):
            break
        descent_start = crossings[i][0]
        # find the next 'up' (ascent start = bottom)
        j = i + 1
        while j < len(crossings) and crossings[j][1] != 'up':
            j += 1
        if j >= len(crossings):
            break  # no ascent — incomplete rep, drop it
        ascent_start = crossings[j][0]
        # find the next 'down' (top of this rep)
        k = j + 1
        while k < len(crossings) and crossings[k][1] != 'down':
            k += 1
        top_frame = crossings[k][0] if k < len(crossings) else n - 1
        next_descent = top_frame

        # bottom is the lowest position between descent_start and ascent_start
        seg = smoothed[descent_start:ascent_start + 1]
        if seg:
            bottom_offset = max(range(len(seg)), key=lambda idx: seg[idx])  # max y = lowest
            bottom_frame = descent_start + bottom_offset
        else:
            bottom_frame = (descent_start + ascent_start) // 2

        # Find sticking point: first local-min velocity during ascent after a grace period
        grace = max(1, int(sticking_grace_sec * fps))
        stick_search_start = bottom_frame + grace
        sticking_frame = None
        if stick_search_start < top_frame - 1:
            for s in range(stick_search_start + 1, top_frame):
                if vel_mps[s] > 0 and vel_mps[s] < vel_mps[s - 1] and vel_mps[s] < vel_mps[s + 1]:
                    sticking_frame = s
                    break

        # Velocity stats
        ascent_vels = [v for v in vel_mps[bottom_frame:top_frame + 1] if v > 0]
        peak_v = max(ascent_vels) if ascent_vels else 0.0
        mean_v = sum(ascent_vels) / len(ascent_vels) if ascent_vels else 0.0

        rep = {
            'peak_frame':           top_frame,
            'bottom_frame':         bottom_frame,
            'descent_start':        descent_start,
            'ascent_start':         ascent_start,
            'start_frame':          descent_start,
            'end_frame':            next_descent,
            'sticking_frame':       sticking_frame,
            'peak_velocity_mps':    round(peak_v, 3),
            'mean_concentric_mps':  round(mean_v, 3),
            'peak_value':           smoothed[top_frame],
        }
        # advance to the next 'down' (k), regardless of accept/reject
        next_i = (k) if k < len(crossings) else len(crossings)
        # skip if too close to last accepted top
        if reps and (rep['peak_frame'] - reps[-1]['peak_frame']) < min_gap:
            i = next_i + 1 if next_i <= i else next_i
            if i <= len(crossings) and next_i == i:
                i += 1
            continue
        reps.append(rep)
        i = next_i if next_i > i else i + 1

    # Cap to expected count, keeping fastest reps
    if expected_reps > 0 and len(reps) > expected_reps:
        reps.sort(key=lambda r: r['peak_velocity_mps'], reverse=True)
        reps = reps[:expected_reps]
        reps.sort(key=lambda r: r['peak_frame'])

    return reps
