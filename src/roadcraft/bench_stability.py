"""Measured drift and settled wheel motion for physics-bench recordings.

These metrics describe the recorded surface and inputs, never campaign acceptance.
Missing spin/contact telemetry is reported as unavailable, not as zero motion.
"""
from __future__ import annotations
import math
import statistics

def phase_stability(samples, plan, hull, *, settle_seconds=2.0, end_margin_seconds=1.0,
                    observed_windows=False, include_pedal_ramp=False):
    """Measure either nominal schedule windows or their full observed input runs.

    The recorder and input writer have separate clocks. Observed mode uses the
    nominal window only to locate a control run, then extends to both observed
    transitions. Multiple separated matches fail closed instead of selecting a
    convenient fragment. Gear is requested metadata, not a filter: shifts and
    delayed gear engagement belong in the measured launch.

    include_pedal_ramp keeps the target-pedal seed but extends to observed brake
    transitions while steering remains straight. It requires alternating brake
    phases and preserves ramp samples before the target pedal is reached. This
    window measures the launch; it is not proof of constant pedal throughout.
    """
    if include_pedal_ramp:
        if not observed_windows:
            raise ValueError("Pedal ramps require observed windows")
        controls_list = [controls for _, controls in plan['steps']]
        if any(abs(c[1]) > 1e-8 for c in controls_list):
            raise ValueError("Brake-bounded ramps require a straight protocol")
        if any(a[2] == b[2] for a, b in zip(controls_list, controls_list[1:])):
            raise ValueError("Brake-bounded ramps require alternating handbrake phases")
    results = {}
    for k, (start, controls) in enumerate(plan['steps']):
        end = plan['steps'][k+1][0] if k+1 < len(plan['steps']) else plan['duration']
        pedal, steer, brake, gear = controls
        def matches(s):
            return (abs(s.get('pedal', math.inf)-pedal) < .02
                    and abs(s.get('steer', math.inf)-steer) < .02
                    and s.get('engine', {}).get('handbrake') == (brake == 'On'))

        def boundary_matches(s):
            if not include_pedal_ramp:
                return matches(s)
            return (abs(s.get('steer', math.inf)-steer) < .02
                    and s.get('engine', {}).get('handbrake') == (brake == 'On'))

        observed_range = None
        if observed_windows:
            seeds = [i for i, s in enumerate(samples)
                     if start <= s['t'] < end and matches(s)]
            if not seeds:
                rows = []
            else:
                first, last = seeds[0], seeds[-1]
                while first > 0 and boundary_matches(samples[first-1]):
                    first -= 1
                while last+1 < len(samples) and boundary_matches(samples[last+1]):
                    last += 1
                if any(not boundary_matches(s) for s in samples[first:last+1]):
                    results[plan['names'][k]] = {
                        'status': 'ambiguous_observed_phase', 'n': len(seeds),
                        'reason': 'Separated matching control runs overlap the nominal phase.'}
                    continue
                observed_range = [samples[first]['t'], samples[last]['t']]
                rows = [s for s in samples[first:last+1]
                        if observed_range[0]+settle_seconds <= s['t'] <= observed_range[1]-end_margin_seconds
                        and hull in s.get('bodies', {})]
        else:
            rows = [s for s in samples
                    if start+settle_seconds <= s['t'] < end-end_margin_seconds
                    and hull in s.get('bodies', {}) and matches(s)]
        if len(rows) < 2:
            results[plan['names'][k]] = {'status': 'insufficient_samples', 'n': len(rows)}
            continue
        bodies = [s['bodies'][hull] for s in rows]
        a, b = bodies[0], bodies[-1]
        x0, _, z0 = a['pos']; fx, _, fz = a['fwd']; length = math.hypot(fx, fz)
        if length < 1e-8:
            results[plan['names'][k]] = {'status': 'heading_unavailable', 'n': len(rows)}
            continue
        fx, fz = fx/length, fz/length
        side = [(h['pos'][0]-x0)*fz - (h['pos'][2]-z0)*fx for h in bodies]
        forward = [(h['pos'][0]-x0)*fx + (h['pos'][2]-z0)*fz for h in bodies]
        angles = [math.degrees(math.atan2(h['fwd'][0], h['fwd'][2])) for h in bodies]
        yaw = [0.0]
        for before, after in zip(angles, angles[1:]):
            yaw.append(yaw[-1] + (after-before+180)%360-180)
        wheels = [w for s in rows for w in s.get('wheels', [])]
        wheel_count = len(rows[0].get('wheels', []))
        complete_wheel_rows = wheel_count > 0 and all(len(s.get('wheels', [])) == wheel_count for s in rows)
        spins = [abs(w['spin']) for w in wheels if 'spin' in w]
        terrain = [w['onTerrain'] for w in wheels if 'onTerrain' in w]
        results[plan['names'][k]] = {
            'status': 'measured', 'n': len(rows),
            'windowSeconds': [rows[0]['t'], rows[-1]['t']],
            'windowBasis': ('observed-handbrake-bounded' if include_pedal_ramp else 'observed-contiguous-inputs') if observed_windows else 'nominal-schedule',
            'observedControlWindowSeconds': observed_range,
            'controls': {'pedal': pedal, 'steer': steer, 'handbrake': brake, 'gear': gear},
            'distanceM': math.hypot(b['pos'][0]-x0, b['pos'][2]-z0),
            'forwardM': forward[-1], 'lateralMaxM': max(map(abs, side)),
            'yawChangeDeg': yaw[-1], 'yawRangeDeg': max(yaw)-min(yaw),
            'heightRangeMm': 1000*(max(h['pos'][1] for h in bodies)-min(h['pos'][1] for h in bodies)),
            'wheelSpinMaxRadS': max(spins) if complete_wheel_rows and len(spins)==len(wheels) else None,
            'onTerrainFraction': statistics.mean(terrain) if complete_wheel_rows and len(terrain)==len(wheels) else None,
        }
    return results
