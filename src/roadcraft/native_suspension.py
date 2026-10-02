"""Native suspension bounds and measured wheel-travel checks.

The legacy vehicle solver reports positive body lift. Native suspension limits
are wheel displacement along Y up, so their signs/order must be reversed.
Lada Niva isolated RoadBuilder trial, 2026-09-30; beta remains an estimate.

Measured stop geometry (KGS25 editor bench and the Lada trials, 2026-10-02): a wheel sits
``height + min + travel`` metres below its modelled place, travel 0 being the top stop (fully
compressed) and ``max - min`` the bottom.  A negative ``min`` therefore raises the top stop (the wheel
may be pushed above its modelled place); it does not extend the wheel down.  See
:func:`stop_positions`; library/suspension-and-wheels.md "Stop geometry".  The functions above it are
kept unchanged for pinned recipes.
"""
import math
from .vehicle import (SUSPENSION_BETA, SUSPENSION_BETA_MEASURED, SUSPENSION_BETA_SPREAD, axle_report,
                      calibrate_beta as _legacy_calibrate, static_sag)

def native_axle_report(axle, share, **kwargs):
    low, high = float(axle['min']), float(axle['max'])
    if not math.isfinite(low + high) or low > high:
        raise ValueError('finite ordered native wheel limits required')
    body = dict(axle, min=-high, max=-low)
    result = axle_report(body, share, **kwargs)
    result['nativeWheelLimits'] = [low, high]
    result['bodyLiftLimits'] = [-high, -low]
    return result

def travel_has_reserve(current, maximum, margin=0.025):
    current, maximum, margin = map(float, (current, maximum, margin))
    if not all(map(math.isfinite, (current, maximum, margin))) or maximum <= 0 or margin < 0:
        raise ValueError('finite travel and a positive range required')
    return margin < current < maximum - margin

def stop_positions(axle):
    """Top and bottom stop in metres below the modelled wheel place (+ = lower), measured geometry.

    KGS25 candidate 02 contacts (min 0, height 0.05): unloaded wheels at 0.050 + travel; fix 1 idlers
    (min -0.15, height 0) hung at travel 0.15, exactly the modelled place.  Engine defaults: min 0, max 1.
    """
    height = float(axle.get('height', 0) or 0)
    low = float(axle.get('min', 0) or 0)
    high = axle.get('max')
    high = 1.0 if high is None else float(high)
    if not math.isfinite(height + low + high) or low > high:
        raise ValueError('finite ordered suspension limits required')
    return {'top': height + low, 'bottom': height + high, 'travel': high - low}

def position_from_travel(axle, travel):
    """Wheel position below its modelled place from a measured spring travel (probe GetCurrentSpringTravelDistance)."""
    stops = stop_positions(axle)
    travel = float(travel)
    if not math.isfinite(travel) or not -1e-6 <= travel <= stops['travel'] + 1e-6:
        raise ValueError('travel outside the axle range')
    return stops['top'] + travel

def design_axle(sag, share, *, lift=0.0, bump=0.16, droop=0.20, damping=0.15, beta=SUSPENSION_BETA):
    """A SuspensionAxle for the measured stop geometry: rests ``lift`` higher than modelled with ``sag``
    of static sag, ``bump`` travel up and ``droop`` down from that rest.

    The spring's neutral point is ``height`` below the modelled place, so the rest is height - sag and
    the stops are ``height + min`` / ``height + max``: min = -(sag + bump), max = droop - sag.
    Inferred from the measured geometry (2026-10-02); no vehicle has been driven on it yet.  For wheels
    hung on a light body (track frames) beta does not apply: measure (library/physics-bench.md).
    """
    sag, share, lift, bump, droop = map(float, (sag, share, lift, bump, droop))
    if not all(map(math.isfinite, (sag, share, lift, bump, droop))) or sag <= 0 or share <= 0 or bump < 0 or droop < 0:
        raise ValueError('positive sag and share, non-negative bump and droop required')
    return {'min': round(-(sag + bump), 4), 'max': round(droop - sag, 4), 'height': round(sag + lift, 4),
            'strength': round(share / (sag * beta), 5), 'damping': damping, '__type': 'SuspensionAxle'}

def rest_report(axle, share, beta=SUSPENSION_BETA, spread=SUSPENSION_BETA_SPREAD, measured=SUSPENSION_BETA_MEASURED):
    """Predicted rest (m below the modelled place, + = vehicle higher) against the measured stops, at
    beta, at its +-spread edges and at the measured beta.  Compare :func:`vehicle.axle_report`, which
    puts the stops at min/max themselves."""
    stops = stop_positions(axle)
    cases = [('expected', beta), ('softer', beta * (1 - spread)), ('stiffer', beta * (1 + spread))]
    if measured and not math.isclose(measured, beta, rel_tol=0.05):
        cases.append(('measured', measured))
    rows = {}
    for label, b in cases:
        rest = float(axle.get('height', 0) or 0) - static_sag(float(axle.get('strength', 0) or 0), share, b)
        clamped = min(max(rest, stops['top']), stops['bottom'])
        rows[label] = {'beta': round(b, 2), 'rest': round(rest, 4), 'onBumpStop': rest <= stops['top'],
                       'onDroopStop': rest >= stops['bottom'], 'bumpRoom': round(clamped - stops['top'], 4),
                       'droopRoom': round(stops['bottom'] - clamped, 4)}
    return {'share': share, 'stops': stops, 'cases': rows}

def calibrate_beta(observations):
    """:func:`vehicle.calibrate_beta` with the measured stops: an observed rest must lie strictly between
    ``height + min`` and ``height + max``.  The beta arithmetic (sag = height - rest) is unchanged."""
    shifted = []
    for item in observations:
        stops = stop_positions(item['axle'])
        shifted.append(dict(item, axle=dict(item['axle'], min=stops['top'], max=stops['bottom'])))
    return _legacy_calibrate(shifted)
