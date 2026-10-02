"""Opt-in checks for native truck utility components AND their playable actions.

Input is the resolved gameplay CLS properties mapping, not a shop preview.
This does not establish runtime, save migration, or campaign acceptance.
"""
from __future__ import annotations

def utility_action_report(properties: dict, utilities: tuple[str, ...]) -> dict:
    allowed = {'winch', 'objective', 'terrain', 'explorer'}
    unknown = set(utilities) - allowed
    if unknown:
        raise ValueError(f'Unknown utility names: {sorted(unknown)}')
    mapper = properties.get('prop_truck_view_actions_mapper', {})
    actions = {value.get('namedActionType') for value in mapper.values() if isinstance(value, dict)}
    checks = []
    def check(name, passed): checks.append({'check': name, 'passed': bool(passed)})
    contracts = {
        'winch': ('prop_truck_view_winch_controller', {'ACTIVATE_PULL_WINCH', 'DEACTIVATE_WINCH'}),
        'objective': ('prop_objective_scanner', {'ACTIVATE_OBJECTIVE_SCANNER'}),
        'terrain': ('prop_truck_extrusion_scanner', {'SWITCH_EXTRUSION_SCANNER'}),
        'explorer': ('prop_truck_view_explorer_controller', {'TOGGLE_EXPLORER'}),
    }
    for utility in utilities:
        component, needed = contracts[utility]
        check(utility + ' native component', component in properties)
        check(utility + ' playable actions', needed <= actions)
        p = properties.get(component, {})
        if utility == 'winch':
            check('winch targeting axis', any(row.get('actionData', {}).get('actionType') == 'TRY_ATTACH_WINCH'
                  for row in mapper.get('axisControls', [])))
            check('winch source points', bool(p.get('winchSourcePoints')))
        elif utility == 'objective':
            check('objective nonzero scan radius', p.get('objectiveScanner', {}).get('radius', 0) > 0)
        elif utility == 'terrain':
            check('terrain effect descriptor', bool(p.get('scannerSfxActorDesc', {}).get('type', {}).get('__type')))
    if utilities:
        config = mapper.get('truckInputConfiguration', {})
        check('utility action sections enabled', all(config.get(k, False) for k in
              ['isMainActionsMapped', 'isSecondaryActionsMapped', 'isFirstActionModeNeeded', 'isSecondActionModeNeeded']))
    return {'passed': all(c['passed'] for c in checks), 'checks': checks,
            'scope': 'Compiled utility wiring only; native/campaign behavior needs separate evidence.'}
