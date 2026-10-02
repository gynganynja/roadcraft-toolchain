"""Opt-in checks for compiled native cockpit targets and paired wiper clips.

These validate references, not geometry fitting, motion or rain behavior.
"""
def cockpit_animation_report(properties, node_names, clip_names):
    nodes=set(node_names);clips=set(clip_names);issues=[]
    dash=properties.get('prop_cockpit_dashboard')
    if not dash:issues.append('Missing compiled cockpit dashboard')
    targets=[]
    for element in (dash or {}).get('elements',{}).values():
        for key in ('nameBone','nameBoneSecond'):
            name=element.get(key)
            if name:
                targets.append(name)
                if name not in nodes:issues.append('Missing cockpit target: '+name)
    if len(targets)!=len(set(targets)):issues.append('Multiple cockpit elements drive the same target')
    wipers=properties.get('prop_wipers_controller')
    if not wipers:issues.append('Missing compiled wiper controller')
    pair=[(wipers or {}).get(k) for k in ('forwardAnimation','backwardAnimation')]
    if not all(pair) or pair[0]==pair[1]:issues.append('Wipers need distinct forward and return animations')
    for name in pair:
        if name and name not in clips:issues.append('Missing exported wiper clip: '+name)
    return {'passed':not issues,'issues':issues,'cockpitTargets':targets,'wiperClips':pair,
            'scope':'Compiled references only; visual fit and native motion require separate evidence.'}
